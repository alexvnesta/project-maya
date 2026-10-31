// Standalone CPU-only numerical witness, UNBUILT/UNRUN. Link the candidate CPU archive
// plus original ds4_iq_cpu.cpp.o and exact selected ggml libraries. No CUDA,
// model payload, timing, or service API. Use the pinned original ds4 header.
// One bounded invocation per n: --n {256,2304,5120} --expect {optimized,fallback}.
// Parent supplies STRATA_NO_IQ256=1 only for the separate fallback invocation.
#include "strata/kernels/cpu/iq_avx2.hpp"
#include "strata/kernels/cpu/native_expert.hpp"
#include "strata/kernels/cpu/expert_layout.hpp"
#include "ds4_gguf_cpu.hpp"
#include "ggml.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace cpu = strata::kernels::cpu;
namespace gg = strata::ds4::gguf;
namespace {
constexpr int type = 17, rows = 7;
constexpr uint32_t sentinel = 0x7fa12345u;
void need(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
uint32_t bits(float f) { uint32_t u; std::memcpy(&u, &f, 4); return u; }
float marker() { float f; std::memcpy(&f, &sentinel, 4); return f; }
uint64_t next(uint64_t& x) { x ^= x << 13; x ^= x >> 7; x ^= x << 17; return x; }

// Valid IQ2_XS blocks: every code/sign/scale byte is legal; only the fp16 block
// multiplier needs constraining. Nonuniform codes distribute grid/sign/scale
// indices across rows, blocks, and patterns; this is a finite witness, not exhaustive.
std::vector<uint8_t> weights(int n, size_t stride, int pattern, uint64_t seed) {
    std::vector<uint8_t> w(stride * rows + 64, 0xa5);
    const uint16_t scales[] = {0x0000, 0x8000, 0x1800, 0x0001, 0x7bff, 0x9800};
    for (int r = 0; r < rows; ++r) for (int b = 0; b < n / 256; ++b) {
        uint8_t* p = w.data() + 32 + r * stride + b * 74;
        for (int j = 0; j < 74; ++j) p[j] = static_cast<uint8_t>(next(seed));
        std::memcpy(p, &scales[pattern], 2);
        // Extreme and enumerated codes, not random floating-point scale bits.
        for (int j = 0; j < 32; ++j) {
            const unsigned grid = (r * 73 + b * 31 + j * 17 + pattern * 97) & 511;
            const unsigned sign = (r * 11 + b * 19 + j * 23 + pattern * 37) & 127;
            const uint16_t code = static_cast<uint16_t>(grid | (sign << 9));
            std::memcpy(p + 2 + j * 2, &code, 2);
        }
        for (int j = 0; j < 8; ++j)
            p[66 + j] = pattern == 4 ? 255 : static_cast<uint8_t>(r * 41 + b * 17 + j * 37 + pattern);
    }
    return w;
}

void same(const std::vector<std::vector<float>>& got,
          const std::vector<std::vector<float>>& ref, int r0, int r1, const char* path) {
    for (size_t t = 0; t < got.size(); ++t) for (int r = 0; r < rows + 2; ++r) {
        const bool used = r >= r0 + 1 && r < r1 + 1;
        const uint32_t want = used ? bits(ref[t][r]) : sentinel;
        if (bits(got[t][r]) != want || (used && !std::isfinite(got[t][r]))) {
            std::fprintf(stderr, "FAIL path=%s t=%zu r=%d actual=%08x expected=%08x\n",
                         path, t, r, bits(got[t][r]), want);
            throw std::runtime_error("Exact finite output/canary mismatch");
        }
    }
}

void check(int n, int nt, int pad, int pattern, int r0, int r1) {
    const auto* wt = ggml_get_type_traits_cpu(GGML_TYPE_IQ2_XS);
    const auto* at = ggml_get_type_traits_cpu(GGML_TYPE_Q8_K);
    need(wt && wt->vec_dot && at && at->from_float, "Pinned ggml traits absent");
    const size_t rb = ggml_row_size(GGML_TYPE_IQ2_XS, n);
    const size_t ab = ggml_row_size(GGML_TYPE_Q8_K, n), stride = rb + pad;
    need(rb == static_cast<size_t>(n / 256) * 74, "Unexpected selected IQ2_XS layout");
    auto w = weights(n, stride, pattern, 17), up = weights(n, stride, pattern, 29);
    // Distinguish up from gate while preserving the valid fp16 multiplier.
    for (int r = 0; r < rows; ++r) for (int b = 0; b < n / 256; ++b)
        up[32 + r * stride + b * 74 + 2] ^= 0x5a;
    const auto w_before = w, up_before = up;
    std::vector<uint8_t> a(nt * ab + 64, 0x3c);
    std::vector<const void*> ap(nt);
    std::vector<float> x(n);
    std::vector<uint8_t> quantized_via_selected(ab);
    uint64_t seed = 0x123456789abcdefULL;
    for (int t = 0; t < nt; ++t) {
        for (int j = 0; j < n; ++j)
            x[j] = pattern == 0 ? 0.f : pattern == 1 ? -0.f :
                   pattern == 4 ? (j & 1 ? 1.f : -1.f) :
                   (static_cast<int>(next(seed) % 2001) - 1000) * 0.001f;
        at->from_float(x.data(), a.data() + 32 + t * ab, n);
        gg::iq_cpu_quant(GGML_TYPE_Q8_K, x.data(), n, quantized_via_selected.data());
        need(std::memcmp(quantized_via_selected.data(), a.data() + 32 + t * ab, ab) == 0,
             "Actual ds4 activation quantization differs");
        if (pattern == 3) { // Exercise subnormal accumulators without quantizer underflow.
            const size_t block_bytes = ggml_type_size(GGML_TYPE_Q8_K);
            for (size_t b = 0; b < ab; b += block_bytes) {
                const float d = std::ldexp(1.f, -120);
                std::memcpy(a.data() + 32 + t * ab + b, &d, 4);
            }
        }
        ap[t] = a.data() + 32 + t * ab;
    }
    const auto a_before = a;
    std::vector<std::vector<float>> ref(nt, std::vector<float>(rows + 2, marker()));
    std::vector<std::vector<float>> gu = ref, plain_gu = ref;
    constexpr float limit = 20.f;
    for (int t = 0; t < nt; ++t) for (int r = r0; r < r1; ++r) {
        float g, u;
        wt->vec_dot(n, &g, 0, w.data() + 32 + r * stride, 0, ap[t], 0, 1);
        wt->vec_dot(n, &u, 0, up.data() + 32 + r * stride, 0, ap[t], 0, 1);
        ref[t][r + 1] = g;
        plain_gu[t][r + 1] = (g / (1.f + std::exp(-g))) * u;
        g = std::fmin(g, limit); u = std::fmin(std::fmax(u, -limit), limit);
        gu[t][r + 1] = (g / (1.f + std::exp(-g))) * u;
    }
    cpu::NativeFmt f; std::string error;
    need(cpu::native_fmt(type, type, 5120, 2304, f, error), "Actual model native format refused");
    gg::IqCpu selected;
    need(gg::iq_cpu_fmt(type, type, 5120, 2304, selected, error), "Actual ds4 format refused");
    // Split APIs accept separate base pointers and strides supplied by the format.
    f.gu_row = f.d_row = stride;
    selected.gu_row = selected.d_row = stride;
    const int paths = n == 256 ? 2 : n == 2304 ? 4 : 6;
    for (int path = 0; path < paths; ++path) {
        std::vector<std::vector<float>> out(nt, std::vector<float>(rows + 2, marker()));
        std::vector<float*> op(nt);
        for (int t = 0; t < nt; ++t) op[t] = out[t].data() + 1;
        if (path == 0) cpu::iq256_rows(type, w.data() + 32, stride, n, ap.data(), nt, op.data(), r0, r1);
        if (path == 1) cpu::iq256_rows1(type, w.data() + 32, stride, n, ap.data(), nt, op.data(), r0, r1);
        if (path == 2 && n == 2304) cpu::native_down_rows_split(f, w.data() + 32, ap.data(), nt, op.data(), r0, r1);
        if (path == 2 && n == 5120) cpu::native_gu_rows_split(f, w.data() + 32, up.data() + 32, ap.data(), nt, op.data(), r0, r1, limit);
        if (path == 3 && n == 2304) gg::iq_cpu_down(selected, w.data() + 32, ap.data(), nt, op.data(), r0, r1);
        if (path == 3 && n == 5120) gg::iq_cpu_gate_up(selected, w.data() + 32, up.data() + 32, ap.data(), nt, op.data(), r0, r1, limit);
        if (path == 4) cpu::native_gu_rows_split(f, w.data() + 32, up.data() + 32, ap.data(), nt, op.data(), r0, r1);
        if (path == 5) gg::iq_cpu_gate_up(selected, w.data() + 32, up.data() + 32, ap.data(), nt, op.data(), r0, r1, 0.f);
        const char* names[] = {"iq256_rows", "iq256_rows1", "native_split", "selected_ds4", "native_unclamped", "selected_ds4_unclamped"};
        same(out, n == 5120 && path >= 2 ? (path >= 4 ? plain_gu : gu) : ref, r0, r1, names[path]);
    }
    need(w == w_before && up == up_before && a == a_before, "Input/padding bytes modified");
    std::printf("PASS n=%d nt=%d pad=%d pattern=%d range=%d:%d paths=%d\n", n, nt, pad, pattern, r0, r1, paths);
}
}

int main(int argc, char** argv) {
    try {
        need(argc == 5 && std::string(argv[1]) == "--n" && std::string(argv[3]) == "--expect", "Exact CLI required");
        const std::string ns = argv[2], expected = argv[4];
        need(ns == "256" || ns == "2304" || ns == "5120", "Dimension refused");
        need(expected == "optimized" || expected == "fallback", "Expectation refused");
        need(cpu::cpu_avx2_ok(), "Physical AVX2 required; no skipped success");
        ggml_cpu_init();
        need(!gg::iq_cpu_own_rows(type), "Actual ds4 unexpectedly bypasses native type17 rows");
        need(cpu::iq256_rows1_supported(type), "Candidate type17 one-token path absent");
        const bool one = cpu::native_rows1_exact(type), multi = cpu::native_multi_rows_exact(type);
        need(one == (expected == "optimized") && multi == (expected == "optimized"), "Actual dispatcher/fallback mismatch");
        std::printf("DISPATCH type=17 one=%d multi=%d expected=%s\n", one, multi, expected.c_str());
        int cases = 0;
        for (int nt = 1; nt <= 16; ++nt) for (int pad : {0, 32}) for (int pattern = 0; pattern < 6; ++pattern)
            for (const auto range : {std::pair<int,int>{0, 7}, {1, 6}, {3, 3}}) {
                check(std::stoi(ns), nt, pad, pattern, range.first, range.second); ++cases;
            }
        need(cases == 576, "Finite inventory incomplete");
        std::printf("{\"status\":\"PASS\",\"type\":17,\"n\":%s,\"cases\":576,\"paths_per_case\":%d,\"expect\":\"%s\"}\n", argv[2], ns == "256" ? 2 : ns == "2304" ? 4 : 6, argv[4]);
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "IQ2_XS_FIRST_FAULT: %s\n", e.what());
        return 1;
    }
}
