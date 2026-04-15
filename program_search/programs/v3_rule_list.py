"""Refactoring of v2 - short-circuit rule list.

We lean on `int(bool)` = 0/1, which happens to match our class labels
(0 malignant, 1 benign). Each stage of the cascade then collapses to a
single return statement instead of a nested if/else.

Exact equivalence argument:
- If `small_tumor`: the tree's answer depended only on `worst_edges_smooth`.
- Else if `mean_edges_smooth`: the answer depended only on `texture_mild`.
- Else: benign iff BOTH `texture_very_mild` and `concavity_shallow`.

Same case split as v2, just expressed more compactly.
"""


def predict(f):
    small_tumor = f["worst perimeter"] <= 106.0999984741211
    worst_edges_smooth = f["worst concave points"] <= 0.15839999914169312
    mean_edges_smooth = f["mean concave points"] <= 0.048864999786019325
    texture_mild = f["worst texture"] <= 26.02999973297119
    texture_very_mild = f["worst texture"] <= 20.645000457763672
    concavity_shallow = f["mean concavity"] <= 0.156700000166893

    if small_tumor:
        return int(worst_edges_smooth)
    if mean_edges_smooth:
        return int(texture_mild)
    return int(texture_very_mild and concavity_shallow)
