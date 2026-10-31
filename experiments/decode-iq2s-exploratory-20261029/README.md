# IQ2_S whole-model decode exploration, October 29, 2026

The persistent IQ2_S candidate showed **no clear throughput gain** in this small whole-model test. It remains undeployed. Selected native `92abb8bc` with config `c43dd3d9` and prefill chunk 4096 was restored after both arms and verified again at 18:34 UTC without another inference request.

| Synthetic sequence case | Selected native tok/s | Candidate tok/s | Selected generated tokens | Candidate generated tokens | Selected client seconds | Candidate client seconds |
|---|---:|---:|---:|---:|---:|---:|
| Cold |53.759|54.272|3289|3223|65.570|63.738|
| Warm prefix |59.211|57.577|5297|2821|89.536|49.057|

Rates count all native generated tokens, including hidden reasoning. The descriptive changes were **+0.95% cold and −2.76% warm**. All four visible answers were identical correct JSON sequences containing integers 1 through 1024. Their full generated paths differed. Warm completion was faster with 46.74% fewer generated tokens, so this does not establish that the kernel accelerated equivalent work.

**Prose speed was not measured.** This predictable sequence task gives the draft model an easier target than general writing. There was one cold and one warm observation per arm, with no replication or statistical acceptance. No general quality, numerical equivalence, causal kernel speed or overall task speed claim follows.

## Preserved production settings

Both isolated arms used the same model, native images, Q8/check1/1, mode1, L22 scale1 projection over all 40 mainblocks, unchanged drafter, DSpark 0.65/max4, TP1 with automatic 19/21 placement, 24 CPU threads, all CPU experts in RAM and stream0. Production capacity stayed **1,048,576 total context tokens and 262,144 output allowance**. Benchmark requests retained cap 32768 and effort 100.

The synthetic input had 1429 tokens; warm prefix reuse was 1428. Output was not truncated or fitted. These small requests do not qualify near-filled 1M context or full 256K generation. Buffered first-visible stream timing is not true time to first token. Images, tools, coding and broad prose quality were outside this panel.

Selected executable: `92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1`.
Candidate executable: `da28ca8b108048990f5950e76909cccacacb9f921d8e37fad9f16b440bb513a6`.
Selected config: `c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa`.

## Qualification and lifecycle evidence

ROOT and the same dedicated Astra reviewer manually read the complete source/tests before the corrected FIRST 137 bounded CPU controls on each physical Mac and Ubuntu host. Both proofs matched 17 source files, 965 inputs and 137 test IDs. The frozen qualification pinned 2268 files plus its own hash. No native build or passed kernel-control replay was needed for this panel.

Each arm had separate current-owner/idle/source/resource admission, two natural correct requests, an independently bounded terminal audit and manual result review. Private native, private API and window exited 0. Old production owner closures were prospectively captured. The selected deployment was restored with sole GPU ownership, correct configuration, router/default DeepSeek, public401/authenticated200 and assembled READY/stop/DONE evidence. The final live observation checked process identity, executable/configuration, controlled flags, cgroup, units, idle state, kernel and resources without queuing another generation.

| Arm | Private native PID | Private API PID | Window | Minimum root free GiB | Swap delta bytes |
|---|---:|---:|---|---:|---:|
| X0 selected |2324111|2324040|20261029T172803Z|829.346|299008|
| X1 candidate |2424389|2424363|20261029T180231Z|837.636|0|

The final descriptive comparison ran once per physical host under the existing child-only CPU 30s/Linux AS 512MiB/wall 90s/nice 15/CUDA-hidden limits. Both produced byte-identical result `e7e5fb3b97dcbc3f608e2ef0e8c2ee3e89c571afaae53a0a28865c79b9e4519b`. Astra independently recomputed the arithmetic from saved terminal receipts.

## Preserved failures and limits

The earlier strict numerical mode remains **CLOSED_HOLD_TOKEN_PATH_DIFFERS**. This separately requested exploration did not relax its gate or qualify activation. Candidate kernel correctness 104 cases is a prerequisite, not whole-model numerical equivalence. The historical kernel-era hosted API exit-status gap remains explicit; these later arm closures do not retrofill it.

The original Mac FIRST CPU proof failed its final trace-glob assertion because `native-ready.json` also matched `native-*`. Its source, failed receipt and log remain unchanged. A reviewed correction used the trace-only glob and a new proof namespace; corrected controls passed on both hosts. A pre-child audit path refusal and a metadata-composer syntax refusal are also preserved. Neither launched a model or was silently regraded.

The window wrapper includes historical October25 GLM fields. They are not evidence that GLM ran during these arms. Its inner `maintenance_held` state describes the continued outer maintenance lease; the outer controller separately restored production.

## Evidence index

- [CLOSEOUT.json](CLOSEOUT.json), [final Astra review](FINAL_COMPARISON_ASTRA_REVIEW.json), [both-host comparison](EXPLORATORY_COMPARISON_FIRST_BOTH_HOSTS.json).
- [Final production observation](final-production-observation.json), [canonical publication](FINAL_CANONICAL_PUBLICATION.json), [final arm registry](exploratory-arms.json).
- [X0 audit](X0/terminal-audit.json), [X1 audit](X1/terminal-audit.json), both raw FIRST packets and hash manifests.
- Frozen criteria, fixture/token bytes, source maps, qualification, manual reviews, admissions, actual preflights, corrected CPU receipts and preserved failed lineage are included verbatim.

[ARCHIVE_MANIFEST.json](ARCHIVE_MANIFEST.json) maps every copied file to its original path and SHA256. Duplicate transport tar files and interpreter caches are omitted; their raw text payloads remain. No weights, native binaries, logits, conversation caches or user workloads are included. This is an operator evidence archive requiring its original qualification workspace and dependencies, not an installer or permission to replay closed arms. No additional model run, replication or promotion is admitted by this result.
