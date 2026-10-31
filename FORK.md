# Alex's DeepSeek fork on Maya 1.1.44

The candidate branch is rebased onto Project Maya `5d20b0e8fd7c15fde2a9f2b4eac5e9776883690b`
(v1.1.44). The full native has not been built, run on the GPUs, or deployed. Production continues
using the separately qualified native `92abb8…`, config `c43dd3…`, and chunk4096 profile.

The native delta retains our checked direction loader, projection of the 40 main
blocks with the drafter untouched, per-device projection check, and guarded prompt-copy
checks. Current upstream implementations supply the HC/router fusions, decode trims,
loader, prompt lookup, tensor-parallel paths and other upstream engine changes.
Earlier local implementations were not replayed over newer upstream code. The losing
Q5/shared-sums and cache-migration runtime bundle is not included in this candidate.

The deployment target for the next comparison is the published Maya-S model, with
DSpark drafting enabled, 1,048,576 total context, 262,144 output allowance, effort100,
native images, and the same runtime projection. Engine speed and placement changes
need new bounded correctness, quality, resource and lifecycle evidence before deployment.
No claim is made that the private S2 engine or its reported speeds have been reproduced.

The portable files in `integrations/strata-hosted` describe the currently qualified
production API/profile and its historical source pins. They are not a declaration
that this new native is qualified or installed. Source integration of the new native
must preserve those API/quality/capacity contracts without applying an old patch blindly.

`qualification/` and the benchmark documents retain historical successes, failures,
and incomplete runs. They do not qualify the new native. The old combined-candidate
notes and their source controls are under `qualification/pre-maya144-copy-checks/`.
The preserved branch `archive/prefill-before-maya144-20261031` retains the original tree.

Fresh CPU proof on physical macOS and Ubuntu passed: 40 projection controls, 16
actual-extracted copy-guard controls, five startup order/mutation controls, and 27
full-build controller controls on each host. These 88 checks qualify those bounded
CPU decisions only. They establish no GPU correctness, model quality or speed gain.
