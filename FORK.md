# Alex's DeepSeek fork

This fork preserves the selected Maya `4615f346` native base and the hosted changes used with
DeepSeek-V4.1-Flash IQ2_XS. The production source branch is `alex/production-20261026`;
`alex/combined-optimizations-20261026` contains the combined optimization candidate.

The hosted profile uses context 524288, an output default of 131072, effort 100, TP1,
native images, Q8 batching with its startup check, and DSpark at confidence 0.65.
Runtime residual projection is opt-in in the engine and enabled in the hosted profile.
Its loader checks direction consistency, tensor extents and scales; the projection targets
the 40 main blocks, leaves the drafter unchanged, and checks its arithmetic on each GPU.
No model weights or direction artifact are included in this repository.

## Integrated optimization sources

| Upstream PR | Pinned head | Included scope |
| --- | --- | --- |
| [511](https://github.com/mw00/project-maya/pull/511) | `aab71b989fb3ab9def238c841134fef3434db64c` | HC and router fusion, single-token and verify-window variants, startup byte checks |
| [512](https://github.com/mw00/project-maya/pull/512) | `28e66e7bc02de3b5866abbcb9f9bee2e7f452ed0` | Fused rounding, compressor copies and drafter-to-head handoff; adapted to existing fixed drafter placement |
| [520](https://github.com/mw00/project-maya/pull/520) | `b5eb8ca76cce399121d1a15c7cc0f42895483c72` | Member-only prompt staging, opt-in registered RAM DMA, guarded byte checks; excludes new models and quant formats |
| [434](https://github.com/mw00/project-maya/pull/434) | `d29b6c5812607beb543d130d51683a3ee207bd7f` | Region-scoped load advice, load thread/file ordering controls; additional cache advice is opt-in here |
| [399](https://github.com/mw00/project-maya/pull/399) | `0a429dea6d51d6e5dc1b2c4853b7dc99a75eaf63` | Offline raw-count profile refresh tool and tests; never refreshes live placement automatically |
| [519](https://github.com/mw00/project-maya/pull/519) | `739f65181860d9461e04531dea3361ca110bec17` | Only the three drafter-VRAM cap commits; excludes its unrelated helper/flow stack |

The runtime projection derives from [469](https://github.com/mw00/project-maya/pull/469)
at `78362195803b7333ef2859acbe8299b1da2e024e`, with local loading, scope and numeric safeguards.
Original authors are retained in the cherry-picked commits. PR520's selected port is credited in its commit.
The previously qualified per-32 activation Q5_K shared-expert reference is retained for TP checks.

## Qualification status

The original hosted profile has targeted native/API/lifecycle qualification. That evidence does
not qualify this combined candidate. The optional image-RAM slot prototype remains parked and is
not included. No near-filled 512K input, full 128K output, broad accuracy, refusal-rate or speed
claim follows from the configured limits.

The combined source has separate CPU checks on macOS and physical Ubuntu: 42 controls exercise exact
extracted native methods through a fake device backend, and five tests cover the offline profile tool.
The tests cover RAM/file and NUMA/member layouts, direct DMA bytes and guards, copy/read failures,
pin registration rollback, and drafter cap rejection. They do not execute CUDA or prove fused arithmetic.
The production fused paths have their own startup byte checks, which must pass on real devices before use.

The new optimization controls are off when unset. `DS4_COPY_PIN=1` registers copies only for the
non-flow prompt copy path; it does not accelerate the independent flow path or imply a decode gain.
TP stays 1 in the hosted template. Drafter caps alter placement and require measurement before selection.
New source must be built, audited and qualified through the existing owned maintenance lifecycle before
replacing a hosted binary. No benchmark, restart, model download or service change happens by cloning this fork.

See [the hosted integration](integrations/strata-hosted/README.md) for reproducible API and hosting sources.
