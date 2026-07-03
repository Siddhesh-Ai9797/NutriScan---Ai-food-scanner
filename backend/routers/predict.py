from fastapi import APIRouter, UploadFile, File, HTTPException
from services.model_service import classifier
from services.nutrition_service import get_nutrition
from services.ood_service import gpt4o_identify, estimate_portion
from services.s3_service import upload_food_photo

router = APIRouter()


@router.post("/predict")
async def predict(file: UploadFile = File(...)):
    """
    Main prediction endpoint.
    Upload a food photo → get back food name + calories + macros + S3 image URL.
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
        image_url = None   # don't fail prediction if S3 upload fails

    # ── Step 3: Known food → USDA + GPT-4o portion estimate ──────────────
    if not is_ood:
        nutrition    = await get_nutrition(food_label)
        weight_grams = await estimate_portion(image_bytes, food_label)
        scale        = weight_grams / 100

        return {
            "status"      : "success",
            "source"      : "efficientnet",
            "food"        : nutrition["food"],
            "confidence"  : round(confidence * 100, 1),
            "weight_grams": weight_grams,
            "calories"    : round((nutrition["calories"] or 0) * scale),
            "protein"     : round((nutrition["protein"]  or 0) * scale, 1),
            "carbs"       : round((nutrition["carbs"]    or 0) * scale, 1),
            "fat"         : round((nutrition["fat"]      or 0) * scale, 1),
            "serving"     : f"estimated portion ({weight_grams}g)",
            "top5"        : top5,
            "is_ood"      : False,
            "image_url"   : image_url,
        }

    # ── Step 4: Unknown food → GPT-4o Vision fallback ────────────────────
    gpt_result = await gpt4o_identify(image_bytes)

    if gpt_result.get("source") == "unknown":
        return {
            "status"    : "unknown",
            "source"    : "unknown",
            "food"      : None,
            "confidence": round(confidence * 100, 1),
            "calories"  : None,
            "protein"   : None,
            "carbs"     : None,
            "fat"       : None,
            "serving"   : None,
            "top5"      : top5,
            "is_ood"    : True,
            "image_url" : image_url,
            "message"   : "Could not identify this food. Please describe it manually.",
        }

    return {
        "status"      : "success",
        "source"      : "gpt4o",
        "food"        : gpt_result["food"],
        "confidence"  : None,
        "weight_grams": gpt_result.get("weight_grams"),
        "calories"    : gpt_result["calories"],
        "protein"     : gpt_result["protein"],
        "carbs"       : gpt_result["carbs"],
        "fat"         : gpt_result["fat"],
        "serving"     : gpt_result.get("serving"),
        "top5"        : top5,
        "is_ood"      : True,
        "image_url"   : image_url,
        "message"     : "Identified by AI — please confirm the dish name below to help us improve.",
    }