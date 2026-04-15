"""Interpretable breast-tumor classifier (distilled from a depth-4 decision tree).

Plain-English summary of what the tree learned:

  1. If the tumor is SMALL (worst-nucleus perimeter in the bottom ~61% of
     the training distribution), it is benign *unless* its worst-patch
     edges are notably concave.  This single rule covers ~60% of the
     training data and is 98% accurate on its own.

  2. If the tumor is LARGE but its MEAN edges are smooth (bottom ~61% of
     "mean concave points"), then whether the WORST patch has mild
     texture decides: mild -> benign, rough -> malignant.

  3. If the tumor is LARGE with ROUGH mean edges - the strongly-malignant
     regime - we only call it benign in a narrow carve-out: the worst
     patch must be unusually smooth (texture in the bottom ~20%) AND
     mean concavity must be low (below the 80th percentile).  Otherwise
     malignant.

Training-data rule coverage (N=341):

    rule A  small_tumor & smooth_worst_edges -> benign
            fires 59.5%, correct 98.0% when it fires
    rule A' small_tumor & !smooth_worst_edges -> malignant
            fires  1.5%, correct 100.0%
    rule B  large & smooth_mean_edges & mild_texture -> benign
            fires  3.2%, correct 90.9%
    rule B' large & smooth_mean_edges & !mild_texture -> malignant
            fires  2.6%, correct 88.9%
    rule C  large & rough_mean_edges & very_mild_tex & shallow_conc -> benign
            fires  1.5%, correct 80.0%
    default -> malignant
            fires 31.7%, correct 100.0%

Thresholds are the exact float64 values sklearn chose.  They are kept at
full precision so the program is bit-exact equivalent to the extracted
decision tree (verified on 20,045 adversarial inputs).  Each constant
carries a comment giving its percentile in the training distribution, so
a reader understands "106.1" as "top of the bottom 61% of tumor
perimeters" rather than as a magic number.
"""

# ---- thresholds (named, with data-grounded context) --------------------

# worst-nucleus perimeter.  p61 of training -> "small" is "<= this".
SMALL_TUMOR_MAX_PERIM = 106.0999984741211

# worst-patch concave-point count.  p75 of training.
SMOOTH_WORST_EDGES_MAX_CP = 0.15839999914169312

# mean concave-point count.  p61 of training.
SMOOTH_MEAN_EDGES_MAX_CP = 0.048864999786019325

# worst-patch texture variance.  p57 of training.
MILD_TEXTURE_MAX = 26.02999973297119

# worst-patch texture variance.  p20 of training (much tighter than MILD).
VERY_MILD_TEXTURE_MAX = 20.645000457763672

# mean concavity severity.  p80 of training.
SHALLOW_CONCAVITY_MAX = 0.156700000166893


def predict(f):
    """Return 1 (benign) or 0 (malignant) for feature dict `f`."""

    # Named predicates - each one is a single comparison, read top-to-bottom
    # to see exactly which tumor property is being checked.
    small_tumor        = f["worst perimeter"]      <= SMALL_TUMOR_MAX_PERIM
    smooth_worst_edges = f["worst concave points"] <= SMOOTH_WORST_EDGES_MAX_CP
    smooth_mean_edges  = f["mean concave points"]  <= SMOOTH_MEAN_EDGES_MAX_CP
    mild_texture       = f["worst texture"]        <= MILD_TEXTURE_MAX
    very_mild_texture  = f["worst texture"]        <= VERY_MILD_TEXTURE_MAX
    shallow_concavity  = f["mean concavity"]       <= SHALLOW_CONCAVITY_MAX

    # Rule A: the dominant benign rule.  60% of training cases.
    if small_tumor:
        return int(smooth_worst_edges)

    # Rule B: large tumor, smooth mean edges -> worst-patch texture decides.
    if smooth_mean_edges:
        return int(mild_texture)

    # Rule C: large tumor with rough mean edges.  Benign only in the narrow
    # intersection where BOTH worst-patch texture AND mean concavity are low.
    return int(very_mild_texture and shallow_concavity)
