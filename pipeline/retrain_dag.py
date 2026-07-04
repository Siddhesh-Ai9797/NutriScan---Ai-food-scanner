"""
retrain_dag.py
──────────────
Airflow DAG that runs the full retraining pipeline.

Schedule: Runs every day at midnight
Trigger : Only proceeds if 50+ labeled images in DynamoDB

DAG Tasks:
    1. check_labels      — check if enough data exists
    2. download_data     — download images from S3
    3. retrain           — fine-tune EfficientNet
    4. evaluate          — compare new vs old model
    5. deploy            — upload to S3, trigger Railway redeploy
    6. cleanup           — remove temporary files
"""

from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.utils.dates import days_ago
from datetime import datetime, timedelta
import sys
import os

# Add pipeline directory to path
sys.path.insert(0, os.path.dirname(__file__))

from check_labels  import get_labeled_data
from download_data import download_images
from retrain       import train
from evaluate      import evaluate
from deploy        import deploy_new_model

# ── DAG default args ──────────────────────────────────────────────────────
default_args = {
    "owner"           : "nutriscan",
    "retries"         : 1,
    "retry_delay"     : timedelta(minutes=5),
    "email_on_failure": False,
}

# ── DAG definition ────────────────────────────────────────────────────────
dag = DAG(
    dag_id           = "nutriscan_retrain_pipeline",
    description      = "Automatic retraining pipeline for NutriScan food classifier",
    default_args     = default_args,
    schedule_interval= "0 0 * * *",   # runs every day at midnight
    start_date       = days_ago(1),
    catchup          = False,
    tags             = ["nutriscan", "ml", "retraining"],
)


# ── Task 1: Check if enough labeled data exists ───────────────────────────
def task_check_labels(**context):
    """
    Checks DynamoDB for 50+ confirmed labeled images.
    Returns True to continue pipeline, False to stop.
    """
    data = get_labeled_data()
    context["task_instance"].xcom_push(key="training_data", value={
        "total"       : data["total"],
        "food_classes": {k: len(v) for k, v in data["food_classes"].items()},
    })
    print(f"Total labeled images: {data['total']}")
    print(f"Ready: {data['ready']}")
    return data["ready"]   # ShortCircuitOperator stops if False


check_labels_task = ShortCircuitOperator(
    task_id        = "check_labels",
    python_callable= task_check_labels,
    provide_context= True,
    dag            = dag,
)


# ── Task 2: Download new images from S3 ──────────────────────────────────
def task_download_data(**context):
    data   = get_labeled_data()
    result = download_images(data)
    print(f"Downloaded {result['downloaded']} images")
    print(f"Classes: {result['classes']}")
    return result["downloaded"]


download_task = PythonOperator(
    task_id        = "download_data",
    python_callable= task_download_data,
    provide_context= True,
    dag            = dag,
)


# ── Task 3: Retrain EfficientNet ──────────────────────────────────────────
def task_retrain(**context):
    success = train()
    if not success:
        raise Exception("Retraining failed — no new classes found")
    print("Retraining complete")


retrain_task = PythonOperator(
    task_id        = "retrain",
    python_callable= task_retrain,
    provide_context= True,
    execution_timeout= timedelta(hours=6),   # max 6 hours for training
    dag            = dag,
)


# ── Task 4: Evaluate new model ────────────────────────────────────────────
def task_evaluate(**context):
    result = evaluate()
    if not result["approved"]:
        raise Exception(
            f"Model evaluation failed. "
            f"New class acc: {result['new_class_acc']}%, "
            f"Old class acc: {result['old_class_acc']}%"
        )
    print(f"Model approved for deployment!")
    print(f"New class accuracy: {result['new_class_acc']}%")


evaluate_task = PythonOperator(
    task_id        = "evaluate",
    python_callable= task_evaluate,
    provide_context= True,
    dag            = dag,
)


# ── Task 5: Deploy new model ──────────────────────────────────────────────
def task_deploy(**context):
    success = deploy_new_model()
    if not success:
        raise Exception("Deployment failed")
    print("New model deployed successfully!")


deploy_task = PythonOperator(
    task_id        = "deploy",
    python_callable= task_deploy,
    provide_context= True,
    dag            = dag,
)


# ── Task 6: Cleanup temporary files ──────────────────────────────────────
def task_cleanup(**context):
    import shutil
    new_data_dir = os.path.join(os.path.dirname(__file__), "new_training_data")
    retrained    = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model_retrained.pth")

    if os.path.exists(new_data_dir):
        shutil.rmtree(new_data_dir)
        print(f"Cleaned up: {new_data_dir}")

    if os.path.exists(retrained):
        os.remove(retrained)
        print(f"Cleaned up: {retrained}")

    print("Cleanup complete")


cleanup_task = PythonOperator(
    task_id        = "cleanup",
    python_callable= task_cleanup,
    provide_context= True,
    dag            = dag,
)


# ── DAG task dependencies ─────────────────────────────────────────────────
check_labels_task >> download_task >> retrain_task >> evaluate_task >> deploy_task >> cleanup_task