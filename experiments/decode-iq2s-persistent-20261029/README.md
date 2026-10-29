# Isolated IQ2_S persistent-kernel candidate

This experiment ports Maya v1.1.37's persistent token/window scheduling for IQ2_S routed experts into the exact selected native source. It retains the original arithmetic and fallback kernels. The switch defaults off. IQ1, light prompts, IMMA, CPU kernels and serving behavior are outside this candidate.

The candidate compiled and linked. Both physical CMP170HX GPUs passed 52 exact-output cases each, including public Q8 integration, dispatch selection and memory guards. The owned kernel window exited successfully; the selected native92/chunk4096 deployment was restored and passed authentication and assembled READY/stop/DONE checks. Production has not adopted this candidate.

The build, policy and kernel-controller suites first passed 59, 46 and 68 controls on each physical host. The distinct whole-model numerical source first passed 109 bounded controls on macOS and Ubuntu with matching 11-source and 931-input maps. Whole-model numerical windows and generation-speed measurements remain unrun in this snapshot. CPU and kernel correctness do not establish whole-model equivalence or a speed gain.

Known limits are retained: persistent gate specializations NE4/8 each have eight bytes of compiler-reported stack/spill traffic. The old native's clean close and API unit stop job were observed, but an independent historical API process exit status was not captured in the kernel window. The new model controller prospectively requires that evidence. This kernel window had no private API server. Historical GLM fields in inherited window metadata do not indicate a GLM activation.

`RESULTS.json` states the bounded result. `ARCHIVE_SOURCE_MAP.json` hashes the verbatim source and receipt payloads. The candidate, operator sources, raw child receipts, manual reviews, initial refusals and failed observations are preserved. Absolute paths describe provenance in the original qualification workspace; this directory is not a standalone installer. Model weights, native binaries, private user requests, credentials and cache contents are excluded. Diagnostic patches and dependency files retain their original whitespace.

The earlier IMMA candidate remains separately closed on `HOLD_TOKEN_PATH_DIFFERS`. It was not replayed or regraded here. Model, quality settings, total context and output allowance remain unchanged in production.
