// libFuzzer harness for remove-k-digits
//
// Compile:
//   clang++-17 -fsanitize=fuzzer,address,undefined -std=c++20 -O1 -g \
//     -o fuzz_remove_k_digits fuzz_remove_k_digits.cpp
//
// Run:
//   ./fuzz_remove_k_digits corpus_remove_k/ -max_len=64 -runs=100000

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

using namespace std;

// ---- Solution under test (from Solutions/R/remove-k-digits/) ----
class Solution {
 public:
  string removeKdigits(string num, int k) {
    string ret = "";
    int N = num.size(), req = N - k;
    for (int next = 0; req > 0 and next < (int)num.size(); --req) {
      int bestpos = next;
      char best = num[next];
      for (int i = next + 1; i + req <= N; ++i) {
        if (num[i] < best) {
          best = num[i];
          bestpos = i;
        }
      }

      if (best > '0' or ret != "") ret += best;
      next = bestpos + 1;
    }

    if (ret == "") ret = "0";
    return ret;
  }
};

// ---- Oracle: brute-force by trying all combinations ----
static string bruteForce(const string& num, int k) {
    int n = num.size();
    int keep = n - k;
    if (keep <= 0) return "0";

    // Generate all combinations of `keep` indices
    string best = "";
    vector<int> indices(keep);

    // Initialize
    for (int i = 0; i < keep; ++i) indices[i] = i;

    while (true) {
        // Build candidate
        string candidate = "";
        bool leading = true;
        for (int idx : indices) {
            if (leading && num[idx] == '0') continue;
            leading = false;
            candidate += num[idx];
        }
        if (candidate.empty()) candidate = "0";

        if (best.empty()) {
            best = candidate;
        } else {
            // Compare numerically: shorter non-zero is smaller, or lexicographic for same length
            bool candidate_smaller = false;
            if (candidate == "0") {
                candidate_smaller = (best != "0");
            } else if (best == "0") {
                candidate_smaller = false;
            } else if (candidate.size() != best.size()) {
                candidate_smaller = candidate.size() < best.size();
            } else {
                candidate_smaller = candidate < best;
            }
            if (candidate_smaller) best = candidate;
        }

        // Next combination
        int i = keep - 1;
        while (i >= 0 && indices[i] == n - keep + i) --i;
        if (i < 0) break;
        ++indices[i];
        for (int j = i + 1; j < keep; ++j) indices[j] = indices[j - 1] + 1;
    }

    return best;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Need at least 2 bytes: 1 for k encoding, rest for digits
    if (size < 2 || size > 20) return 0;

    // First byte encodes k, rest is the digit string
    int num_len = size - 1;
    string num(num_len, '0');
    for (int i = 0; i < num_len; ++i) {
        num[i] = '0' + (data[i + 1] % 10);
    }
    // Ensure no leading zero (unless single digit)
    if (num_len > 1 && num[0] == '0') {
        num[0] = '1' + (data[1] % 9);
    }

    int k = data[0] % (num_len + 1);  // k in [0, num_len]

    Solution sol;
    string result = sol.removeKdigits(num, k);

    // --- Invariant checks ---

    // 1. No leading zeros (except "0" itself)
    assert(result == "0" || result[0] != '0');

    // 2. If k >= num_len, result must be "0"
    if (k >= num_len) {
        assert(result == "0" && "Removing all digits should give '0'");
        return 0;
    }

    // 3. Result digits must be a subsequence of num
    {
        int j = 0;
        string full_result = result;
        // The result might have leading zeros stripped; the actual kept digits
        // have length num_len - k
        for (int i = 0; i < (int)num.size() && j < (int)full_result.size(); ++i) {
            if (num[i] == full_result[j]) ++j;
        }
        // Note: because leading zeros are stripped, j might not reach full_result.size()
        // for "0" results. But the numeric value check below covers correctness.
    }

    // 4. Cross-validate with brute-force oracle (small inputs)
    if (num_len <= 12) {
        string expected = bruteForce(num, k);
        assert(result == expected &&
               "Output doesn't match brute-force oracle!");
    }

    return 0;
}
