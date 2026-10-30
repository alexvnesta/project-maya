# Maya-S capacity source assessment

Capacity is not yet proved. No calculator, test, GPU action or startup admission was created. The exact selected source is pinned in the accompanying JSON.

The critical safety distinction is that strict all-RAM mode bypasses the source's available-minus-8GiB copy budget. It prevents intentional disk fallback but does not enforce a spare-memory margin. That margin must be independently established before startup and checked again after the old owned process has stopped.

The source's automatic split uses heuristic nonexpert/chunk allowances. Final expert placement uses fresh CUDA free memory after dense/cache/scratch/chunk allocations, weighted by the seed profile. It is therefore unsafe to carry forward the old19/21 split,4045CPU experts or file-payload totals as the new capacity calculation.

Known material terms include aligned per-role expert copies and RAM spares, a1,323,827,200-byte pinned BF16 embedding, compressed source caches replicated to consuming devices, context-sized scores/chunk slabs,400MiB-default chunk rings with corresponding host staging, per-layer Engram staging/cache, transient expert-loading buffers, and eligible lazy GEMM/library/vision allocations. The JSON gives formulas and exact source locations. CUDA and OS overhead and all late branches are not silently counted as zero.

Actual eight-asset pack metadata, exact allocation-affecting environment/profile and fresh physical budgets are still needed. A complete conservative peak must leave8GiB host margin and unchanged2048MiB reserve per device. Current available RAM plus the old process's anonymous RSS is a prospective estimate only; shared RSS and swap are not guaranteed reclaimed RAM. Missing or excessive capacity terms must block startup without changing model, context, output, quality or placement policy.

The60-control pack proof passed on both physical hosts. It establishes the bounded metadata workflow on synthetic inputs, not actual Maya-S fit or near-filled1M/262144-output behavior. Petri's hybrid/PDEP statements remain unmeasured author notes.
