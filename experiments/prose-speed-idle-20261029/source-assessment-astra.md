# Selected-model prose measurement design

Use two new synthetic prose requests against the already running selected native92/configc43 on loopback18141. Preserve context1M/defaultoutput256K, requestcap32768, effort100, temperature1, seed1 and chunk4096. Do not run a candidate, restart a service or reuse closed arms.

The selected API already returns native timing, generated-count, drafting and prompt-reuse fields in each request’s final SSE. Exact expert hit/lookups and raw native token traces are not available through that response; do not invent them. This measures direct nativeAPI client completion, not public-router latency, and buffered first-visible output is not true TTFT.

Idle GET followed by POST is not atomic. The smallest practical design is conservative user-priority cancellation: our request goes directly to18141, so any router work is foreign. On foreign demand, queueing, a second native request, cursor gap, ownership change or ambiguity, close only our own socket and preserve partial/UNRUN without retry. Never cancel by a guessed server request ID, use a shared stop endpoint, or wait for globalidle while a user is running. The existing per-socket watcher polls every0.5s; zero added user latency cannot be guaranteed. A clean accepted sample needs a contiguous, uniquely attributed redacted request epoch.

Existing private coordinate stops the router and native. It is a viable separatelyconfirmed fallback with graceful-drain proof, but cannot be called unchanged for hostedmeasurement or faked with no-op lifecycle methods. The old private transport explicitly rejects18141; create a distinct narrow fixed-host transport and leave old guards untouched.

The JSON report contains exact prompts, factual/coherence rubrics, source references, five proposed source modules plus matching tests, race/cancellation controls and bounded bothhostCPU requirements. Actual testcounts must come from written source. No implementation or inference admission is granted by this source design.
