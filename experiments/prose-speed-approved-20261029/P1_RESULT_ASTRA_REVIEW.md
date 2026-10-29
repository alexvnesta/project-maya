P1 completed both synthetic prose requests naturally with stop and DONE. Full answers and reasoning were manually read; all saved SSE text was independently reassembled and matched the response records. Original raw manual-review-pending statuses remain unchanged.

| Request | Server-rounded native rate, including reasoning | API completion tokens | Full client time | Visible words | Prompt reuse |
|---|---:|---:|---:|---:|---:|
| Hash-table explanation | 43.0 tokens/s | 5,463 | 127.21 s | 931 | 168/169 |
| Coastal clock-repair story | 46.2 tokens/s | 10,532 | 230.11 s | 998 | 0/176 |

Both satisfy their narrow prompt requirements, including exact final sentences. The explanation uses conventional simplified hash-cost/resizing assumptions; the story is narrative, not validated clock-repair advice.

Selected binding f2b87ac5943049aca1ca6eff01607397 / native2427790 remained unchanged. Cleanup records have no primary, reservation-release or owner error. No restart or settings change was recorded. Final resource snapshot reports zero swap delta and 837.539 GiB free root space.

Rates are the API's native server-reported values rounded to 0.1, not exact independently counted native tokens and not visible-prose-only rates. First visible content arrived after 108.24/206.65 seconds; these buffered timings are not true TTFT. Client latency can include FIFO waiting. Warm explanation and cold story are different tasks with different reasoning lengths, so neither establishes a comparative improvement. No near-full-context, general-quality, candidate or promotion claim follows. P0 and earlier numerical HOLD remain unchanged.

The separate 20:19:23 UTC production observation confirms the same native2427790 and exact released P1 nonce, ready/default DeepSeek, zero active/queued/reserved work, no competing phase, both existing units active with Restart=no, and a clean-kernel guard since20:01. Final root space was837.533GiB. This is a local audit of the saved observation, not another live probe.
