"""Optional image-based supplementary disease signal.

The default prototype uses an explainable pixel heuristic so the feature works
without a TensorFlow installation. A trained Keras model can be dropped in at
ai/varroa_model.keras and will be used automatically when TensorFlow is
available. The image result is supplementary; it must not be described as a
laboratory diagnosis.
"""

from __future__ import annotations

import os
import numpy as np
from PIL import Image

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "varroa_model.keras")
IMG_SIZE = (96, 96)
_cached_model = None
_model_attempted = False


def _risk(score: float) -> str:
    if score >= 0.60:
        return "high"
    if score >= 0.30:
        return "medium"
    return "low"


def _load_model():
    global _cached_model, _model_attempted
    if _model_attempted:
        return _cached_model
    _model_attempted = True
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        from tensorflow import keras
        _cached_model = keras.models.load_model(MODEL_PATH)
    except Exception:
        _cached_model = None
    return _cached_model


def _heuristic(image_path: str) -> dict:
    img = Image.open(image_path).convert("L").resize(IMG_SIZE)
    arr = np.asarray(img, dtype=np.float32)
    mean = float(arr.mean())
    mask = arr < max(15, mean - 35)
    visited = np.zeros_like(mask, dtype=bool)
    sizes = []
    h, w = mask.shape
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            size = 0
            while stack:
                cy, cx = stack.pop()
                size += 1
                for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            sizes.append(size)
    candidate = [s for s in sizes if 2 <= s <= 40]
    score = round(min(1.0, len(candidate) / 8.0) * 0.6 + min(1.0, sum(candidate) / (IMG_SIZE[0]*IMG_SIZE[1]*0.05)) * 0.4, 3)
    return {"risk": _risk(score), "score": score, "candidate_clusters": len(candidate), "method": "pixel-heuristic", "label": "Varroa-associated visual risk screening (prototype signal)"}


def predict_disease_risk_from_image(image_path: str) -> dict:
    model = _load_model()
    if model is None:
        return _heuristic(image_path)
    img = Image.open(image_path).convert("RGB").resize(IMG_SIZE)
    arr = np.asarray(img, dtype=np.float32)[None, ...]
    score = float(model.predict(arr, verbose=0)[0][0])
    return {"risk": _risk(score), "score": round(score, 3), "method": "trained-cnn", "label": "Varroa-associated visual risk screening"}
