"""
run_pipeline.py
───────────────
Runs the full retraining pipeline manually without Airflow.
Use this to test the pipeline or trigger retraining manually.

Usage:
    python pipeline/run_pipeline.py
    python pipeline/run_pipeline.py --force   # skip 50 image threshold
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from check_labels  import get_labeled_data
from download_data import download_images
from retrain       import train
from evaluate      import evaluate
from deploy        import deploy_new_model


def run(force: bool = False):
    print("\n" + "="*50)
    print("  NutriScan Retraining Pipeline")
    print("="*50 + "\n")

    # ── Step 1: Check labels ──────────────────────────────────────────────
    print("STEP 1/5 — Checking labeled data...")
    data = get_labeled_data()

    if not data["ready"] and not force:
        print(f"\n⏳ Not enough data yet.")
        print(f"   Have: {data['total']} images")
        print(f"   Need: {data['threshold']} images")
        print(f"\nRun with --force to skip this check.")
        return False

    if force and not data["ready"]:
        print(f"⚠️  Force mode — proceeding with {data['total']} images")

    # ── Step 2: Download data ─────────────────────────────────────────────
    print("\nSTEP 2/5 — Downloading images from S3...")
    download_result = download_images(data)

    if download_result["downloaded"] == 0:
        print("❌ No images downloaded. Aborting.")
        return False

    # ── Step 3: Retrain ───────────────────────────────────────────────────
    print("\nSTEP 3/5 — Retraining EfficientNet...")
    success = train()

    if not success:
        print("❌ Retraining failed. Aborting.")
        return False

    # ── Step 4: Evaluate ──────────────────────────────────────────────────
    print("\nSTEP 4/5 — Evaluating new model...")
    eval_result = evaluate()

    if not eval_result["approved"]:
        print("❌ Model not approved. Aborting deployment.")
        print(f"   New class acc : {eval_result['new_class_acc']}%")
        print(f"   Old class acc : {eval_result['old_class_acc']}%")
        return False

    # ── Step 5: Deploy ────────────────────────────────────────────────────
    print("\nSTEP 5/5 — Deploying new model...")
    deployed = deploy_new_model()

    if deployed:
        print("\n" + "="*50)
        print("  ✅ Pipeline complete! New model is live.")
        print("="*50 + "\n")
        return True
    else:
        print("❌ Deployment failed.")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NutriScan Retraining Pipeline")
    parser.add_argument("--force", action="store_true", help="Skip 50 image threshold")
    args = parser.parse_args()

    success = run(force=args.force)
    sys.exit(0 if success else 1)