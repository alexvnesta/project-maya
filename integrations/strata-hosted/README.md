# Hosted Strata integration

Our deployed API derives from [Strata](https://github.com/Niko1221/Strata) commit
`7dd5cf18e68c639a8773e096c5c79f971ea2a9f5`, rather than Maya's separate Python API.
This directory preserves its changes without overwriting Maya's server.

To reconstruct the API in an isolated Strata checkout at that exact commit:

1. Apply `native-vision-and-tools.patch` with `git apply --check` followed by `git apply`.
2. Copy `overlay/serve/ds4_vision.py` into `serve/`.
3. Confirm `serve/server.py` has SHA256
   `b1be40294f6c49692829ad5f85a7aa2867218180fdc8fbc9bef7710371ba3b9f`.

The patch retains structured JSON with client tools and adds native DeepSeek image preparation,
literal-marker protection, expanded-token context checks and request-owned DSI1 cleanup.
The Strata license is included. No tokenizer, images, prompts, weights, caches, API keys or live receipts
are shipped here. Existing upstream dependencies remain pinned by the Strata checkout.

`hosting_entry.py`, `hosting_defaults.py`, `hosting_preflight.py`, `hosting_ready.py`,
`controller.py`, `switcher.py` and `model_ready_gate.py` preserve our hosting and lease/close/readiness
behavior as portable source templates. Required installation roots are supplied explicitly through
`MAYA_DEPLOY_ROOT` and `MAYA_QUALIFICATION_ROOT`; the preflight also requires `MAYA_DIRECTION_SHA256`.
The configuration's `${...}` values are placeholders to fill deliberately, not automatic expansion.
The direction identity must be part of the KV-cache namespace, so projected and unprojected states never mix.

These templates create no services and perform no installation by themselves. Adapting paths or manifests
requires a fresh source, configuration and lifecycle review. The router retains its existing explicit
backend-selection support, but this DeepSeek fork does not start or qualify other models.
`PROVENANCE.json` distinguishes deployed source identity from template portability changes.

The current profile allocates 1,048,576 context tokens and defaults to a 262,144-token
output allowance. The context includes generated output, leaving 786,432 prompt tokens
before framing when the full output allowance is reserved. These settings passed actual
allocation and targeted image/tool/cache/cancellation/recovery checks on the selected native;
they are not a filled-1M or full-256K-generation result. See
[`FORK_BENCHMARK.md`](../../docs/FORK_BENCHMARK.md#capacity-update-2026-10-27) for the bounded result.

The current portable profile retains mode1 prompt skipping and a 4096-token prefill chunk.
A separately frozen four-arm comparison reproduced about 21.90% less cold 32K prefill time
than chunk2048 on the selected dual-CMP170HX setup; coding decode stayed roughly flat.
Chunk4096 was activated and publicly verified at 16:28:49 UTC on 2026-10-28 after separate
source, both-host CPU and existing-owner lifecycle qualification. The earlier chunk2048
result remains documented as a historical comparison.
Cache namespaces include direction, mode and chunk identity; retain older namespaces.
The portable pathname uses the full direction placeholder, so template bytes deliberately
differ from installation-specific production bytes. Portable CPU controls qualify templates,
not a new deployment. See [`prefill-chunk4096-20261028.md`](../../docs/prefill-chunk4096-20261028.md)
for measured results, activation evidence and limitations.
