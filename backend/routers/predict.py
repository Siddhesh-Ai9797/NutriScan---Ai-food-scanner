from fastapi import APIRouter, UploadFile, File, HTTPException
from services.model_service import classifier
from services.nutrition_service import get_nutrition
from services.ood_service import detect_all_foods
from services.s3_service import upload_food_photo

router = APIRouter()


@router.post("/predict")
async def predict(file: UploadFile = File(...)):
    """
    Main prediction endpoint.
    Upload a food photo → get back all detected food items + total nutrition.

    Flow:
        1. Read image bytes
        2. EfficientNet classifies → primary food + confidence
        3. Upload photo to S3
        4. GPT-4o detects ALL food items in the photo
        5. Return combined nutrition for everything on the plate
    """

    # ── Validate file type ────────────────────────────────────────────────
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a JPEG, PNG, or WEBP image."
        )

    # ── Read image bytes ──────────────────────────────────────────────────
    image_bytes = await file.read()

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Image too large. Please upload an image under 10MB."
        )

    # ── Step 1: EfficientNet inference ────────────────────────────────────
    try:
        food_label, confidence, is_ood = classifier.predict(image_bytes)
        top5 = classifier.top5_predictions(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {str(e)}")

    # ── Step 2: Upload photo to S3 ────────────────────────────────────────
    try:
        image_url = upload_food_photo(
            image_bytes  = image_bytes,
            food_label   = food_label if not is_ood else "unknown",
            content_type = file.content_type or "image/jpeg",
        )
    except Exception:
        image_url = None

    # ── Step 3: GPT-4o detects ALL food items in the photo ───────────────
    # Pass EfficientNet's result as a hint if it was confident
    primary_hint = food_label if not is_ood else None
    gpt_result   = await detect_all_foods(image_bytes, primary_food=primary_hint)

    items    = gpt_result.get("items", [])
    has_data = len(items) > 0 and gpt_result.get("total_calories", 0) > 0

    # ── Step 4: Build response ────────────────────────────────────────────
    if has_data:
        primary_name = food_label if not is_ood else gpt_result.get("primary_food", "Unknown food")

        return {
            "status"      : "success",
            "source"      : "efficientnet" if not is_ood else "gpt4o",
            "food"        : primary_name,
            "confidence"  : round(confidence * 100, 1) if not is_ood else None,
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