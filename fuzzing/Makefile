# Fuzzing Test Harness for LeetCode Solutions
# ============================================
#
# Uses libFuzzer (clang -fsanitize=fuzzer) for coverage-guided fuzzing
# of C++ solutions, then generates a Python test suite that cross-validates
# both C++ and Python implementations.
#
# Quick start:
#   make all         # Build, fuzz, generate tests, run them
#   make fuzz        # Just run the fuzzers (200k iterations each)
#   make tests       # Generate and run the pytest suite
#   make clean       # Remove all generated artifacts
#
# Requirements: clang++-17, python3, pytest

CXX = clang++-17
CXXFLAGS = -std=c++20 -O1 -g
FUZZ_FLAGS = -fsanitize=fuzzer,address,undefined
PLAIN_FLAGS = -O2

FUZZ_RUNS ?= 200000

.PHONY: all build fuzz generate-tests run-tests tests clean

all: build fuzz generate-tests run-tests

# --- Build ---

build: fuzz_longest_palindrome fuzz_remove_k_digits longest_palindrome remove_k_digits

fuzz_longest_palindrome: fuzz_longest_palindrome.cpp
	$(CXX) $(CXXFLAGS) $(FUZZ_FLAGS) -o $@ $<

fuzz_remove_k_digits: fuzz_remove_k_digits.cpp
	$(CXX) $(CXXFLAGS) $(FUZZ_FLAGS) -o $@ $<

longest_palindrome: longest_palindrome_wrapper.cpp
	g++ -std=c++20 $(PLAIN_FLAGS) -o $@ $<

remove_k_digits: remove_k_digits_wrapper.cpp
	g++ -std=c++20 $(PLAIN_FLAGS) -o $@ $<

# --- Fuzz ---

fuzz: build corpus_palindrome corpus_remove_k
	./fuzz_longest_palindrome corpus_palindrome/ -max_len=200 -runs=$(FUZZ_RUNS) -print_final_stats=1
	./fuzz_remove_k_digits corpus_remove_k/ -max_len=20 -runs=$(FUZZ_RUNS) -print_final_stats=1

corpus_palindrome:
	mkdir -p $@
	echo -n "a" > $@/seed_1
	echo -n "aba" > $@/seed_2
	echo -n "abba" > $@/seed_3
	echo -n "racecar" > $@/seed_4
	echo -n "abcdefg" > $@/seed_5

corpus_remove_k:
	mkdir -p $@
	printf '\x01\x31\x30' > $@/seed_1
	printf '\x03\x31\x34\x33\x32\x32\x31\x39' > $@/seed_2
	printf '\x01\x31\x30\x32\x30\x30' > $@/seed_3

# --- Test generation ---

generate-tests: build
	python3 corpus_to_tests.py

run-tests:
	python3 -m pytest test_longest_palindromic_substring.py test_remove_k_digits.py -v --tb=short

tests: generate-tests run-tests

# --- Cleanup ---

clean:
	rm -f fuzz_longest_palindrome fuzz_remove_k_digits
	rm -f longest_palindrome remove_k_digits
	rm -rf corpus_palindrome corpus_remove_k
	rm -f test_longest_palindromic_substring.py test_remove_k_digits.py
	rm -f test_suite_*.json
	rm -rf crash-* leak-*
