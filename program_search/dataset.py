"""Loads the Wisconsin Breast Cancer dataset and provides train/test/probe splits.

We pick this dataset because:
- 30 continuous features (enough complexity for a non-trivial tree).
- Binary classification (malignant=0, benign=1) with a clear human meaning.
- Built into sklearn, so the experiment is reproducible offline.

The "probe" split is a large set of points used to measure equivalence of
candidate programs against a reference model. It is disjoint from train/test.
"""

from __future__ import annotations

import numpy as np
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split


def load(seed: int = 0):
    data = load_breast_cancer()
    X, y = data.data, data.target
    feature_names = list(data.feature_names)
    target_names = list(data.target_names)  # ['malignant', 'benign']

    X_train, X_rest, y_train, y_rest = train_test_split(
        X, y, test_size=0.40, random_state=seed, stratify=y
    )
    X_test, X_probe, y_test, y_probe = train_test_split(
        X_rest, y_rest, test_size=0.50, random_state=seed, stratify=y_rest
    )
    return {
        "X_train": X_train, "y_train": y_train,
        "X_test": X_test, "y_test": y_test,
        "X_probe": X_probe, "y_probe": y_probe,
        "feature_names": feature_names,
        "target_names": target_names,
    }


def feature_slug(name: str) -> str:
    """Make a feature name into a safe Python identifier."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


if __name__ == "__main__":
    d = load()
    print("train", d["X_train"].shape, "test", d["X_test"].shape, "probe", d["X_probe"].shape)
    print("class balance train:", np.bincount(d["y_train"]))
    print("first 5 features:", d["feature_names"][:5])
