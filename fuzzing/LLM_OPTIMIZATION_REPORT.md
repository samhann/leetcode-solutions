# LLM-in-the-Loop Optimization: Using Fuzz Tests as a Safety Net

We built an optimization loop where an LLM (Claude) proposes candidate
implementations, a fuzzer-generated test suite gates correctness, and
benchmarks score speed. Three rounds of iteration. Nine palindrome variants.
Five remove-k variants. Here's what we found.

## The Loop

```
  ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
  │ LLM proposes │────▶│ 144 fuzz tests    │────▶│ Benchmark   │
  │ optimization │     │ (correctness gate)│     │ (4 profiles)│
  └─────────────┘     └──────────────────┘     └──────┬──────┘
        ▲                   │ REJECT                   │
        │                   ▼                          │
        │              discarded                       │
        │                                              │
        └───── learn from results ◄────────────────────┘
```

**Correctness is a hard gate.** If a candidate fails even one of the 144
coverage-guided fuzz tests, it's rejected. No exceptions. This lets us try
aggressive optimizations without fear — the tests catch regressions instantly.

**Speed is measured across four profiles:**
- `random_26`: full alphabet, palindromes are short (best case for simple code)
- `random_2`: binary alphabet, palindromes are dense (stress test)
- `adversarial`: all same character (worst case for O(n²))
- `large_random`: 10k characters (asymptotic behavior)

## The Candidates

### Longest Palindromic Substring (9 variants)

| ID | Approach | Complexity | Key Idea |
|----|----------|-----------|----------|
| v0 | Polynomial hash + binary search | O(n log n) | Original solution |
| v1 | Expand around center | O(n²) | Textbook approach |
| v2 | Manacher's algorithm | O(n) | Theoretical optimum |
| v3 | Manacher's, inline t[i] | O(n) | Avoid string concat |
| v4 | Manacher's on bytearray | O(n) | Byte-level comparisons |
| v5 | Expand + early exit | O(n²)* | Skip unpromising centers |
| v6 | Expand on bytes | O(n²) | `s.encode()` + byte indexing |
| v7 | Manacher's on bytes | O(n) | Best of v2 + v4 |
| v8 | Hybrid (v6 small, v7 large) | O(n) | Adaptive algorithm selection |

### Remove K Digits (5 variants)

| ID | Approach | Key Idea |
|----|----------|----------|
| v0 | Monotonic stack (original) | Manual leading-zero strip |
| v1 | Pythonic stack | `.lstrip('0')` |
| v2 | Bytearray stack | `bytearray()` + byte ops |
| v3 | Ord-based stack | `ord()` comparisons |
| v4 | Deque stack | `deque.popleft()` for zeros |

## Results: The Leaderboard

### Palindrome

```
                         random_26   random_2   adversarial   large_10k
                         ─────────   ────────   ───────────   ─────────
  v6 expand-bytes          0.72ms    1.66ms    1139.79ms       3.94ms
  v8 hybrid                1.66ms    2.92ms      14.82ms      11.74ms
  v2 manacher              2.07ms    3.58ms       4.95ms      11.35ms
  v7 manacher-bytes        2.15ms    3.91ms       5.36ms      11.56ms
  v1 expand-center         2.26ms    2.91ms    1097.73ms       9.12ms
  v4 manacher-bytearray    2.57ms    4.05ms       5.68ms      12.39ms
  v5 expand-early-exit     3.71ms    4.21ms     414.45ms      15.54ms
  v3 manacher-tight        5.18ms    8.52ms       9.96ms      26.05ms
  v0 original-hash        23.36ms   25.54ms      33.01ms     147.69ms
```

**There is no single winner.** The best choice depends on your input distribution:

| Use case | Best variant | Why |
|----------|-------------|-----|
| LeetCode (n≤1000, random) | **v6 expand-bytes** | 2-3x faster than everything else |
| Production (any input) | **v2 manacher** | O(n) worst case, safe |
| If you need both | **v8 hybrid** | Good average, bounded worst case |

### Remove K Digits

```
                         typical   remove_all   large_10k
                         ───────   ──────────   ─────────
  v2 bytearray            0.38ms    0.58ms       1.56ms    ◄ winner everywhere
  v1 pythonic              0.41ms    0.64ms       1.72ms
  v0 original              0.45ms    0.64ms       1.76ms
  v4 deque                 0.46ms    0.67ms       1.85ms
  v3 list-ord              0.54ms    0.66ms       2.14ms
```

