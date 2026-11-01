# DeepSeek model selection and cleanup, 2026-11-01

**Selected: the existing GSQ-RCO IQ2_XS deployment, native `92abb8bc…` / config `c43dd3d9…`, TP1 automatic 19/21 and chunk 4096.** The completed comparison did not qualify a replacement. No new model or native binary was activated.

The deployment retains 1,048,576 TOTAL context, 262,144 output allowance, native images, the deployed DSpark drafter at .65/max4, Q8/check1/1, mode1, L22 scale1 projection across all 40 main blocks with drafter untouched, 24 CPU threads, all CPU experts in RAM and stream0. The final live API/native owner stayed unchanged throughout filesystem cleanup.

## Fresh matched meaningful cold-prefill comparison

Same complete original 8,469-token input/IDs, zero reuse, request cap 32,768, effort 100, seed 1, temperature 1 and top_p 1; no fitting, truncation, numerical dumps or timeout changes. This compares whole profiles, including model/Engram/template/native/TP factors, rather than isolating TP causality.

| Profile | Cold prefill | Generated tokens | Decode ms | Client seconds | Known answer |
|---|---:|---:|---:|---:|---|
| Selected GSQ-RCO/native92 TP1, A1 | 8,862.4ms |366|7,318.0|16.222|Correct, natural stop|
| Original Maya-S/adff TP2/direct1, B1 |10,244.7ms|179|3,456.6|13.735|Correct, natural stop|

Maya-S prefill regressed **15.5974%**, exceeding the frozen 3% maximum. The first pair is CLOSED FAIL. B2/A2 and later formal sustained-prose/coding comparisons against native92 were not admitted. Different natural reasoning/output lengths mean the shorter client time is not an equal-work throughput improvement; both observed end-to-end times remain recorded. Short 179/366-token decode is not a sustained coding/prose benchmark.

Both arms passed independent source-bound terminal audits, full ROOT final+reasoning review, actual native/private API/window/controller exit0, exact1M/262K policy/placement/cgroup/flags checks, DSpark execution, zero owned swap or OOM, clean kernel and selectedproduction restoration/authentication/assembled READY/stop/DONE. The final qualification had 163 core, 11 profile, 16 auditor and 64 recovery controls each physical Mac/Ubuntu with exact source/input/test IDs. Earlier CPU/observer/map refusals remain separate historical evidence, without model retries or regrades.

## Completed short-task observations

These are whole original public tasks at the same configured 1M/262K allowance, cap 32768 and effort 100 and respective drafter. Different reasoning/output lengths prevent equal-work or topology-only causal claims.

| Profile | Prose tokens / native tok/s / client seconds | Coding tokens / native tok/s / client seconds | Disposition |
|---|---|---|---|
| Maya-S TP2 |6384 /62.05 /104.85|16869 /56.66 /299.28;17885 /57.25 /313.91|Balanced new candidate; rejected by fresh matched cold-prefill gate above|
| Maya-S TP1 |5647 /57.19 /100.61|14413 /50.79 /285.32|Completed control observations; no replacement qualification|
| Public HGU hybrid |2628 /44.06 /61.72|10622 /60.31 /177.70;14264 /59.93 /239.63|Reversed coding screen failed: +4.68%rate below 5% minimum and +6.68%short-prefill beyond 3%; no fifth arm|
| Unsloth UD-IQ2_XXS |16478 /67.98 /244.18|15774 /53.32 /297.30|Mixed workload behavior; fastest prose token rate used much more output. No matched native92 quality/speed win established|

All covered coding outputs and supplied tests were fully manually read before FIRST bounded independent 4414 checks across 2207 cases plus supplied tests and 4 negatives on each physical host. All passed. Prose was fully read. These are bounded task screens, not a broad reasoning-quality ranking or proof that any quant is universally inferior.

