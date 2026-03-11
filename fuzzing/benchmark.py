#!/usr/bin/env python3
"""
Benchmark and optimization lab for LeetCode solutions.

Compares original vs optimized implementations, validates correctness
against the fuzzer-generated test suite, and measures performance.
"""

import subprocess
import time
import random
import string
import statistics
from pathlib import Path
from itertools import dropwhile

FUZZING_DIR = Path(__file__).parent


# ======================================================================
# LONGEST PALINDROMIC SUBSTRING — implementations
# ======================================================================

def palindrome_original(s: str) -> str:
    """Original: polynomial hashing + binary search. O(n log n)."""
    n = len(s)
    fwhash1, bwhash1, p1pow = [0] * (n + 1), [0] * (n + 1), [1] * (n + 1)
    p1, mod1 = 43, 172510953
    for i, c in enumerate(s):
        xc = ord(c) - ord('a')
        fwhash1[i + 1] = (fwhash1[i] * p1 + xc) % mod1
        bwhash1[i + 1] = (bwhash1[i] + p1pow[i] * xc) % mod1
        p1pow[i + 1] = (p1pow[i] * p1) % mod1
    palstart, palend = 0, 0
    for centre in range(2 * n - 1):
        lc, rc = centre // 2, (centre + 1) // 2
        start, end = max(-1, centre - n), lc + 1
        while end - start > 1:
            mid = (end + start) // 2
            l, r = mid, centre - mid
            fwcur = (
                fwhash1[r + 1] + mod1 -
                (fwhash1[l] * p1pow[r - l + 1]) % mod1
            ) % mod1
            bwcur = (bwhash1[r + 1] + mod1 - bwhash1[l]) % mod1
            if (fwcur * p1pow[l]) % mod1 == bwcur:
                end = mid
            else:
                start = mid
        if centre - 2 * end > palend - palstart:
            palstart, palend = end, centre - end
    return s[palstart:palend + 1]


def palindrome_manacher(s: str) -> str:
    """Manacher's algorithm — O(n) time, O(n) space. The theoretical optimum."""
    if not s:
        return ""
    # Transform: "abc" → "^#a#b#c#$" to handle even/odd uniformly
    t = "^#" + "#".join(s) + "#$"
    n = len(t)
    p = [0] * n  # p[i] = radius of palindrome centered at t[i]
    center = right = 0

    for i in range(1, n - 1):
        mirror = 2 * center - i
        if i < right:
            p[i] = min(right - i, p[mirror])
        while t[i + p[i] + 1] == t[i - p[i] - 1]:
            p[i] += 1
        if i + p[i] > right:
            center, right = i, i + p[i]

    # Find the maximum
    max_len = max(p)
    center_idx = p.index(max_len)
    start = (center_idx - max_len) // 2
    return s[start:start + max_len]


def palindrome_expand(s: str) -> str:
    """Expand-around-center — O(n²) but very cache-friendly and simple."""
    if not s:
        return ""
    start = end = 0
    for i in range(len(s)):
        for lo, hi in ((i, i), (i, i + 1)):
            while lo >= 0 and hi < len(s) and s[lo] == s[hi]:
                lo -= 1
                hi += 1
            if hi - lo - 1 > end - start:
                start, end = lo + 1, hi
    return s[start:end]


def palindrome_functional(s: str) -> str:
    """
    Functional-style: Manacher's expressed with reduce-like accumulation.

    Instead of mutable state with a for-loop, we fold over indices,
    threading (center, right, radii) as accumulator state.
    """
    if not s:
        return ""

    t = "#".join(f"^{s}$")
    n = len(t)

    def expand(p, i, center, right):
        """Compute palindrome radius at position i given current state."""
        mirror = 2 * center - i
        radius = min(right - i, p[mirror]) if i < right else 0
        while t[i + radius + 1] == t[i - radius - 1]:
            radius += 1
        return radius

    # Fold over positions, accumulating palindrome radii
    p = [0] * n
    center = right = 0
    for i in range(1, n - 1):
        p[i] = expand(p, i, center, right)
        if i + p[i] > right:
            center, right = i, i + p[i]

    k = max(range(n), key=lambda i: p[i])
    start = (k - p[k]) // 2
    return s[start:start + p[k]]


