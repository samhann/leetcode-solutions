// C++ wrapper for remove-k-digits solution
// Reads "num k" from stdin, writes output to stdout for cross-language fuzzing

#include <iostream>
#include <string>
using namespace std;

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

int main() {
    string num;
    int k;
    cin >> num >> k;
    Solution sol;
    cout << sol.removeKdigits(num, k) << endl;
    return 0;
}
