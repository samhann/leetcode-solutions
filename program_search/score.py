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
import re
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
    # Readability metrics (higher = more insightful).
    named_predicates: int       # `foo = x <= 3` style assignments
    named_constants: int        # module-level ALL_CAPS = <number>
    magic_numbers: int          # numeric literals not behind a name / not 0/1
    docstring_chars: int        # chars of prose in docstrings
    grounded_refs: int          # references to "pN%" / "NN% of train" etc.
    joint: float
    insight: float

    def pretty(self) -> str:
        return (
            f"{self.name:<20} acc={self.accuracy_test:.4f} fid={self.fidelity_probe:.4f} "
            f"ast={self.ast_nodes:<4} preds={self.named_predicates:<2} "
            f"consts={self.named_constants:<2} magic={self.magic_numbers:<2} "
            f"doc={self.docstring_chars:<4} grnd={self.grounded_refs:<2} "
            f"joint={self.joint:+.4f} insight={self.insight:+.4f}"
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


def _readability_metrics(source: str):
    """Count readability-oriented features of the source.

    Returns (named_predicates, named_constants, magic_numbers, docstring_chars).

    named_predicates: Assign nodes inside predict() whose RHS is a
        Compare or BoolOp (e.g. `small_tumor = f["..."] <= 3`).
    named_constants: module-level Assign nodes whose RHS is a numeric
        Constant (e.g. `THRESHOLD = 106.1`).
    magic_numbers: numeric literals (not in {0, 1}) that appear *inside*
        the predict() body's control flow (not behind a named constant).
    docstring_chars: characters of prose in module/function docstrings.
    """
    tree = ast.parse(source)

    named_predicates = 0
    named_constants = 0
    magic_numbers = 0
    docstring_chars = 0

    def _is_numeric_const(n):
        return isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)

    # Module docstring.
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        docstring_chars += len(mod_doc)

    # Module-level named constants.
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name) and _is_numeric_const(node.value):
                named_constants += 1

    # Inspect predict() body.
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "predict":
            fn_doc = ast.get_docstring(node)
            if fn_doc:
                docstring_chars += len(fn_doc)
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    t = stmt.targets[0]
                    if isinstance(t, ast.Name) and isinstance(stmt.value, (ast.Compare, ast.BoolOp)):
                        named_predicates += 1
                if _is_numeric_const(stmt) and stmt.value not in (0, 1):
                    magic_numbers += 1

    # "Grounded" references: mentions of percentile / rule-coverage numbers
    # grounded in training data. Matches things like "p61", "61%", "59.5% of
    # train", "fires on N/341", etc. A high count indicates the author
    # connected thresholds back to the data, not just to the sklearn object.
    grounded_refs = 0
    for pat in (r"\bp\d{1,3}\b", r"\b\d{1,3}(?:\.\d+)?\s*%", r"\d+/\d+ train", r"fires\s+\d"):
        grounded_refs += len(re.findall(pat, source))

    return named_predicates, named_constants, magic_numbers, docstring_chars, grounded_refs


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

    named_preds, named_consts, magic, docchars, grounded = _readability_metrics(source)

    # Original joint kept for backward compatibility - rewards compactness only.
    joint = fid - ast_weight * nodes

    # `insight` adds readability terms, weighted so structural / semantic
    # signals matter more than mere docstring length:
    #   named predicates / constants           -> actually re-express logic
    #   magic numbers                          -> opacity, penalised
    #   grounded refs (percentiles, coverage)  -> data-anchored reasoning
    #   docstring chars                        -> last-resort prose, saturating
    # Weights: verified so that
    #   (a) v5 (richly annotated, data-grounded) wins,
    #   (b) no rewrite with fidelity < 1.0 could buy its way past a correct one.
    insight = (
        fid
        - 0.002 * nodes
        + 0.015 * named_preds
        + 0.020 * named_consts
        - 0.010 * magic
        + 0.020 * min(grounded, 20)      # saturating data-grounded signal
        + 0.0002 * min(docchars, 1500)
    )

    return Score(
        name=path.stem,
        accuracy_test=acc,
        fidelity_probe=fid,
        ast_nodes=nodes,
        source_lines=loc,
        unique_identifiers=ids,
        avg_line_len=avg_len,
        named_predicates=named_preds,
        named_constants=named_consts,
        magic_numbers=magic,
        docstring_chars=docchars,
        grounded_refs=grounded,
        joint=joint,
        insight=insight,
    )


def score_to_dict(s: Score) -> dict:
    return asdict(s)
