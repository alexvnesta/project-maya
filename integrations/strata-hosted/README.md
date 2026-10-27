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