Exact private Discord S2 remains unavailable: the public HGU variant only replaces L25/26 gate/up with official MXFP4; it does not contain private T16 overlays or private engine additions. Q2_K_XL was not downloaded/tested. Near-filled 1M/full 262144 generation runtime bounds remain unproven.

## Cleanup and final production check

The user authorized cleanup after selection. **15 complete exclusive unselected payload files, 664,358,869,199 bytes (618.73 GiB), were removed**: six Maya-S GGUFs, six Unsloth GGUFs, the public HGU overlay and its two official source shards. This is a deployment-selection cleanup, not a globalquality judgment.

Selected RCOweights/Engram/DSpark/vision/seed/projection/executable/config and shared published Maya-S drafter/vision were protected. All caches/namespaces, pack/tokenizer/Engram metadata, source/build records, prior failed/partial/raw receipts and upstream download revision/SHA provenance remain. Future unselected-model use requires redownload/new qualification; closed arms cannot be replayed.

The deletion plan matched every file against actual native-use/constructor dev/inode/size/mtime/ctime signatures and historical fullSHA provenance, without rereading 664GB. Exact 15-path sudo-lsof found no open/mapped payload; no active candidate/download/constructor process referenced them. The final cleanup operation had 30 FIRST real-temp-file safety controls per physical host with exact3source/6input/30IDs, child CPU30s/LinuxAS512MiB/wall90/nice15/CUDAhidden. It durably recorded intent, confirmedunlink, parentfsync and postcheck separately for every file; zero unknown deletions.

Two earlier cleanup-wrapper failures are preserved: an incorrect free-lock assumption, and a missing observer receipt directory. Both stopped before unlinking any payload, released any owned CPU claim, and left production untouched. Separately reviewed source/proofs/operation namespaces closed these issues. The existing hosting API inherits the canonical maintenance flock; the final operation verified its exact bound PID/kernel/FD lock witness, kept that lock/service untouched, and used an exclusive persistent attempt plus exact canonicalCPUclaim under the cooperative ownership protocol. This is not an independent OS security/CAS claim.

Actual final cleanup child 1197850 exited0 in 4.473s. Final production verification at 10:53:03 UTC passed with the SAME API1166336/native1166373/binding6bd4a6d9c93243ce999dca37f7ce7f79. Both existing units are active/Restart=no/defaultDeepSeek, source/config/exe/cgroup/flags/soleGPUowner and protecteddependencies unchanged. Public models401/authenticatedmodels200 and assembledREAD+Y/stop/DONE passed. Root free was 821.489 GiB. The final READY probe reused its existing selected cache; it is availability evidence, not a cold-speed benchmark.

## Evidence

- `SELECTED_PRODUCTION_LOCK.json`: exact selected profile, limits and final receipt pins.
- `FINAL_PRODUCTION_VERIFICATION_FIRST.json` and `POST-CLEANUP-PRODUCTION-VERIFY-FIRST/`: live selected identity, units and raw public SSE.
- `PAYLOAD_REMOVAL_TARGET_R3_RESULT_FIRST.json` and `PAYLOAD_REMOVAL_TARGET_R3_FIRST.jsonl`:15 actual durable unlinks/zero unknowns.
- `CLEANUP_PLAN.json`, `DEPENDENCY_AUDIT_FIRST.json`, source reviews, both-host CPU and historical HOLD directories: bounded housekeeping provenance.
- Sibling `../formal-prefill-comparison-20261101/`: separately frozen fresh A1/B1 comparison, source/proofs/full raw results.
- Sibling `../model-short-task-20261101/`: all ten short observations and independent generated-code checks.

All remaining comparison/build/download/activation work in this selected campaign is closed. The existing production setup remains available. No global claim of bestquant, numericalequivalence, full 1M runtime or equal-work whole-task speedup is made.

The copied qualification source is preserved for review. Running it requires the original canonical qualification directory layout and fresh authorization; these closed historical arms are not portable rerun commands.
