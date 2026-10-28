# Selected prompt-skip CPU fixture

These extracts pin the selected runtime source, rather than assuming that this
fork's current HEAD is the deployed binary. `selected-skip-fragments.json` records
the source hashes and exact methods/plan. The test uses synthetic layer metadata;
it does not run a model, CUDA, numerical KV operations or a capacity test.

From the repository root, using an existing compiler:

```sh
c++ -std=c++17 -O1 -Wall -Wextra -Werror -I tools/ds4_prompt_skip_selected tools/ds4_prompt_skip_selected_test.cpp -o /tmp/ds4-selected-skip-test
/tmp/ds4-selected-skip-test
```

The unchanged fixture passed 62 exact named controls on macOS and physical Ubuntu
under separate bounded compile/test children. The geometry controls distinguish
mode1's suffix requirement from an arbitrary balanced split; KEEP overrides and
mode2 are excluded from the qualified serving profile. The minimum 3692 applies
to newly fed rows, not the total saved history. CPU results do not qualify GPU
performance or numerical equivalence.
