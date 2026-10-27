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
runtime projection were selected at that comparison; the measured main requests used cap 32768
and effort 100. The later capacity change below does not alter those comparison settings or results.

This single process pair is not order-balanced or statistical evidence, a p95 estimate, broad accuracy,
near-filled 512K input/full 128K output proof, or proof that any individual PR is beneficial. No candidate
activation or further sweep is planned from these results. Raw private receipts and original failed attempts
remain retained outside this repository; this document contains only aggregate qualification metadata.

## Capacity update: 2026-10-27

The unchanged selected native `92abb8` now allocates 1,048,576 context tokens, with a
262,144-token default output allowance. TP1, Q8 batch/check, native images, runtime projection,
DSpark, sampling policy and the frozen profile seed remain unchanged. The combined optimization
candidate above remains unpromoted.

A focused check observed actual native KV residency at 1,048,576 tokens, both-GPU Q8 and
projection checks, 3,903 CPU experts entirely in RAM and 11,457 GPU expert slots. Seven native
requests/eight HTTP requests passed the omitted-output-default probe, 32K typed JSON, native
image, typed tool, exact-prefix cache reuse, active/queued cancellation and recovery gates.
The omitted-cap request reached native with `max_new=262144` and stopped naturally after eight
tokens. Native, API and window exits were 0; kernel, disk/swap and DSI1 cleanup checks passed.
Production startup, authenticated discovery and raw streaming READY passed after activation.

Two initial harness attempts remain unqualified: a strict observation-path refusal before
inference, then a wrapper false negative for a valid `tool_calls` finish. Their original
receipts remain unchanged; the latter left cache/cancellation/recovery UNRUN. The corrected
phase was manually reviewed and passed 111 bounded CPU controls on each of macOS and physical
Ubuntu, including the entire phase body with scripted API/native boundaries and negative
controls. Those CPU controls are separate from the actual native results above.

This was an allocation and targeted-functionality check, with at most 32,761 prompt tokens.
It does not establish near-filled 1M quality, latency or capacity behavior, full 256K generation,
a speed gain or broad accuracy. With the full output allowance reserved, context leaves
786,432 prompt tokens before framing. Old explicit lower request caps are still honored.
