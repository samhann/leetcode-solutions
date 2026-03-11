#!/usr/bin/env python3
"""
LLM-in-the-Loop Optimization Engine
=====================================

Framework for iterative solution optimization:
  1. Register candidate implementations
  2. Validate each against the fuzz test suite (correctness gate)
  3. Benchmark survivors on multiple input distributions
  4. Rank by speed, report the leaderboard

This script is the harness. The "LLM" (Claude, or a human) proposes new
implementations by adding them to the CANDIDATES dict. Then run:

    python3 opt_loop.py

Design:
  - Correctness is a hard gate: if a candidate fails ANY fuzz test, it's rejected
  - Speed is measured across multiple input profiles (random, adversarial, etc.)
  - Each round's results are appended to a JSON log for historical tracking
"""

import json
import os
import statistics
import string
import time
import random
from pathlib import Path
from dataclasses import dataclass

FUZZING_DIR = Path(__file__).parent


# ======================================================================
# Test suite loader
# ======================================================================

def load_test_cases(test_file: Path) -> list[dict]:
    """Parse TEST_CASES from a generated pytest file."""
    content = test_file.read_text()
    start = content.index("TEST_CASES = ")
    bracket_start = content.index("[", start)
    depth = 0
    for i, c in enumerate(content[bracket_start:], bracket_start):
        if c == "[": depth += 1
        elif c == "]": depth -= 1
        if depth == 0:
            return eval(content[bracket_start:i + 1])
    raise ValueError("Could not parse TEST_CASES")


PAL_TESTS = load_test_cases(FUZZING_DIR / "test_longest_palindromic_substring.py")
RKD_TESTS = load_test_cases(FUZZING_DIR / "test_remove_k_digits.py")


# ======================================================================
# Validation
# ======================================================================

def validate_palindrome(func, name: str) -> tuple[int, int, list[str]]:
    """Returns (passed, failed, error_messages)."""
    passed = failed = 0
    errors = []
    for tc in PAL_TESTS:
        s = tc["inputs"]["s"]
        try:
            result = func(s)
        except Exception as e:
            failed += 1
            errors.append(f"CRASH on {s[:30]!r}: {e}")
            continue

        expected_len = len(tc["py_output"])
        is_pal = result == result[::-1]
        is_sub = result in s
        right_len = len(result) == expected_len

        if is_pal and is_sub and right_len:
            passed += 1
        else:
            failed += 1
            reasons = []
            if not is_pal: reasons.append("not palindrome")
            if not is_sub: reasons.append("not substring")
            if not right_len: reasons.append(f"len={len(result)} expected={expected_len}")
            errors.append(f"FAIL on {s[:30]!r}: {', '.join(reasons)} (got {result!r})")
    return passed, failed, errors


def validate_remove_k(func, name: str) -> tuple[int, int, list[str]]:
    passed = failed = 0
    errors = []
    for tc in RKD_TESTS:
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        try:
            result = func(num, k)
        except Exception as e:
            failed += 1
            errors.append(f"CRASH on num={num} k={k}: {e}")
            continue

        expected = tc["py_output"]
        if result == expected:
            passed += 1
        else:
            failed += 1
            errors.append(f"FAIL on num={num} k={k}: got {result!r} expected {expected!r}")
    return passed, failed, errors


# ======================================================================
# Benchmarking
# ======================================================================

@dataclass
class BenchProfile:
    name: str
    inputs: list
    description: str


def make_palindrome_profiles(rng) -> list[BenchProfile]:
    return [
        BenchProfile(
            "random_26",
            ["".join(rng.choices(string.ascii_lowercase, k=n)) for n in [100, 500, 1000] for _ in range(3)],
            "Random text, full alphabet",
        ),
        BenchProfile(
            "random_2",
            ["".join(rng.choices("ab", k=n)) for n in [100, 500, 1000] for _ in range(3)],
            "Small alphabet (dense palindromes)",
        ),
        BenchProfile(
            "adversarial",
            ["a" * n for n in [100, 500, 1000, 5000]],
            "All same char (worst case for O(n²))",
        ),
        BenchProfile(
            "large_random",
            ["".join(rng.choices(string.ascii_lowercase[:5], k=10000)) for _ in range(2)],
            "Large input, 10k chars",
        ),
    ]


