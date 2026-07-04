"""
retrain.py
──────────
Fine-tunes EfficientNet-B3 on combined dataset:
    - Original Food-101 (101 classes, 750 images each)
    - New user-labeled images (new food classes)

Strategy:
    - Load existing best_model.pth
    - Add new classification heads for new classes
    - Fine-tune with aggressive augmentation on new classes
    - Save new model as best_model_retrained.pth
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset, ConcatDataset
from torchvision import datasets, transforms, models
from torch.cuda.amp import GradScaler, autocast
import mlflow
import os
import time
import json
import shutil
from PIL import Image

# ── Config ───────────────────────────────────────────────────────────────
DEVICE          = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model.pth")
NEW_MODEL_PATH  = os.path.join(os.path.dirname(__file__), "../checkpoints/best_model_retrained.pth")
FOOD101_DIR     = os.path.join(os.path.dirname(__file__), "../data/food-101/images")
NEW_DATA_DIR    = os.path.join(os.path.dirname(__file__), "new_training_data")
IMG_SIZE        = 300
BATCH_SIZE      = 16
EPOCHS          = 10
LR              = 5e-5   # low LR to avoid forgetting old classes
NUM_WORKERS     = 0      # Windows safe
MLFLOW_EXP      = "food-nutrition-scanner-retrain"


# ── Transforms ────────────────────────────────────────────────────────────
# Aggressive augmentation for new classes (fewer images)
new_class_transforms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomVerticalFlip(p=0.2),
    transforms.RandomRotation(30),
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
    transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# Standard transforms for Food-101 classes
food101_transforms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(brightness=0.2, contrast=0.2),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

val_transforms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class AugmentedDataset(Dataset):
    """
    Wraps a dataset and applies augmentation multiple times
    to artificially increase dataset size for small classes.
    """
    def __init__(self, dataset, augment_factor: int = 8):
        self.dataset        = dataset
        self.augment_factor = augment_factor

    def __len__(self):
        return len(self.dataset) * self.augment_factor

    def __getitem__(self, idx):
        real_idx = idx % len(self.dataset)
        return self.dataset[real_idx]


def load_new_classes() -> tuple:
    """
    Loads new user-labeled images from pipeline/new_training_data/
    Returns (dataset, class_names)
    """
    if not os.path.exists(NEW_DATA_DIR):
        print("No new training data found.")
        return None, []

    new_classes = [d for d in os.listdir(NEW_DATA_DIR)
                   if os.path.isdir(os.path.join(NEW_DATA_DIR, d))]

    if not new_classes:
        print("No new class folders found.")
        return None, []

    print(f"Found {len(new_classes)} new food classes: {new_classes}")

    dataset = datasets.ImageFolder(NEW_DATA_DIR, transform=new_class_transforms)

    # Augment 8x since we have few images per class
    augmented = AugmentedDataset(dataset, augment_factor=8)

    return augmented, dataset.classes


def load_food101_subset() -> tuple:
    """
    Loads a subset of Food-101 to keep existing class knowledge.
    Uses 200 images per class (instead of 750) to speed up retraining.
    """
    if not os.path.exists(FOOD101_DIR):
        print("Food-101 not found — skipping existing class data.")
        return None, []

    dataset = datasets.ImageFolder(FOOD101_DIR, transform=food101_transforms)

    # Sample 200 images per class to keep training fast
    from torch.utils.data import Subset
    import random

    class_to_indices = {}
    for idx, (_, label) in enumerate(dataset.samples):
        if label not in class_to_indices:
            class_to_indices[label] = []
        class_to_indices[label].append(idx)

    selected_indices = []
    for label, indices in class_to_indices.items():
        selected = random.sample(indices, min(200, len(indices)))
        selected_indices.extend(selected)

    subset = Subset(dataset, selected_indices)
    print(f"Loaded Food-101 subset: {len(subset)} images, {len(dataset.classes)} classes")

    return subset, dataset.classes


def build_expanded_model(old_classes: list, new_classes: list) -> tuple:
    """
    Loads existing model and expands classifier for new classes.
    
    Returns:
        (model, all_classes)
    """
    all_classes = old_classes + [c for c in new_classes if c not in old_classes]
    num_classes = len(all_classes)

    print(f"\nExpanding model:")
    print(f"  Old classes : {len(old_classes)}")
    print(f"  New classes : {len(new_classes)}")
    print(f"  Total       : {num_classes}")

    # Load existing model
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=False)

    model = models.efficientnet_b3(weights=None)
    in_features = model.classifier[1].in_features

    # Build new classifier with expanded output
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, num_classes),
    )

    # Load old weights — only for existing classes
    old_state = checkpoint["model_state"]
    new_state  = model.state_dict()

    # Copy old classifier weights for existing classes
    old_weight = old_state["classifier.1.weight"]
    old_bias   = old_state["classifier.1.bias"]

    new_state["classifier.1.weight"][:len(old_classes)] = old_weight
    new_state["classifier.1.bias"][:len(old_classes)]   = old_bias

    # Load all other layers from old model
    for key in old_state:
        if "classifier" not in key:
            new_state[key] = old_state[key]

    model.load_state_dict(new_state)
    model = model.to(DEVICE)

    return model, all_classes


def train():
    if __name__ == "__main__":
        print(f"\nDevice : {DEVICE}")
        if torch.cuda.is_available():
            print(f"GPU    : {torch.cuda.get_device_name(0)}")

    # ── Load data ─────────────────────────────────────────────────────────
    new_dataset, new_classes   = load_new_classes()
    food101_dataset, old_classes = load_food101_subset()

    if not new_classes:
        print("No new classes to train on. Exiting.")
        return False

    # ── Build expanded model ──────────────────────────────────────────────
    model, all_classes = build_expanded_model(old_classes, new_classes)

    # ── Combine datasets ──────────────────────────────────────────────────
    # We need to remap labels since Food-101 and new data have different indices
    # Use separate DataLoaders and combine batches during training

    new_loader = DataLoader(
        new_dataset,
        batch_size  = BATCH_SIZE,
        shuffle     = True,
        num_workers = NUM_WORKERS,
        pin_memory  = True,
    )

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LR)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    scaler    = GradScaler()

    best_loss    = float("inf")
    best_acc     = 0.0

    mlflow.set_experiment(MLFLOW_EXP)

    with mlflow.start_run(run_name=f"retrain-{len(new_classes)}-new-classes"):
        mlflow.log_params({
            "new_classes"   : new_classes,
            "total_classes" : len(all_classes),
            "epochs"        : EPOCHS,
            "lr"            : LR,
            "batch_size"    : BATCH_SIZE,
            "device"        : str(DEVICE),
        })

        print(f"\n── Starting retraining for {len(new_classes)} new classes ──\n")

        for epoch in range(1, EPOCHS + 1):
            model.train()
            total_loss, correct, total = 0.0, 0, 0
            start = time.time()

            # Train on new classes only
            # New class indices start after old classes
            offset = len(old_classes)

            for batch_idx, (images, labels) in enumerate(new_loader):
                # Offset labels to correct position in expanded classifier
                labels  = labels + offset
                images  = images.to(DEVICE)
                labels  = labels.to(DEVICE)

                optimizer.zero_grad()
                with autocast():
                    outputs = model(images)
                    loss    = criterion(outputs, labels)

                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()

                total_loss += loss.item()
                preds       = outputs.argmax(dim=1)
                correct    += (preds == labels).sum().item()
                total      += labels.size(0)

                if batch_idx % 50 == 0:
                    print(f"  Epoch {epoch}/{EPOCHS} | Batch {batch_idx}/{len(new_loader)} | "
                          f"Loss: {loss.item():.4f} | Acc: {100.*correct/max(total,1):.2f}%")

            scheduler.step()
            elapsed    = time.time() - start
            train_loss = total_loss / len(new_loader)
            train_acc  = 100.0 * correct / max(total, 1)

            print(f"\nEpoch {epoch}/{EPOCHS} ({elapsed:.0f}s) | "
                  f"Loss: {train_loss:.4f} | Acc: {train_acc:.2f}%")

            mlflow.log_metrics({
                "train_loss": train_loss,
                "train_acc" : train_acc,
            }, step=epoch)

            if train_loss < best_loss:
                best_loss = train_loss
                best_acc  = train_acc
                torch.save({
                    "epoch"      : epoch,
                    "model_state": model.state_dict(),
                    "val_acc"    : best_acc,
                    "classes"    : all_classes,
                    "new_classes": new_classes,
                }, NEW_MODEL_PATH)
                print(f"  ✅ New best model saved — loss: {best_loss:.4f}")

        mlflow.log_metric("best_acc", best_acc)
        print(f"\nRetraining complete!")
        print(f"Best accuracy : {best_acc:.2f}%")
        print(f"New model     : {NEW_MODEL_PATH}")
        print(f"New classes   : {new_classes}")

    return True


if __name__ == "__main__":
    train()