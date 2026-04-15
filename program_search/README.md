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
| `score.py` | compute accuracy, fidelity, AST nodes, LOC, identifiers, joint |
| `pipeline.py` | score every program in `programs/` and apply the acceptance rule |
| `verify.py` | bit-exact equivalence check on real + adversarial probes |
| `programs/v0..v4*.py` | the baseline and four refactorings |

## Results

Joint score formula: `fidelity − 0.002 · ast_nodes`. Acceptance: `fidelity == 1.0` on both probe sets **and** joint > baseline joint.

| program | test acc | fidelity | AST | LOC | joint | Δ vs baseline |
|---|---|---|---|---|---|---|
| v0_tree (extracted) | 0.9211 | 1.0000 | 107 | 33 | +0.7860 | — |
| v1_dead_code_removed | 0.9211 | 1.0000 | 74 | 51 | +0.8520 | **+0.066** |
| v2_named_predicates | 0.9211 | 1.0000 | 101 | 22 | +0.7980 | +0.012 |
| v3_rule_list | 0.9211 | 1.0000 | 100 | 22 | +0.8000 | +0.014 |
| v4_minimal (dead-code + short-circuit) | 0.9211 | 1.0000 | 70 | 15 | +0.8600 | **+0.074** |

All four rewrites verified bit-exact against `v0_tree.py` on **114 real probe points + 20,045 adversarial points** (random uniform across the widened feature box plus `threshold ± {0, 1e-9, 1e-6}` for every split in the tree).

## What the adversarial probe actually caught

Two real defects, neither of which the 114-row real probe noticed:

1. **Threshold rounding in the canonical emitter.** First version of `tree_to_program.py` printed thresholds as `{:.6f}`. A point at `threshold + 1e-9` flipped. Fix: print thresholds via `repr(float(t))` so the source literal round-trips to the exact IEEE-754 bits sklearn holds.

2. **Hand-written refactorings copied rounded constants.** After regenerating v0 with full-precision literals, v1/v2/v3 still had the old rounded constants (`0.048865` vs `0.048864999786019325`). The probe flagged 4 adversarial disagreements on v1/v2/v3 while v0 passed. Fix: keep constants identical to v0.

Both are exactly the kind of quiet bug that creeps into an LLM-produced rewrite: semantics *look* preserved, real-data accuracy *is* preserved, but there's a 10⁻⁶-wide band where behaviour flips. The probe is cheap and catches it.

## Readings of the scoreboard

- **v4 wins on the joint** because `λ = 0.002` heavily rewards AST-node savings and v4 combines every structural simplification.
- **v2 has the best LOC and identifier counts** (22 LOC, 8 named predicates), but named predicates add `Assign` + `Name` AST nodes and penalise it on the joint.
- The weighting is a knob. `λ` too small and the LLM never gets credit for simplification; too large and it's incentivised to strip every readable intermediate.

## How to run

```
python3 fit_baseline.py        # fit tree, emit v0_tree.py, save probe data
python3 adversarial_probe.py   # build 20k adversarial points, oracle = v0_tree
python3 verify.py              # bit-exact equivalence check
python3 pipeline.py            # score + acceptance rule
```

## Notes on the architecture choice: sklearn vs v0_tree as the oracle

The initial version used `clf.predict()` as the equivalence oracle. That turned out to be wrong for this loop: sklearn compares thresholds in float32 internally, so at ε ≈ 10⁻⁹ to a boundary the sklearn tree and an extracted float64 program can legitimately disagree — without either being "wrong". What we care about in step (4) is "the refactoring preserves the canonical program", so the oracle must be the canonical program. The sklearn tree only earns the right to set the initial extraction.
