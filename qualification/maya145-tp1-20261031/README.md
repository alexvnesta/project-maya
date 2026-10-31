# Maya1.1.45 / public Maya-S: first TP2–TP1 prose pair

Both runs used the unchanged169-token ms-prose-main fixture, full32768 benchmark cap, effort100, temperature1/top_p1/seed1, DSpark.65/max4, chunk4096, native images and L22scale1/all40main projection with unchanged drafter weights. Total context1,048,576 and output allowance262,144 were preserved. Nativeadff28a2/build5c9ba2f and the same public Maya-S pack were used. Diagnostic dumps, round logs and numerical FSIZE limits were absent during timing.

| Observation | TP2 | TP1 |
|---|---:|---:|
| Native decode tok/s |62.3989|56.5180|
| Generated tokens, reasoning plus answer |5653|5777|
| Native decode seconds |90.5946|102.2153|
| Client total seconds |92.5469|104.0900|
| Prompt milliseconds,169tokens/cold |1926.9|1849.9|
| Final prose words |930|939|
| Actual DSpark rounds |1727|1744|

Both independent terminal audits passed, and both entire answers and reasoning were manually read. Each met the requested word range/topics, explicitly invented example and exact final sentence. Native/API/window exits were0; resources and kernel checks passed. Production native92/configc43/chunk4096 was restored and public401/auth200/assembledREADY-stop-DONE verified. TP1 startup was slow on this attempt; it is included in raw receipts and excluded from request timing.

TP2 leads this first pair by10.405% in decode rate and11.090% in client time. Output lengths differ by2.19%, so this is not fixed-token timing or a replicated general task-speed gain. Both tests allocated1Mcontext; neither filled1M or generated256K. Broader current-engine quality/image/cache/cancel/code/prefill checks, timing replication and production activation remain pending. No deployment is authorized by these observations alone.

The archive also preserves separately accepted TP1 finite-state diagnostics and the NEW quality controller/fixture/auditor/recovery source with FIRST65+22+14+63CPU controls on each physical host. That quality source has not run on GPU. Older failed/partial arms and the isolated-import preflight refusal remain preserved, with no replay or regrading.