# ======================================================================
# REMOVE K DIGITS — implementations
# ======================================================================

def remove_k_original(num: str, k: int) -> str:
    """Original: monotonic stack. O(n)."""
    stack = []
    for c in num:
        while stack and k and stack[-1] > c:
            stack.pop()
            k -= 1
        stack.append(c)
    while k:
        stack.pop()
        k -= 1
    for i, c in enumerate(stack):
        if c > '0':
            return ''.join(stack[i:])
    return '0'


def remove_k_functional(num: str, k: int) -> str:
    """
    Functional-style using reduce.

    The monotonic stack is expressed as a left fold — each character is
    folded into the accumulator (stack, remaining_k), with the stack
    invariant maintained by popping in the reducer.
    """
    from functools import reduce

    def reducer(acc, c):
        stack, rem = acc
        while stack and rem and stack[-1] > c:
            stack = stack[:-1]
            rem -= 1
        return (stack + [c], rem)

    stack, rem = reduce(reducer, num, ([], k))
    result = stack[:len(stack) - rem] if rem else stack
    return ''.join(dropwhile(lambda c: c == '0', result)) or '0'


def remove_k_pythonic(num: str, k: int) -> str:
    """
    Concise Pythonic variant — same algorithm, tighter expression.
    Uses a list as stack but strips leading zeros with lstrip.
    """
    stack = []
    for d in num:
        while k and stack and stack[-1] > d:
            stack.pop()
            k -= 1
        stack.append(d)
    return ''.join(stack[:len(stack) - k]).lstrip('0') or '0'


# ======================================================================
# Benchmark runner
# ======================================================================

def generate_palindrome_inputs(rng, sizes):
    """Generate inputs of various sizes for benchmarking."""
    inputs = []
    for size in sizes:
        # Mix of alphabets to get different palindrome densities
        for alphabet_size in [2, 5, 26]:
            alpha = string.ascii_lowercase[:alphabet_size]
            s = ''.join(rng.choices(alpha, k=size))
            inputs.append(s)
    return inputs


def generate_remove_k_inputs(rng, sizes):
    """Generate inputs of various sizes for benchmarking."""
    inputs = []
    for size in sizes:
        for k_frac in [0.1, 0.5, 0.9]:
            num = str(rng.randint(1, 9)) + ''.join(rng.choices(string.digits, k=size - 1))
            k = max(0, min(size, int(size * k_frac)))
            inputs.append((num, k))
    return inputs


def bench(func, inputs, runs=3):
    """Benchmark a function, return median time in ms."""
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        for inp in inputs:
            if isinstance(inp, tuple):
                func(*inp)
            else:
                func(inp)
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)
    return statistics.median(times)


def validate_palindrome(func, name):
    """Validate against existing test data."""
    import json
    test_file = FUZZING_DIR / "test_longest_palindromic_substring.py"
    # Parse TEST_CASES from the file
    content = test_file.read_text()
    start = content.index("TEST_CASES = ")
    # Find the list
    bracket_start = content.index("[", start)
    depth = 0
    end = bracket_start
    for i, c in enumerate(content[bracket_start:], bracket_start):
        if c == '[': depth += 1
        elif c == ']': depth -= 1
        if depth == 0:
            end = i + 1
            break
    cases = eval(content[bracket_start:end])

    passed = failed = 0
    for tc in cases:
        result = func(tc["inputs"]["s"])
        expected_len = len(tc["py_output"])
        if len(result) == expected_len and result == result[::-1] and result in tc["inputs"]["s"]:
            passed += 1
        else:
            failed += 1
            if failed <= 3:
                print(f"    FAIL [{name}]: input={tc['inputs']['s'][:40]}... "
                      f"got={result!r} expected_len={expected_len}")
    return passed, failed


