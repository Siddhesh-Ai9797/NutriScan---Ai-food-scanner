"""
Guardrails around the scan pipeline.

Input guardrail: a zero-shot CLIP check that the photo shows food or drink
before any paid GPT-4o call. CLIP needs no training: it compares the photo
with short text prompts like "a photo of food" and "a selfie".

Output guardrail: GPT-4o's nutrition JSON is checked before a user sees it.
Numbers must be real, non-negative and physically possible, and totals are
rebuilt from the items so they always add up.

If CLIP cannot load, the input check steps aside (fails open) and GPT-4o's
own "is_food" answer is the backstop.
"""
import io
import logging
import os
import re
import threading

logger = logging.getLogger("nutriscan.guardrails")

# ── Input guardrail: is this a food photo? ────────────────────────────────
CLIP_MODEL_NAME  = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")
FOOD_GATE_ON     = os.getenv("FOOD_GATE", "on").lower() != "off"
# Share of CLIP's belief that must go to the food prompts. Kept low on purpose:
# blocking a real meal is worse than paying for one extra GPT-4o call.
FOOD_THRESHOLD   = float(os.getenv("FOOD_GATE_THRESHOLD", "0.30"))

FOOD_PROMPTS = [
    "a photo of food",
    "a photo of a meal on a plate",
    "a photo of a dish of cooked food",
    "a photo of a drink in a glass or cup",
    "a photo of fruit or vegetables",
    "a photo of a snack or dessert",
    "a photo of packaged food",
]
NOT_FOOD_PROMPTS = [
    "a selfie of a person",
    "a photo of people",
    "a screenshot of a phone or computer screen",
    "a photo of a document or text",
    "a photo of an animal",
    "a photo of a room or furniture",
    "a photo of a car or street",
    "a photo of a landscape",
    "a photo of an everyday object",
]

NOT_FOOD_MESSAGE = (
    "This photo doesn't look like food. Please take a clear photo of your meal or drink."
)


class FoodGate:
    """Zero-shot CLIP food check. Loads in the background so startup stays fast."""

    def __init__(self):
        self.ready = False
        self.failed = False
        self._model = None
        self._processor = None
        self._text_features = None
        self._lock = threading.Lock()

    def start_loading(self):
        if not FOOD_GATE_ON or self.ready or self.failed:
            return
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        with self._lock:
            if self.ready or self.failed:
                return
            try:
                import torch
                from transformers import CLIPModel, CLIPProcessor

                model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
                model.eval()
                processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
                with torch.no_grad():
                    text = processor(text=FOOD_PROMPTS + NOT_FOOD_PROMPTS, return_tensors="pt", padding=True)
                    features = model.get_text_features(**text)
                    features = features / features.norm(dim=-1, keepdim=True)
                self._model, self._processor, self._text_features = model, processor, features
                self.ready = True
                logger.info("CLIP food gate ready (%s)", CLIP_MODEL_NAME)
            except Exception as e:  # noqa: BLE001
                self.failed = True
                logger.warning("CLIP food gate unavailable, failing open: %s", e)

    def food_probability(self, image_bytes: bytes) -> float | None:
        """Share of probability on food prompts, or None when the gate is not available."""
        if not self.ready:
            return None
        import torch
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        with torch.no_grad():
            pixels = self._processor(images=image, return_tensors="pt")
            features = self._model.get_image_features(**pixels)
            features = features / features.norm(dim=-1, keepdim=True)
            logits = self._model.logit_scale.exp() * features @ self._text_features.T
            probs = logits.softmax(dim=-1)[0]
        return float(probs[: len(FOOD_PROMPTS)].sum())

    def check(self, image_bytes: bytes) -> tuple[bool, float | None]:
        """Returns (looks_like_food, food_probability). Fails open on any problem."""
        try:
            prob = self.food_probability(image_bytes)
        except Exception as e:  # noqa: BLE001
            logger.warning("CLIP check failed, allowing photo: %s", e)
            return True, None
        if prob is None:
            return True, None
        return prob >= FOOD_THRESHOLD, round(prob, 4)


food_gate = FoodGate()


