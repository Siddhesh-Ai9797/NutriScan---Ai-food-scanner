from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import boto3
import os
import uuid
from datetime import datetime

router = APIRouter()

# ── AWS Config ────────────────────────────────────────────────────────────
AWS_REGION      = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET       = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE  = os.getenv("DYNAMODB_TABLE_NAME", "food-labels")

# ── AWS clients ───────────────────────────────────────────────────────────
s3_client       = boto3.client("s3", region_name=AWS_REGION)
dynamodb        = boto3.resource("dynamodb", region_name=AWS_REGION)
table           = dynamodb.Table(DYNAMODB_TABLE)


@router.post("/label")
async def label_food(
    file      : UploadFile = File(...),
    food_name : str        = Form(...),   # user typed label e.g. "Biryani"
    source    : str        = Form(...),   # "gpt4o" or "user_manual"
):
    """
    Called when:
    - GPT-4o identified a food and user confirms/corrects the label
    - User manually types the food name

    Flow:
        1. Upload image to S3
        2. Save label + metadata to DynamoDB
        3. Return success

    DynamoDB entry:
        {
            "image_id"   : "uuid",
            "food_name"  : "Biryani",
            "s3_key"     : "unknown-foods/uuid.jpg",
            "source"     : "gpt4o",
            "vote_count" : 1,
            "votes"      : ["Biryani"],
            "confirmed"  : false,
            "created_at" : "2026-07-01T10:00:00"
        }
    """

    # ── Validate ──────────────────────────────────────────────────────────
    if not food_name.strip():
        raise HTTPException(status_code=400, detail="Food name cannot be empty.")

    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Invalid file type.")

    # ── Read image ────────────────────────────────────────────────────────
    image_bytes = await file.read()
    image_id    = str(uuid.uuid4())
    s3_key      = f"unknown-foods/{image_id}.jpg"

    # ── Upload to S3 ──────────────────────────────────────────────────────
    try:
        s3_client.put_object(
            Bucket      = S3_BUCKET,
            Key         = s3_key,
            Body        = image_bytes,
            ContentType = file.content_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")

    # ── Save label to DynamoDB ────────────────────────────────────────────
    try:
        table.put_item(Item={
            "image_id"  : image_id,
            "food_name" : food_name.strip().lower(),
            "s3_key"    : s3_key,
            "source"    : source,
            "vote_count": 1,
            "votes"     : [food_name.strip().lower()],
            "confirmed" : False,   # becomes True after majority voting
            "created_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DynamoDB save failed: {str(e)}")

    return {
        "status"    : "saved",
        "image_id"  : image_id,
        "food_name" : food_name.strip(),
        "message"   : f"Thank you! '{food_name}' saved. This helps us improve the model.",
    }


@router.post("/vote/{image_id}")
async def vote_label(
    image_id  : str,
    food_name : str = Form(...),
):
    """
    Majority voting — when a second or third user sees the same unknown food
    and confirms or corrects the label.

    After 3 votes → mark as confirmed → eligible for retraining.
    """
    try:
        # Get existing item
        response = table.get_item(Key={"image_id": image_id})
        item     = response.get("Item")

        if not item:
            raise HTTPException(status_code=404, detail="Image not found.")

        # Add this vote
        votes      = item.get("votes", [])
        vote_count = item.get("vote_count", 0) + 1
        votes.append(food_name.strip().lower())

        # Majority vote — most common label wins
        confirmed_label = max(set(votes), key=votes.count)
        is_confirmed    = vote_count >= 3

        # Update DynamoDB
        table.update_item(
            Key={ "image_id": image_id },
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