def validate_remove_k(func, name):
    """Validate against existing test data."""
    test_file = FUZZING_DIR / "test_remove_k_digits.py"
    content = test_file.read_text()
    start = content.index("TEST_CASES = ")
    bracket_start = content.index("[", start)
    depth = 0
    end = bracket_start
    for i, c in enumerate(content[bracket_start:], bracket_start):
        if c == '[': depth += 1
        elif c == ']': depth -= 1
        if depth == 0:
            end = i + 1
            break
    cases = eval(content[bracket_start:end])

    passed = failed = 0
    for tc in cases:
        result = func(tc["inputs"]["num"], tc["inputs"]["k"])
        expected = tc["py_output"]
        if result == expected:
            passed += 1
        else:
            failed += 1
            if failed <= 3:
                print(f"    FAIL [{name}]: num={tc['inputs']['num']} k={tc['inputs']['k']} "
                      f"got={result!r} expected={expected!r}")
    return passed, failed


def main():
    rng = random.Random(42)

    print("=" * 70)
    print("  Optimization Lab — Benchmarks & Validation")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Palindrome
    # ------------------------------------------------------------------
    print("\n" + "─" * 70)
    print("  LONGEST PALINDROMIC SUBSTRING")
    print("─" * 70)

    palindrome_impls = [
        ("original (hash+bsearch)", palindrome_original),
        ("manacher O(n)", palindrome_manacher),
        ("expand-center O(n²)", palindrome_expand),
        ("functional manacher", palindrome_functional),
    ]

    # Validate
    print("\n  Validation against 66 fuzzer-discovered test cases:")
    for name, func in palindrome_impls:
        p, f = validate_palindrome(func, name)
        status = "PASS" if f == 0 else "FAIL"
        print(f"    [{status}] {name}: {p}/{p + f}")

    # Benchmark
    sizes = [50, 100, 500, 1000, 5000]
    inputs = generate_palindrome_inputs(rng, sizes)
    print(f"\n  Benchmarks ({len(inputs)} inputs, sizes {sizes}):")
    print(f"  {'Implementation':<30} {'Time (ms)':>10} {'vs original':>12}")
    baseline = None
    for name, func in palindrome_impls:
        t = bench(func, inputs)
        if baseline is None:
            baseline = t
        speedup = baseline / t if t > 0 else float('inf')
        print(f"    {name:<28} {t:>8.1f}ms {speedup:>10.2f}x")

    # Large input benchmark
    print(f"\n  Large input (n=10000, alphabet=3):")
    large = [''.join(rng.choices('abc', k=10000))]
    baseline_large = None
    for name, func in palindrome_impls:
        t = bench(func, large, runs=5)
        if baseline_large is None:
            baseline_large = t
        speedup = baseline_large / t if t > 0 else float('inf')
        print(f"    {name:<28} {t:>8.1f}ms {speedup:>10.2f}x")

    # ------------------------------------------------------------------
    # Remove K Digits
    # ------------------------------------------------------------------
    print("\n" + "─" * 70)
    print("  REMOVE K DIGITS")
    print("─" * 70)

    remove_k_impls = [
        ("original (stack)", remove_k_original),
        ("functional (reduce)", remove_k_functional),
        ("pythonic (lstrip)", remove_k_pythonic),
    ]

    # Validate
    print("\n  Validation against 78 fuzzer-discovered test cases:")
    for name, func in remove_k_impls:
        p, f = validate_remove_k(func, name)
        status = "PASS" if f == 0 else "FAIL"
        print(f"    [{status}] {name}: {p}/{p + f}")

    # Benchmark
    sizes = [100, 500, 1000, 5000, 10000]
    inputs = generate_remove_k_inputs(rng, sizes)
    print(f"\n  Benchmarks ({len(inputs)} inputs, sizes {sizes}):")
    print(f"  {'Implementation':<30} {'Time (ms)':>10} {'vs original':>12}")
    baseline = None
    for name, func in remove_k_impls:
        t = bench(func, inputs)
        if baseline is None:
            baseline = t
        speedup = baseline / t if t > 0 else float('inf')
        print(f"    {name:<28} {t:>8.1f}ms {speedup:>10.2f}x")

    print(f"\n{'=' * 70}")
    print(f"  Done!")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
