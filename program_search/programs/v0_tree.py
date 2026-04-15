"""Auto-generated from a sklearn DecisionTreeClassifier.

Each branch is a `<= threshold` comparison on a single feature.
Leaves return 0 (malignant) or 1 (benign).
"""


def predict(f):
    if f["worst perimeter"] <= 106.0999984741211:
        if f["worst concave points"] <= 0.15839999914169312:
            if f["worst concave points"] <= 0.1339999958872795:
                if f["radius error"] <= 0.544050008058548:
                    return 1  # benign
                else:
                    return 1  # benign
            else:
                return 1  # benign
        else:
            return 0  # malignant
    else:
        if f["mean concave points"] <= 0.048864999786019325:
            if f["worst texture"] <= 26.02999973297119:
                if f["worst smoothness"] <= 0.1257999986410141:
                    return 1  # benign
                else:
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
