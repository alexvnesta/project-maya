# Maya 1.1.45 / public Maya-S qualification checkpoint

Upstream: `mw00/project-maya` `6ecbd3cbc5330b57f70cd5cf8a5c42eb8ef950cc` (1.1.45). Retained local guards preserve the existing L22 scale-1 projection on all 40 main blocks, leave the drafter unchanged, and check prompt-copy storage after final pinning. Upstream 1.1.45 adds the recent-slot drain safety fix. The new native is isolated and **not deployed**.

Native SHA-256: `adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f`.

The selected production native remains `92abb8bc…`, config `c43dd3d9…`, chunk4096. It was restored and verified after every attempted phase. The most recent restoration receipt binds native330807/invocation7ad654ccf35845e8825fbb7b829e1092; refresh that dated binding before another action.

## First accepted compatibility response

The separately frozen `maya145-placement-v2/DTP2` phase used public Maya-S and its published DSpark drafter at **1,048,576 total context and 262,144 output allowance**, effort100, images, mode1, chunk4096, Q8/check1/1, 24 CPU threads and all CPU experts in RAM. TP2 uses source-supported uneven GGUF blocks and FP32 reductions. This is not the author's private S2 engine.

| Observation | Actual result |
| --- | --- |
| Prompt | 44 tokens, cold/reused0 |
| Emitted output, including reasoning | 186 tokens, natural stop |
| Final literal | Correct |
| Native prefill | 631.9 ms |
| Native decode | 4,193.6 ms, 44.3533 tok/s |
| Client completion | 4.8491 s |
| Actual DSpark | 68 rounds; 109/179 drafts accepted |
| Native / private API / canonical window | Exit0 / exit0 / exit0 |
| Kernel faults / swap-out delta | None / 0 |
| Private fence | Actual80GiB, swap0; original properties restored |
| Production verification | Public401, authenticated models200, assembled READY/stop/DONE |

**This short startup check is not a steady decode benchmark, a comparison win, general quality proof, numerical equivalence, or a near-full-context/output test.** Longer correctness/numerical, prose/coding and prefill comparisons remain pending. No new deployment is admitted.

## Preserved failures and separate closures

- Maya1.1.44 CTP2 loaded and closed cleanly before inference. Its stale observer expected resident vision memory; the current engine reports borrowed chunk room. The wrapper also installed76GiB rather than the intended80GiB. That failed attempt remains HOLD.
- Maya1.1.45 RTP2 loaded and closed cleanly before inference. The validator incorrectly counted two identical placement snapshots as four owners. It remains HOLD. A distinct parser-only family records identical repeats and rejects conflicting snapshots. Its first CPU controls also validate the actual saved startup schema without regrading the old arm.
- DTP2's first offline terminal auditor returned1 because it expected the historical `public-ready-sse.txt`; the producer owns `public-default-output-request.json` and `public-default-output-sse.txt`. The rc1 remains preserved. A first saved-data continuation then hit a missing local window variable. Its rc1 is also preserved.
- A separately source-reviewed continuation with seven bounded controls on each physical host completed the missing downstream checks using the existing qualified default-output consumer. It performed no new inference, native start, restart or GPU window. Neither earlier auditor result was changed to success.

The archive contains original sources, source/input maps, first CPU receipts, failed and successful owned controller/window receipts, raw token/DONE/STAT evidence and selected restoration evidence. `ARCHIVE_MANIFEST.json` hashes every exported file. Model weights, private caches, images and logits are excluded. The original qualification paths refer to canonical Ubuntu locations; archive paths are an explicit evidence mapping, not a substitute for action-time verification.

## Gates before more GPU work

The unchanged native passed61 retained guard controls and37 build-lifecycle controls on each physical host. The DTP2 observer/controller, profile and independent auditor passed58/21/14 exact bounded CPU controls on each host; the prospective recovery wrapper passed61 each. All child-only CPU/AS/wall/environment bounds and raw failures are retained.

Every next fixture/runtime/controller delta requires its own manual source/test read, matching physical-host CPU proof, fresh current-owner/idle/resource checks and explicit single-phase admission. Keep the1200s window/1000s soft/200s cleanup, root132GiB admission/120runtime, swap delta<1GiB, private cache8GiB/log4GiB, benchmark32768 and effort100. Actual draft execution is required for subsequent speed measurements. Preserve output length, native/client/cache/draft counters and placement; wrong, capped, partial and UNRUN results block advancement.

Maya-S is first. A similar public S2 hybrid reconstruction follows only after its baseline is understood; credits alone do not establish the author's private expert selection or engine. The Unsloth acquisition remains paused with verified assets and partials retained. No weight set is deleted.
