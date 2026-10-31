# Narrow upstream PR623 CPU qualification

The isolated candidate ports only IQ2_XS AVX2 rows1 support and lookup/grid changes from upstream PR623. It is not deployed.

Finite synthetic coverage passed for 46 distinct jobs and 6,336 case rows: 25 accepted numerical-v4 jobs plus 21 separately qualified numerical-v5 jobs. The original v3 fixture failure and v4 busy/incomplete result remain unchanged. The separately reviewed v3 fixture repair changes one initializer line. These finite cases do not establish all-input or whole-model equality.

The new whole-model comparison is CLOSED with an exactness HOLD. Its controller/auditor and transport/resource/cleanup gates passed 247 bounded CPU controls on EACH physical Mac and Ubuntu, with exact 19-source/3,639-input maps. The first Mac dependency-environment failure remains preserved. Prospective R2 used pinned task-local copies of existing packages, without installs or global environment changes.

N0 (selected native92) and N1 (candidate cab346cc) completed all four frozen natural-stop text/cache/image states with correct known answers, finite dumps, native/privateAPI/window/controller exit0 and selected production restoration. N0 was independently accepted. N1's FIRST independent comparison failed on cold-text: both have 157 output tokens and 169 finite logit rows (87,393,280 bytes), but full dump hashes differ. Later paths also have different token trajectories and lengths. Original compare exit1 is retained; all six CPU audit groups are absent and the claim was released.

Four standalone state/lifecycle checks passed for N1, but numerical comparison acceptance is false. No timing, retry, tolerance, realignment, regrade or deployment followed. This does not establish incorrect answers or general quality loss. CPU arithmetic, GPU execution and adaptive expert routing were not causally separated. Startup counts match; dynamic per-expert residency was not captured. Dump-instrumented runs are not speed measurements.

Production remains native `92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1`, config `c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa`, chunk4096, with unchanged model/quality/images, 1,048,576 total context and 262,144 output allowance. Restored PIDs are dated receipts. Protected401/authmodels200 and assembled READY/stop/DONE passed after restoration. Near-filled1M/full262K generation and broad reasoning quality remain unproven.

See both N0 and N1 `RESULT_ROOT_REVIEW.json` and `RESULT_ASTRA_REVIEW.json` under `model-v1/`, and `model-v1/N1/raw/audit/AUDIT-FIRST/compare/child.log`. Model qualification: `dab22359ef430012591d8113c4483e633a5f50e2fef24334d4c9d365f0b61849`. Candidate native: `cab346ccefedad1d2b80384db215325a445f474729812ea288a829d843007da4`.

`ARCHIVE_MANIFEST.json` retains the earlier finite package. `MODEL_V1_ARCHIVE_MANIFEST.json` records the added source/CPU/raw metadata. Physical native/archives/Python/vendor binaries, weights, private caches and full float dumps were not exported; exact digests and original evidence locations remain recorded. This is a provenance archive, not a self-contained portable build. No old arm was replayed or relabeled.
