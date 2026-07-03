import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import io
from typing import Tuple

# ── Config ───────────────────────────────────────────────────────────────
CHECKPOINT_PATH = "./checkpoints/best_model.pth"
IMG_SIZE        = 300
NUM_CLASSES     = 101
DEVICE          = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CONFIDENCE_THRESHOLD = 0.85   # below this → OOD detected

# ── Image preprocessing ───────────────────────────────────────────────────
preprocess = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])


class FoodClassifier:
    def __init__(self):
        self.model   = None
        self.classes = None
        self._load_model()

    def _load_model(self):
        print(f"Loading model from {CHECKPOINT_PATH}...")
        checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE)

        # Rebuild EfficientNet-B3 architecture
        model = models.efficientnet_b3(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(
            nn.Dropout(p=0.3, inplace=True),
            nn.Linear(in_features, NUM_CLASSES),
        )

        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        model.to(DEVICE)
        torch.set_num_threads(2)

        self.model   = model
        self.classes = checkpoint["classes"]
        print(f"Model loaded on {DEVICE} | "
              f"Val acc at save: {checkpoint['val_acc']:.2f}% | "
              f"Classes: {len(self.classes)}")

    def predict(self, image_bytes: bytes) -> Tuple[str, float, bool]:
        """
        Returns:
            food_label  : predicted food name (e.g. 'pizza')
            confidence  : float between 0-1
            is_ood      : True if confidence below threshold (unknown food)
        """
        # Load and preprocess image
        image  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = preprocess(image).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            with torch.amp.autocast("cuda"):
                logits = self.model(tensor)

        # Softmax → probabilities
        probs      = torch.softmax(logits, dim=1)
        confidence = probs.max().item()
        class_idx  = probs.argmax().item()
        food_label = self.classes[class_idx]

        # OOD check
        is_ood = confidence < CONFIDENCE_THRESHOLD

        return food_label, confidence, is_ood

    def top5_predictions(self, image_bytes: bytes) -> list:
        """Returns top 5 predictions with confidence scores — useful for debugging."""
        image  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = preprocess(image).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            with torch.amp.autocast("cuda"):
                logits = self.model(tensor)

        probs       = torch.softmax(logits, dim=1)
        top5_probs, top5_idx = probs.topk(5)

        return [
            {
                "food"      : self.classes[idx.item()],
                "confidence": round(prob.item(), 4),
            }
            for prob, idx in zip(top5_probs[0], top5_idx[0])
        ]


# ── Singleton — loaded once when FastAPI starts ───────────────────────────
classifier = FoodClassifier()