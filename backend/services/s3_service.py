import boto3
import os
import uuid
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "food-scanner-unknown-foods")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3_client = boto3.client(
    "s3",
    region_name          = AWS_REGION,
    aws_access_key_id    = os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key= os.getenv("AWS_SECRET_ACCESS_KEY"),
)


def upload_food_photo(image_bytes: bytes, food_label: str, content_type: str = "image/jpeg") -> str:
    """
    Uploads a food photo to S3.
    Returns the public URL of the uploaded image.

    Args:
        image_bytes : raw image bytes
        food_label  : food name e.g. "hamburger" (used for folder organization)
        content_type: image MIME type

    Returns:
        S3 URL string
    """
    image_id = str(uuid.uuid4())
    # Organize by food label so you can browse by food type
    s3_key   = f"user-uploads/{food_label}/{image_id}.jpg"

    s3_client.put_object(
        Bucket     = S3_BUCKET,
        Key        = s3_key,
        Body       = image_bytes,
        ContentType= content_type,
    )

    url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
    return url