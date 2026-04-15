"""Fit the reference interpretable model and emit programs/v0_tree.py.

We use a DecisionTreeClassifier with a moderate depth so the extracted program
is neither trivial (one split) nor unwieldy (hundreds of leaves). max_depth=4
and min_samples_leaf=10 tend to give ~8-12 leaves on this dataset.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeClassifier

from dataset import load
from score import load_predict, predict_many
from tree_to_program import tree_to_source


HERE = Path(__file__).parent


def main():
    d = load(seed=0)
    clf = DecisionTreeClassifier(
        max_depth=5, min_samples_leaf=5, random_state=0
    )
    clf.fit(d["X_train"], d["y_train"])

    acc_train = clf.score(d["X_train"], d["y_train"])
    acc_test = clf.score(d["X_test"], d["y_test"])
    print(f"reference tree: train acc={acc_train:.4f}  test acc={acc_test:.4f}")
    print(f"reference tree: n_leaves={clf.get_n_leaves()}  depth={clf.get_depth()}")

    source = tree_to_source(clf, d["feature_names"])
    out = HERE / "programs" / "v0_tree.py"
    out.write_text(source)
    print(f"wrote {out}  ({len(source.splitlines())} lines)")

    # Oracle for equivalence checks is the emitted program v0_tree.py,
    # not the sklearn object. See adversarial_probe.py for the reasoning.
    v0_predict = load_predict(out)
    probe_preds = predict_many(v0_predict, d["X_probe"], d["feature_names"])
    np.save(HERE / "runs" / "reference_probe_preds.npy", probe_preds)
    np.save(HERE / "runs" / "X_probe.npy", d["X_probe"])
    np.save(HERE / "runs" / "y_probe.npy", d["y_probe"])
    np.save(HERE / "runs" / "X_test.npy", d["X_test"])
    np.save(HERE / "runs" / "y_test.npy", d["y_test"])
    with open(HERE / "runs" / "feature_names.txt", "w") as f:
        for name in d["feature_names"]:
            f.write(name + "\n")
    print(f"wrote reference probe predictions ({len(probe_preds)} rows)")


if __name__ == "__main__":
    main()
