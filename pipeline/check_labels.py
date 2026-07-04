"""
check_labels.py
───────────────
Checks DynamoDB for total confirmed labeled images.
Triggers retraining when total reaches 50.

Returns:
    - List of new food classes with their image URLs
    - Total count of new labeled images
"""

import boto3
import os
import json
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

DYNAMODB_TABLE    = os.getenv("DYNAMODB_TABLE_NAME", "food-labels")
RETRAIN_THRESHOLD = 50   # trigger retraining when total hits this number
AWS_REGION        = os.getenv("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table    = dynamodb.Table(DYNAMODB_TABLE)


def get_labeled_data() -> dict:
    """
    Scans DynamoDB and returns all confirmed labeled images.
    
    Returns:
        {
            "total"       : 52,
            "ready"       : True,
            "food_classes": {
                "pomplet fry": [
                    {"image_url": "s3://...", "calories": 180, "protein": 22}
                ],
                "biryani": [...],
            }
        }
    """
    response = table.scan()
    items    = response.get("Items", [])

    # Only use confirmed labels
    confirmed = [
    item for item in items 
    if item.get("confirmed") is True 
    and not item.get("used_for_training")
    ]

    # Group by food name
    food_classes = defaultdict(list)
    for item in confirmed:
        food_name = item.get("food_name", "").strip().lower()
        if food_name and item.get("image_url"):
            food_classes[food_name].append({
                "image_url": item["image_url"],
                "calories" : item.get("calories"),
                "protein"  : item.get("protein"),
                "carbs"    : item.get("carbs"),
                "fat"      : item.get("fat"),
                "source"   : item.get("source", "unknown"),
            })

    total = sum(len(imgs) for imgs in food_classes.values())
    ready = total >= RETRAIN_THRESHOLD

    result = {
        "total"       : total,
        "ready"       : ready,
        "threshold"   : RETRAIN_THRESHOLD,
        "food_classes": dict(food_classes),
        "class_counts": {food: len(imgs) for food, imgs in food_classes.items()},
    }

    print(f"\n── Training Data Status ──────────────────")
    print(f"Total confirmed labels : {total}")
    print(f"Unique food classes    : {len(food_classes)}")
    print(f"Ready for retraining   : {ready}")
    print(f"Threshold              : {RETRAIN_THRESHOLD}")
    print(f"\nBreakdown:")
    for food, count in sorted(result["class_counts"].items(), key=lambda x: -x[1]):
        print(f"  {food:<30} {count} images")
    print(f"─────────────────────────────────────────\n")

    return result


def save_status(result: dict, output_path: str = "./pipeline/training_status.json"):
    """Saves the training status to a JSON file for Airflow to read."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        # Don't save full image URLs in status file — just counts
        status = {
            "total"       : result["total"],
            "ready"       : result["ready"],
            "threshold"   : result["threshold"],
            "class_counts": result["class_counts"],
        }
        json.dump(status, f, indent=2)
    print(f"Status saved to {output_path}")


if __name__ == "__main__":
    result = get_labeled_data()
    save_status(result)

    if result["ready"]:
        print("✅ Ready to retrain! Run retrain_dag.py to start.")
    else:
        remaining = result["threshold"] - result["total"]
        print(f"⏳ Need {remaining} more labeled images to trigger retraining.")