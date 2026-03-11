#!/usr/bin/env python3
"""
Coverage-Guided Fuzzing Harness for LeetCode Solutions
=======================================================

This is the orchestration script for the fuzzing pipeline. It drives the
end-to-end workflow: compile → fuzz → generate tests → validate.

Architecture
------------

The fuzzing uses a 3-layer approach:

1. **libFuzzer (C++)** — Coverage-guided fuzzing via clang's built-in fuzzer.
   Each harness (fuzz_*.cpp) wraps a LeetCode solution with:
   - Input decoding: raw bytes → valid problem inputs
   - Solution execution under AddressSanitizer + UndefinedBehaviorSanitizer
   - Invariant assertions: palindrome checks, subsequence checks, etc.
   - Brute-force oracle: cross-validate against O(n^3)/O(C(n,k)) reference

   libFuzzer tracks *edge coverage* (transitions between basic blocks) with
   compiler instrumentation — orders of magnitude faster and more precise than
   Python-level tracing. It uses mutation strategies: bit flips, insertions,
   deletions, cross-over, and auto-dictionaries.

2. **Corpus → Test Suite (Python)** — corpus_to_tests.py reads the libFuzzer
   corpus (inputs that expanded coverage), decodes them, and generates a
   pytest test suite with:
   - Cross-validation: C++ output vs Python output
   - Independent validators: palindrome check, no-leading-zeros, etc.
   - Brute-force oracles for small inputs
   - Self-contained: test data embedded in the .py file

3. **Differential Testing** — The generated tests run both implementations
   (C++ via subprocess, Python inline) on every corpus input and assert they
   agree. This catches bugs that only manifest in one implementation.

Usage
-----

    # Full pipeline
    python3 fuzz_harness.py

    # Or step by step:
    make build            # Compile harnesses and wrappers
    make fuzz             # Run libFuzzer (200k iterations per target)
    make generate-tests   # Convert corpus → pytest
    make run-tests        # Run the test suite

    # Customize fuzz rounds:
    make fuzz FUZZ_RUNS=1000000

Target Solutions
----------------

1. **Longest Palindromic Substring**
   - C++: expand-around-center O(n^2)
   - Python: polynomial hashing + binary search O(n log n)
   - Fuzzer asserts: is_palindrome, is_substring, length matches oracle

2. **Remove K Digits**
   - C++: greedy scanning O(n*k)
   - Python: monotonic stack O(n)
   - Fuzzer asserts: no leading zeros, result matches brute-force
"""

import os
import subprocess
import sys
from pathlib import Path

FUZZING_DIR = Path(__file__).parent


def run(cmd: str, **kwargs):
    """Run a shell command, printing it first."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=str(FUZZING_DIR), **kwargs)
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        return False
    return True


def main():
    fuzz_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 200000

    print("=" * 70)
    print("  Coverage-Guided Fuzzing Pipeline")
    print("=" * 70)

    # Step 1: Compile
    print("\n[1/4] Compiling libFuzzer harnesses and wrappers...")
    ok = all([
        run("clang++-17 -fsanitize=fuzzer,address,undefined -std=c++20 -O1 -g "
            "-o fuzz_longest_palindrome fuzz_longest_palindrome.cpp"),
        run("clang++-17 -fsanitize=fuzzer,address,undefined -std=c++20 -O1 -g "
            "-o fuzz_remove_k_digits fuzz_remove_k_digits.cpp"),
        run("g++ -std=c++20 -O2 -o longest_palindrome longest_palindrome_wrapper.cpp"),
        run("g++ -std=c++20 -O2 -o remove_k_digits remove_k_digits_wrapper.cpp"),
    ])
    if not ok:
        sys.exit(1)

    # Step 2: Create seed corpus
    print("\n[2/4] Setting up seed corpus and running libFuzzer...")
    os.makedirs(FUZZING_DIR / "corpus_palindrome", exist_ok=True)
    os.makedirs(FUZZING_DIR / "corpus_remove_k", exist_ok=True)

    for name, content in [("seed_1", b"a"), ("seed_2", b"aba"), ("seed_3", b"abba"),
                          ("seed_4", b"racecar"), ("seed_5", b"abcdefg")]:
        (FUZZING_DIR / "corpus_palindrome" / name).write_bytes(content)

    for name, content in [("seed_1", b"\x01\x31\x30"), ("seed_2", b"\x03\x31\x34\x33\x32\x32\x31\x39"),
                          ("seed_3", b"\x01\x31\x30\x32\x30\x30")]:
        (FUZZING_DIR / "corpus_remove_k" / name).write_bytes(content)

    # Run fuzzers
    run(f"./fuzz_longest_palindrome corpus_palindrome/ -max_len=200 "
        f"-runs={fuzz_runs} -print_final_stats=1")
    run(f"./fuzz_remove_k_digits corpus_remove_k/ -max_len=20 "
        f"-runs={fuzz_runs} -print_final_stats=1")

    # Step 3: Generate tests
    print("\n[3/4] Generating pytest suite from corpus...")
    run("python3 corpus_to_tests.py")

    # Step 4: Run tests
    print("\n[4/4] Running test suite...")
    run("python3 -m pytest test_longest_palindromic_substring.py "
        "test_remove_k_digits.py -v --tb=short")

    print("\n" + "=" * 70)
    print("  Pipeline complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
