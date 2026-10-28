# Selected mode1 prefill and Harness progress

The selected existing native supports mode1 prompt skipping on the actual 19/21
layer placement. A focused A1/B1/B2/A2 comparison enabled only `DS4_YOCO=1` and
`STRATA_DS4_PROMPT_SKIP=1`. All other model, context, output, Q8, sampling,
ablation, DSpark, CPU-thread and prefill-chunk settings stayed fixed.

| Measure | Control | Mode1 | Change |
| --- | ---: | ---: | ---: |
| Cold 32761-token prefill, pooled mean | 51.5418s | 43.61095s | 15.387% less time |
| Coding native decode, pooled | 43.9222 token/s | 44.0386 token/s | +0.265%, effectively flat |
| Generated coding tokens | 19829 | 21655 | +9.209% |

Both matched pairs reduced cold prefill time by more than 10% (15.816% and14.953%).
Coding decode changes were −0.578% and +1.420%. Longer and variable generated output
means the candidate's total coding client time increased; this is not an overall
task speedup. No statistical, p95 or nearfilled1M claim follows from this 32K panel.

All 20 main requests stopped naturally. Original basic grades were 5/5 per arm;
original full grades were 3/5 per arm and remain unregraded. Generated coding
modules and all supplied tests were manually read before independent 2207-case/
4414-check reviews plus supplied tests and four negative controls on each host.
Targeted tools, JSON, images, long-image warm reuse, text slot return, prefill and
decode cancellation, queued cancellation and recovery controls passed. The four
arms used 52 native/56 HTTP requests; eight separate unmeasured cap1 numerical
requests preceded them. First-token distributions were close but not bit equal;
they do not establish whole-model equivalence or broad accuracy.

Mode1 was activated on the same native SHA
`92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1`.
Only the two flags and a fresh mode-specific conversation-cache namespace changed.
The old namespace was retained. Native source and executable were not rebuilt or
replaced for activation. The selected profile remains 1M context, 256K output
allowance, TP1, Q8 checks on, native images, runtime projection, 24 CPU threads,
prefill chunk 1024 and all CPU experts in RAM. The previously losing Q5_K/cache
migration bundle remains off. This branch retains its source history for review;
its HEAD is not asserted to be the selected production binary.

Activation controls passed 28 exact tests on each host after review. Existing
production ownership, clean native close, free GPUs, experiment lock, resource
admission and kernel checks were retained. The final target verified 972 manifest
pins, actual process ownership/argv/environment, Q8/projection startup checks,
protected 401, authenticated model metadata 200 and a raw streaming READY/stop/DONE
response. No fifth benchmark or automatic retry was performed.

The optional `integrations/harness-deepseek-status` plugin is installed through
Harness's supported plugin interface. It displays shared-server reading position,
generation rate, elapsed time and queue activity without changing requests or
idle timeouts. Position includes reused rows and is not an ETA. Its diagnostic
stores bounded content-free counts in RAM. It helps distinguish slow prefill from
a silent server; it does not guarantee HTTP client delivery or prevent every
transport failure. Image histories can still lose reuse after displacement;
the separate custom image-cache prototype remains parked and unbuilt.

The live Harness footer and 1M/images/ablated model label were verified when the
plugin was enabled. The final repeated UI observation was unavailable because the
Mac was locked; final serving metadata and streaming verification passed.
