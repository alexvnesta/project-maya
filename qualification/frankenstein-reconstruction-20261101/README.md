# S2-inspired Frankenstein reconstruction, November 1

This is a new reconstruction effort after the earlier model comparison closed. Current production remains GSQ-RCO/native92/configc43, TP1/chunk4096. No new hybrid has been built, GPU-tested or deployed.

The supplied October 30 followup changes the preferred target from the older document: use original Maya-S, IQ3_S gate/up on layers 24-28, and original MXFP4 for a selected CPU expert set, initially static. Exact private S2 IDs, calibration and engine commits remain unavailable. Public ingredients allow a local reconstruction; they do not establish byte-identical private S2 or its reported speed/quality.

## Work completed

| Component | Current evidence |
|---|---|
| Maya-S base | New isolated download namespace; same pinned revision and complete SHA manifest. First43 acquisition controls each physical Mac/Ubuntu. Transfer paused safely for user work with16,508,780,544bytes retained, then resumed under a fresh qualified idle/owner guard. Raw current acquisition-state is authoritative. |
| Expert selection and byte plan | First26 controls each host with exact source/IDs; all sensitive-layer CPU experts covered before remaining native slots selected by use counts. Requires actual frozen GPU IDs, never aggregate slot inference. |
| Native MXFP4 codec | New down support as well as gate/up. First9 controls each host, including complete [5120,2304] down and [2304,5120] gate/up geometries, all nibble/finite exponent values and refusal of incomplete/NaN input. Lossless CPU byte mapping only. |
| Original sensitive-layer sources | First7 controls each host with exact4source/7input maps. All3840gate/up matrices and weight/scale planes located in official shards27-31 at immutable original revision. |
| Upstreams | DSX main98f1259 and Maya main3589d6f/v1.1.46 freshly checked. PR741 parity is unmerged and excludes MXFP4/mixed layers and TP; PR747 direct-NH path is single-member. Neither supplies this selective native CPU lane. |

These85 controls per host qualify only the acquisition and source/codec components, not whole-model numerical behavior, speed, quality or activation.

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

## Next steps and selection

1. Finish/verify the pinned base acquisition; retain new partial/completed assets.
2. Qualify an original-MXFP4-to-IQ3_S encoder and calibration. Do not upconvert existing IQ2 bytes and claim recovered precision.
3. Qualify a distinct1M initialization/placement diagnostic, then freeze exact GPU IDs and select the1870original CPU experts from a public/owned-synthetic routing profile.
4. Build the checked original CPU payload and explicit selective CPU representation/dispatch, avoiding duplicated RAM copies. Static placement first; adaptive swaps need separately defined representation semantics and qualification.
5. Prove component/numerical-distribution, code/prose/tool/image/cache/cancel/lifecycle/resource gates before full-model timing.
6. Compare matched natural completion time and answer quality against current production and the needed Maya-S control. Record prefill, decode, native/client/output/reasoning/cache/draft counters. **A prefill regression alone will not reject the candidate.** Earlier failed screens remain historical records; new criteria require new separately frozen comparisons.

1,048,576total context,262,144output allowance, effort100, benchmarkcap32768, DSpark, images, Q8/check1/1, mode1 and the L22projection across all40main blocks remain requirements. Configured capacity does not prove near-filled1M or full262144generation bounds. No expert deferral, FP8 projection switch, pruning, hardware/driver/power/VM change or cache cleanup.

`PLAN.json`, `STATE.json`, `FIRST_COMPONENT_PROOFS.json`, `CAPACITY_AND_ENGINE_FINDINGS.json` and the exact component directories carry the source/proof paths. The source archive is provenance; it is not a ready-to-run installer or permission to replay old arms.
