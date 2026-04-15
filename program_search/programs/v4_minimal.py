"""Refactoring combining v1's dead-code pruning with v3's short-circuit form.

No helper variables - we go straight from feature access to return. This
maximises compactness at the cost of the human-readable predicate names
introduced in v2. Useful as a data point on the readability/compactness
trade-off.
"""


def predict(f):
    if f["worst perimeter"] <= 106.0999984741211:
        return int(f["worst concave points"] <= 0.15839999914169312)
    if f["mean concave points"] <= 0.048864999786019325:
        return int(f["worst texture"] <= 26.02999973297119)
    return int(
        f["worst texture"] <= 20.645000457763672
        and f["mean concavity"] <= 0.156700000166893
    )
