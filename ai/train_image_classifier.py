"""
Honey Chain -- train the real Varroa mite image classifier.

RUN THIS ONCE PERSON 5 HAS REAL LABELED IMAGES.

Expected folder layout (create these folders and drop images in):

    ai/data/mite/       <- photos showing visible Varroa mites
    ai/data/no_mite/     <- clean/healthy bee or comb photos

Good sources for real images include reputable public research/dataset
repositories. Use only datasets whose licenses permit your intended use.
A few hundred labelled images per class can be a starting point for a
prototype, but validation with field data is still required.

Usage:
    python train_image_classifier.py

This produces ai/varroa_model.keras. Once that file exists,
predict_disease_risk_from_image() in image_classifier.py automatically
starts using it instead of the pixel heuristic -- no other code changes
needed anywhere else in the app.
"""

import os
from image_classifier import build_model, IMG_SIZE, MODEL_PATH

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    try:
        from tensorflow import keras
    except ImportError as exc:
        print("TensorFlow is optional for the core prototype.")
        print("Install requirements-ml.txt in a Python 3.11/3.12 environment to train the CNN.")
        print(f"Details: {exc}")
        return

    mite_dir = os.path.join(DATA_DIR, "mite")
    no_mite_dir = os.path.join(DATA_DIR, "no_mite")

    if not (os.path.isdir(mite_dir) and os.path.isdir(no_mite_dir)):
        print("No training data found.")
        print(f"Create these folders and add images before running this script:")
        print(f"  {mite_dir}")
        print(f"  {no_mite_dir}")
        print("\nTip: run generate_demo_dataset.py first if you just want to")
        print("prove the training pipeline works end-to-end before your real")
        print("dataset is ready -- it creates small synthetic placeholder")
        print("images so this script has something to train on.")
        return

    train_ds = keras.utils.image_dataset_from_directory(
        DATA_DIR,
        labels="inferred",
        label_mode="binary",
        class_names=["no_mite", "mite"],
        image_size=IMG_SIZE,
        batch_size=16,
        validation_split=0.2,
        subset="training",
        seed=42,
    )
    val_ds = keras.utils.image_dataset_from_directory(
        DATA_DIR,
        labels="inferred",
        label_mode="binary",
        class_names=["no_mite", "mite"],
        image_size=IMG_SIZE,
        batch_size=16,
        validation_split=0.2,
        subset="validation",
        seed=42,
    )

    model = build_model()
    print(model.summary())

    model.fit(train_ds, validation_data=val_ds, epochs=10)
    model.save(MODEL_PATH)
    print(f"\nSaved trained model to {MODEL_PATH}")
    print("The backend will now automatically use this trained model for")
    print("disease detection instead of the pixel heuristic.")


if __name__ == "__main__":
    main()
