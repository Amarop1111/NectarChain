"""Explainable baseline AI models for the Honey Chain prototype.

Disease-risk prediction is a deterministic sensor model because real KVIC
labelled hive-health data is not available in the prototype. Yield prediction
uses a small scikit-learn regression model trained on synthetic samples.
The interfaces are deliberately simple so real field data can replace the
synthetic training data later.
"""

from __future__ import annotations

import random

try:
    import numpy as np
    from sklearn.linear_model import LinearRegression
except Exception:  # graceful fallback when dependencies have not been installed yet
    np = None
    LinearRegression = None


def predict_disease_risk_from_readings(temperature: float, humidity: float, weight: float) -> str:
    risk_score = 0
    if temperature < 32 or temperature > 37:
        risk_score += 1
    if humidity < 40 or humidity > 65:
        risk_score += 1
    if weight < 22:
        risk_score += 1
    if risk_score >= 3:
        return "high"
    if risk_score >= 1:
        return "medium"
    return "low"


def _synthetic_training_data(n: int = 300, seed: int = 42):
    rng = random.Random(seed)
    rows, targets = [], []
    for _ in range(n):
        temp = rng.uniform(32, 37)
        humidity = rng.uniform(42, 65)
        pre_harvest_weight = rng.uniform(22, 45)
        yield_kg = (
            0.28 * pre_harvest_weight
            + 0.55 * max(0, 1 - abs(temp - 34.5) / 4)
            + 0.35 * max(0, 1 - abs(humidity - 55) / 20)
            + rng.uniform(-0.7, 0.7)
        )
        rows.append([temp, humidity, pre_harvest_weight])
        targets.append(max(2.5, yield_kg))
    return np.array(rows), np.array(targets)


if LinearRegression is not None:
    _X, _y = _synthetic_training_data()
    _model = LinearRegression().fit(_X, _y)
else:
    _model = None


def predict_productivity(temperature: float, humidity: float, weight: float) -> float:
    """Predict expected harvest quantity in kg from synthetic baseline model."""
    if _model is None:
        # Fallback keeps the prototype usable even before pip install completes.
        value = 0.28 * weight + 0.55 * max(0, 1 - abs(temperature - 34.5) / 4) + 0.35 * max(0, 1 - abs(humidity - 55) / 20)
        return round(max(2.5, value), 2)
    pred = float(_model.predict(np.array([[temperature, humidity, weight]], dtype=float))[0])
    return round(max(2.5, pred), 2)