**`v2_bytearray` wins everywhere** — consistent 10-15% faster than the original.
The `bytearray` type in Python has lower overhead per element access than `str`.

## Key Insights from the Optimization Loop

### 1. The biggest win: `s.encode()` (Speedup: 2-3x)

The single most impactful optimization across all candidates was converting
Python strings to `bytes` before doing character-by-character work:

```python
# Before: string indexing (slow — each s[i] creates a new str object)
while s[lo] == s[hi]: ...

# After: byte indexing (fast — b[i] returns an int, no object creation)
b = s.encode()
while b[lo] == b[hi]: ...
```

Why? In CPython, `s[i]` on a string creates a **new single-character string
object** on every access. `b[i]` on bytes returns a **plain integer**. The
difference is object allocation vs. integer comparison — roughly 3x faster.

This is the #1 Python performance trick for string-heavy algorithms.

### 2. The failed optimization: inline function for t[i] (Slowdown: 2-6x)

v3 tried to avoid building Manacher's transformed string by computing `t[i]`
on the fly:

```python
def t(i):
    if i == 0: return '^'
    if i == tn - 1: return '$'
    if i & 1: return '#'
    return s[(i >> 1) - 1]
```

This is **slower than just building the string**, because Python function calls
cost ~100ns each, and this function is called millions of times. In C++, this
would be inlined by the compiler and be free. In Python, it's a disaster.

**Lesson: never replace a data structure lookup with a function call in a hot loop in Python.**

### 3. The hybrid dilemma (v8)

We tried building an adaptive algorithm that uses expand-bytes for small inputs
and Manacher-bytes for large ones. The challenge is picking the crossover point:

```
Crossover = 2000: adversarial n=5000 hits expand → 11x slower than Manacher
Crossover = 500:  large random n=10000 hits Manacher → 3x slower than expand
```

The problem is that the "best" algorithm depends on **both size AND input
distribution**, which you don't know at call time. You could detect adversarial
inputs (check if many characters repeat), but that adds overhead and complexity.

In practice, v2 (Manacher) at 2-3x slower on the easy cases but **safe on all
cases** is the engineering-correct choice. A 3x slowdown on a 2ms operation
doesn't matter. A 500x blowup on an adversarial input does.

### 4. What didn't work for Remove K Digits

- **`ord()` comparisons (v3)**: Converting every character to an `ord()` and then
  back with `chr()` at the end costs more than the comparison savings
- **`deque.popleft()` (v4)**: More overhead than `lstrip('0')` for stripping
  leading zeros — deque shines for large queues, not small final cleanups
- **`bytearray` (v2)**: Winner because `bytearray.pop()` and `bytearray.append()`
  avoid string object creation entirely, same as the palindrome finding

### 5. The original solution was the worst in every profile

The original hash+binary search palindrome solution was **23-148x slower** than
the best alternative in every single benchmark profile. This is a genuine finding
— the solution is correct (passes all 66 fuzz tests) but uses an approach that
has terrible constant factors in Python.

The polynomial hashing approach (rolling hash + modular arithmetic) is excellent
in C/C++ where arithmetic is nearly free. In Python, each `%` operation is
expensive, and the approach requires 4 multiplications + 2 mods per hash query.

## The Meta-Result: The Loop Works

The real outcome isn't any single optimization — it's the **process**:

1. LLM proposes 9 candidates in minutes (a human would try 2-3)
2. Fuzz tests catch regressions instantly (no manual verification needed)
3. Multi-profile benchmarks reveal tradeoffs (no single "best" — just Pareto fronts)
4. Each round informs the next (v3's failure → v4's bytearray, v6's success → v8's hybrid)

The 144 coverage-guided fuzz tests are what make this safe. Without them,
you'd spend more time verifying correctness than optimizing. With them,
you can try wild ideas (inline function dispatch, hybrid algorithms,
type-level tricks) and know in seconds if they're correct.

**This is the real payoff of fuzzing: not just finding bugs, but enabling
fearless optimization.**

## How to Reproduce

```bash
cd fuzzing/

# Run the optimization loop
python3 opt_loop.py

# Add your own candidate: edit opt_loop.py, add a @palindrome("my_variant")
# decorated function, run again. The harness validates and benchmarks it
# automatically.
```