# ── Output guardrail: are the nutrition numbers sensible? ─────────────────
MAX_ITEMS         = 15
MAX_ITEM_GRAMS    = 2500
MAX_PLATE_KCAL    = 6000
MAX_KCAL_PER_GRAM = 9.5     # pure fat is about 9 kcal per gram
NUMBER_FIELDS     = ("weight_grams", "calories", "protein", "carbs", "fat")


class NotFoodPhoto(ValueError):
    """The model says there is no food or drink in the photo."""


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _clean_name(value) -> str:
    name = re.sub(r"<[^>]*>", " ", str(value or ""))
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name)
    return re.sub(r"\s+", " ", name).strip()[:80]


def check_plate(data: dict | None) -> tuple[dict | None, list[str]]:
    """
    Validates GPT-4o's plate JSON.

    Returns (clean_result, flags). clean_result is None when nothing usable is
    left. flags name every rule that fired, for monitoring.
    Raises NotFoodPhoto when the model says the photo has no food.
    """
    flags: list[str] = []
    if not isinstance(data, dict):
        return None, ["bad_json"]
    if data.get("is_food") is False:
        raise NotFoodPhoto()

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return None, ["bad_json"]
    if len(raw_items) > MAX_ITEMS:
        flags.append("too_many_items")
        raw_items = raw_items[:MAX_ITEMS]

    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            flags.append("bad_item")
            continue
        name = _clean_name(raw.get("food") or raw.get("name"))
        if not name:
            flags.append("bad_item")
            continue
        values = {f: _number(raw.get(f)) for f in NUMBER_FIELDS}
        if values["calories"] is None:
            flags.append("missing_calories")
            continue
        for f, v in values.items():
            if v is not None and v < 0:
                flags.append("negative_value")
                values[f] = 0.0
        for f in ("protein", "carbs", "fat"):
            if values[f] is None:
                values[f] = 0.0

        weight = values["weight_grams"]
        if weight is not None and weight > MAX_ITEM_GRAMS:
            flags.append("item_too_heavy")
            continue
        if weight and values["calories"] / weight > MAX_KCAL_PER_GRAM:
            flags.append("impossible_density")
            continue

        macro_kcal = 4 * values["protein"] + 4 * values["carbs"] + 9 * values["fat"]
        if macro_kcal > values["calories"] * 1.25 + 40:
            # Macros can't hold more energy than the item. Trust the macros.
            flags.append("calories_below_macros")
            values["calories"] = macro_kcal

        items.append({
            "food"        : name,
            "weight_grams": round(weight) if weight else None,
            "calories"    : round(values["calories"]),
            "protein"     : round(values["protein"], 1),
            "carbs"       : round(values["carbs"], 1),
            "fat"         : round(values["fat"], 1),
        })

    if not items:
        return None, flags or ["no_items"]

    totals = {
        "total_calories": round(sum(i["calories"] for i in items)),
        "total_protein" : round(sum(i["protein"] for i in items), 1),
        "total_carbs"   : round(sum(i["carbs"] for i in items), 1),
        "total_fat"     : round(sum(i["fat"] for i in items), 1),
    }
    if totals["total_calories"] <= 0:
        return None, flags + ["zero_calories"]
    if totals["total_calories"] > MAX_PLATE_KCAL:
        return None, flags + ["plate_too_large"]

    claimed = _number(data.get("total_calories"))
    if claimed is not None and abs(claimed - totals["total_calories"]) > max(10, 0.05 * totals["total_calories"]):
        flags.append("totals_recomputed")

    primary = _clean_name(data.get("primary_food")) or items[0]["food"]
    hint_correct = data.get("hint_correct")
    return {
        "items"       : items,
        **totals,
        "primary_food": primary,
        "hint_correct": hint_correct if isinstance(hint_correct, bool) else None,
    }, flags


def check_per_100g(calories, protein, carbs, fat) -> list[str]:
    """Flags for a per-100g lookup. An empty list means the values look fine."""
    flags = []
    values = [_number(v) for v in (calories, protein, carbs, fat)]
    if any(v is None or v < 0 for v in values):
        return ["bad_value"]
    kcal, p, c, f = values
    if kcal > 950:
        flags.append("impossible_density")
    if p + c + f > 105:
        flags.append("macros_over_100g")
    return flags
