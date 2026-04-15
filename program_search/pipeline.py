"""End-to-end runner: score every program in programs/ against the reference.

Usage:
    python3 pipeline.py                # score all
    python3 pipeline.py v0_tree v1_dead_code_removed   # score a subset

For each program we report:
    accuracy on the test set,
    fidelity (agreement rate with the reference tree) on the probe set,
    AST node count, source line count,
    and a joint score = fidelity - 0.002 * ast_nodes.

A rewrite is "accepted" iff:
    fidelity >= 1.0 (bit-exact on probe)  AND  joint > joint(v0_tree)

This enforces the invariant that we never pay for complexity reduction with a
behavioural change. In practice this is the cheap, strong version of step (4)
in the plan: we check equivalence bit-exactly on a large held-out probe set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from score import score_program, score_to_dict

HERE = Path(__file__).parent


def main(argv):
    X_probe = np.load(HERE / "runs" / "X_probe.npy")
    X_test = np.load(HERE / "runs" / "X_test.npy")
    y_test = np.load(HERE / "runs" / "y_test.npy")
    ref_probe = np.load(HERE / "runs" / "reference_probe_preds.npy")
    feature_names = (HERE / "runs" / "feature_names.txt").read_text().splitlines()

    programs_dir = HERE / "programs"
    if argv:
        paths = [programs_dir / f"{name}.py" for name in argv]
    else:
        paths = sorted(programs_dir.glob("*.py"))

    scores = []
    for path in paths:
        s = score_program(
            path, X_test, y_test, ref_probe, X_probe, feature_names
        )
        scores.append(s)
        print(s.pretty())

    # baseline
    base = next((s for s in scores if s.name == "v0_tree"), None)
    if base is not None:
        print()
        print("acceptance (fidelity==1.0 AND joint > baseline joint):")
        for s in scores:
            if s.name == "v0_tree":
                print(f"  {s.name:<20} BASELINE")
                continue
            ok = s.fidelity_probe >= 1.0 and s.joint > base.joint
            delta = s.joint - base.joint
            print(f"  {s.name:<20} {'ACCEPT' if ok else 'REJECT'}  "
                  f"fid={s.fidelity_probe:.4f} delta_joint={delta:+.4f}")

    out = HERE / "runs" / "scores.json"
    out.write_text(json.dumps([score_to_dict(s) for s in scores], indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
