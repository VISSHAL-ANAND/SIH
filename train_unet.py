"""
SIH26143 - Slick Detection: Baseline U-Net Training
Owner: VISSHAL
Task: Train baseline U-Net slick segmentation model

IMPORTANT for the 3-day timeline: this uses a PRETRAINED encoder (ResNet34 on
ImageNet) via segmentation_models_pytorch, not a from-scratch U-Net. Training
a segmentation model from random weights in a few hours on a small dataset
will not converge to anything usable. Transfer learning gets you a working
model in ~30-60 min of GPU time instead of a full day+.

Install first:
    pip install segmentation-models-pytorch torch torchvision --break-system-packages

Class imbalance warning: "Oil Spill" pixels will be a small minority of the
image (most of a SAR frame is just open sea). Plain pixel-accuracy will look
great even if the model just predicts "background" everywhere. That's why
this script:
  - uses a class-weighted loss (weight oil_spill higher)
  - reports per-class IoU, not just accuracy
  - reports Oil Spill IoU specifically as the number that actually matters
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import segmentation_models_pytorch as smp

# ---- CONFIG ----------------------------------------------------------------
DATA_DIR = "../data/processed"
NUM_CLASSES = 5
CLASS_NAMES = ["background", "oil_spill", "look_alike", "ship", "land"]
BATCH_SIZE = 8
EPOCHS = 15          # transfer learning converges fast; raise if you have time left
LR = 1e-4
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Loss weights: push the model to care about oil_spill and look_alike (the
# classes that matter for this problem) more than background/land/ship.
CLASS_WEIGHTS = torch.tensor([0.3, 3.0, 2.0, 1.0, 0.5])


class SlickDataset(Dataset):
    def __init__(self, split: str):
        self.images = np.load(f"{DATA_DIR}/{split}_images.npy")  # (N, H, W, 3) uint8
        self.masks = np.load(f"{DATA_DIR}/{split}_masks.npy")    # (N, H, W) uint8

    def __len__(self):
        return len(self.images)

    def __getitem__(self, i):
        img = self.images[i].astype(np.float32) / 255.0
        img = torch.from_numpy(img).permute(2, 0, 1)  # -> (3, H, W)
        mask = torch.from_numpy(self.masks[i].astype(np.int64))
        return img, mask


def compute_iou(pred, target, num_classes):
    """Per-class IoU for one batch. Returns array of length num_classes (NaN where class absent)."""
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
    mean_ious = np.nanmean(np.array(all_ious), axis=0)
    return mean_ious


def main():
    train_ds = SlickDataset("train")
    val_ds = SlickDataset("val")
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)

    print(f"Train: {len(train_ds)} images | Val: {len(val_ds)} images | Device: {DEVICE}")

    # Pretrained ResNet34 encoder, U-Net decoder. This is the transfer-learning
    # move that makes this feasible in a 3-day sprint.
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights="imagenet",
        in_channels=3,
        classes=NUM_CLASSES,
    ).to(DEVICE)

    criterion = nn.CrossEntropyLoss(weight=CLASS_WEIGHTS.to(DEVICE))
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    best_oil_iou = -1.0
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
        oil_iou = ious[1]  # index 1 = oil_spill

        print(f"Epoch {epoch:2d}/{EPOCHS} | loss {avg_loss:.4f} | "
              f"mean IoU {np.nanmean(ious):.3f} | OIL SPILL IoU {oil_iou:.3f}")

        if oil_iou > best_oil_iou:
            best_oil_iou = oil_iou
            torch.save(model.state_dict(), "../data/processed/best_unet.pt")
            print(f"  -> new best oil-spill IoU ({oil_iou:.3f}), checkpoint saved")

    print("\nFinal per-class IoU:")
    for name, iou in zip(CLASS_NAMES, ious):
        print(f"  {name:12s}: {iou:.3f}")
    print(f"\nBest Oil Spill IoU achieved: {best_oil_iou:.3f}")
    print("Checkpoint: ../data/processed/best_unet.pt")
    print("\nNext step -> pass this checkpoint's predicted mask into the "
          "linear-vs-blob shape classifier (your Aug 24 task).")


if __name__ == "__main__":
    main()
