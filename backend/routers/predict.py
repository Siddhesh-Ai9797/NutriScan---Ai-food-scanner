import os
import re
import time

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool

from services import metrics_service
from services.auth_service import rate_limit
from services.cache_service import CACHE_ON, photo_cache, photo_key
from services.guardrail_service import food_gate, NotFoodPhoto, NOT_FOOD_MESSAGE
from services.image_service import normalize_image, ImageError, NOT_AN_IMAGE
from services.model_service import classifier
from services.ood_service import detect_all_foods, FAST_MODEL, FULL_MODEL
from services.s3_service import upload_food_photo

router = APIRouter()

# Router: EfficientNet scans at or above this confidence go to the cheap model
# with a small image. Anything less sure, or anything the cheap model disputes,
# goes to the full model.
ROUTER_ON         = os.getenv("ROUTER", "on").lower() != "off"
ROUTER_CONFIDENCE = float(os.getenv("ROUTER_CONFIDENCE", "0.95"))


def _folder_name(name: str) -> str:
    """S3 folder for a food name, e.g. 'Chicken Biryani' -> 'chicken_biryani'."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or "unknown"


@router.post("/predict", dependencies=[Depends(rate_limit("predict", 60))])
async def predict(file: UploadFile = File(...)):
    """
    Upload a food photo, get back every food on the plate plus total nutrition.

    Flow:
        1. Clean the photo. Same photo seen recently? Reuse that answer (cache).
        2. CLIP checks the photo shows food (input guardrail).
        3. EfficientNet guesses the main dish.
        4. Router: a confident guess goes to gpt-4o-mini with a small image.
           An unsure guess, or one the cheap model disputes, goes to gpt-4o.
        5. The vision reply is checked for impossible numbers (output guardrail).
        6. Photo saved to S3; every step is timed and priced (monitoring).
    """
    trace = metrics_service.start_trace("predict")
    status_code = 200
    try:
        return await _predict(file, trace)
    except HTTPException as e:
        status_code = e.status_code
        raise
    except Exception:
        status_code = 500
        trace.route = "failed"
        raise
    finally:
        metrics_service.finish_trace(trace, status_code)


async def _predict(file: UploadFile, trace):
    # ── Validate and normalise the photo ──────────────────────────────────
    # Anything Pillow can open is accepted (JPEG, PNG, WEBP, iPhone HEIC...)
    # and converted to a clean JPEG; other files get a clear 400 message.
    if file.content_type and not (
        file.content_type.startswith("image/") or file.content_type == "application/octet-stream"
    ):
        trace.route = "rejected"
        raise HTTPException(status_code=400, detail=NOT_AN_IMAGE)

    try:
        image_bytes = normalize_image(await file.read())
    except ImageError as e:
        trace.route = "rejected"
        raise HTTPException(status_code=400, detail=str(e))

    key = photo_key(image_bytes)
    analysis = photo_cache.get(key) if CACHE_ON else None
    if analysis is not None:
        trace.route = "cache"
        trace.cache_hit = True
    else:
        analysis = await _analyse(image_bytes, trace)
        if CACHE_ON and (analysis.get("plate") or analysis.get("blocked")):
            photo_cache.set(key, analysis)

    if analysis.get("blocked"):
        trace.route = "blocked"
        raise HTTPException(status_code=422, detail=NOT_FOOD_MESSAGE)

    return _build_response(analysis, image_bytes, trace)


async def _analyse(image_bytes: bytes, trace) -> dict:
    """Runs the guardrail, model and router steps. Result is safe to cache."""
    # ── Input guardrail ───────────────────────────────────────────────────
    started = time.perf_counter()
    looks_like_food, food_prob = await run_in_threadpool(food_gate.check, image_bytes)
    trace.stage("food_gate", started)
    if not looks_like_food:
        trace.flag("clip_not_food")
        return {"blocked": True, "food_prob": food_prob}

    # ── EfficientNet ──────────────────────────────────────────────────────
    started = time.perf_counter()
    try:
        food_label, confidence, is_ood = await run_in_threadpool(classifier.predict, image_bytes)
        top5 = await run_in_threadpool(classifier.top5_predictions, image_bytes)
    except Exception:
        trace.errors.append("classifier")
        raise HTTPException(status_code=500, detail="Our food model had a problem. Please try again.")
    trace.stage("classifier", started)

    hint = food_label if not is_ood else None
    plate = None
    route = "full"

    # ── Router: confident scans try the cheap model first ────────────────
    if ROUTER_ON and not is_ood and confidence >= ROUTER_CONFIDENCE:
        started = time.perf_counter()
        try:
            plate, flags = await detect_all_foods(image_bytes, primary_food=hint, model=FAST_MODEL, detail="low")
        except NotFoodPhoto:
            plate, flags = None, ["fast_said_not_food"]
        trace.stage("fast_model", started)
        for rule in flags:
            trace.flag(rule)
        if plate is not None and plate["hint_correct"] is False:
            trace.flag("fast_disputed_classifier")
            plate = None
        if plate is not None:
            route = "fast"
        else:
            route = "escalated"

    # ── Full model for unsure, disputed, or failed fast scans ────────────
    if plate is None:
        started = time.perf_counter()
        try:
            plate, flags = await detect_all_foods(image_bytes, primary_food=hint, model=FULL_MODEL)
        except NotFoodPhoto:
            trace.stage("full_model", started)
            trace.flag("llm_not_food")
            return {"blocked": True, "food_prob": food_prob}
        trace.stage("full_model", started)
        for rule in flags:
            trace.flag(rule)

    trace.route = route
    return {
        "food_label": food_label,
        "confidence": confidence,
        "is_ood"    : is_ood,
        "top5"      : top5,
        "plate"     : plate,
        "route"     : route,
        "food_prob" : food_prob,
    }


def _build_response(analysis: dict, image_bytes: bytes, trace) -> dict:
    food_label = analysis["food_label"]
    confidence = analysis["confidence"]
    is_ood     = analysis["is_ood"]
    top5       = analysis["top5"]
    plate      = analysis["plate"]

    # The vision model overrules EfficientNet when it looked at the photo and
    # disagreed (e.g. biryani classified as fried_rice at 94%).
    gpt_overruled = plate is not None and not is_ood and plate.get("hint_correct") is False
    use_gpt_name  = is_ood or gpt_overruled

    if plate is not None:
        primary_name = (plate.get("primary_food") or "Unknown food") if use_gpt_name else food_label
    else:
        primary_name = None
    display_name = primary_name.replace("_", " ") if primary_name else None

    # ── Save the user's photo to S3, filed under the final name ──────────
    started = time.perf_counter()
    try:
        image_url = upload_food_photo(
            image_bytes  = image_bytes,
            food_label   = _folder_name(display_name) if display_name else "unknown",
            content_type = "image/jpeg",
        )
    except Exception:
        image_url = None
        trace.errors.append("s3_upload")
    trace.stage("s3_upload", started)

    if plate is not None:
        items = plate["items"]
        return {
            "status"      : "success",
            "source"      : "gpt4o" if use_gpt_name else "efficientnet",
            "route"       : trace.route,
            "food"        : display_name,
            "confidence"  : None if use_gpt_name else round(confidence * 100, 1),
            "model_guess" : food_label.replace("_", " ") if gpt_overruled else None,
            "items"       : items,
            "calories"    : plate["total_calories"],
            "protein"     : plate["total_protein"],
            "carbs"       : plate["total_carbs"],
            "fat"         : plate["total_fat"],
            "serving"     : f"full meal ({len(items)} item{'s' if len(items) > 1 else ''})",
            "weight_grams": sum(i.get("weight_grams") or 0 for i in items),
            "top5"        : top5,
            "is_ood"      : is_ood,
            "image_url"   : image_url,
            "multi_item"  : len(items) > 1,
        }

    # ── Fallback: nothing usable came back ────────────────────────────────
    trace.route = "failed"
    return {
        "status"    : "unknown",
        "source"    : "unknown",
        "route"     : trace.route,
        "food"      : None,
        "confidence": round(confidence * 100, 1),
        "items"     : [],
        "calories"  : None,
        "protein"   : None,
        "carbs"     : None,
        "fat"       : None,
        "serving"   : None,
        "top5"      : top5,
        "is_ood"    : True,
        "image_url" : image_url,
        "multi_item": False,
        "message"   : "Could not identify this food. Please describe it manually.",
    }
