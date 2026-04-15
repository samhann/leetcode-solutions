"""Build a large + adversarial probe set for equivalence testing.

Step (4) in the plan: 'exhaustive cases if feasible, otherwise a very large
validation set plus adversarial edge cases'. The feature space is continuous
in 30 dimensions so exhaustive is impossible, but we can:

1. Draw ~20k uniformly random points inside a slightly-widened feature
   bounding box. This gives broad coverage of the input distribution.
2. Add adversarial points that sit right at, just below, and just above
   every threshold appearing in the reference tree. These probe the
   `<=` boundary behaviour where floating-point drift would bite first.

We then check bit-exact agreement between every candidate program and the
reference tree on the union.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeClassifier

from dataset import load
from score import load_predict, predict_many
from tree_to_program import tree_to_source


HERE = Path(__file__).parent


def adversarial_points(
    X_base: np.ndarray,
    tree: DecisionTreeClassifier,
    feature_names,
    n_random: int = 20_000,
    epsilon: float = 1e-9,
    seed: int = 1,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    lo = X_base.min(axis=0)
    hi = X_base.max(axis=0)
    span = hi - lo
    # Widen box by 5% on each side so we also cover near-boundary extrapolation.
    lo_ext = lo - 0.05 * span
    hi_ext = hi + 0.05 * span
    random_pts = rng.uniform(lo_ext, hi_ext, size=(n_random, X_base.shape[1]))

    # Adversarial: for every (feature, threshold) in the tree, create a point
    # whose that-feature value is threshold, threshold+eps, threshold-eps, and
    # whose other features are the mean of the training data.
    mean = X_base.mean(axis=0)
    t = tree.tree_
    feats = t.feature
    thr = t.threshold
    adv = []
    for node in range(t.node_count):
        if feats[node] == -2:  # leaf (sklearn uses -2 for TREE_UNDEFINED)
            continue
        j = feats[node]
        v = thr[node]
        for offset in (0.0, +epsilon, -epsilon, +1e-6, -1e-6):
            pt = mean.copy()
            pt[j] = v + offset
            adv.append(pt)
    adv = np.asarray(adv)
    return np.vstack([random_pts, adv])


def main():
    d = load(seed=0)
    clf = DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=0)
    clf.fit(d["X_train"], d["y_train"])

    X_all = np.vstack([d["X_train"], d["X_test"], d["X_probe"]])
    X_adv = adversarial_points(X_all, clf, d["feature_names"])

    # The equivalence oracle is v0_tree.py (the canonical program), NOT the
    # sklearn tree object. sklearn does threshold comparisons in float32
    # while our programs use float64 - a property of the sklearn runtime,
    # not a property of the extracted program. Equivalence means "the
    # rewrite behaves the same as v0_tree", which is the property we care
    # about in a search-and-check loop.
    v0_predict = load_predict(HERE / "programs" / "v0_tree.py")
    y_adv = predict_many(v0_predict, X_adv, d["feature_names"])

    print(f"adversarial probe: {X_adv.shape[0]} rows (oracle: v0_tree.py)")
    np.save(HERE / "runs" / "X_adv.npy", X_adv)
    np.save(HERE / "runs" / "reference_adv_preds.npy", y_adv)


if __name__ == "__main__":
    main()
