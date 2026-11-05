#!/usr/bin/env bash
# Builds the zip for the daily readiness alert Lambda.
# boto3 already ships with the AWS Lambda Python runtime, and the rest of
# lambda_notify.py uses only the standard library, so the zip holds one file.
set -euo pipefail
cd "$(dirname "$0")"
rm -f lambda_notify.zip
zip -q lambda_notify.zip lambda_notify.py
echo "Built pipeline/lambda_notify.zip"
echo "Deploy with:"
echo "  aws lambda update-function-code --function-name <your-function> --zip-file fileb://lambda_notify.zip"
