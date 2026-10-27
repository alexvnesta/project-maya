// Included inside strata::ds4::gguf::iq after the private kernel/dispatcher declarations.
// Mandatory before any request when shared sums are enabled. No model weights needed.
bool q5k_shared_sums_check(int dev, std::string& err) {
    constexpr int NJ = 4;
    constexpr size_t GUARD = 256;
    int original = 0;
    auto failure = [&](const char* what) {
        err = "Q5_K shared sums on CUDA" + std::to_string(dev) + ": " + what;
        std::fprintf(stderr, "ds4: CUDA%d Q5_K shared sums check FAILED: %s\n", dev, what);
        return false;
    };
    if (!q5k_shared_sums()) return failure("optimized dispatcher is disabled");
    if (cudaGetDevice(&original) != cudaSuccess || cudaSetDevice(dev) != cudaSuccess)
        return failure("device selection");
    size_t checked_values = 0;
    for (int columns = 1; columns <= 18; ++columns) {
        const int nc = columns >= 17 ? 16 : columns;
        const int mixed[NJ] = {1, 3, 5, 16};
        const int ks[NJ] = {256, 5120, 7168, columns == 17 ? 32768 : 8192};
        const int ns[NJ] = {17, 33, 19, 9};
        struct Inputs {
            std::vector<uint8_t> w;
            std::vector<int8_t> q;
            std::vector<float> d, bias;
        };
        auto* held = new std::vector<Inputs>(NJ);
        Jobs reference{}, optimized{};
        std::vector<void*> allocations;
        size_t offsets[NJ], set_bytes = 0;
        for (int j = 0; j < NJ; ++j) {
            const int cols = columns == 18 ? mixed[j] : nc;
            offsets[j] = set_bytes + GUARD;
            set_bytes = offsets[j] + (size_t) cols * (ns[j] + 3) * sizeof(float) + GUARD;
        }
        cudaStream_t stream = nullptr;
        cudaEvent_t event = nullptr;
        uint8_t *output = nullptr, *back = nullptr;
        bool ok = cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking) == cudaSuccess &&
                  cudaEventCreateWithFlags(&event, cudaEventDisableTiming) == cudaSuccess &&
                  cudaMalloc((void**) &output, 3 * set_bytes) == cudaSuccess &&
                  cudaMallocHost((void**) &back, 3 * set_bytes) == cudaSuccess;
        bool submitted = false;
        uint32_t rng = 0x51a7c93du + (uint32_t) columns;
        auto random = [&]() { rng = rng * 1664525u + 1013904223u; return rng; };
        auto upload = [&](const void* src, size_t bytes, void*& dst) {
            if (!ok) return;
            ok = cudaMalloc(&dst, bytes) == cudaSuccess;
            if (!ok) return;
            allocations.push_back(dst);
            submitted = true;
            ok = cudaMemcpyAsync(dst, src, bytes, cudaMemcpyHostToDevice, stream) == cudaSuccess;
        };
        for (int j = 0; j < NJ && ok; ++j) {
            const int cols = columns == 18 ? mixed[j] : nc;
            Inputs& h = (*held)[(size_t) j];
            const size_t ld = (size_t) (ks[j] / 256) * 176 + 16;
            h.w.resize((size_t) ns[j] * ld);
            for (auto& b : h.w) b = (uint8_t) random();
            for (int r = 0; r < ns[j]; ++r)
                for (int sb = 0; sb < ks[j] / 256; ++sb) {
                    uint8_t* b = h.w.data() + (size_t) r * ld + (size_t) sb * 176;
                    const uint16_t d = (uint16_t) (0x2c00u + (random() & 0x1fffu));
                    const uint16_t min = (uint16_t) (0x3000u + (random() & 0x0fffu));
                    b[0] = (uint8_t) d; b[1] = (uint8_t) (d >> 8);
                    b[2] = (uint8_t) min; b[3] = (uint8_t) (min >> 8);
                }
            h.q.resize((size_t) cols * ks[j]);
            for (size_t i = 0; i < h.q.size(); ++i)
                h.q[i] = i % 97 == 0 ? 0 : (int8_t) ((int) (random() % 256u) - 128);
            h.d.resize((size_t) cols * (ks[j] / 32));
            for (size_t i = 0; i < h.d.size(); ++i) h.d[i] = i % 11 == 0 ? 0.0f : (float) (1 + random() % 31u) / 1024.0f;
            h.bias.resize(ns[j]);
            for (float& v : h.bias) v = (float) ((int) (random() % 2001u) - 1000) / 256.0f;
            void *dw = nullptr, *dq = nullptr, *dd = nullptr, *db = nullptr;
            upload(h.w.data(), h.w.size(), dw);
            upload(h.q.data(), h.q.size(), dq);
            upload(h.d.data(), h.d.size() * sizeof(float), dd);
            upload(h.bias.data(), h.bias.size() * sizeof(float), db);
            MvJob b;
            b.w = (const uint8_t*) dw; b.ld = ld; b.type = kQ5_K;
            b.k = ks[j]; b.n = ns[j]; b.ncol = cols;
            b.xq = (const int8_t*) dq; b.xd = (const float*) dd;
            b.y = output ? (float*) (output + offsets[j]) : nullptr; b.ycs = ns[j] + 3;
            b.bias = j % 2 ? (const float*) db : nullptr;
            b.alpha = j % 2 ? -0.5f : 1.0f;
            reference.j[j] = optimized.j[j] = b;
            optimized.j[j].y = output ? (float*) (output + set_bytes + offsets[j]) : nullptr;
        }
        if (ok) {
            submitted = true;
            ok = cudaMemsetAsync(output, 0xA5, 2 * set_bytes, stream) == cudaSuccess &&
                 cudaMemsetAsync(output + 2 * set_bytes, 0x5A, set_bytes, stream) == cudaSuccess;
            const dim3 grid((33u + kWarps - 1) / kWarps, NJ);
            if (nc == 1) mv_kernel<kQ5_K, 1><<<grid, kThreads, 0, stream>>>(reference);
            else if (nc <= 4) mv_kernel<kQ5_K, 4><<<grid, kThreads, 0, stream>>>(reference);
            else mv_kernel<kQ5_K, 16><<<grid, kThreads, 0, stream>>>(reference);
            // Production dispatcher: group 17 crosses its shared-memory bound and retains the old kernel.
            mv_nc<kQ5_K>(optimized, NJ, 33, nc, stream);
            for (int j = 0; j < NJ; ++j) optimized.j[j].y = (float*) (output + 2 * set_bytes + offsets[j]);
            mv_nc<kQ5_K>(optimized, NJ, 33, nc, stream);
            ok = ok && cudaGetLastError() == cudaSuccess &&
                 cudaMemcpyAsync(back, output, 3 * set_bytes, cudaMemcpyDeviceToHost, stream) == cudaSuccess;
        }
        bool done = !submitted;
        if (submitted) {
            const bool recorded = cudaEventRecord(event, stream) == cudaSuccess;
            ok = ok && recorded;
            const auto began = std::chrono::steady_clock::now();
            cudaError_t state;
            while ((state = recorded ? cudaEventQuery(event) : cudaStreamQuery(stream)) == cudaErrorNotReady &&
                   std::chrono::steady_clock::now() - began < std::chrono::seconds(10))
                std::this_thread::sleep_for(std::chrono::microseconds(100));
            done = state == cudaSuccess;
            ok = ok && done;
        }
        std::vector<uint8_t> result;
        if (ok) result.assign(back, back + 3 * set_bytes);
        // A failed/unfinished stream keeps every referenced input and allocation until owned process cleanup.
        if (done) {
            for (void* v : allocations) ok = (cudaFree(v) == cudaSuccess) && ok;
            if (output) ok = (cudaFree(output) == cudaSuccess) && ok;
            if (back) ok = (cudaFreeHost(back) == cudaSuccess) && ok;
            if (event) ok = (cudaEventDestroy(event) == cudaSuccess) && ok;
            if (stream) ok = (cudaStreamDestroy(stream) == cudaSuccess) && ok;
            delete held;
        }
        if (!ok) { (void) cudaGetLastError(); cudaSetDevice(original); return failure("CUDA setup/launch/completion/cleanup"); }
        std::vector<uint8_t> payload(set_bytes, 0);
        for (int j = 0; j < NJ; ++j)
            for (int c = 0; c < (columns == 18 ? mixed[j] : nc); ++c)
                for (int r = 0; r < ns[j]; ++r) {
                    const size_t at = offsets[j] + ((size_t) c * (ns[j] + 3) + r) * sizeof(float);
                    for (size_t b = 0; b < sizeof(float); ++b) payload[at + b] = 1;
                    ++checked_values;
                }
        for (size_t i = 0; i < set_bytes; ++i) {
            if (payload[i]) {
                if (result[i] != result[set_bytes + i] || result[i] != result[2 * set_bytes + i]) {
                    cudaSetDevice(original); return failure("output bits differ from original kernel");
                }
            } else if (result[i] != 0xA5 || result[set_bytes + i] != 0xA5 || result[2 * set_bytes + i] != 0x5A) {
                cudaSetDevice(original); return failure("output guard/padding overwritten");
            }
        }
    }
    if (cudaSetDevice(original) != cudaSuccess) return failure("restore device");
    std::fprintf(stderr, "ds4: CUDA%d Q5_K shared sums check: 72 jobs, columns 1..16 and mixed, k 256..32768, %zu values "
                         "bit for bit, guards/padding intact, large-K fallback PASS\n", dev, checked_values);
    return true;
}
