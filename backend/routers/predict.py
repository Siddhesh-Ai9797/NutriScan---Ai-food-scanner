import re
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from services.auth_service import rate_limit
from services.image_service import normalize_image, ImageError, NOT_AN_IMAGE
from services.model_service import classifier
from services.ood_service import detect_all_foods
from services.s3_service import upload_food_photo

router = APIRouter()


def _folder_name(name: str) -> str:
    """S3 folder for a food name, e.g. 'Chicken Biryani' -> 'chicken_biryani'."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or "unknown"


@router.post("/predict", dependencies=[Depends(rate_limit("predict", 60))])
async def predict(file: UploadFile = File(...)):
    """
    Main prediction endpoint.
    Upload a food photo → get back all detected food items + total nutrition.

    Flow:
        1. Read image bytes
        2. EfficientNet classifies → primary food + confidence
        3. GPT-4o detects ALL food items and checks EfficientNet's guess
        4. Upload photo to S3 under the final food name
        5. Return combined nutrition for everything on the plate
    """

    # ── Validate and normalise the photo ──────────────────────────────────
    # Anything Pillow can open is accepted (JPEG, PNG, WEBP, iPhone HEIC...)
    # and converted to a clean JPEG; other files get a clear 400 message.
    if file.content_type and not (
        file.content_type.startswith("image/") or file.content_type == "application/octet-stream"
    ):
        raise HTTPException(status_code=400, detail=NOT_AN_IMAGE)

    try:
        image_bytes = normalize_image(await file.read())
    except ImageError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Step 1: EfficientNet inference ────────────────────────────────────
    try:
        food_label, confidence, is_ood = classifier.predict(image_bytes)
        top5 = classifier.top5_predictions(image_bytes)
    except Exception:
        raise HTTPException(status_code=500, detail="Our food model had a problem. Please try again.")

    # ── Step 2: GPT-4o detects ALL food items in the photo ───────────────
    # Pass EfficientNet's result as a hint to verify if it was confident
    primary_hint = food_label if not is_ood else None
    gpt_result   = await detect_all_foods(image_bytes, primary_food=primary_hint)

    items    = gpt_result.get("items", [])
    has_data = len(items) > 0 and gpt_result.get("total_calories", 0) > 0

    # GPT-4o overrules EfficientNet when it looked at the photo and disagreed
    # (e.g. biryani classified as fried_rice at 94%).
    gpt_overruled = has_data and not is_ood and gpt_result.get("hint_correct") is False
    use_gpt_name  = is_ood or gpt_overruled

    if has_data:
        primary_name = (gpt_result.get("primary_food") or "Unknown food") if use_gpt_name else food_label
    else:
        primary_name = None
    display_name = primary_name.replace("_", " ") if primary_name else None

    # ── Step 3: Upload photo to S3, filed under the final name ───────────
    try:
        image_url = upload_food_photo(
            image_bytes  = image_bytes,
            food_label   = _folder_name(display_name) if display_name else "unknown",
            content_type = "image/jpeg",
        )
    except Exception:
        image_url = None

    # ── Step 4: Build response ────────────────────────────────────────────
    if has_data:
        return {
            "status"      : "success",
            "source"      : "gpt4o" if use_gpt_name else "efficientnet",
            "food"        : display_name,
            "confidence"  : None if use_gpt_name else round(confidence * 100, 1),
            "model_guess" : food_label.replace("_", " ") if gpt_overruled else None,
            "items"       : items,
            "calories"    : gpt_result["total_calories"],
            "protein"     : gpt_result["total_protein"],
            "carbs"       : gpt_result["total_carbs"],
            "fat"         : gpt_result["total_fat"],
            "serving"     : f"full meal ({len(items)} item{'s' if len(items) > 1 else ''})",
            "weight_grams": sum(i.get("weight_grams", 0) for i in items),
            "top5"        : top5,
            "is_ood"      : is_ood,
            "image_url"   : image_url,
            "multi_item"  : len(items) > 1,
        }

    # ── Fallback — nothing detected ───────────────────────────────────────
    return {
        "status"    : "unknown",
        "source"    : "unknown",
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