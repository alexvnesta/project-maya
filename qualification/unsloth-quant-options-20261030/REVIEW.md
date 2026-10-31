# Unsloth quant comparison, 2026-10-30

**Recommendation:** Finish the existing **UD-IQ2_XXS v3.1** acquisition and qualify it first. It is not established as the best quality/performance quant. **UD-Q2_K_XL v3.1** is the stronger published quality candidate, but has a source-level mixed-format admission blocker in the selected native engine, and adds about 32 GiB to the non-Engram weight set. Do not switch acquisition or promote either model on this review.

Observed repository revision: `8a6ec9cf118e785a362ea94ee123c61c70553be6`, last modified `2026-10-30T13:21:51Z`. Exact sizes and all nine current public option names are in [current_public_options.json](current_public_options.json). Tensor metadata, dimensions, offsets and per-file hashes are in [hf_metadata_policy.json](hf_metadata_policy.json).

| Observed metadata / derived quantity | UD-IQ2_XXS | UD-Q2_K_XL |
| --- | ---: | ---: |
| GGUF files | 6 | 7 |
| File bytes | 300,475,464,795 | 334,793,544,836 |
| File GiB | 279.8396 | 311.8008 |
| Tensor weight bytes | 300,469,616,416 | 334,787,696,416 |
| Engram weight bytes, Q5_K | 135,172,021,600 | 135,172,021,600 |
| Non-Engram weights, GiB | 153.9454 | 185.9066 |
| Routed expert weights, GiB | 146.1072 | 178.0115 |
| Whole-model tensor bits/parameter | 3.21146 | 3.57825 |
| Routed expert bits/parameter | 2.30885 | 2.81302 |

Bits/parameter includes scale overhead; whole-model denominator is 748,494,643,824 parameters, including Engram. These are storage quantities, not resident-memory predictions. All routed tensors have 384 experts; a tensor count below is not an individual expert count.

| Actual routed tensor type | XXS count | XL count |
| --- | ---: | ---: |
| IQ1_S | 20 | 0 |
| IQ2_XXS | 33 | 29 |
| IQ2_XS | 6 | 4 |
| IQ2_S | 45 | 20 |
| IQ3_XXS | 15 | 50 |
| IQ3_S | 0 | 10 |
| Q2_K | 1 | 0 |
| MXFP4 | 0 | 7 |

**XL has no Q2_K tensor.** Its MXFP4 tensors are `ffn_down_exps.weight` at blocks 0, 1, 15, 16, 17, 18, 19. XXS has Q2_K only at block 0 down. Both use Q8_0 token embeddings, Q6_K output head, Q8_0 shared experts, and small F32/BF16 controls. Other dense matrices mix Q8_0/Q6_K; XXS additionally has 39 Q5_K matrices that XL stores as Q6_K. Same Engram format/shape/size does not prove byte identity or authorize reusing shards.

Unsloth-published quality evidence, not independently reproduced:

| Metric | XXS v3.1 | XL v3.1 | Q8 reference |
| --- | ---: | ---: | ---: |
| AIME25 | 96.88 | 97.50 | 97.08 |
| HMMT Feb26 | 67.61 | 69.89 | 68.94 |
| GPQA-D | 88.95 | 89.58 | 90.47 |
| MMLU-Pro | 87.53 | 88.28 | 88.61 |
| IFEval | 95.19 | 94.92 | 95.10 |
| LCB v6 | 83.62 | 84.76 | 85.90 |
| Six-task mean | 86.63 | 87.49 | 87.68 |
| Truncated percent | 2.71 | 2.10 | 1.48 |
| Aider pass@1 | 44.38 | unreported | unreported |
| wiki1100 KL / top1 | .203 / 90.5% | .138 / 91.5% | .00476 / 98.5% |
| long17k KL / top1 | .142 / 91.2% | .0879 / 93.3% | .00281 / 98.7% |

