"""
deploy.py
─────────
If evaluation passes:
    1. Backs up current production model in S3
    2. Uploads new retrained model to S3
    3. Replaces local best_model.pth with retrained version
    4. Triggers Railway redeploy via webhook

Railway will then restart and download the new model from S3.
"""

import boto3
import os
import shutil
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

S3_BUCKET        = os.getenv("S3_BUCKET_NAME", "food-scanner-unknown-foods")
AWS_REGION       = os.getenv("AWS_REGION", "us-east-1")
RAILWAY_WEBHOOK  = os.getenv("RAILWAY_WEBHOOK_URL", "")  # optional

OLD_MODEL_PATH   = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model.pth")
NEW_MODEL_PATH   = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model_retrained.pth")
BACKUP_DIR       = os.path.join(os.path.dirname(__file__), "../checkpoints/backups")

s3 = boto3.client(
    "s3",
    region_name           = AWS_REGION,
    aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
)


def backup_current_model():
    """Backs up current production model with timestamp."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"best_model_{timestamp}.pth")

    # Local backup
    shutil.copy2(OLD_MODEL_PATH, backup_path)
    print(f"Local backup saved: {backup_path}")

    # S3 backup
    s3_backup_key = f"models/backups/best_model_{timestamp}.pth"
    s3.upload_file(OLD_MODEL_PATH, S3_BUCKET, s3_backup_key)
    print(f"S3 backup saved: s3://{S3_BUCKET}/{s3_backup_key}")

    return backup_path

def reset_training_labels():
    """
    Marks all confirmed labels as 'used' after successful deployment.
    So the counter resets and Lambda won't send daily emails anymore.
    """
    import boto3
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

    dynamodb   = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
    table      = dynamodb.Table(os.getenv("DYNAMODB_TABLE_NAME", "food-labels"))

    response = table.scan()
    items    = response.get("Items", [])

    count = 0
    for item in items:
        if item.get("confirmed") and not item.get("used_for_training"):
            table.update_item(
                Key={"image_id": item["image_id"]},
                UpdateExpression="SET used_for_training = :u",
                ExpressionAttributeValues={":u": True}
            )
            count += 1

    print(f"Reset {count} labels — marked as used for training")

def deploy_new_model():
    """
    Deploys the retrained model:
    1. Backup current model
    2. Upload new model to S3
    3. Replace local model file
    4. Trigger Railway redeploy
    """
    print("\n── Deployment ────────────────────────────")

    if not os.path.exists(NEW_MODEL_PATH):
        print("❌ No retrained model found. Run retrain.py first.")
        return False

    # Load evaluation results
    results_path = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    if os.path.exists(results_path):
        with open(results_path) as f:
            eval_results = json.load(f)
        if not eval_results.get("approved"):
            print("❌ Model not approved by evaluation. Aborting deployment.")
            return False
    else:
        print("⚠️  No evaluation results found. Proceeding with caution...")

    # Step 1 — Backup current model
    print("\nStep 1: Backing up current model...")
    backup_path = backup_current_model()

    # Step 2 — Upload new model to S3
    print("\nStep 2: Uploading new model to S3...")
    s3_model_key = "models/best_model.pth"
    s3.upload_file(NEW_MODEL_PATH, S3_BUCKET, s3_model_key)
    print(f"✅ Uploaded to s3://{S3_BUCKET}/{s3_model_key}")

    # Step 3 — Replace local model
    print("\nStep 3: Replacing local production model...")
    shutil.copy2(NEW_MODEL_PATH, OLD_MODEL_PATH)
    print(f"✅ Local model updated: {OLD_MODEL_PATH}")

    # Step 4 — Trigger Railway redeploy
    if RAILWAY_WEBHOOK:
        print("\nStep 4: Triggering Railway redeploy...")
        try:
            response = requests.post(RAILWAY_WEBHOOK, timeout=10)
            if response.status_code == 200:
                print("✅ Railway redeploy triggered successfully")
            else:
                print(f"⚠️  Railway webhook returned {response.status_code}")
        except Exception as e:
            print(f"⚠️  Railway webhook failed: {e}")
            print("    Manually redeploy on Railway dashboard.")
    else:
        print("\nStep 4: No Railway webhook configured.")
        print("    Go to Railway dashboard and click Redeploy manually.")
        print("    The new model is already uploaded to S3.")

    # Save deployment log
    log = {
        "deployed_at"    : datetime.now().isoformat(),
        "backup_path"    : backup_path,
        "s3_model_key"   : s3_model_key,
        "eval_results"   : eval_results if os.path.exists(results_path) else {},
    }
    log_path = os.path.join(os.path.dirname(__file__), "deployment_log.json")
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n── Deployment Complete ───────────────────")
    print(f"✅ New model is live on S3")
    print(f"✅ Railway will use new model on next restart")
    # Reset labels so Lambda doesn't send daily emails
    print("\nResetting training labels...")
    reset_training_labels()
    print(f"─────────────────────────────────────────\n")

    return True


if __name__ == "__main__":
    success = deploy_new_model()
    exit(0 if success else 1)