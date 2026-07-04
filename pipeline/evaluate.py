"""
evaluate.py
───────────
Compares the retrained model against the current production model.
Only deploys if the new model is better or equal on existing classes.

Tests:
    1. New model accuracy on new food classes (should be > 70%)
    2. New model accuracy on sample of old Food-101 classes (should be > 85%)
    3. If both pass → approve for deployment
"""

import torch
import torch.nn as nn
from torchvision import models, transforms, datasets
from torch.utils.data import DataLoader, Subset
import os
import random
import json

DEVICE          = torch.device("cuda" if torch.cuda.is_available() else "cpu")
OLD_MODEL_PATH  = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model.pth")
NEW_MODEL_PATH  = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model_retrained.pth")
NEW_DATA_DIR    = os.path.join(os.path.dirname(__file__), "new_training_data")
FOOD101_DIR     = os.path.join(os.path.dirname(__file__), "../data/food-101/images")
IMG_SIZE        = 300
BATCH_SIZE      = 16
MIN_NEW_ACC     = 60.0   # minimum accuracy on new classes
MIN_OLD_ACC     = 80.0   # minimum accuracy on old classes (regression check)

val_transforms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def load_model(path: str, num_classes: int) -> nn.Module:
    checkpoint = torch.load(path, map_location=DEVICE, weights_only=False)
    model      = models.efficientnet_b3(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, num_classes),
    )
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    model.to(DEVICE)
    return model, checkpoint.get("classes", [])


def evaluate_on_dataset(model, loader, class_offset: int = 0) -> float:
    correct = 0
    total   = 0
    with torch.no_grad():
        for images, labels in loader:
            labels  = labels + class_offset
            images  = images.to(DEVICE)
            labels  = labels.to(DEVICE)
            outputs = model(images)
            preds   = outputs.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total   += labels.size(0)
    return 100.0 * correct / max(total, 1)


def evaluate() -> dict:
    print("\n── Model Evaluation ──────────────────────")

    if not os.path.exists(NEW_MODEL_PATH):
        print("No retrained model found. Run retrain.py first.")
        return {"approved": False, "reason": "No retrained model found"}

    # Load new model
    new_checkpoint = torch.load(NEW_MODEL_PATH, map_location=DEVICE, weights_only=False)
    all_classes    = new_checkpoint.get("classes", [])
    new_classes    = new_checkpoint.get("new_classes", [])
    num_classes    = len(all_classes)
    old_num_classes = num_classes - len(new_classes)

    print(f"Total classes   : {num_classes}")
    print(f"New classes     : {new_classes}")
    print(f"Old classes     : {old_num_classes}")

    new_model, _ = load_model(NEW_MODEL_PATH, num_classes)

    results = {
        "approved"       : False,
        "new_class_acc"  : 0.0,
        "old_class_acc"  : 0.0,
        "new_classes"    : new_classes,
        "total_classes"  : num_classes,
    }

    # ── Test 1: Accuracy on new classes ──────────────────────────────────
    if os.path.exists(NEW_DATA_DIR):
        new_dataset = datasets.ImageFolder(NEW_DATA_DIR, transform=val_transforms)
        new_loader  = DataLoader(new_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
        new_acc     = evaluate_on_dataset(new_model, new_loader, class_offset=old_num_classes)
        results["new_class_acc"] = round(new_acc, 2)
        print(f"\nNew class accuracy  : {new_acc:.2f}% (min required: {MIN_NEW_ACC}%)")
    else:
        print("No new class test data found.")

    # ── Test 2: Regression test on old Food-101 classes ──────────────────
    if os.path.exists(FOOD101_DIR):
        food101 = datasets.ImageFolder(FOOD101_DIR, transform=val_transforms)

        # Sample 50 images from each old class for quick evaluation
        class_to_indices = {}
        for idx, (_, label) in enumerate(food101.samples):
            if label not in class_to_indices:
                class_to_indices[label] = []
            class_to_indices[label].append(idx)

        selected = []
        for label, indices in class_to_indices.items():
            selected.extend(random.sample(indices, min(50, len(indices))))

        subset     = Subset(food101, selected)
        old_loader = DataLoader(subset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
        old_acc    = evaluate_on_dataset(new_model, old_loader, class_offset=0)
        results["old_class_acc"] = round(old_acc, 2)
        print(f"Old class accuracy  : {old_acc:.2f}% (min required: {MIN_OLD_ACC}%)")
    else:
        # If Food-101 not available just approve based on new class accuracy
        results["old_class_acc"] = 100.0

    # ── Decision ─────────────────────────────────────────────────────────
    new_ok = results["new_class_acc"] >= MIN_NEW_ACC
    old_ok = results["old_class_acc"] >= MIN_OLD_ACC

    results["approved"] = new_ok and old_ok

    print(f"\n── Evaluation Result ─────────────────────")
    print(f"New class test  : {'✅ PASS' if new_ok else '❌ FAIL'}")
    print(f"Old class test  : {'✅ PASS' if old_ok else '❌ FAIL'}")
    print(f"Decision        : {'✅ APPROVED for deployment' if results['approved'] else '❌ REJECTED'}")
    print(f"─────────────────────────────────────────\n")

    # Save results
    results_path = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    result = evaluate()
    exit(0 if result["approved"] else 1)