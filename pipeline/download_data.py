"""
download_data.py
────────────────
Downloads confirmed labeled images from S3 into local training folder.
Organizes them by food class ready for PyTorch ImageFolder.

Output structure:
    pipeline/new_training_data/
    ├── pomplet_fry/
    │   ├── img1.jpg
    │   └── img2.jpg
    ├── biryani/
    │   └── img3.jpg
    └── dal_makhani/
        └── img4.jpg
"""

import boto3
import os
import requests
import shutil
from dotenv import load_dotenv
from check_labels import get_labeled_data

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "new_training_data")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def clean_class_name(food_name: str) -> str:
    """Convert food name to valid folder name."""
    return food_name.strip().lower().replace(" ", "_").replace("/", "_")


def download_images(data: dict) -> dict:
    """
    Downloads all labeled images from S3 to local folder.
    
    Returns:
        {
            "downloaded" : 48,
            "failed"     : 2,
            "classes"    : {"pomplet_fry": 15, "biryani": 20, ...}
        }
    """
    # Clean output directory
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    downloaded = 0
    failed     = 0
    class_counts = {}

    food_classes = data.get("food_classes", {})

    for food_name, images in food_classes.items():
        class_name   = clean_class_name(food_name)
        class_dir    = os.path.join(OUTPUT_DIR, class_name)
        os.makedirs(class_dir, exist_ok=True)

        class_count = 0
        print(f"\nDownloading {len(images)} images for '{food_name}'...")

        for i, img_data in enumerate(images):
            image_url = img_data.get("image_url")
            if not image_url:
                failed += 1
                continue

            try:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()

                img_path = os.path.join(class_dir, f"{class_name}_{i:04d}.jpg")
                with open(img_path, "wb") as f:
                    f.write(response.content)

                downloaded  += 1
                class_count += 1

            except Exception as e:
                print(f"  Failed to download {image_url}: {e}")
                failed += 1

        class_counts[class_name] = class_count
        print(f"  ✅ Downloaded {class_count} images for '{food_name}'")

    print(f"\n── Download Summary ──────────────────────")
    print(f"Total downloaded : {downloaded}")
    print(f"Total failed     : {failed}")
    print(f"Output directory : {OUTPUT_DIR}")
    print(f"─────────────────────────────────────────\n")

    return {
        "downloaded" : downloaded,
        "failed"     : failed,
        "classes"    : class_counts,
        "output_dir" : OUTPUT_DIR,
    }


if __name__ == "__main__":
    print("Fetching labeled data from DynamoDB...")
    data   = get_labeled_data()

    if not data["ready"]:
        print(f"Not enough data yet. Have {data['total']}, need {data['threshold']}.")
        exit(0)

    print(f"\nStarting download of {data['total']} images...")
    result = download_images(data)
    print(f"\nDone! {result['downloaded']} images ready for training.")