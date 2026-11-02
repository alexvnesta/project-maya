# Maya-S TP2 RAM safeguards

The original public Maya-S TP2 setup remains selected. A host-wide OOM killed it on November 1, 2026 at 21:37 EST. The final RAM-only deployment was verified on November 1 at 23:51 EST. Native engine, model assets, quality settings, drafter, images, 1,048,576 total context and 262,144 output allowance are unchanged.

## Changes actually applied

| Change | Actual result |
|---|---|
| Old shared-memory objects | 659 objects with no live mappings or descriptors were copied to private local disk, fully compared, and then unlinked from `/dev/shm`. Reclaimed 23,784,882,176 bytes, or **22.1514 GiB** of allocated tmpfs space. |
| CI memory handling | Four existing runners now have `MemoryHigh=4G`. Existing hard limits, PIDs and invocations were preserved; no runner restart was requested. |
| Saved conversation cache | `STRATA_DS4_SLOT_CAP=2` and `STRATA_DS4_SLOT_RAM_GB=2`. The existing disk cache, identity and 8 GiB disk-retention policy remain. No manual conversation-cache pruning or cross-loading occurred. |
| New inference admission | Before reading an inference body, reject new requests when available host RAM is below 8 GiB, memory PSI `some avg10` reaches 10%, or the readings are unavailable. Return HTTP 503, code `host_memory_pressure`, and `Retry-After: 5`. Already admitted answers are not cancelled by this guard. |
| Startup readiness | Wait for the same memory gate before the first readiness inference, inside the original 1,100-second startup deadline. The request still has its original 180-second timeout. A failed HTTP request or wrong answer is never retried or regraded. |

The shared-memory objects had no live references, but their original producer was not established. Their contents remain recoverable on Ubuntu in the root-only quarantine at `E/maintenance/mayas-ram-safety-20261102/quarantine`. No object payload was exported. Per-object metadata and copy/unlink receipts remain on that host.

At the final audit, available RAM was **39.52 GiB**, free swap was **2.67 GiB**, and the native process reported about **47.5 MiB** swapped. These are dated observations, not fixed reservations or a promise of zero swapping.

## Verification and failed attempts

The cleanup helper first passed 24 bounded CPU controls on each physical Mac and Ubuntu host. Eight bounded, low-priority copy batches then completed with actual exit 0 and verified backups.

The final serving version passed **36 new controls on each physical host**: 21 config/source/HTTP controls, seven lifecycle controls and eight tests of the actual readiness observer with synthetic host readings and HTTP. Children used CPU 30 seconds, wall 90 seconds, nice 15, hidden CUDA, one math-library thread and, on Linux, a 512 MiB address-space bound. Source maps and test IDs matched.

Two earlier activations remain failed. Version 1 did not carry the verified old-owner closure onto the startup owner. Version 2 loaded the native model but its first readiness request returned HTTP 503; that response body was not captured, so the precise rejection reason remains unproven. Each failure was followed by a separate restoration and successful public verification of the prior qualified profile. Neither failed activation was replayed or regraded. Version 3 adds the prospective pre-request memory wait and preserves any first HTTP failure payload.

The final activation completed with actual controller exit 0 in **609.51 seconds**, within its 1,000-second soft / 200-second cleanup envelope. The old native and API exited 0. Startup verified both GPU Q8 checks, TP2, projection checks, all 6,490 CPU experts copied into the RAM tier, the active native cache budget and a real `READY` answer. Public checks verified unauthenticated models 401, authenticated models 200, and assembled SSE `READY`, natural `stop`, and `DONE`. All **979 release-file pins** were checked again after activation. Both existing serving units were active with `Restart=no`.

No new whole-model speed, broad quality, near-filled 1M-context or full 262,144-token generation result is claimed. The 2 GiB cache budget is soft: one large saved state and the serialization peak may exceed it. New-request admission cannot prevent every allocation spike inside a request already running. CPU RAM-tier copy counts do not prove every process page is always physically resident.

## Current identity and evidence

- Native SHA256: `adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f`.
- Config SHA256: `429255f61cf01c279c863e8659c0939e9243baea92e95d580731ea6d398b1dc2`.
- Final qualification: `96f85917915270f2248734f2d670c76d3be86453eff0fe6cfabf34bfd1a5cf55`.
- Deployment revision: `ramguard-20261102`; the model release ID remains `deepseek-maya-s-tp2-1m-vision-q8-yoco1-output256k-20261101`.
- Canonical audit: `E/maintenance/mayas-ram-safety-20261102/FINAL_PRODUCTION_AUDIT_FIRST.json`.
- Active owner adapter: `E/maintenance/mayas-ram-safety-20261102/profile-v3/ram_activate.py`, with `target_host(...)` and the fresh canonical `decode_optimization_current.selected_identity.start_binding`.

Here `E=/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025`. PIDs in receipts are historical snapshots. The old bare Maya-S adapter expects the previous config and must not be used to assert the current identity without the RAM-profile qualification.

`FINAL_PRODUCTION_AUDIT_FIRST.json` contains the successful public and resource checks. `memory_admission.py`, the two patches, the selected config and unit drop-in expose the small active serving delta. `source-and-receipts.tar.gz` preserves the full new source, source/input maps, CPU results and failed/successful controller receipts. Its hash and member hashes are in `MANIFEST_FIRST.json`. Existing canonical qualification dependencies are referenced, not bundled as a new engine distribution. Activation namespaces are consumed and must not be replayed.

## Rollback notes

The selected prior config and source are backed up under the final activation's `before/` directory. A serving rollback must use a separate owned maintenance operation: refresh the live binding, drain the existing owner, retain actual native/API closure receipts, restore only the exact backed-up source/config/release bytes, remove only the matching owned helper and unit drop-in, reload the user manager, and perform one qualified start and public verification. The earlier failed attempts and their separate recovery receipts must remain unchanged.

CI soft limits can be independently returned to their recorded prior value with `systemctl set-property UNIT MemoryHigh=infinity`; hard limits need not change. The disk quarantine should be restored only for specifically needed objects, after checking for name collisions and live users, using the original metadata retained on Ubuntu. Do not bulk-delete the quarantine or restore unknown objects into active shared memory.
