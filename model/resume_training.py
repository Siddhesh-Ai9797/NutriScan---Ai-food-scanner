import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models
from torch.cuda.amp import GradScaler, autocast
import mlflow
import mlflow.pytorch
import os
import time

# ── Config ───────────────────────────────────────────────────────────────
DEVICE         = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DATA_DIR       = "./data"
CHECKPOINT_DIR = "./checkpoints"
BATCH_SIZE     = 16       # reduced from 64 — fits in 8GB VRAM
EPOCHS         = 10       # Phase 2 only: epochs 6-15
LR_FINETUNE    = 1e-4
NUM_CLASSES    = 101
IMG_SIZE       = 300
NUM_WORKERS    = 0        # 0 fixes Windows DataLoader deadlock
MLFLOW_EXP     = "food-nutrition-scanner"
CHECKPOINT_PATH = os.path.join(CHECKPOINT_DIR, "best_model.pth")

os.makedirs(CHECKPOINT_DIR, exist_ok=True)

if __name__ == "__main__":
    print(f"Device : {DEVICE}")
    if torch.cuda.is_available():
        print(f"GPU    : {torch.cuda.get_device_name(0)}")
        print(f"VRAM   : {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # ── Data transforms ──────────────────────────────────────────────────
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

    # ── Load Food-101 (already downloaded) ───────────────────────────────
    print("\nLoading Food-101 from disk...")
    train_dataset = datasets.Food101(
        root=DATA_DIR, split="train",
        transform=train_transforms, download=False,
    )
    val_dataset = datasets.Food101(
        root=DATA_DIR, split="test",
        transform=val_transforms, download=False,
    )

    train_loader = DataLoader(
        train_dataset, batch_size=BATCH_SIZE,
        shuffle=True, num_workers=NUM_WORKERS, pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=BATCH_SIZE,
        shuffle=False, num_workers=NUM_WORKERS, pin_memory=True,
    )
    print(f"Train: {len(train_dataset):,} | Val: {len(val_dataset):,}")

    # ── Load model from Phase 1 checkpoint ───────────────────────────────
    print(f"\nLoading checkpoint from {CHECKPOINT_PATH}...")
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE)

    model = models.efficientnet_b3(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, NUM_CLASSES),
    )
    model.load_state_dict(checkpoint["model_state"])
    model = model.to(DEVICE)

    starting_val_acc = checkpoint["val_acc"]
    print(f"Resumed from epoch {checkpoint['epoch']} | "
          f"Best val acc so far: {starting_val_acc:.2f}%")

    # ── Unfreeze ALL layers for Phase 2 ──────────────────────────────────
    for param in model.parameters():
        param.requires_grad = True
    print("All layers unfrozen for full fine-tuning")

    # ── Optimizer + scheduler + AMP scaler ───────────────────────────────
    optimizer = optim.Adam(model.parameters(), lr=LR_FINETUNE)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    criterion = nn.CrossEntropyLoss()
    scaler    = GradScaler()   # mixed precision — halves VRAM usage

    best_val_acc = starting_val_acc

    # ── Train one epoch ───────────────────────────────────────────────────
    def train_epoch(epoch):
        model.train()
        total_loss, correct, total = 0.0, 0, 0

        for batch_idx, (images, labels) in enumerate(train_loader):
            images, labels = images.to(DEVICE), labels.to(DEVICE)

            optimizer.zero_grad()
            with autocast():                        # mixed precision forward
                outputs = model(images)
                loss    = criterion(outputs, labels)

            scaler.scale(loss).backward()           # scaled backward
            scaler.step(optimizer)
            scaler.update()

            total_loss += loss.item()
            preds       = outputs.argmax(dim=1)
            correct    += (preds == labels).sum().item()
            total      += labels.size(0)

            if batch_idx % 200 == 0:
                print(f"  Epoch {epoch} | Batch {batch_idx}/{len(train_loader)} | "
                      f"Loss: {loss.item():.4f} | Acc: {100.*correct/total:.2f}%")

        return total_loss / len(train_loader), 100.0 * correct / total

    # ── Validate ──────────────────────────────────────────────────────────
    def validate():
        model.eval()
        total_loss, correct, total = 0.0, 0, 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(DEVICE), labels.to(DEVICE)
                with autocast():
                    outputs = model(images)
                    loss    = criterion(outputs, labels)

                total_loss += loss.item()
                preds       = outputs.argmax(dim=1)
                correct    += (preds == labels).sum().item()
                total      += labels.size(0)

        return total_loss / len(val_loader), 100.0 * correct / total

    # ── Phase 2 training loop ─────────────────────────────────────────────
    print("\n── Phase 2: Full fine-tuning with mixed precision ──\n")

    mlflow.set_experiment(MLFLOW_EXP)

    with mlflow.start_run(run_name="efficientnet-b3-phase2-amp"):
        mlflow.log_params({
            "phase"      : 2,
            "batch_size" : BATCH_SIZE,
            "epochs"     : EPOCHS,
            "lr"         : LR_FINETUNE,
            "amp"        : True,
            "num_workers": NUM_WORKERS,
        })

        for epoch in range(1, EPOCHS + 1):
            start = time.time()
            train_loss, train_acc = train_epoch(epoch)
            val_loss, val_acc     = validate()
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
                    "epoch"      : checkpoint["epoch"] + epoch,
                    "model_state": model.state_dict(),
                    "val_acc"    : val_acc,
                    "classes"    : checkpoint["classes"],
                }, ckpt_path)
                print(f"  ✓ New best model saved — val_acc: {val_acc:.2f}%")

        mlflow.log_metric("best_val_acc", best_val_acc)
        print(f"\nPhase 2 complete. Best val accuracy: {best_val_acc:.2f}%")