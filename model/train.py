import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models
import mlflow
import mlflow.pytorch
import os
import time

# ── Config ──────────────────────────────────────────────────────────────
DEVICE        = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DATA_DIR      = "./data"
CHECKPOINT_DIR = "./checkpoints"
BATCH_SIZE    = 64
EPOCHS        = 15
LR            = 1e-3
LR_FINETUNE   = 1e-4
NUM_CLASSES   = 101
IMG_SIZE      = 300          # EfficientNet-B3 native resolution
NUM_WORKERS   = 4
MLFLOW_EXP    = "food-nutrition-scanner"

os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

print(f"Device: {DEVICE}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")


# ── Data transforms ──────────────────────────────────────────────────────
train_transforms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(15),
    transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

val_transforms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


# ── Download & load Food-101 ─────────────────────────────────────────────
def get_dataloaders():
    print("Downloading Food-101 dataset (this may take a few minutes)...")
    train_dataset = datasets.Food101(
        root=DATA_DIR,
        split="train",
        transform=train_transforms,
        download=True,
    )
    val_dataset = datasets.Food101(
        root=DATA_DIR,
        split="test",
        transform=val_transforms,
        download=True,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )

    print(f"Train samples : {len(train_dataset):,}")
    print(f"Val samples   : {len(val_dataset):,}")
    print(f"Classes       : {len(train_dataset.classes)}")
    return train_loader, val_loader, train_dataset.classes


# ── Model ────────────────────────────────────────────────────────────────
def build_model():
    model = models.efficientnet_b3(weights=models.EfficientNet_B3_Weights.DEFAULT)

    # Freeze all layers first
    for param in model.parameters():
        param.requires_grad = False

    # Replace classifier head for 101 classes
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, NUM_CLASSES),
    )

    return model.to(DEVICE)


# ── Train one epoch ───────────────────────────────────────────────────────
def train_epoch(model, loader, optimizer, criterion):
    model.train()
    total_loss, correct, total = 0.0, 0, 0

    for batch_idx, (images, labels) in enumerate(loader):
        images, labels = images.to(DEVICE), labels.to(DEVICE)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        preds = outputs.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += labels.size(0)

        if batch_idx % 100 == 0:
            print(f"  Batch {batch_idx}/{len(loader)} | "
                  f"Loss: {loss.item():.4f} | "
                  f"Acc: {100.*correct/total:.2f}%")

    return total_loss / len(loader), 100.0 * correct / total


# ── Validate ──────────────────────────────────────────────────────────────
def validate(model, loader, criterion):
    model.eval()
    total_loss, correct, total = 0.0, 0, 0

    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(DEVICE), labels.to(DEVICE)
            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item()
            preds = outputs.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)

    return total_loss / len(loader), 100.0 * correct / total


# ── Main training loop ────────────────────────────────────────────────────
def train():
    train_loader, val_loader, classes = get_dataloaders()
    model = build_model()
    criterion = nn.CrossEntropyLoss()

    mlflow.set_experiment(MLFLOW_EXP)

    with mlflow.start_run(run_name="efficientnet-b3-food101"):
        mlflow.log_params({
            "model"      : "efficientnet_b3",
            "dataset"    : "food101",
            "batch_size" : BATCH_SIZE,
            "epochs"     : EPOCHS,
            "img_size"   : IMG_SIZE,
            "num_classes": NUM_CLASSES,
            "device"     : str(DEVICE),
        })

        best_val_acc = 0.0

        # ── Phase 1: Train only the classifier head (5 epochs) ──
        print("\n── Phase 1: Training classifier head ──")
        optimizer = optim.Adam(model.classifier.parameters(), lr=LR)
        scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=2, gamma=0.5)

        for epoch in range(1, 6):
            start = time.time()
            train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion)
            val_loss, val_acc = validate(model, val_loader, criterion)
            scheduler.step()
            elapsed = time.time() - start

            print(f"\nEpoch {epoch}/5 ({elapsed:.0f}s) | "
                  f"Train Loss: {train_loss:.4f} Acc: {train_acc:.2f}% | "
                  f"Val Loss: {val_loss:.4f} Acc: {val_acc:.2f}%")

            mlflow.log_metrics({
                "train_loss": train_loss,
                "train_acc" : train_acc,
                "val_loss"  : val_loss,
                "val_acc"   : val_acc,
            }, step=epoch)

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                ckpt_path = os.path.join(CHECKPOINT_DIR, "best_model.pth")
                torch.save({
                    "epoch"     : epoch,
                    "model_state": model.state_dict(),
                    "val_acc"   : val_acc,
                    "classes"   : classes,
                }, ckpt_path)
                print(f"  Saved best model — val_acc: {val_acc:.2f}%")

        # ── Phase 2: Unfreeze all layers and fine-tune (10 epochs) ──
        print("\n── Phase 2: Full fine-tuning ──")
        for param in model.parameters():
            param.requires_grad = True

        optimizer = optim.Adam(model.parameters(), lr=LR_FINETUNE)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=10)

        for epoch in range(6, EPOCHS + 1):
            start = time.time()
            train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion)
            val_loss, val_acc = validate(model, val_loader, criterion)
            scheduler.step()
            elapsed = time.time() - start

            print(f"\nEpoch {epoch}/{EPOCHS} ({elapsed:.0f}s) | "
                  f"Train Loss: {train_loss:.4f} Acc: {train_acc:.2f}% | "
                  f"Val Loss: {val_loss:.4f} Acc: {val_acc:.2f}%")

            mlflow.log_metrics({
                "train_loss": train_loss,
                "train_acc" : train_acc,
                "val_loss"  : val_loss,
                "val_acc"   : val_acc,
            }, step=epoch)

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                ckpt_path = os.path.join(CHECKPOINT_DIR, "best_model.pth")
                torch.save({
                    "epoch"      : epoch,
                    "model_state": model.state_dict(),
                    "val_acc"    : val_acc,
                    "classes"    : classes,
                }, ckpt_path)
                print(f"  Saved best model — val_acc: {val_acc:.2f}%")

        mlflow.log_metric("best_val_acc", best_val_acc)
        mlflow.log_artifact(os.path.join(CHECKPOINT_DIR, "best_model.pth"))
        print(f"\nTraining complete. Best val accuracy: {best_val_acc:.2f}%")


if __name__ == "__main__":
    train()