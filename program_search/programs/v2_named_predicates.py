"""Refactoring of v1 - introduce named boolean predicates.

Each predicate keeps the *exact* threshold from the decision tree (sklearn
thresholds are midpoints between adjacent sorted feature values, so rounding
can in principle disagree on data points that land exactly on the split).

The structural logic is the same cascade as v1. A human reader now gets:

    small_tumor, smooth_edges, ...

instead of raw dictionary lookups with 6-digit constants.
"""


def predict(f):
    small_tumor = f["worst perimeter"] <= 106.0999984741211
    worst_edges_smooth = f["worst concave points"] <= 0.15839999914169312
    mean_edges_smooth = f["mean concave points"] <= 0.048864999786019325
    texture_mild = f["worst texture"] <= 26.02999973297119
    texture_very_mild = f["worst texture"] <= 20.645000457763672
    concavity_shallow = f["mean concavity"] <= 0.156700000166893

    if small_tumor:
        return 1 if worst_edges_smooth else 0
    # large tumor, but if mean edges are smooth, texture alone decides
    if mean_edges_smooth:
        return 1 if texture_mild else 0
    # large tumor with rough mean edges - benign only if texture is
    # very mild AND concavity is shallow
    if texture_very_mild and concavity_shallow:
        return 1
    return 0
