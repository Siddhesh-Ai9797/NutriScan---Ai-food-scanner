from fastapi import APIRouter, HTTPException, Depends
from services.auth_service import rate_limit
from services.s3_service import key_from_photo_url
from pydantic import BaseModel
from typing import Optional
import boto3
import os
import re
import unicodedata
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

router = APIRouter()

AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET      = os.getenv("S3_BUCKET_NAME", "food-scanner-unknown-foods")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE_NAME", "food-labels")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table    = dynamodb.Table(DYNAMODB_TABLE)


class LabelRequest(BaseModel):
    food_name : str
    image_url : Optional[str] = None
    source    : str  = "efficientnet"  # efficientnet / gpt4o / user_correction
    calories  : Optional[float] = None
    protein   : Optional[float] = None
    carbs     : Optional[float] = None
    fat       : Optional[float] = None
    confirmed : bool = True


def clean_food_name(name: str) -> str:
    """
    Keeps letters (any language), digits, spaces and simple punctuation.
    Strips HTML and control characters so labels are safe to train on and display.
    """
    name = re.sub(r"<[^>]*>", " ", name or "")
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] in ("L", "N", "M") or ch in " -'&,./()")
    return re.sub(r"\s+", " ", name).strip().lower()[:80]


def _num(value):
    """DynamoDB-friendly number string; keeps 0, drops missing or negative values."""
    return str(value) if value is not None and value >= 0 else None


@router.post("/label", dependencies=[Depends(rate_limit("label", 120))])
async def save_label(request: LabelRequest):
    """
    Called when user confirms or corrects a food identification.
    Saves label + nutrition data to DynamoDB for future retraining.
    Image is already in S3 from the predict endpoint.
    """
    food_name = clean_food_name(request.food_name)
    if not food_name:
        raise HTTPException(status_code=400, detail="Food name cannot be empty.")
    # Only photos this API uploaded; the retrain pipeline downloads these URLs.
    image_url = request.image_url if request.image_url and key_from_photo_url(request.image_url) else None
    if request.source not in ("efficientnet", "gpt4o", "user_correction"):
        raise HTTPException(status_code=400, detail="Unknown label source.")

    label_id = str(uuid.uuid4())

    try:
        table.put_item(Item={
            "image_id"  : label_id,
            "food_name" : food_name,
            "image_url" : image_url,
            "source"    : request.source,
            "calories"  : _num(request.calories),
            "protein"   : _num(request.protein),
            "carbs"     : _num(request.carbs),
            "fat"       : _num(request.fat),
            "confirmed" : request.confirmed,
            "vote_count": 1,
            "votes"     : [food_name],
            "created_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save label: {str(e)}")

    return {
        "status"   : "saved",
        "label_id" : label_id,
        "food_name": food_name,
    }


@router.post("/vote/{image_id}", dependencies=[Depends(rate_limit("label", 120))])
async def vote_label(
    image_id : str,
    food_name: str,
):
    """
    Majority voting — when a second or third user sees the same unknown food
    and confirms or corrects the label.
    After 3 votes → mark as confirmed → eligible for retraining.
    """
    try:
        response = table.get_item(Key={"image_id": image_id})
        item     = response.get("Item")

        if not item:
            raise HTTPException(status_code=404, detail="Image not found.")

        votes      = item.get("votes", [])
        vote_count = item.get("vote_count", 0) + 1
        cleaned = clean_food_name(food_name)
        if not cleaned:
            raise HTTPException(status_code=400, detail="Food name cannot be empty.")
        votes.append(cleaned)

        # Majority vote — most common label wins
        confirmed_label = max(set(votes), key=votes.count)
        is_confirmed    = vote_count >= 3

        table.update_item(
            Key={"image_id": image_id},
            UpdateExpression=(
                "SET vote_count = :vc, votes = :v, "
                "food_name = :fn, confirmed = :c"
            ),
            ExpressionAttributeValues={
                ":vc": vote_count,
                ":v" : votes,
                ":fn": confirmed_label,
                ":c" : is_confirmed,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vote failed: {str(e)}")

    return {
        "status"         : "voted",
        "image_id"       : image_id,
        "confirmed_label": confirmed_label,
        "vote_count"     : vote_count,
        "confirmed"      : is_confirmed,
        "message"        : "Label confirmed!" if is_confirmed else f"Vote recorded. {3 - vote_count} more votes needed.",
    }


@router.get("/training-data/count")
async def get_training_data_count():
    """
    Returns count of labeled images per food class.
    Used to check when we have enough data to retrain.
    """
    try:
        response = table.scan()
        items    = response.get("Items", [])

        food_counts: dict = {}
        for item in items:
            name = item.get("food_name", "unknown")
            food_counts[name] = food_counts.get(name, 0) + 1

        ready_for_training = {
            food: count
            for food, count in food_counts.items()
            if count >= 50
        }

        return {
            "total_labeled"      : len(items),
            "unique_foods"       : len(food_counts),
            "food_counts"        : food_counts,
            "ready_for_training" : ready_for_training,
            "needs_more_data"    : {
                food: 50 - count
                for food, count in food_counts.items()
                if count < 50
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))