"""
lambda_notify.py
────────────────
AWS Lambda function that runs every day at midnight via CloudWatch Events.
Checks DynamoDB for 50+ confirmed labeled images.
If ready → sends email notification via Gmail SMTP.

Deploy this to AWS Lambda with these environment variables:
    DYNAMODB_TABLE_NAME
    AWS_REGION_NAME (use this instead of AWS_REGION to avoid conflict)
    GMAIL_USER
    GMAIL_APP_PASSWORD
    NOTIFY_EMAIL
    RETRAIN_THRESHOLD (default: 50)
"""

import json
import os
import boto3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict


def get_labeled_data(table):
    """Scans DynamoDB and returns confirmed labeled image counts."""
    response = table.scan()
    items    = response.get("Items", [])

    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    confirmed    = [item for item in items if item.get("confirmed") is True]
    food_counts  = defaultdict(int)

    for item in confirmed:
        food_name = item.get("food_name", "unknown").strip().lower()
        if food_name:
            food_counts[food_name] += 1

    return {
        "total"       : len(confirmed),
        "food_counts" : dict(food_counts),
        "unique_foods": len(food_counts),
    }


def send_email_notification(data: dict):
    """Sends email via Gmail SMTP."""
    gmail_user     = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    notify_email   = os.environ.get("NOTIFY_EMAIL", gmail_user)
    threshold      = int(os.environ.get("RETRAIN_THRESHOLD", "50"))

    # Build food breakdown table
    food_rows = ""
    for food, count in sorted(data["food_counts"].items(), key=lambda x: -x[1]):
        food_rows += f"  {food:<30} {count} images\n"

    subject = f"🧠 NutriScan: Ready to Retrain! {data['total']} images collected"

    body = f"""
Hello Siddhesh,

Your NutriScan AI model is ready for retraining!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TRAINING DATA SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Total confirmed images : {data['total']} / {threshold}
  Unique food classes    : {data['unique_foods']}

  Food breakdown:
{food_rows}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TO START RETRAINING:
  1. Turn on your PC
  2. Open terminal
  3. Run:

     conda activate ai-env
     cd "C:\\Users\\sidpa\\Food Scanner"
     python pipeline/run_pipeline.py

  Training will take 2-3 hours on your RTX 5060 Ti.
  New model will be deployed automatically when done.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NutriScan AI — Automatic Retraining System
"""

    msg = MIMEMultipart()
    msg["From"]    = gmail_user
    msg["To"]      = notify_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, notify_email, msg.as_string())

    print(f"Email sent to {notify_email}")


def lambda_handler(event, context):
    """Main Lambda handler — called by CloudWatch Events every day at midnight."""

    region    = os.environ.get("AWS_REGION_NAME", "us-east-1")
    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "food-labels")
    threshold  = int(os.environ.get("RETRAIN_THRESHOLD", "50"))

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table    = dynamodb.Table(table_name)

    print(f"Checking DynamoDB table: {table_name}")
    data = get_labeled_data(table)

    print(f"Total confirmed images: {data['total']}")
    print(f"Threshold: {threshold}")
    print(f"Food counts: {data['food_counts']}")

    if data["total"] >= threshold:
        print(f"✅ Threshold reached! Sending email notification...")
        send_email_notification(data)
        return {
            "statusCode": 200,
            "body"      : json.dumps({
                "status"       : "notification_sent",
                "total_images" : data["total"],
                "food_counts"  : data["food_counts"],
            })
        }
    else:
        remaining = threshold - data["total"]
        print(f"⏳ Not ready yet. Need {remaining} more images.")
        return {
            "statusCode": 200,
            "body"      : json.dumps({
                "status"       : "not_ready",
                "total_images" : data["total"],
                "remaining"    : remaining,
                "food_counts"  : data["food_counts"],
            })
        }