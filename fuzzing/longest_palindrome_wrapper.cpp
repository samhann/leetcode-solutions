// C++ wrapper for longest-palindromic-substring solution
// Reads input from stdin, writes output to stdout for cross-language fuzzing

#include <iostream>
#include <string>
using namespace std;

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

int main() {
    string s;
    getline(cin, s);
    Solution sol;
    cout << sol.longestPalindrome(s) << endl;
    return 0;
}
