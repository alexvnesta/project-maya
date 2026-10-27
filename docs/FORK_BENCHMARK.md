# Combined optimization comparison

The combined candidate is not selected. One baseline and one combined candidate were run on the same
host and frozen short panel, with one repeated coding request in each process. There was no per-PR sweep.

| Measure | Baseline | Combined candidate |
| --- | ---: | ---: |
| Cold 32,761-token native prefill | 50.7174 s | 97.9343 s |
| First coding native decode | 45.0033 tok/s | 44.9185 tok/s |
| First coding generated tokens | 12,631 | 9,411 |
| Image client completion | 4.8749 s | 7.1181 s |
| Repeated coding | Natural stop, 7,820 tokens | Deadline cancellation, 8,458 tokens; partial |

The frozen selection rule required at least 2% pooled coding decode improvement with both matched coding
observations positive, no more than 3% cold 32K prefill regression, and no material image/control regression.
The candidate fails the prefill limit and the repeat is incomplete. A shorter first coding client elapsed
is not a speed gain: the candidate generated fewer tokens, while native decode rate was effectively flat.

The tested candidate enabled HC/route fusion 2, decode trim 15, drafter VRAM cap 96, scoped load cache drop,
registered prompt copies, and flow 0. Flow 0 makes the registered-copy path reachable at TP1. This is a combined
configuration result; it does not identify which PR or flag caused a difference. The offline profile-refresh
tool is included in the fork but no new profile calibration was performed.

Both GPUs passed the actual startup arithmetic/byte/guard checks before requests. The unchanged five main
requests stopped naturally and passed the basic JSON/tool/image gates in both arms; exact-prefix cache reuse,
active+queued cancellation and recovery passed. Raw basic 5/5 and full 3/5 remain separate from offline code
checks. Each completed coding module and all supplied tests were read before bounded checks on macOS and
physical Ubuntu. Baseline main 28 tests, baseline repeat 17 tests and candidate main 13 tests passed, along with
2,207 independent cases/4,414 checks and four negative controls each. Candidate repeat code review remains UNRUN.

Both private runs closed their native/API/window processes with exit 0. Kernel and root/swap resource guards
passed. The original hosted native 92abb8/configuration was restored and verified through public 401,
authenticated model discovery and raw streaming READY. Context 524288/output default 131072/Q8/TP1/native images/
runtime projection remain selected; the measured main requests used cap 32768 and effort 100.

This single process pair is not order-balanced or statistical evidence, a p95 estimate, broad accuracy,
near-filled 512K input/full 128K output proof, or proof that any individual PR is beneficial. No candidate
activation or further sweep is planned from these results. Raw private receipts and original failed attempts
remain retained outside this repository; this document contains only aggregate qualification metadata.
