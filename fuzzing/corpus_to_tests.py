#!/usr/bin/env python3
"""
Converts libFuzzer corpus files into a Python pytest test suite.

Reads the raw binary corpus entries that libFuzzer discovered through
coverage-guided fuzzing, decodes them into proper problem inputs,
runs both C++ and Python implementations, and generates a self-contained
pytest file with all the discovered test cases.

Usage:
    python3 corpus_to_tests.py
"""

import json
import os
import subprocess
import time
from pathlib import Path

FUZZING_DIR = Path(__file__).parent


# ===========================================================================
# Corpus decoders — convert raw fuzzer bytes back to problem inputs
# ===========================================================================

def decode_palindrome_input(data: bytes) -> dict | None:
    """Convert raw bytes to a palindrome problem input string."""
    if len(data) == 0 or len(data) > 200:
        return None
    s = "".join(chr(ord('a') + (b % 26)) for b in data)
    return {"s": s}


def decode_remove_k_input(data: bytes) -> dict | None:
    """Convert raw bytes to remove-k-digits problem inputs."""
    if len(data) < 2 or len(data) > 20:
        return None
    num_len = len(data) - 1
    digits = [str(b % 10) for b in data[1:]]
    if num_len > 1 and digits[0] == "0":
        digits[0] = str(1 + (data[1] % 9))
    num = "".join(digits)
    k = data[0] % (num_len + 1)
    return {"num": num, "k": k}


# ===========================================================================
# Solution runners
# ===========================================================================

