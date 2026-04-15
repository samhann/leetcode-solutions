"""Convert a fitted sklearn DecisionTreeClassifier into a canonical Python program.

Canonical form:

    def predict(f):
        if f["mean concave points"] <= 0.05:
            if f["worst radius"] <= 16.83:
                return 1  # benign
            else:
                return 0  # malignant
        else:
            ...

We keep the form deliberately constrained: nested if/else, leaf returns
literal class labels, comparisons are <= against a constant. This is easy
to verify and to refactor.
"""

from __future__ import annotations

from typing import List

from sklearn.tree import DecisionTreeClassifier


HEADER = '''"""Auto-generated from a sklearn DecisionTreeClassifier.

Each branch is a `<= threshold` comparison on a single feature.
Leaves return 0 (malignant) or 1 (benign).
"""


def predict(f):
'''


def tree_to_source(clf: DecisionTreeClassifier, feature_names: List[str]) -> str:
    tree = clf.tree_
    feat_idx = tree.feature
    thresh = tree.threshold
    left = tree.children_left
    right = tree.children_right
    value = tree.value  # shape (n_nodes, 1, n_classes)

    lines: List[str] = []

    def walk(node: int, depth: int) -> None:
        indent = "    " * (depth + 1)
        if left[node] == -1:  # leaf
            counts = value[node][0]
            label = int(counts.argmax())
            comment = "benign" if label == 1 else "malignant"
            lines.append(f"{indent}return {label}  # {comment}")
            return
        fname = feature_names[feat_idx[node]]
        t = thresh[node]
        # Use repr() so the printed threshold round-trips to the exact
        # float sklearn stored. `{:.6f}` drops precision and causes
        # boundary disagreements on adversarial inputs within ~1e-7 of a split.
        lines.append(f'{indent}if f["{fname}"] <= {float(t)!r}:')
        walk(left[node], depth + 1)
        lines.append(f"{indent}else:")
        walk(right[node], depth + 1)

    walk(0, 0)
    return HEADER + "\n".join(lines) + "\n"