def make_remove_k_profiles(rng) -> list[BenchProfile]:
    def make_num(n):
        return str(rng.randint(1, 9)) + "".join(rng.choices(string.digits, k=n - 1))
    return [
        BenchProfile(
            "typical",
            [(make_num(n), n // 2) for n in [100, 500, 1000] for _ in range(3)],
            "Typical: remove half the digits",
        ),
        BenchProfile(
            "remove_almost_all",
            [(make_num(n), n - 1) for n in [100, 500, 1000] for _ in range(3)],
            "Remove all but one digit",
        ),
        BenchProfile(
            "large",
            [(make_num(10000), 5000) for _ in range(2)],
            "Large input, 10k digits",
        ),
    ]


def bench(func, inputs, runs=5) -> float:
    """Return median time in ms."""
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        for inp in inputs:
            if isinstance(inp, tuple):
                func(*inp)
            else:
                func(inp)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


# ======================================================================
# Candidate implementations
# ======================================================================

PALINDROME_CANDIDATES = {}
REMOVE_K_CANDIDATES = {}


def palindrome(name):
    def decorator(func):
        PALINDROME_CANDIDATES[name] = func
        return func
    return decorator


def remove_k(name):
    def decorator(func):
        REMOVE_K_CANDIDATES[name] = func
        return func
    return decorator


# --- PALINDROME CANDIDATES ---

@palindrome("v0_original_hash")
def pal_v0(s):
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
        lc = centre // 2
        start, end = max(-1, centre - n), lc + 1
        while end - start > 1:
            mid = (end + start) // 2
            l, r = mid, centre - mid
            fwcur = (fwhash1[r + 1] + mod1 - (fwhash1[l] * p1pow[r - l + 1]) % mod1) % mod1
            bwcur = (bwhash1[r + 1] + mod1 - bwhash1[l]) % mod1
            if (fwcur * p1pow[l]) % mod1 == bwcur:
                end = mid
            else:
                start = mid
        if centre - 2 * end > palend - palstart:
            palstart, palend = end, centre - end
    return s[palstart:palend + 1]


@palindrome("v1_expand_center")
def pal_v1(s):
    """Expand around center. O(n²) but simple inner loop."""
    if not s: return ""
    start = end = 0
    for i in range(len(s)):
        for lo, hi in ((i, i), (i, i + 1)):
            while lo >= 0 and hi < len(s) and s[lo] == s[hi]:
                lo -= 1
                hi += 1
            if hi - lo - 1 > end - start:
                start, end = lo + 1, hi
    return s[start:end]


@palindrome("v2_manacher")
def pal_v2(s):
    """Manacher's algorithm. O(n)."""
    if not s: return ""
    t = "^#" + "#".join(s) + "#$"
    n = len(t)
    p = [0] * n
    center = right = 0
    for i in range(1, n - 1):
        mirror = 2 * center - i
        if i < right:
            p[i] = min(right - i, p[mirror])
        while t[i + p[i] + 1] == t[i - p[i] - 1]:
            p[i] += 1
        if i + p[i] > right:
            center, right = i, i + p[i]
    max_len = max(p)
    center_idx = p.index(max_len)
    start = (center_idx - max_len) // 2
    return s[start:start + max_len]


@palindrome("v3_manacher_tight")
def pal_v3(s):
    """Manacher's with reduced overhead: avoid string concat, use list."""
    if not s: return ""
    n = len(s)
    # Build transformed array without string concat
    # "^#a#b#c#$" → use indices: transformed[2*i+2] = s[i]
    tn = 2 * n + 3
    p = [0] * tn
    # Instead of building t, compute t[i] inline
    # t[0]='^', t[tn-1]='$', t[odd]='#', t[2*i+2]=s[i]
    def t(i):
        if i == 0: return '^'
        if i == tn - 1: return '$'
        if i & 1: return '#'
        return s[(i >> 1) - 1]

    center = right = 0
    best_i = best_p = 0
    for i in range(1, tn - 1):
        mirror = 2 * center - i
        if i < right:
            p[i] = min(right - i, p[mirror])
        while t(i + p[i] + 1) == t(i - p[i] - 1):
            p[i] += 1
        if i + p[i] > right:
            center, right = i, i + p[i]
        if p[i] > best_p:
            best_i, best_p = i, p[i]

    start = (best_i - best_p) // 2
    return s[start:start + best_p]


@palindrome("v4_manacher_bytearray")
def pal_v4(s):
    """Manacher's using a bytearray for the transformed string — avoids function call overhead."""
    if not s: return ""
    n = len(s)
    # Build transformed string as bytes: sentinel(0) # s[0] # s[1] # ... # sentinel(1)
    # Use 0 and 1 as sentinels, 2 as separator, ord(c) for characters
    sb = s.encode()
    t = bytearray(2 * n + 3)
    t[0] = 0  # start sentinel
    t[-1] = 1  # end sentinel
    for i in range(n):
        t[2 * i + 1] = 2  # separator
        t[2 * i + 2] = sb[i]
    t[2 * n + 1] = 2  # final separator

    tn = len(t)
    p = [0] * tn
    center = right = 0
    best_i = best_p = 0

    for i in range(1, tn - 1):
        mirror = 2 * center - i
        if i < right:
            p[i] = min(right - i, p[mirror])
        while t[i + p[i] + 1] == t[i - p[i] - 1]:
            p[i] += 1
        if i + p[i] > right:
            center, right = i, i + p[i]
        if p[i] > best_p:
            best_i, best_p = i, p[i]

    start = (best_i - best_p) // 2
    return s[start:start + best_p]


@palindrome("v5_expand_early_exit")
def pal_v5(s):
    """Expand-around-center with early termination: skip centers that can't beat current best."""
    if not s: return ""
    n = len(s)
    start = end = 0
    best = 0
    for i in range(n):
        # Max possible palindrome centered at i is 2*(min(i, n-1-i))+1
        # For even: 2*min(i+1, n-1-i)
        # If neither can beat current best, skip
        max_odd = 2 * min(i, n - 1 - i) + 1
        max_even = 2 * min(i + 1, n - 1 - i)
        if max(max_odd, max_even) <= best:
            continue
        for lo, hi in ((i, i), (i, i + 1)):
            while lo >= 0 and hi < n and s[lo] == s[hi]:
                lo -= 1
                hi += 1
            length = hi - lo - 1
            if length > best:
                best = length
                start, end = lo + 1, hi
    return s[start:end]


@palindrome("v6_expand_memview")
def pal_v6(s):
    """Expand-around-center operating on bytes (avoids Python string indexing overhead)."""
    if not s: return ""
    b = s.encode()
    n = len(b)
    best_start = best_len = 0
    for i in range(n):
        # Odd-length
        lo, hi = i, i
        while lo > 0 and hi < n - 1 and b[lo - 1] == b[hi + 1]:
            lo -= 1
            hi += 1
        if hi - lo + 1 > best_len:
            best_len = hi - lo + 1
            best_start = lo
        # Even-length
        lo, hi = i, i + 1
        if hi < n and b[lo] == b[hi]:
            while lo > 0 and hi < n - 1 and b[lo - 1] == b[hi + 1]:
                lo -= 1
                hi += 1
            if hi - lo + 1 > best_len:
                best_len = hi - lo + 1
                best_start = lo
    return s[best_start:best_start + best_len]


@palindrome("v7_manacher_bytes")
def pal_v7(s):
    """Manacher's on raw bytes — O(n) with fast byte-level comparisons."""
    if not s: return ""
    n = len(s)
    sb = s.encode()
    # Build transformed array as bytearray: [0, 255, s[0], 255, s[1], ..., 255, 1]
    tn = 2 * n + 3
    t = bytearray(tn)
    t[0] = 0    # start sentinel
    t[-1] = 1   # end sentinel (different from start!)
    j = 1
    for i in range(n):
        t[j] = 255  # separator
        t[j + 1] = sb[i]
        j += 2
    t[j] = 255  # final separator

    p = [0] * tn
    center = right = 0
    best_c = best_r = 0

    for i in range(1, tn - 1):
        if i < right:
            mirror = 2 * center - i
            p[i] = min(right - i, p[mirror])
        while t[i + p[i] + 1] == t[i - p[i] - 1]:
            p[i] += 1
        if i + p[i] > right:
            center, right = i, i + p[i]
        if p[i] > best_r:
            best_c, best_r = i, p[i]

    start = (best_c - best_r) // 2
    return s[start:start + best_r]


@palindrome("v8_hybrid")
def pal_v8(s):
    """
    Hybrid: expand-on-bytes for short strings, Manacher-on-bytes for long.
    Best of both worlds — fast constant factors for typical inputs,
    safe O(n) for adversarial ones.
    """
    if not s: return ""
    n = len(s)

    # Crossover point determined empirically from benchmarks:
    # expand-bytes wins on random text up to ~10k but loses badly on
    # adversarial (all-same-char) above ~500. We use 500 as a safe cutoff.
    if n <= 500:
        # Expand-on-bytes (v6)
        b = s.encode()
        best_start = best_len = 0
        for i in range(n):
            lo, hi = i, i
            while lo > 0 and hi < n - 1 and b[lo - 1] == b[hi + 1]:
                lo -= 1
                hi += 1
            if hi - lo + 1 > best_len:
                best_len = hi - lo + 1
                best_start = lo
            lo, hi = i, i + 1
            if hi < n and b[lo] == b[hi]:
                while lo > 0 and hi < n - 1 and b[lo - 1] == b[hi + 1]:
                    lo -= 1
                    hi += 1
                if hi - lo + 1 > best_len:
                    best_len = hi - lo + 1
                    best_start = lo
        return s[best_start:best_start + best_len]
    else:
        # Manacher-on-bytes (v7) for large/adversarial
        sb = s.encode()
        tn = 2 * n + 3
        t = bytearray(tn)
        t[0] = 0
        t[-1] = 1
        j = 1
        for i in range(n):
            t[j] = 255
            t[j + 1] = sb[i]
            j += 2
        t[j] = 255

        p = [0] * tn
        center = right = 0
        best_c = best_r = 0

        for i in range(1, tn - 1):
            if i < right:
                mirror = 2 * center - i
                p[i] = min(right - i, p[mirror])
            while t[i + p[i] + 1] == t[i - p[i] - 1]:
                p[i] += 1
            if i + p[i] > right:
                center, right = i, i + p[i]
            if p[i] > best_r:
                best_c, best_r = i, p[i]

        start = (best_c - best_r) // 2
        return s[start:start + best_r]


# --- REMOVE K CANDIDATES ---

@remove_k("v0_original_stack")
def rkd_v0(num, k):
    """Original monotonic stack."""
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


@remove_k("v1_pythonic")
def rkd_v1(num, k):
    """Pythonic: lstrip instead of manual loop."""
    stack = []
    for d in num:
        while k and stack and stack[-1] > d:
            stack.pop()
            k -= 1
        stack.append(d)
    return ''.join(stack[:len(stack) - k]).lstrip('0') or '0'


@remove_k("v2_bytearray")
def rkd_v2(num, k):
    """Operate on bytes instead of string characters."""
    b = num.encode()
    stack = bytearray()
    for c in b:
        while k and stack and stack[-1] > c:
            stack.pop()
            k -= 1
        stack.append(c)
    if k:
        stack = stack[:-k]
    result = stack.lstrip(b'0')
    return result.decode() if result else '0'


@remove_k("v3_list_ord")
def rkd_v3(num, k):
    """Compare ords instead of characters (avoids string comparison overhead)."""
    ords = [ord(c) for c in num]
    stack = []
    for o in ords:
        while k and stack and stack[-1] > o:
            stack.pop()
            k -= 1
        stack.append(o)
    if k:
        stack = stack[:-k]
    # Strip leading zeros (ord('0') = 48)
    i = 0
    while i < len(stack) - 1 and stack[i] == 48:
        i += 1
    if not stack:
        return '0'
    return ''.join(chr(o) for o in stack[i:]) if stack[i] != 48 or i == len(stack) - 1 else '0'


@remove_k("v4_deque")
def rkd_v4(num, k):
    """Use collections.deque for O(1) appendleft-free leading zero handling."""
    from collections import deque
    stack = deque()
    for d in num:
        while k and stack and stack[-1] > d:
            stack.pop()
            k -= 1
        stack.append(d)
    while k:
        stack.pop()
        k -= 1
    while stack and stack[0] == '0':
        stack.popleft()
    return ''.join(stack) or '0'


# ======================================================================
# Runner
# ======================================================================

def run_optimization_loop():
    rng = random.Random(42)

    print("=" * 72)
    print("  LLM-in-the-Loop Optimization Engine")
    print("  Correctness gate: 144 coverage-guided fuzz tests")
    print("=" * 72)

    results = {"palindrome": {}, "remove_k": {}}

    # --- PALINDROME ---
    print(f"\n{'━' * 72}")
    print("  LONGEST PALINDROMIC SUBSTRING")
    print(f"{'━' * 72}")

    profiles = make_palindrome_profiles(rng)

    print(f"\n  Validation gate ({len(PAL_TESTS)} fuzz tests):")
    survivors = {}
    for name, func in PALINDROME_CANDIDATES.items():
        p, f, errs = validate_palindrome(func, name)
        status = "PASS" if f == 0 else "REJECT"
        print(f"    [{status}] {name}: {p}/{p + f}")
        if errs:
            for e in errs[:2]:
                print(f"           {e}")
        if f == 0:
            survivors[name] = func

    print(f"\n  Benchmarks ({len(survivors)} survivors):")
    for profile in profiles:
        print(f"\n    Profile: {profile.name} — {profile.description}")
        print(f"    {'Candidate':<30} {'Time':>10} {'vs best':>10}")
        times = {}
        for name, func in survivors.items():
            t = bench(func, profile.inputs)
            times[name] = t
        best_time = min(times.values()) if times else 1
        for name in sorted(times, key=lambda n: times[n]):
            t = times[name]
            ratio = t / best_time
            marker = " ◄ best" if ratio < 1.01 else ""
            print(f"      {name:<28} {t:>8.2f}ms {ratio:>8.2f}x{marker}")
        results["palindrome"][profile.name] = times

    # --- REMOVE K ---
    print(f"\n{'━' * 72}")
    print("  REMOVE K DIGITS")
    print(f"{'━' * 72}")

    profiles = make_remove_k_profiles(rng)

    print(f"\n  Validation gate ({len(RKD_TESTS)} fuzz tests):")
    survivors = {}
    for name, func in REMOVE_K_CANDIDATES.items():
        p, f, errs = validate_remove_k(func, name)
        status = "PASS" if f == 0 else "REJECT"
        print(f"    [{status}] {name}: {p}/{p + f}")
        if errs:
            for e in errs[:2]:
                print(f"           {e}")
        if f == 0:
            survivors[name] = func

    print(f"\n  Benchmarks ({len(survivors)} survivors):")
    for profile in profiles:
        print(f"\n    Profile: {profile.name} — {profile.description}")
        print(f"    {'Candidate':<30} {'Time':>10} {'vs best':>10}")
        times = {}
        for name, func in survivors.items():
            t = bench(func, profile.inputs)
            times[name] = t
        best_time = min(times.values()) if times else 1
        for name in sorted(times, key=lambda n: times[n]):
            t = times[name]
            ratio = t / best_time
            marker = " ◄ best" if ratio < 1.01 else ""
            print(f"      {name:<28} {t:>8.2f}ms {ratio:>8.2f}x{marker}")
        results["remove_k"][profile.name] = times

    # Save results
    log_path = FUZZING_DIR / "opt_loop_results.json"
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results,
    }
    log = []
    if log_path.exists():
        log = json.loads(log_path.read_text())
    log.append(entry)
    log_path.write_text(json.dumps(log, indent=2))

    print(f"\n{'=' * 72}")
    print(f"  Results saved to {log_path.name}")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    run_optimization_loop()
