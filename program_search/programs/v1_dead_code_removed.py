"""Refactoring of v0_tree.py - dead-branch elimination.

Transformations applied (each preserves exact semantics):
- collapse `if X <= t: return 1 else: return 1` to `return 1`.
- collapse nested checks on the same feature when the outer one already
  implied the answer on one side.

Specifically in v0:
    if worst concave points <= 0.158400:
        if worst concave points <= 0.134000:     # both inner branches end in 1
            if radius error <= 0.544050:
                return 1
            else:
                return 1
        else:
            return 1
    else:
        return 0
collapses to:
    if worst concave points <= 0.158400: return 1
    else: return 0

And in the other sub-tree:
    if worst texture <= 26.030000:
        if worst smoothness <= 0.125800:          # both inner branches end in 1
            return 1
        else:
            return 1
    else:
        return 0
collapses to:
    if worst texture <= 26.030000: return 1
    else: return 0
"""


def predict(f):
    if f["worst perimeter"] <= 106.0999984741211:
        if f["worst concave points"] <= 0.15839999914169312:
            return 1  # benign
        else:
            return 0  # malignant
    else:
        if f["mean concave points"] <= 0.048864999786019325:
            if f["worst texture"] <= 26.02999973297119:
                return 1  # benign
            else:
                return 0  # malignant
        else:
            if f["worst texture"] <= 20.645000457763672:
                if f["mean concavity"] <= 0.156700000166893:
                    return 1  # benign
                else:
                    return 0  # malignant
            else:
                return 0  # malignant
