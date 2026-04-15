# program_search — fit → extract → refactor → verify

An end-to-end experiment implementing the pipeline:

1. fit an interpretable model (sklearn `DecisionTreeClassifier`)
2. translate it into a canonical Python program
3. propose refactorings (rename, remove dead code, introduce helper predicates, reshape into rule list)
4. equivalence-check each rewrite against the canonical program, on real + adversarial probes
5. score each rewrite on a joint objective `fidelity − λ · ast_nodes`
6. accept only rewrites that improve the score and stay bit-exact

The "LLM" in step (3) is the assistant writing each candidate by hand — this keeps the loop end-to-end runnable without an API key, while the search-and-check machinery around it does the real work.

## Dataset

Wisconsin Breast Cancer (sklearn built-in). 569 samples, 30 continuous features, binary classification (malignant/benign). Split 60/20/20 into train / test / probe.

## Layout

| file | role |
|---|---|
| `dataset.py` | load + split |
| `tree_to_program.py` | emit canonical `predict(f)` from a fitted tree |
| `fit_baseline.py` | fit tree → `programs/v0_tree.py` + save probe data |
| `adversarial_probe.py` | build 20k random + boundary-epsilon points, use `v0_tree.py` as the equivalence oracle |
| `annotate.py` | compute threshold percentiles + rule coverage from training data — feeds v5 its data-grounded comments |
| `score.py` | accuracy, fidelity, AST nodes, LOC, named predicates, named constants, magic numbers, grounded refs, joint, insight |
| `pipeline.py` | score every program in `programs/` and apply the acceptance rule |
| `verify.py` | bit-exact equivalence check on real + adversarial probes |
| `programs/v0..v5*.py` | the baseline and five refactorings |

## Results

Two scalar objectives are tracked:

- `joint     = fidelity − 0.002·ast_nodes`  — rewards only *compactness*.
- `insight   = fidelity − 0.002·ast + 0.015·named_predicates + 0.020·named_constants − 0.010·magic_numbers + 0.020·min(grounded_refs, 20) + 0.0002·min(docstring_chars, 1500)` — rewards structure + data-grounded explanation.

Acceptance: `fidelity == 1.0` on both probe sets **and** `insight > baseline.insight`.

| program | acc | fid | AST | preds | consts | magic | grnd | joint | insight | Δ insight |
|---|---|---|---|---|---|---|---|---|---|---|
| v0_tree (extracted) | 0.9211 | 1.0 | 107 | 0 | 0 | 9 | 0 | +0.786 | +0.728 | — |
| v1_dead_code_removed | 0.9211 | 1.0 | 74  | 0 | 0 | 6 | 0 | +0.852 | +0.988 | +0.26 |
| v2_named_predicates | 0.9211 | 1.0 | 101 | 6 | 0 | 6 | 0 | +0.798 | +0.918 | +0.19 |
| v3_rule_list | 0.9211 | 1.0 | 100 | 6 | 0 | 6 | 0 | +0.800 | +0.939 | +0.21 |
| v4_minimal | 0.9211 | 1.0 | **70** | 0 | 0 | 6 | 0 | **+0.860** | +0.861 | +0.13 |
| v5_annotated | 0.9211 | 1.0 | 132 | 6 | **6** | **0** | **31** | +0.736 | **+1.646** | **+0.92** |

All five rewrites verified bit-exact against `v0_tree.py` on **114 real probe points + 20,045 adversarial points** (random uniform across the widened feature box plus `threshold ± {0, 1e-9, 1e-6}` for every split in the tree).

The `joint` and `insight` columns deliberately disagree. v4 is the most compact program; v5 is the most *readable* — it names every threshold, names every predicate, carries zero magic numbers in the function body, and makes 31 data-grounded references (percentiles + training-coverage stats). A reader of v5 can see not just *what* the model does but *what each threshold means in context* and *how often each rule fires*.

## What the adversarial probe actually caught

Two real defects, neither of which the 114-row real probe noticed:

1. **Threshold rounding in the canonical emitter.** First version of `tree_to_program.py` printed thresholds as `{:.6f}`. A point at `threshold + 1e-9` flipped. Fix: print thresholds via `repr(float(t))` so the source literal round-trips to the exact IEEE-754 bits sklearn holds.

2. **Hand-written refactorings copied rounded constants.** After regenerating v0 with full-precision literals, v1/v2/v3 still had the old rounded constants (`0.048865` vs `0.048864999786019325`). The probe flagged 4 adversarial disagreements on v1/v2/v3 while v0 passed. Fix: keep constants identical to v0.

Both are exactly the kind of quiet bug that creeps into an LLM-produced rewrite: semantics *look* preserved, real-data accuracy *is* preserved, but there's a 10⁻⁶-wide band where behaviour flips. The probe is cheap and catches it.

## Readings of the scoreboard

- **v4 wins on `joint`** because the joint only rewards AST savings, and v4 is 15 LOC with zero helper bindings. It is also *the least informative program in the set*. This is the direct failure mode of the original objective.
- **v5 wins on `insight`** by ~3× the next-best rewrite, because magic numbers are now behind named constants, every predicate has a meaning, and the docstring ties each rule back to the training distribution.
- `joint` and `insight` actively disagree. The search-and-check loop should therefore not collapse readability into one scalar; a two-axis Pareto front (compactness × explainability) is the honest view.

### Why compactness is not insight

A program that minimises AST nodes compresses its thresholds into anonymous floats next to anonymous feature lookups. After step (6), you have a program that passes the equivalence check and improves on complexity — and that no reader can interrogate. The fix, demonstrated here, is twofold:

1. **Score the things that actually carry meaning.** `named_predicates`, `named_constants`, `magic_numbers`, and `grounded_refs` each have an obvious direction and are cheap to compute from the AST / regex over comments.
2. **Feed the refactorer data, not just source.** `annotate.py` hands the refactor step real numbers: the percentile of each threshold in the training distribution, and how often each rule fires and with what purity. Without that input the LLM can only explain the code to itself in tautologies; with it, the docstring and comments carry actual information about the dataset.

## How to run

```
python3 fit_baseline.py        # fit tree, emit v0_tree.py, save probe data
python3 adversarial_probe.py   # build 20k adversarial points, oracle = v0_tree
python3 annotate.py            # percentiles + per-rule coverage (used by v5)
python3 verify.py              # bit-exact equivalence check
python3 pipeline.py            # score + acceptance rule
```

## Notes on the architecture choice: sklearn vs v0_tree as the oracle

The initial version used `clf.predict()` as the equivalence oracle. That turned out to be wrong for this loop: sklearn compares thresholds in float32 internally, so at ε ≈ 10⁻⁹ to a boundary the sklearn tree and an extracted float64 program can legitimately disagree — without either being "wrong". What we care about in step (4) is "the refactoring preserves the canonical program", so the oracle must be the canonical program. The sklearn tree only earns the right to set the initial extraction.
