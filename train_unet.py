"""
SIH26143 - Slick Detection: Baseline U-Net Training (v2 - binary)
Owner: VISSHAL
Task: Train baseline U-Net slick segmentation model

Updated 2026-08-24 to match the actual dataset (Kaggle SOS, binary masks)
instead of the originally-planned 5-class MKLab scheme.

Still uses a PRETRAINED encoder (ResNet34 on ImageNet) via
segmentation_models_pytorch, not a from-scratch U-Net -- same reasoning as
before, training from scratch won't converge in a 3-day window.

Install first:
    pip install segmentation-models-pytorch torch torchvision --break-system-packages

Class imbalance still applies: oil pixels are a minority of any frame.
Weighted loss + reporting Oil Spill IoU specifically (not just accuracy)
still stands, just with 2 classes instead of 5 now.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import segmentation_models_pytorch as smp

# ---- CONFIG ----------------------------------------------------------------
DATA_DIR = "data/processed"
NUM_CLASSES = 2
CLASS_NAMES = ["background", "oil_spill"]
BATCH_SIZE = 8
EPOCHS = 15
LR = 1e-4
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Recalibrated 2026-08-24 against VISSHAL's actual preprocess.py output:
# oil_spill = 24.89% of pixels (NOT the ~2-3% we originally assumed -- this
# "refined" dataset is patch-cropped to be oil-enriched, not raw full scenes).
# Inverse-frequency weights normalized to mean 1: bg=0.75->0.50, oil=0.25->1.50.
# The old [0.4, 3.5] weighting was tuned for a much rarer minority class and
# would have pushed the model to over-predict oil -- bad news given we already
# lost the look-alike class as a false-positive check.
CLASS_WEIGHTS = torch.tensor([0.5, 1.5])


class SlickDataset(Dataset):
    def __init__(self, split: str):
        self.images = np.load(f"{DATA_DIR}/{split}_images.npy")  # (N, H, W, 3) uint8
        self.masks = np.load(f"{DATA_DIR}/{split}_masks.npy")    # (N, H, W) uint8, values 0/1

    def __len__(self):
        return len(self.images)

    def __getitem__(self, i):
        img = self.images[i].astype(np.float32) / 255.0
        img = torch.from_numpy(img).permute(2, 0, 1)  # -> (3, H, W)
        mask = torch.from_numpy(self.masks[i].astype(np.int64))
        return img, mask


def compute_iou(pred, target, num_classes):
    ious = []
    pred = pred.view(-1)
    target = target.view(-1)
    for c in range(num_classes):
        pred_c = pred == c
        target_c = target == c
        intersection = (pred_c & target_c).sum().item()
        union = (pred_c | target_c).sum().item()
        ious.append(float("nan") if union == 0 else intersection / union)
    return ious


def evaluate(model, loader):
    model.eval()
    all_ious = []
    with torch.no_grad():
        for imgs, masks in loader:
            imgs, masks = imgs.to(DEVICE), masks.to(DEVICE)
            logits = model(imgs)
            preds = torch.argmax(logits, dim=1)
            all_ious.append(compute_iou(preds, masks, NUM_CLASSES))
    return np.nanmean(np.array(all_ious), axis=0)


def main():
    train_ds = SlickDataset("train")
    val_ds = SlickDataset("val")
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)

    print(f"Train: {len(train_ds)} images | Val: {len(val_ds)} images | Device: {DEVICE}")

    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights="imagenet",
        in_channels=3,
        classes=NUM_CLASSES,
    ).to(DEVICE)

    criterion = nn.CrossEntropyLoss(weight=CLASS_WEIGHTS.to(DEVICE))
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    best_oil_iou = -1.0
    ious = [float("nan")] * NUM_CLASSES
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss = 0.0
        for imgs, masks in train_loader:
            imgs, masks = imgs.to(DEVICE), masks.to(DEVICE)
            optimizer.zero_grad()
            logits = model(imgs)
            loss = criterion(logits, masks)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * imgs.size(0)

        avg_loss = total_loss / len(train_ds)
        ious = evaluate(model, val_loader)
        oil_iou = ious[1]

        print(f"Epoch {epoch:2d}/{EPOCHS} | loss {avg_loss:.4f} | "
              f"mean IoU {np.nanmean(ious):.3f} | OIL SPILL IoU {oil_iou:.3f}")

        if oil_iou > best_oil_iou:
            best_oil_iou = oil_iou
            torch.save(model.state_dict(), "data/processed/best_unet.pt")
            print(f"  -> new best oil-spill IoU ({oil_iou:.3f}), checkpoint saved")

    print("\nFinal per-class IoU:")
    for name, iou in zip(CLASS_NAMES, ious):
        print(f"  {name:12s}: {iou:.3f}")
    print(f"\nBest Oil Spill IoU achieved: {best_oil_iou:.3f}")
    print("Checkpoint: data/processed/best_unet.pt")
    print("\nNext step -> pass this checkpoint's predicted mask into the "
          "linear-vs-blob shape classifier (your Aug 24 task). Since this "
          "dataset has no look-alike label, the shape classifier now carries "
          "more weight for cutting false positives than originally planned.")


if __name__ == "__main__":
    main()