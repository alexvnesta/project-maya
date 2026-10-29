# Experimental Q5_K tensor-core decode candidate

This is a source candidate, not the selected production deployment. The qualified chunk4096 profile and native92 executable remain selected, with the same model, quantization, quality settings, native images, runtime projection, 1,048,576 total context and 262,144 output allowance.

The candidate isolates [Maya PR624](https://github.com/mw00/project-maya/pull/624), head1872501868fee0a1c40b13de76fa7b4380ab2abf, against the exact selected native source. It uses int8 tensor cores for eligible multirow Q5_K dense GEMVs on SM80+. Integer dot products and the original floating-point recurrence are retained by design. The isolated GPU kernel passed exact comparisons on both physical devices. Whole-model numerical equivalence and generation speed remain unproven.

The port makes the threshold apply to every job in a batch, adds test-only dispatch accounting and provides a bounded correctness-only test entry. It excludes the earlier losing shared-sums/cache bundle and does not import Maya's newer parallel protocol. The flag defaults off; threshold2 is the first proposed factor.

## Evidence and remaining gates

SOURCE.json records the exact selected source and candidate hashes. CPU.json records first bounded qualification on macOS and physical Ubuntu:478 checks each, matching source maps and case IDs. These controls exercise the actual dispatch predicate and strict device/Q8 admission helpers. They do not compile or run CUDA. Separate compiler/lifecycle controls passed on both hosts before compilation and the first GPU window.

The executed GPU fixture covers110 prequantized GEMV cases and12 public GGUF/Q8 integration cases per device. It checks actual NG1/NG2/fallback dispatch, all1–16 column counts, full reduction widths, row tails, padded strides, mixed batches, output guards and small deterministic extreme/subnormal cases. Its command accepts only device0 or1, requires Q8batch/check1/1 before CUDA setup, and runs the actual Q8 startup check. It has no implicit timing benchmark.

GPU.json records the first actual build and 244 passing GPU cases, a clean bounded window and verified restoration of selected4096. Native integration, whole-model equality, task quality, cancellation/resources and replicated decode performance remain separate gates before promotion. This patch is intended for the selected source hashes; applying it to an arbitrary upstream checkout is not qualified.

The first unchanged-object control relink reproduced the selected native92 bytes exactly. The new candidate native is bef0b4d37e4ca028698d69babe227e23aa701c00d2bb1a706b821f1e98e4367a; it has not been run as a model or deployed. No tokens/s improvement is claimed.

## Upstream comparison

[Maya v1.1.36](https://github.com/mw00/project-maya/releases/tag/v1.1.36) includes CPU worker correctness, NUMA and MXFP4 activation-copy changes, plus parallel drafting. The NUMA and MXFP4-copy mechanisms do not directly establish a gain for this single-NUMA-node IQ deployment. [PR622](https://github.com/mw00/project-maya/pull/622), lazy drafter-head rows, is a separate follow-on candidate.

The [SeriousRising CMP170HX recipe](https://github.com/SeriousRising/ds41-flash-cmp170hx/tree/1e5a6a84b03c492522d51b301ab9e4ba09339e50) pins engine4fa4ba55717bdfe71fdc923d39d589d3cfc1311f. Its IMMA work overlaps this candidate. Unique leads include HC pre-normalization/fusion and tensor-core split attention. The latter explicitly changes numerical results and needs a separate numerical review. FLOW/PIPE changes need additional caller and lifecycle review.

Its reported47–52tokens/s uses a different quantization/profile,512K context, vision off, different CPU allocation and effort settings. Those numbers are not a matched comparison to this deployment, and its configuration, hot-expert profile and model files are not imported.
