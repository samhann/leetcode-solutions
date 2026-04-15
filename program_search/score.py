"""Score a candidate `predict(f)` program on the joint objective.

Components:
- fidelity: agreement with the reference model on the probe set (large, held-out).
- accuracy: accuracy of the program on the test set (ground truth).
- complexity: number of AST nodes and number of source lines.
- readability: light proxy - unique identifier count, average line length.

Joint score (higher is better):
    score = fidelity - 0.002 * ast_nodes

Fidelity is the dominant term; we accept complexity reductions only when they
do not drop fidelity below the reference model's own test accuracy within a
small epsilon.
"""

from __future__ import annotations

import ast
import importlib.util
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Sequence

import numpy as np


def load_predict(path: Path) -> Callable:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.predict


def predict_many(predict: Callable, X: np.ndarray, feature_names: Sequence[str]) -> np.ndarray:
    out = np.empty(len(X), dtype=int)
    for i, row in enumerate(X):
        f = {name: float(v) for name, v in zip(feature_names, row)}
        out[i] = int(predict(f))
    return out


@dataclass
class Score:
    name: str
    accuracy_test: float
    fidelity_probe: float
    ast_nodes: int
    source_lines: int
    unique_identifiers: int
    avg_line_len: float
    joint: float

    def pretty(self) -> str:
        return (
            f"{self.name:<20} acc={self.accuracy_test:.4f} fid={self.fidelity_probe:.4f} "
            f"ast={self.ast_nodes:<4} loc={self.source_lines:<4} "
            f"ids={self.unique_identifiers:<3} joint={self.joint:+.4f}"
        )


def _count_ast_nodes(source: str) -> int:
    tree = ast.parse(source)
    return sum(1 for _ in ast.walk(tree))


def _count_identifiers(source: str) -> int:
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
            names.update(a.arg for a in node.args.args)
    return len(names)


def score_program(
    path: Path,
    X_test: np.ndarray,
    y_test: np.ndarray,
    reference_probe_preds: np.ndarray,
    X_probe: np.ndarray,
    feature_names: Sequence[str],
    *,
    ast_weight: float = 0.002,
) -> Score:
    source = path.read_text()
    predict = load_predict(path)

    preds_test = predict_many(predict, X_test, feature_names)
    preds_probe = predict_many(predict, X_probe, feature_names)

    acc = float((preds_test == y_test).mean())
    fid = float((preds_probe == reference_probe_preds).mean())
    nodes = _count_ast_nodes(source)
    raw_lines = [ln for ln in source.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    loc = len(raw_lines)
    ids = _count_identifiers(source)
    avg_len = statistics.mean(len(ln) for ln in raw_lines) if raw_lines else 0.0

    joint = fid - ast_weight * nodes

    return Score(
        name=path.stem,
        accuracy_test=acc,
        fidelity_probe=fid,
        ast_nodes=nodes,
        source_lines=loc,
        unique_identifiers=ids,
        avg_line_len=avg_len,
        joint=joint,
    )


def score_to_dict(s: Score) -> dict:
    return asdict(s)