def run_cpp_palindrome(s: str) -> str:
    result = subprocess.run(
        [str(FUZZING_DIR / "longest_palindrome")],
        input=s, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"C++ crash: {result.stderr}"
    return result.stdout.strip()


def run_cpp_remove_k(num: str, k: int) -> str:
    result = subprocess.run(
        [str(FUZZING_DIR / "remove_k_digits")],
        input=f"{num} {k}", capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"C++ crash: {result.stderr}"
    return result.stdout.strip()


def run_py_palindrome(s: str) -> str:
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


def run_py_remove_k(num: str, k: int) -> str:
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


# ===========================================================================
# Main: read corpus, generate test cases, write pytest file
# ===========================================================================

def process_corpus(corpus_dir: Path, decoder, py_runner, cpp_runner, problem_name: str) -> list[dict]:
    """Read all corpus files, decode inputs, run both implementations."""
    test_cases = []
    seen = set()

    for fname in sorted(os.listdir(corpus_dir)):
        fpath = corpus_dir / fname
        if not fpath.is_file():
            continue
        data = fpath.read_bytes()
        inputs = decoder(data)
        if inputs is None:
            continue

        key = json.dumps(inputs, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)

        try:
            py_out = py_runner(inputs)
            cpp_out = cpp_runner(inputs)
        except Exception as e:
            print(f"  Error on {fname}: {e}")
            test_cases.append({
                "inputs": inputs,
                "expected_output": None,
                "error": str(e),
                "corpus_file": fname,
            })
            continue

        test_cases.append({
            "inputs": inputs,
            "py_output": py_out,
            "cpp_output": cpp_out,
            "match": (py_out == cpp_out) if problem_name != "longest-palindromic-substring"
                     else (len(py_out) == len(cpp_out)),
            "corpus_file": fname,
        })

    return test_cases


def generate_test_file(problem_name: str, test_cases: list[dict], output_path: Path):
    """Generate a self-contained pytest file with all test cases embedded."""
    safe_name = problem_name.replace("-", "_")

    # Build the test data as a Python literal
    cases_for_embed = []
    for tc in test_cases:
        if tc.get("error"):
            continue
        cases_for_embed.append({
            "inputs": tc["inputs"],
            "py_output": tc["py_output"],
            "cpp_output": tc["cpp_output"],
        })

    header = f'''#!/usr/bin/env python3
"""
Test suite for {problem_name}
Auto-generated from libFuzzer corpus ({len(cases_for_embed)} coverage-guided test cases).
Generated at: {time.strftime("%Y-%m-%dT%H:%M:%S")}

These tests were discovered by libFuzzer (clang -fsanitize=fuzzer,address,undefined)
running coverage-guided fuzzing over the C++ solution. Each test case represents an
input that exercises a distinct code path. The inputs are cross-validated against
both the C++ and Python implementations.

To regenerate:
    1. Run the libFuzzer harnesses to build a corpus
    2. Run: python3 corpus_to_tests.py
"""

import subprocess
import pytest
from pathlib import Path

FUZZING_DIR = Path(__file__).parent

'''

    if problem_name == "longest-palindromic-substring":
        # Embed test data
        code = header
        code += f"TEST_CASES = {json.dumps(cases_for_embed, indent=2)}\n\n"
        code += '''
# --- Python implementation under test ---

def py_longest_palindrome(s: str) -> str:
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
            fwcur = (fwhash1[r + 1] + mod1 - (fwhash1[l] * p1pow[r - l + 1]) % mod1) % mod1
            bwcur = (bwhash1[r + 1] + mod1 - bwhash1[l]) % mod1
            if (fwcur * p1pow[l]) % mod1 == bwcur:
                end = mid
            else:
                start = mid
        if centre - 2 * end > palend - palstart:
            palstart, palend = end, centre - end
    return s[palstart:palend + 1]


def cpp_longest_palindrome(s: str) -> str:
    binary = FUZZING_DIR / "longest_palindrome"
    result = subprocess.run([str(binary)], input=s, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, f"C++ crashed: {result.stderr}"
    return result.stdout.strip()


def is_palindrome(s: str) -> bool:
    return s == s[::-1]


def brute_force_longest_palindrome_len(s: str) -> int:
    """O(n^3) oracle for correctness checking."""
    best = 1
    for i in range(len(s)):
        for j in range(i + 1, len(s) + 1):
            sub = s[i:j]
            if sub == sub[::-1] and len(sub) > best:
                best = len(sub)
    return best


@pytest.mark.parametrize("tc", TEST_CASES, ids=lambda tc: tc["inputs"]["s"][:30])
class TestLongestPalindromicSubstring:
    """Tests generated from libFuzzer coverage-guided corpus."""

    def test_py_result_is_palindrome(self, tc):
        result = py_longest_palindrome(tc["inputs"]["s"])
        assert is_palindrome(result)

    def test_py_result_is_substring(self, tc):
        s = tc["inputs"]["s"]
        result = py_longest_palindrome(s)
        assert result in s

    def test_cpp_result_is_palindrome(self, tc):
        result = cpp_longest_palindrome(tc["inputs"]["s"])
        assert is_palindrome(result)

    def test_cpp_result_is_substring(self, tc):
        s = tc["inputs"]["s"]
        result = cpp_longest_palindrome(s)
        assert result in s

    def test_cross_validate_length(self, tc):
        """C++ and Python must find palindromes of the same maximum length."""
        s = tc["inputs"]["s"]
        py_res = py_longest_palindrome(s)
        cpp_res = cpp_longest_palindrome(s)
        assert len(py_res) == len(cpp_res), (
            f"Python='{py_res}' (len={len(py_res)}) vs C++='{cpp_res}' (len={len(cpp_res)})"
        )

    def test_brute_force_oracle(self, tc):
        """Verify against O(n^3) brute-force for inputs <= 80 chars."""
        s = tc["inputs"]["s"]
        if len(s) > 80:
            pytest.skip("Input too large for brute-force oracle")
        expected_len = brute_force_longest_palindrome_len(s)
        py_res = py_longest_palindrome(s)
        assert len(py_res) == expected_len, (
            f"Python found '{py_res}' (len={len(py_res)}) but brute-force says max is {expected_len}"
        )
'''

    elif problem_name == "remove-k-digits":
        code = header
        code += f"TEST_CASES = {json.dumps(cases_for_embed, indent=2)}\n\n"
        code += '''
# --- Python implementation under test ---

def py_remove_k_digits(num: str, k: int) -> str:
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


def cpp_remove_k_digits(num: str, k: int) -> str:
    binary = FUZZING_DIR / "remove_k_digits"
    result = subprocess.run(
        [str(binary)], input=f"{num} {k}",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"C++ crashed: {result.stderr}"
    return result.stdout.strip()


def brute_force_remove_k(num: str, k: int) -> str:
    """O(C(n,k)) oracle for correctness checking."""
    from itertools import combinations
    n = len(num)
    keep = n - k
    if keep <= 0:
        return "0"
    best = None
    for indices in combinations(range(n), keep):
        candidate = "".join(num[i] for i in indices).lstrip("0") or "0"
        if best is None or int(candidate) < int(best):
            best = candidate
    return best


@pytest.mark.parametrize(
    "tc", TEST_CASES,
    ids=lambda tc: f"{tc['inputs']['num'][:12]}_k{tc['inputs']['k']}"
)
class TestRemoveKDigits:
    """Tests generated from libFuzzer coverage-guided corpus."""

    def test_py_matches_cpp(self, tc):
        """Cross-validate: Python and C++ must agree."""
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        py_res = py_remove_k_digits(num, k)
        cpp_res = cpp_remove_k_digits(num, k)
        assert py_res == cpp_res, f"Python='{py_res}' vs C++='{cpp_res}'"

    def test_no_leading_zeros(self, tc):
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        result = py_remove_k_digits(num, k)
        if result != "0":
            assert result[0] != "0", f"Leading zero: '{result}'"

    def test_remove_all_gives_zero(self, tc):
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        if k >= len(num):
            assert py_remove_k_digits(num, k) == "0"

    def test_result_length(self, tc):
        """Result should have at most len(num)-k digits."""
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        result = py_remove_k_digits(num, k)
        if result != "0":
            assert len(result) <= len(num) - k

    def test_brute_force_oracle(self, tc):
        """Verify against brute-force for small inputs."""
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        if len(num) > 12:
            pytest.skip("Input too large for brute-force oracle")
        expected = brute_force_remove_k(num, k)
        py_res = py_remove_k_digits(num, k)
        assert py_res == expected, f"Python='{py_res}' vs brute-force='{expected}'"

    def test_cpp_brute_force_oracle(self, tc):
        """Verify C++ against brute-force for small inputs."""
        num, k = tc["inputs"]["num"], tc["inputs"]["k"]
        if len(num) > 12:
            pytest.skip("Input too large for brute-force oracle")
        expected = brute_force_remove_k(num, k)
        cpp_res = cpp_remove_k_digits(num, k)
        assert cpp_res == expected, f"C++='{cpp_res}' vs brute-force='{expected}'"
'''
    else:
        raise ValueError(f"Unknown problem: {problem_name}")

    output_path.write_text(code)
    return len(cases_for_embed)


def main():
    print("=" * 70)
    print("  Corpus → Test Suite Generator")
    print("  Converting libFuzzer corpus to pytest test cases")
    print("=" * 70)

    configs = [
        {
            "name": "longest-palindromic-substring",
            "corpus_dir": FUZZING_DIR / "corpus_palindrome",
            "decoder": decode_palindrome_input,
            "py_runner": lambda inp: run_py_palindrome(inp["s"]),
            "cpp_runner": lambda inp: run_cpp_palindrome(inp["s"]),
            "output": FUZZING_DIR / "test_longest_palindromic_substring.py",
        },
        {
            "name": "remove-k-digits",
            "corpus_dir": FUZZING_DIR / "corpus_remove_k",
            "decoder": decode_remove_k_input,
            "py_runner": lambda inp: run_py_remove_k(inp["num"], inp["k"]),
            "cpp_runner": lambda inp: run_cpp_remove_k(inp["num"], inp["k"]),
            "output": FUZZING_DIR / "test_remove_k_digits.py",
        },
    ]

    for cfg in configs:
        print(f"\n  Processing: {cfg['name']}")
        print(f"  Corpus dir: {cfg['corpus_dir']}")

        test_cases = process_corpus(
            cfg["corpus_dir"], cfg["decoder"],
            cfg["py_runner"], cfg["cpp_runner"],
            cfg["name"],
        )
        print(f"  Decoded {len(test_cases)} corpus entries")

        matches = sum(1 for tc in test_cases if tc.get("match", False))
        print(f"  Cross-validation: {matches}/{len(test_cases)} match")

        n = generate_test_file(cfg["name"], test_cases, cfg["output"])
        print(f"  Generated: {cfg['output'].name} ({n} test cases)")

    print(f"\n{'=' * 70}")
    print("  Done! Run tests with: pytest fuzzing/ -v")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
