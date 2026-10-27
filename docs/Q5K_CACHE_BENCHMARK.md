# Combined Q5_K/cache migration comparison

Decision: **retain the selected production native; do not activate this candidate**. The first pair failed the frozen improvement rule, so the conditional B2/A2 confirmation was not admitted. No per-PR sweep or replay followed.

| Measure | Selected baseline | Combined candidate |
| --- | ---: | ---: |
| Coding native decode | 43.9307 tok/s | 42.3222 tok/s |
| Coding output tokens | 12,295 | 11,685 |
| Cold 32,761-token native prefill | 51.3200 s | 51.7321 s |
| Image client completion | 5.1287 s | 4.8435 s |
| Image output tokens | 78 | 46 |
| Image native prefill | 3.4476 s | 3.5982 s |
| Summed main client time | 349.5252 s | 348.1459 s |
| Main generated tokens | 12,612 | 12,039 |

Coding decode regressed **3.6614%**; pooled main native decode regressed **3.6760%**.
Cold 32K prefill increased **0.8030%**. The slightly shorter client totals are accompanied by fewer output tokens; they do not establish a task speedup. In particular, the candidate image response generated 46 rather than 78 tokens while its prefill was slower. No component-specific speed claim follows from this combined comparison.

The candidate retained the existing fork changes and kept the previously rejected fusion/trim/drafter/registered-copy/flow bundle disabled. Its new factors were `DS4_Q5K_SHARED_SUMS=1`, `DS4_CACHE_REUSE_MIB=2`, and the mapped-input publication guard derived from Maya PR550. Both arms used TP1, Q8 batch/check, 1,048,576 context allocation, native images, runtime ablation, DSpark confidence .65/max4/cumulative0, 24 CPU threads, prefill chunk1024, and the same frozen placement seed. Actual placement was 11,457 GPU expert slots and 3,903 CPU experts, all in RAM, in both arms. Production's output default remained262144; the five frozen main requests retained cap32768 and effort100.

The stricter admission policy recorded 32,460 deferral attempts and 2,272 completed swaps cumulatively by candidate shutdown. Deferrals are not unique misses, transfers, or bytes saved. Coding native GPU expert hits/lookups declined from3,795,224/3,813,855 (99.5115%) to3,533,102/3,576,465 (98.7875%). This is consistent with a migration-versus-CPU-work tradeoff, but the combined experiment does not isolate causality. Draft acceptance and output lengths also varied; all per-case native/client/cache/length/acceptance data remain in the comparison artifact.

Both GPUs passed the new original-versus-optimized Q5_K startup check before candidate requests: 72 synthetic jobs and12,211 output values per device, bit-for-bit equality, padding/guards, columns1–16, mixed batches and large-K fallback. Both arms passed existing Q8 and ablation checks. These are bounded arithmetic checks, not whole-model equivalence.

All10 main responses across the pair stopped naturally, with no capped, partial, or unrun main cases. Each arm passed typed JSON/tools/images, exact-prefix cache reuse (32,760/32,761 tokens), active+queued cancellation and recovery; 9 native/10 HTTP requests each. API-owned DSI1 leftovers were empty. Raw basic5/5/full3/5 grades per arm remain unchanged and separate from offline coding adjudication. Both generated modules and all15 baseline/17 candidate supplied tests were manually read before2,207 independent cases/4,414 checks, supplied tests and four negative controls passed on each of macOS and physical Ubuntu.

CPU qualification is separate:19 policy/layout/actual-method controls,22 build-admission controls, and134 current-context API/lifecycle/mode controls passed on each host, with exact source and test inventories. Initial CPU receipt buffering, adapted-test imports/context metadata and the system-Python dependency refusal remain preserved; corrections used the existing virtual environment and unchanged bounds, with no dependency installation or relaxed limit. The isolated SM80 native build passed; all1,051 source files and dependencies/RUNPATH were audited without executing the engine. The legacy supervisor's state inherited an old commit label; the exact candidate patch/all-file manifest and static audit establish built source `e6034d7da591bc5c848d7f6143387343904ea34e`.

Both private native/API/window exits were0 and kernel/resource guards passed. Minimum root free was845.68/837.34GiB; system-wide swapout was150/410 pages, below the1GiB guard and not attributed to the model. Selected `92abb8` hosting was restored after each arm, with unchanged config`45dac9`, sole GPU ownership, protected public401, authenticated model discovery200 and raw streaming READY/stop/DONE. A final independent metadata check confirmed1M context,256K output, Q8 flags1/1, TP1, images, ablation, both units active/Restart=no, and no experimental flags.

This is one matched process pair on a short panel, not order-balanced/statistical/p95/broad-accuracy/near-filled1M/full256K-output proof. The candidate was not promoted. The conditional confirmation is closed and no further experiment is scheduled.
