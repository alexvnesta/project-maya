# S2-inspired Frankenstein reconstruction, November 1

This is a new reconstruction effort after the earlier model comparison closed. Current production remains GSQ-RCO/native92/configc43, TP1/chunk4096. The new hybrid engine compiled successfully on physical Ubuntu. Its IQ3_S overlay and remaining original-expert sources are being materialized. No hybrid GPU inference, speed comparison or default activation has occurred.

The supplied October 30 followup changes the preferred target from the older document: use original Maya-S, IQ3_S gate/up on layers 24-28, and original MXFP4 for a selected CPU expert set, initially static. Exact private S2 IDs, calibration and engine commits remain unavailable. Public ingredients allow a local reconstruction; they do not establish byte-identical private S2 or its reported speed/quality.

## Work completed

| Component | Current evidence |
|---|---|
| Maya-S base | All eight published assets,347,445,667,721bytes, completed and passed their full published SHA checks. Downloader exited0 at2026-11-01T17:32:12UTC. |
| Native engine | Actual first configure/compile exited0,699.56s compilation,44,728,824-byte artifact `c942a4cf8047d154dd2201b3541b4653c70d88e687b3c014dc649eb09beaac86`. Source/helper controls passed each physical host, plus existing bounded owned-build controls. No GPU/model execution yet. |
| CPU representation | Exactly1870 selected CPU experts retain all three original MXFP4 roles. Their IQ CPU copies are excluded. All remaining CPU experts must be in RAM. StaticTP1 only; sensitive-layer prompt batches use their original CPU representation and other prompt layers retain the pack's IQ path. |
| Runtime arithmetic prerequisite | The new native prospectively compares eight selected experts, all three roles, one/four strided rows against its established homogeneous MXFP4 CPU implementation. This actual startup check has not run yet. |
| IQ3_S overlay | All3840 gate/up matrices on layers24–28 will be encoded from original MXFP4. Qualified four-worker CPU conversion is running. Upstream NULL-imatrix squared-weight-magnitude weighting is used; this is not the private author's Hessian/calibration recipe. |
| Original sources | Five sensitive-layer shards are complete. The remaining conservative original trunk closure is40shards00003–00042,295,672,271,408bytes total. It excludes dense/head/drafter/Engram shards. Passive acquisition is running; it is not the frozen1870selection. |
| Actual placement / native payload | Metadata is constructed. One separately qualified no-inference1M placement will freeze actual expert IDs. The35GB original CPU payload and real hybrid fit remain pending. |

The new source and actual build receipts are in `engine-build-and-materialization-1759/`. CPU/build results establish source and component behavior, not whole-model quality, speed or deployment. Earlier receipts remain unchanged.


## Concrete artifact sizes

- Original native CPU pack for1870 experts, all three roles: **35,157,196,800bytes**.
- IQ3_S gate/up overlay for all experts on layers24-28: **19,464,192,000bytes**.
- That overlay is **7,785,676,800bytes larger** than those Maya-S IQ2_XXS gate/up matrices.
- Corresponding original weight+scale planes total24,064,819,200bytes, distributed across five complete source shards totaling36,959,958,872bytes.

The native CPU bytes replace selected IQ CPU copies. Adding them while retaining all of those original IQ copies in CPU RAM would waste memory. The retained IQ representation on disk may still be needed by prefill/GPU paths. The engine must explicitly handle this distinction rather than editing homogeneous-layer pack metadata alone.

## 1M capacity and engine gap

Our actual original Maya-S TP2 run at1,048,576total context copied6490CPU experts into RAM (71.9GB rounded), versus the author's5753 reported at256K. That initialization took407.6seconds for CPU expert copies. CUDA0 had1918MiB free and CUDA1 had9534MiB free. The native/source record must account for this imbalance and the IQ3_S growth before any hybrid admission.

The public source already supports distributing the three unchanged drafter blocks (`DS4_DRAFT_DEV`). The specific0,1,1 distribution is a source-backed candidate for the observed imbalance, not an admitted test or measured speed claim. Actual GPU IDs/slots and RAM remain to be frozen from the resulting candidate. The existing private80GiB fence and8GiB host margin remain; no silent context/output reductions or fence increases.

Latest Maya has optimized IQ2/IQ3 CPU rows and family-specific PDEP avoidance for some formats. A generic slow-PDEP explanation does not establish a2x per-expert improvement on our current engine. In one owned short cold task only0.5% of expert picks used the CPU, so workload-specific full-model measurements matter.

## Remaining essential checks and selection

Alex requested a small practical comparison, not a new broad benchmark campaign:

1. Complete the original-source acquisition and original-to-IQ3_S conversion; preserve all source and output SHA receipts.
2. Capture actual1M static GPU/CPU placement, select1870CPU IDs and make the lossless original three-role payload.
3. Check actual hybrid allocation, CPU arithmetic, finite numerical behavior, known answers, code/prose, images/tools, cache/cancel/recovery and owned lifecycle/resources.
4. Compare one small matched natural-completion prose/coding panel against current production. Keep prefill, decode, total time, output/reasoning lengths, native/client/cache/draft counters and actual placement. A prefill slowdown alone does not reject it.
5. Change the default only after all essentials pass and combined natural task time improves by at least10%, without an individual task regression above10%. No quant/TP/cache sweep or universal-quality claim follows from this small panel.

1,048,576total context,262,144output allowance, effort100, benchmarkcap32768, DSpark, images, Q8/check1/1, mode1 and the L22projection across all40main blocks remain requirements. Configured capacity does not prove near-filled1M or full262144generation bounds. No expert deferral, FP8 projection switch, pruning, hardware/driver/power/VM change or cache cleanup.

`PLAN.json`, `STATE.json`, `FIRST_COMPONENT_PROOFS.json`, `CAPACITY_AND_ENGINE_FINDINGS.json` and the exact component directories carry the source/proof paths. The source archive is provenance; it is not a ready-to-run installer or permission to replay old arms.
