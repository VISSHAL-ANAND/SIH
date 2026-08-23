# Slick Detection — VISSHAL's Track (SIH26143)

Hey — this is your corner of the oil-spill project: finding the actual slick
in a SAR image before anyone can figure out who caused it. Everything below
is set up so you can just run it, not go hunting for what's missing.

## Install this first
```bash
pip install segmentation-models-pytorch torch torchvision numpy pillow --break-system-packages
```
You'll also want a GPU if you can get one (Colab's free T4 is fine). CPU
works too, just slower — see the note in step 2 below.

---

## What's done vs. what's left

| File | Where it stands | Built |
|---|---|---|
| `src/preprocess.py` | Ready — just point it at the dataset | 2026-08-23 18:21 UTC |
| `src/train_unet.py` | Ready — run it after preprocessing | 2026-08-23 18:21 UTC |
| `data/processed/best_unet.pt` | Doesn't exist yet — this is what running the scripts produces | not yet |

---

## Step 1 — Get the dataset

We're using the **MKLab Oil Spill Detection Dataset** on Zenodo. It's the one
most teams working this exact problem end up using, because it's the only
public dataset that separates a real "Oil Spill" from a "Look-alike" — which
matters a lot, since look-alikes are the main source of false positives in
this kind of project.

1. Grab it here: https://zenodo.org/records/6552722 (free account, few GB — Zenodo doesn't allow scripted bulk downloads, so this part's manual)
2. Unzip it into `data/raw/` so it looks like this:
   ```
   data/raw/train/images/*.jpg
   data/raw/train/labels/*.png
   data/raw/test/images/*.jpg
   data/raw/test/labels/*.png
   ```
3. Run the preprocessing script:
   ```bash
   cd src
   python preprocess.py
   ```
   This resizes everything, turns the color masks into class-index masks, and
   splits it into train/val/test as `.npy` files.

   **One thing to actually look at:** the script prints out how many pixels
   belong to each class. If "oil_spill" is only 2-3% of all pixels, that's a
   real imbalance problem worth flagging to the team — not something to just
   shrug off.

## Step 2 — Train the baseline model

```bash
cd src
python train_unet.py
```

This isn't training from scratch — it uses a ResNet34 encoder that's already
pretrained on ImageNet, and just fine-tunes it for our classes. Given we've
got 3 days, not 3 weeks, training from zero simply wouldn't converge to
anything usable in time. This will.

On a GPU, expect well under an hour for 15 epochs. Stuck on CPU only? Drop
`EPOCHS` down to 5-8 in the script just to get a working checkpoint today,
then re-run it properly once someone gets you GPU time.

**Watch "Oil Spill IoU" in the console, not the accuracy number.** Accuracy
will look great even if the model just learns to predict "background"
everywhere, because most of any SAR frame genuinely is open sea. Oil Spill
IoU is the number that tells you if it's actually working.

---

## Where this feeds into tomorrow

Once you've got `data/processed/best_unet.pt`, that's the input for your Aug
24 task — the linear-vs-blob shape classifier. A **linear** slick shape
usually means a moving vessel discharge (which is a real lead for
RINOSH/ASHMIL's suspect-matching work); a **blob** shape usually means a
static leak, less tied to one passing ship. So today's work isn't just a
box to check — it's what tomorrow's differentiation piece actually runs on.

## If you get stuck today

- Zenodo download being annoying → ask around, someone on the team may
  already have it downloaded.
- No GPU → Colab's free tier handles this dataset size fine. Just upload
  the `.npy` files from `data/processed/` and run `train_unet.py` there.