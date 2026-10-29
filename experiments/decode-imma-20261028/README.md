# Experimental Q5_K tensor-core decode candidate

The candidate is on hold after full-model numerical testing. All four synthetic answers were correct, but generated token paths differed from the baseline and failed the frozen exact-state gate. The qualified chunk4096 profile and native92 executable remain selected, with the same model, quantization, quality settings, native images, runtime projection, 1,048,576 total context and 262,144 output allowance. No generation-speed gain or promotion is claimed.

The candidate isolates [Maya PR624](https://github.com/mw00/project-maya/pull/624), head1872501868fee0a1c40b13de76fa7b4380ab2abf, against the exact selected native source. It uses int8 tensor cores for eligible multirow Q5_K dense GEMVs on SM80+. Integer dot products and the original floating-point recurrence are retained by design. The isolated GPU kernel passed exact comparisons on both physical devices. Whole-model numerical equivalence remains unproven; the source claim alone does not qualify deployment.

The port makes the threshold apply to every job in a batch, adds test-only dispatch accounting and provides a bounded correctness-only test entry. It excludes the earlier losing shared-sums/cache bundle and does not import Maya's newer parallel protocol. The flag defaults off; threshold2 is the first proposed factor.

## Evidence and remaining gates

SOURCE.json records the exact selected source and candidate hashes. CPU.json records first bounded qualification on macOS and physical Ubuntu:478 checks each, matching source maps and case IDs. These controls exercise the actual dispatch predicate and strict device/Q8 admission helpers. They do not compile or run CUDA. Separate compiler/lifecycle controls passed on both hosts before compilation and the first GPU window.

The executed GPU fixture covers110 prequantized GEMV cases and12 public GGUF/Q8 integration cases per device. It checks actual NG1/NG2/fallback dispatch, all1–16 column counts, full reduction widths, row tails, padded strides, mixed batches, output guards and small deterministic extreme/subnormal cases. Its command accepts only device0 or1, requires Q8batch/check1/1 before CUDA setup, and runs the actual Q8 startup check. It has no implicit timing benchmark.

GPU.json records the first actual build and 244 passing GPU cases, a clean bounded window and verified restoration of selected4096. Native integration, whole-model equality, task quality, cancellation/resources and replicated decode performance remain separate gates before promotion. This patch is intended for the selected source hashes; applying it to an arbitrary upstream checkout is not qualified.

The first unchanged-object control relink reproduced the selected native92 bytes exactly. The new candidate native is bef0b4d37e4ca028698d69babe227e23aa701c00d2bb1a706b821f1e98e4367a. It has now run in one separately qualified private numerical window and has not been deployed.

MODEL_NUMERICAL.json records two fresh numerical arms: selected92/IMMA0 and candidatebef0/IMMA2. FIRST90 bounded runtime/controller/entry/auditor CPU controls passed on each physical host with eight matching source files,898 input pins and matching case IDs, following a separate63-control component proof. Each GPU arm checked1668 actual file pins plus qualification self, retained the32768 benchmark cap and effort100, and used fresh private cache state. All four requests naturally stopped with correct typed answers, positive draft acceptance, expected cache reuse and finite retained logits. Native, API and window exits were0, kernel/resource guards passed, and selected4096 was publicly verified after each arm.

The exact comparison remains HOLD_TOKEN_PATH_DIFFERS: baseline/candidate output lengths were196/157,156/195,69/224 and180/169. Rows from speculative verification cannot be aligned generically with emitted tokens after divergence. A bounded offline check found the cold initial prompt-logit row byte-identical before sampling. This narrows the investigation to later draft/verify/sampling/state behavior and does not establish its cause or excuse the failed gate. The selected native also retains a sampling counter across requests, so later requests inherit earlier output-length differences. No timed performance arm, confirmation or activation followed this result.

The archived model-qualification sources require the original qualification workspace and its exact inherited runtime/assets. They are evidence sources, not a standalone deployment installer. Raw receipts and the original failed mock/preflight metadata remain retained in that workspace; this summary does not silently replace them. GPU.json remains the historical kernel-only checkpoint from before model execution.

## Upstream comparison

[Maya v1.1.36](https://github.com/mw00/project-maya/releases/tag/v1.1.36) includes CPU worker correctness, NUMA and MXFP4 activation-copy changes, plus parallel drafting. The NUMA and MXFP4-copy mechanisms do not directly establish a gain for this single-NUMA-node IQ deployment. [PR622](https://github.com/mw00/project-maya/pull/622), lazy drafter-head rows, is a separate follow-on candidate.

The [SeriousRising CMP170HX recipe](https://github.com/SeriousRising/ds41-flash-cmp170hx/tree/1e5a6a84b03c492522d51b301ab9e4ba09339e50) pins engine4fa4ba55717bdfe71fdc923d39d589d3cfc1311f. Its IMMA work overlaps this candidate. Unique leads include HC pre-normalization/fusion and tensor-core split attention. The latter explicitly changes numerical results and needs a separate numerical review. FLOW/PIPE changes need additional caller and lifecycle review.

Its reported47–52tokens/s uses a different quantization/profile,512K context, vision off, different CPU allocation and effort settings. Those numbers are not a matched comparison to this deployment, and its configuration, hot-expert profile and model files are not imported.
