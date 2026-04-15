"""Compute data-grounded annotations for a program.

Given the fitted tree, the training data, and the tree's thresholds, we
produce two kinds of annotations the refactored program can surface:

1. Threshold percentile: for each split `feature <= threshold`, where
   does `threshold` fall in the training distribution of that feature?
   A reader gets "this is roughly the bottom 47%" instead of "106.1".

2. Per-leaf coverage and purity: for each leaf path, how many training
   samples end up there and what fraction are benign. A reader gets
   "this rule catches 57% of training data and is 98% benign when it
   fires" instead of having to guess which branches matter.

Run:
    python3 annotate.py
prints the annotations that v5 will hard-code as comments / docstring.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeClassifier

from dataset import load


HERE = Path(__file__).parent


def threshold_percentile(values: np.ndarray, threshold: float) -> float:
    """Return the percentile of `threshold` inside `values` (0-100)."""
    return float((values <= threshold).mean() * 100.0)


def leaf_paths(tree, feature_names):
    """Yield (path, leaf_class, leaf_sample_count, leaf_benign_fraction) per leaf.

    `path` is a list of (feature_name, op, threshold) tuples, with op in
    {"<=", ">"}. sklearn's tree_ attributes:
      children_left[node]  - id of left (true, <=) child, -1 if leaf
      children_right[node] - id of right (false, >)  child, -1 if leaf
      feature[node]        - feature index at this split node
      threshold[node]      - split threshold
      value[node][0]       - class *proportions* at this node (sklearn >=1.8)
      n_node_samples[node] - total training samples reaching this node
    """
    t = tree.tree_
    out = []

    def walk(node, path):
        if t.children_left[node] == -1:
            props = t.value[node][0]  # class proportions, sum to 1
            total = int(t.n_node_samples[node])
            benign_frac = float(props[1])
            label = int(props.argmax())
            out.append((list(path), label, total, benign_frac))
            return
        j = t.feature[node]
        v = float(t.threshold[node])
        fname = feature_names[j]
        path.append((fname, "<=", v))
        walk(t.children_left[node], path)
        path.pop()
        path.append((fname, ">", v))
        walk(t.children_right[node], path)
        path.pop()

    walk(0, [])
    return out


def rule_stats(X: np.ndarray, y: np.ndarray, fname_to_col, rule_fns):
    """For each (name, predicate_fn) rule, return (fires, correct_given_fires).

    `rule_fns` is a list of (name, fn, predicted_label) where
       fn(x_row_as_dict) -> bool        # whether this rule fires
       predicted_label in {0,1}         # what the rule predicts if it fires
    Rules are "first match wins" - we stop at the first firing rule per row.
    """
    N = len(X)
    counts = [(n, 0, 0) for (n, _, _) in rule_fns]
    counts = [list(t) for t in counts]  # mutable
    for i in range(N):
        row = {name: float(X[i, col]) for name, col in fname_to_col.items()}
        for k, (_name, fn, label) in enumerate(rule_fns):
            if fn(row):
                counts[k][1] += 1
                if y[i] == label:
                    counts[k][2] += 1
                break
    return counts


def main():
    d = load(seed=0)
    clf = DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=0)
    clf.fit(d["X_train"], d["y_train"])

    X_train = d["X_train"]
    y_train = d["y_train"]
    feature_names = d["feature_names"]

    # Collect (feature_name, threshold) uniquely across the tree, attach percentile.
    print("== threshold percentiles (training distribution) ==")
    seen = set()
    t = clf.tree_
    for node in range(t.node_count):
        if t.feature[node] == -2:  # leaf
            continue
        j = t.feature[node]
        thr = float(t.threshold[node])
        key = (feature_names[j], thr)
        if key in seen:
            continue
        seen.add(key)
        p = threshold_percentile(X_train[:, j], thr)
        n_total = len(X_train)
        n_below = int((X_train[:, j] <= thr).sum())
        print(f"  {feature_names[j]:<25} <= {thr:<22.6g}  "
              f"p={p:5.1f}%  ({n_below}/{n_total} train points below)")

    print()
    print("== leaf (rule) coverage on training data ==")
    N = len(X_train)
    for path, label, n, benign in leaf_paths(clf, feature_names):
        conds = " AND ".join(f'{fn} {op} {v:.6g}' for fn, op, v in path)
        kind = "benign" if label == 1 else "malignant"
        purity = benign if label == 1 else (1 - benign)
        print(f"  [{kind:<9}] n={n:3d} ({100*n/N:4.1f}% of train) "
              f"purity={100*purity:5.1f}%")
        print(f"             if {conds}")

    # ---- collapsed rule stats (the form v4/v5 use) ----
    print()
    print("== collapsed rule stats (v4/v5 cascade on training data) ==")
    fname_to_col = {n: i for i, n in enumerate(feature_names)}

    # Thresholds from the tree.
    T_perim = 106.0999984741211
    T_worst_cp = 0.15839999914169312
    T_mean_cp = 0.048864999786019325
    T_tex_mild = 26.02999973297119
    T_tex_very_mild = 20.645000457763672
    T_conc_shallow = 0.156700000166893

    rule_fns = [
        # (display name, fires_when, predicted_label_if_fires)
        # But our rules have conditional labels, so compute "A fires", then
        # the prediction is int(smooth_worst_edges). To keep the helper
        # simple we split into "A-benign fires" and "A-malignant fires".
        ("A1 small_tumor & smooth_worst_edges -> benign",
         lambda r: r["worst perimeter"] <= T_perim and r["worst concave points"] <= T_worst_cp,
         1),
        ("A2 small_tumor & NOT smooth_worst_edges -> malignant",
         lambda r: r["worst perimeter"] <= T_perim and r["worst concave points"] > T_worst_cp,
         0),
        ("B1 large & smooth_mean_edges & mild_texture -> benign",
         lambda r: r["worst perimeter"] > T_perim and r["mean concave points"] <= T_mean_cp and r["worst texture"] <= T_tex_mild,
         1),
        ("B2 large & smooth_mean_edges & NOT mild_texture -> malignant",
         lambda r: r["worst perimeter"] > T_perim and r["mean concave points"] <= T_mean_cp and r["worst texture"] > T_tex_mild,
         0),
        ("C1 large & rough_mean_edges & very_mild_tex & shallow_conc -> benign",
         lambda r: r["worst perimeter"] > T_perim and r["mean concave points"] > T_mean_cp and r["worst texture"] <= T_tex_very_mild and r["mean concavity"] <= T_conc_shallow,
         1),
        ("C2 everything else -> malignant",
         lambda r: True,  # catch-all
         0),
    ]

    for name, fires, corr in rule_stats(X_train, y_train, fname_to_col, rule_fns):
        frac_fires = fires / N * 100
        acc = (corr / fires * 100) if fires else 0.0
        print(f"  [{name}]")
        print(f"    fires on {fires:3d}/{N} train ({frac_fires:4.1f}%), "
              f"correct {corr:3d}/{fires} ({acc:5.1f}%)")


if __name__ == "__main__":
    main()
