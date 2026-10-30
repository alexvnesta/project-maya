# Isolated Q8 input-sharing design

Selected GGUF source recovered from local git4615: CU `0735989826d5a9a8a9ec101ef2fbe1017ab7604c9f1e17e4217740104e107033`, header `1aab95ff58820ba9da9b05c1a056996df4d3442f1f5dfcbd65e8fbbc4578f34c`. Historical physical audit, selected92 build record, complete changed-file audit and selected header/object pins establish the retained provenance chain. Fresh physical comparison remains an action-time condition; object hash alone does not identify source.

Port only per-call input sharing from upstream50a3313. Deduplicate exact `(x,effective stride,rows,k)` keys and point matching readers at the first job's existing Q8 scratch. Keep selected rounding, batch1/check1, dot/reduction kernels, all model/IQ code, allocation and stream behavior unchanged. Sharing is opt-in/default off. Ownfork HEAD includes parked HC_FUSE changes and is not the base.

Qualify the production predicate on both CPU hosts, exact shared/nonshared Q8 bytes and final GEMV outputs on both GPUs, then fresh full-model state/token/logit equality with actual draft acceptance and complete lifecycle restoration. Any model mismatch holds this candidate before timing. Only a separate frozen reversed-pair performance panel can support a gain; output-length differences remain visible. Output-head batching is a later separate candidate.

No tests, compiler, GPU, remote action or deployment performed. Exact gate inventory and evidence hashes are in the adjacent JSON.