The six tasks use 32,768-token caps. AIME explicitly uses effort 50, temperature 1, 16 samples/problem. Other sample counts: HMMT16, GPQA8, MMLU2, IFEval2, LCB3. No confidence intervals are supplied. The methodology table says “mean of 9” despite six tasks; displayed averages match six. The task rows explicitly say v3.1; the later KL table lacks an explicit version label. No benchmark runtime/file-hash linkage is supplied. XL improves five tasks, but its Aider result is absent. These results do not qualify effort100, 1M context, images, tools or native DSpark. [Published benchmark and methodology source](https://unsloth.ai/docs/models/deepseek-v4.1-flash).

## Selected engine and hardware implications

The exact selected source was read and SHA256 verified:
`selected-ds4_model.cu`, `dfe326d6a60d77354c8c92fb14ec423a92afff76b91f0810104f0a54a51a6350`, under `maya-s-comparison-v1/model-v1/`.

Lines 2069–2072 admit Q2_K, IQ1_S and the other relevant low-bit identifiers. Lines 2105–2112 explicitly reject a low-bit gate/up pair combined with MXFP4 down. XL has seven such triples; XXS does not. The current fork helper `ds4_gguf.cuh:44–45` defines MXFP4 experts as all three projections MXFP4 (helper SHA256 `f8c89f3e5b46a462d5b98c7e7af1e482e2497acceb6d550ec76d432a892fab20`, checkout HEAD `c386986056e1ac59785668abb38a7aa8f78d84fd`). That helper checkout is supporting context, not a receipt for every file in selected binary92. The selected source's explicit guard is the material admission concern.

XXS CPU low-bit experts use generic ggml dots through `cpu_experts_iq` at lines 6632 onward; GPU matrices dispatch through `gg::mv` at 9024 onward. Missing formats in public Strata's separate fast MMVQ whitelist do **not** establish inability to load. Conversely, source identifier support does not establish numerical parity, speed, workspace fit or safe long generation. Current Maya-S short-run success with MXFP4 supports its existing format combination only.

On 2×64 GiB GA100 plus 121.4 GiB physical host RAM, XL's additional **31.9612 GiB non-Engram** must come from some combination of GPU headroom, fewer GPU experts, additional resident CPU experts, and reduced cache/runtime headroom. The split cannot be inferred from file totals or current expert counts. The 76 GiB private-memory fence, duplicated per-device buffers, 1M workspace, Engram cache and optional drafter all matter. No measured throughput ranking exists for these two candidates on this configuration. Kernel decode cost, CPU routing, speculative acceptance and generation length can offset or compound the larger byte traffic.

The optional public drafter is separate: Q8_0 file 7,976,914,240 bytes, BF16 file 8,506,281,280 bytes. Both retain MXFP4 routed experts and BF16 Markov heads; 25 projection tensors differ. The drafter borrows target embeddings/head. Unsloth reports equal acceptance in its tests, but provides no CMP170HX/native92 measurement. Target quantization can change draft acceptance. [Drafter model card](https://huggingface.co/unsloth/DeepSeek-V4.1-Flash-1017-GGUF/raw/8a6ec9cf118e785a362ea94ee123c61c70553be6/dspark/README.md).

XL warrants a later comparison because its published mean is 0.86 points higher with fewer truncations. First resolve and qualify its mixed-projection admission, then compare matched prompts, seeds, effort100, context/output allowances, image/tool protocol, DSpark settings, and the same memory fences. Record load time, placement, prefill, sustained decode, acceptance, output length, correctness and peak private/GPU memory. No test or engine change was performed here. Acquiring XL as a second complete pack requires 334.8 GB additional transfer/storage; 34.3 GB is only the size difference when substituting one pack for the other. Do not assume shard reuse.

## Provenance and scope

Only public primary sources and the exact authorized source file/current helper context were read. The GGUF reader issued strict HTTP206 exact Content-Range requests totaling **131,676 bytes**, covering directory metadata only; no tensor payload was requested or retained. First tokenizer-only shards were limited to their 24-byte prefixes. No model acquisition, inference, GPU/host changes, memory writes, automation or promotion occurred.

- [HF repository API with sizes and LFS hashes](https://huggingface.co/api/models/unsloth/DeepSeek-V4.1-Flash-1017-GGUF?blobs=true), observed pinned revision above.
- [Pinned XXS files](https://huggingface.co/unsloth/DeepSeek-V4.1-Flash-1017-GGUF/tree/8a6ec9cf118e785a362ea94ee123c61c70553be6/UD-IQ2_XXS) and [pinned XL files](https://huggingface.co/unsloth/DeepSeek-V4.1-Flash-1017-GGUF/tree/8a6ec9cf118e785a362ea94ee123c61c70553be6/UD-Q2_K_XL).
- [Public Strata native MMVQ source](https://github.com/mach10x/strata/blob/1678de333d0e0711bc414ad992b640e1a37dd814/src/kernels/cuda/native_mmvq.cu#L1441), main observed `1678de333d0e0711bc414ad992b640e1a37dd814`; not selected custom92 provenance.
- [Unsloth llama.cpp PR298](https://github.com/unslothai/llama.cpp/pull/298), closed/unmerged, head `4c4de092d03c1be09101c03adde849b0d7a93a40`.
- [llama.cpp PR30817](https://github.com/ggml-org/llama.cpp/pull/30817), closed/unmerged, head `b72050d03ae14bb3cb5138ecefab3f3f65157d31`.
- [GGUF type/block definitions](https://github.com/ggml-org/llama.cpp/blob/5047748f114564fcf271e6a648f60e2d2eae6264/gguf-py/gguf/constants.py), upstream master observed `5047748f114564fcf271e6a648f60e2d2eae6264`, timestamp `2026-10-30T19:36:30Z`. Fork MXFP8 id43 and current upstream F8_E4M3 id43 differ, so engine enum provenance matters; the two target Engram tensors here use Q5_K.

Exact observation timestamp is retained in the metadata JSON. Research completed 2026-10-30 UTC.
