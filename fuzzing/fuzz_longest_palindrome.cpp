// libFuzzer harness for longest-palindromic-substring
//
// Compile:
//   clang++-17 -fsanitize=fuzzer,address,undefined -std=c++20 -O1 -g \
//     -o fuzz_longest_palindrome fuzz_longest_palindrome.cpp
//
// Run:
//   ./fuzz_longest_palindrome corpus_palindrome/ -max_len=256 -runs=100000

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <string>

using namespace std;

// ---- Solution under test (from Solutions/L/longest-palindromic-substring/) ----
class Solution {
 public:
  string longestPalindrome(string s) {
    int best = 0, bestl = -1, n = s.size();
    for (int i = 0; i < n; ++i) {
      for (int j = i, k = i; j >= 0 && k < n; --j, ++k) {
        if (s[j] == s[k]) {
          if (k - j + 1 > best) best = k - j + 1, bestl = j;
        } else
          break;
      }
    }
    for (int i = 0; i < n; ++i) {
      for (int j = i, k = i + 1; j >= 0 && k < n; --j, ++k) {
        if (s[j] == s[k]) {
          if (k - j + 1 > best) best = k - j + 1, bestl = j;
        } else
          break;
      }
    }
    return s.substr(bestl, best);
  }
};

// ---- Oracle: brute-force O(n^3) reference implementation ----
static bool isPalindrome(const string& s, int l, int r) {
    while (l < r) {
        if (s[l] != s[r]) return false;
        ++l; --r;
    }
    return true;
}

static int bruteForceLongestPalLen(const string& s) {
    int n = s.size();
    int best = 1;
    for (int i = 0; i < n; ++i) {
        for (int j = i; j < n; ++j) {
            if (j - i + 1 > best && isPalindrome(s, i, j)) {
                best = j - i + 1;
            }
        }
    }
    return best;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size == 0 || size > 200) return 0;

    // Map raw bytes to lowercase letters (a-z) for valid input
    string s(size, 'a');
    for (size_t i = 0; i < size; ++i) {
        s[i] = 'a' + (data[i] % 26);
    }

    Solution sol;
    string result = sol.longestPalindrome(s);

    // --- Invariant checks (assertions under ASan/UBSan) ---

    // 1. Result must be a palindrome
    string rev = result;
    reverse(rev.begin(), rev.end());
    assert(result == rev && "Output is not a palindrome!");

    // 2. Result must be a substring of the input
    assert(s.find(result) != string::npos && "Output is not a substring of input!");

    // 3. Result length must match brute-force oracle (for sizes <= 80)
    if (size <= 80) {
        int expected_len = bruteForceLongestPalLen(s);
        assert((int)result.size() == expected_len &&
               "Output length doesn't match brute-force oracle!");
    }

    // 4. Result must not be empty for non-empty input
    assert(!result.empty() && "Output is empty for non-empty input!");

    return 0;
}
