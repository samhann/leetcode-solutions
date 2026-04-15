"""Run the adversarial-probe equivalence check on every program in programs/.

Report fidelity on the held-out probe AND on the 20k+ adversarial probe.
A rewrite that disagrees on *any* adversarial point is flagged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from score import load_predict, predict_many

HERE = Path(__file__).parent


def main(argv):
    X_probe = np.load(HERE / "runs" / "X_probe.npy")
    ref_probe = np.load(HERE / "runs" / "reference_probe_preds.npy")
    X_adv = np.load(HERE / "runs" / "X_adv.npy")
    ref_adv = np.load(HERE / "runs" / "reference_adv_preds.npy")
    feature_names = (HERE / "runs" / "feature_names.txt").read_text().splitlines()

    programs_dir = HERE / "programs"
    paths = [programs_dir / f"{name}.py" for name in argv] if argv else sorted(programs_dir.glob("*.py"))

    print(f"probe: {len(X_probe)} real rows, adversarial: {len(X_adv)} rows\n")
    for path in paths:
        predict = load_predict(path)
        preds_probe = predict_many(predict, X_probe, feature_names)
        preds_adv = predict_many(predict, X_adv, feature_names)
        fid_probe = (preds_probe == ref_probe).mean()
        fid_adv = (preds_adv == ref_adv).mean()
        mismatches_adv = int((preds_adv != ref_adv).sum())
        status = "EQUIV" if fid_probe == 1.0 and fid_adv == 1.0 else "DIFFERS"
        print(f"{path.stem:<22} {status}  probe={fid_probe:.6f}  adv={fid_adv:.6f}  adv_diff={mismatches_adv}")


if __name__ == "__main__":
    main(sys.argv[1:])
