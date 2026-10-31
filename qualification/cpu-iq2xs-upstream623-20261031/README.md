# Narrow upstream PR623 CPU qualification

The isolated candidate ports only IQ2_XS AVX2 rows1 support and its lookup/grid changes from upstream PR623. It is not deployed.

Finite synthetic coverage passed for 46 distinct jobs and 6,336 case rows: 25 fully accepted jobs from numerical-v4 plus 21 separately qualified jobs from numerical-v5. Both runs were independently reviewed. The original v3 fixture failure and v4 busy/incomplete result remain unchanged. The v3 issue was a fixture comparison of untouched auxiliary bytes initialized differently; its separately reviewed repair changes exactly one initializer line.

The current candidate native digest is `cab346ccefedad1d2b80384db215325a445f474729812ea288a829d843007da4`. Whole-model token/logit/state qualification and decode/prefill speed measurements remain UNRUN. Production remains selected native92/configc43/chunk4096 with the same model, quality, 1,048,576 total context and 262,144 output allowance.

See `numerical-v5/COMBINED_FINITE_COVERAGE_RESULT.json`, both raw result families and their independent reviews. Case rows include zero and empty-range controls. This is finite arithmetic evidence, not all-input exactness, model quality or a performance result.

`ARCHIVE_MANIFEST.json` records each copied member. Physical executables, archives, model weights, redundant manual-read snapshots and unrelated physical router source were not exported; their original receipts/digests remain retained in the qualification workspace and Ubuntu. The path-pinned environment manifests describe that physical environment, not a self-contained portable build.

A new model-v1 architecture is prospective only. It does not admit another run or promotion. No old comparison arm was replayed or relabeled.
