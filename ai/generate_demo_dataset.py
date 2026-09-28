"""
Nectar Chain -- generate a tiny SYNTHETIC placeholder image dataset.

This is NOT real training data and will NOT produce a classifier that
detects real Varroa mites. Its only purpose is to let you run
train_image_classifier.py right now and confirm the whole pipeline
(folders -> training -> saved model -> automatic pickup by the app)
actually works end-to-end, before Person 5's real dataset is ready.

Once real images are in ai/data/mite/ and ai/data/no_mite/, delete this
synthetic data (or just overwrite it) and retrain for a real result.

Usage:
    python generate_demo_dataset.py
"""

import os
import random
from PIL import Image, ImageDraw

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
IMG_SIZE = (96, 96)
N_PER_CLASS = 60


def make_no_mite_image():
    """Plain honey-comb-ish background: warm gradient, no dark speckles."""
    img = Image.new("RGB", IMG_SIZE, (0, 0, 0))
    base = random.randint(180, 230)
    for y in range(IMG_SIZE[1]):
        shade = base - int(20 * y / IMG_SIZE[1])
        for x in range(IMG_SIZE[0]):
            img.putpixel((x, y), (shade, shade - 30, shade - 90))
    return img


def make_mite_image():
    """Same background, plus a few small dark oval speckles standing in
    for mites -- exactly the pattern the pixel heuristic looks for."""
    img = make_no_mite_image()
    draw = ImageDraw.Draw(img)
    n_spots = random.randint(2, 5)
    for _ in range(n_spots):
        cx = random.randint(10, IMG_SIZE[0] - 10)
        cy = random.randint(10, IMG_SIZE[1] - 10)
        r = random.randint(2, 4)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 20, 15))
    return img


def main():
    mite_dir = os.path.join(DATA_DIR, "mite")
    no_mite_dir = os.path.join(DATA_DIR, "no_mite")
    os.makedirs(mite_dir, exist_ok=True)
    os.makedirs(no_mite_dir, exist_ok=True)

    for i in range(N_PER_CLASS):
        make_no_mite_image().save(os.path.join(no_mite_dir, f"synthetic_{i:03d}.png"))
        make_mite_image().save(os.path.join(mite_dir, f"synthetic_{i:03d}.png"))

    print(f"Generated {N_PER_CLASS} synthetic images per class in:")
    print(f"  {mite_dir}")
    print(f"  {no_mite_dir}")
    print("\nThis is placeholder data ONLY, for proving the pipeline works.")
    print("Run train_image_classifier.py next, then replace with real")
    print("images before the actual demo.")


if __name__ == "__main__":
    main()
