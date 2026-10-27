// Exact extracted Model methods, synthetic layouts and a CPU copy/registration backend.
// This does not execute CUDA, validate fused arithmetic, or establish an engine speedup.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

using cudaStream_t = int;
constexpr int cudaSuccess = 0, cudaHostRegisterPortable = 1, cudaMemcpyHostToDevice = 1;
static std::atomic<int> pins{0}, unpins{0}, pin_fail_at{-1}, copy_calls{0}, copy_fail_at{-1};
static bool unpin_fail = false;
static int cudaHostRegister(void*, size_t, int) { return pins.fetch_add(1) == pin_fail_at ? 1 : 0; }
static int cudaHostUnregister(void*) { ++unpins; return unpin_fail ? 1 : 0; }
static int cudaGetLastError() { return 0; }
static int cudaMemcpyAsync(void* d, const void* s, size_t n, int, cudaStream_t) {
    if (copy_calls.fetch_add(1) == copy_fail_at) return 1;
    std::memcpy(d, s, n); return 0;
}
static double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
namespace gg {
constexpr int kFmtMXFP4 = 1;
struct Layout { int fmt = kFmtMXFP4; size_t trellis[3]{}; int type[3]{1, 1, 2}; };
static size_t type_row_bytes(int t, int n) {
    if (n % 256 || n < 0) throw std::runtime_error("invalid synthetic quant row");
    return size_t(n / 256) * (t == 1 ? 84 : 176);
}
static int expert_type(const Layout& l, int r) { return l.type[r]; }
}
struct Layer {
    gg::Layout lay, hlay;
    int nm = 1, ff0 = 0, ffn = 768, il = 0, n_exp = 128, n_cls = 1;
    bool mtp = false;
    size_t blob = 0;
    std::vector<int> ram{0}, region_file{0};
    std::vector<size_t> region_off{0}, region_bytes{0};
};
struct Harness {
    struct Geometry { int dim = 512, ff = 768, nl = 1, n_mtp = 3, d_n_exp = 128; } g;
    struct Pack {
        std::vector<uint8_t> bytes;
        bool read_at(int, size_t off, size_t n, void* dst) const {
            if (off > bytes.size() || n > bytes.size() - off) return false;
            std::memcpy(dst, bytes.data() + off, n); return true;
        }
    } pk;
    int NH = 2, chunk = 1024;
    bool cp_dma = false, copy_mode = true, file_fail = false;
    mutable int fallback_calls = 0;
    std::vector<Layer> L, members;
    std::vector<std::vector<uint8_t>> storage;
    std::vector<std::vector<uint8_t*>> ram_part;
    std::vector<std::vector<size_t>> cp_lay;
    std::vector<uint8_t*> ram_chunks;
    std::vector<size_t> ram_chunk_bytes;
    std::vector<char> cp_chunk;
    std::vector<int> draft_vram;
    const Layer& member(const Layer& l, int m) const { return l.nm == 1 ? l : members.at(m); }
    size_t mx_row_b(const Layer& l, int r) const { return gg::type_row_bytes(gg::expert_type(l.lay, r), r < 2 ? g.dim : g.ff); }
    int mx_n(int r) const { return r < 2 ? g.ff : g.dim; }
    size_t unit(const Layer& l) const { return l.nm == 1 ? l.blob : l.hlay.trellis[2] + size_t(g.dim) * gg::type_row_bytes(2, l.ffn); }
    const uint8_t* mx_part_ptr(const Layer& l, int e, int r, int x) const {
        return ram_part.at(l.ram.at(e)).at(x) + cp_lay.at(l.il).at(r);
    }
    bool read_mx_file(const Layer& l, int, uint8_t* dst) const {
        return !file_fail && pk.read_at(0, 0, l.blob, dst);
    }
    bool read_mx(const Layer& l, int e, uint8_t* dst) const { return read_mx_file(l, e, dst); }
    bool stream_expert(const Layer& l, int m, int, uint8_t* dst, cudaStream_t, std::string&, const uint8_t* si) {
        ++fallback_calls;
        return cudaMemcpyAsync(dst, si, unit(member(l, m)), 1, 0) == 0;
    }
#include "ds4_optimization_methods.inc"
    Harness(int nm = 2, int parts = 2) : NH(parts) {
        Layer l; l.nm = nm;
        const size_t gr = mx_row_b(l, 0), dr = gg::type_row_bytes(2, g.ff);
        l.lay.trellis[0] = 0; l.lay.trellis[1] = size_t(g.ff) * gr;
        l.lay.trellis[2] = 2 * size_t(g.ff) * gr;
        l.blob = l.lay.trellis[2] + size_t(g.dim) * dr;
        pk.bytes.resize(l.blob);
        for (size_t i = 0; i < pk.bytes.size(); ++i) pk.bytes[i] = uint8_t((i * 73 + i / 127) % 251);
        L.assign(4, l); L[0] = l;
        for (int i = 1; i < 4; ++i) { L[i].mtp = true; L[i].il = i; }
        int off = 0;
        for (int m = 0; m < nm; ++m) {
            Layer x = l; x.ff0 = off;
            x.ffn = nm == 1 ? g.ff : nm == 2 ? (m == 0 ? 256 : 512) : 256;
            off += x.ffn;
            x.hlay.trellis[0] = 0; x.hlay.trellis[1] = size_t(x.ffn) * gr;
            x.hlay.trellis[2] = 2 * size_t(x.ffn) * gr;
            members.push_back(x);
        }
        cp_lay = {{0, size_t(g.ff / NH) * gr, 2 * size_t(g.ff / NH) * gr}};
        storage.resize(NH);
        for (int x = 0; x < NH; ++x) {
            storage[x].resize(cp_lay[0][2] + size_t(g.dim / NH) * dr);
            for (int r = 0; r < 3; ++r) {
                size_t nb = size_t(mx_n(r) / NH) * (r < 2 ? gr : dr);
                std::memcpy(storage[x].data() + cp_lay[0][r], pk.bytes.data() + l.lay.trellis[r] + size_t(x) * nb, nb);
            }
        }
        ram_part.resize(1);
        for (auto& b : storage) { ram_part[0].push_back(b.data()); ram_chunks.push_back(b.data()); ram_chunk_bytes.push_back(b.size()); }
    }
    std::vector<uint8_t> expected(int m) const {
        const Layer& l = L[0]; const Layer& x = member(l, m);
        if (l.nm == 1) return pk.bytes;
        std::vector<uint8_t> out(unit(x));
        for (int r = 0; r < 2; ++r) {
            const size_t stride = mx_row_b(l, r);
            std::memcpy(out.data() + x.hlay.trellis[r], pk.bytes.data() + l.lay.trellis[r] + size_t(x.ff0) * stride,
                        size_t(x.ffn) * stride);
        }
        const size_t dr = gg::type_row_bytes(2, g.ff), dh = gg::type_row_bytes(2, x.ffn), d0 = gg::type_row_bytes(2, x.ff0);
        for (int row = 0; row < g.dim; ++row)
            std::memcpy(out.data() + x.hlay.trellis[2] + size_t(row) * dh,
                        pk.bytes.data() + l.lay.trellis[2] + size_t(row) * dr + d0, dh);
        return out;
    }
};
static void require(bool b) { if (!b) throw std::runtime_error("control failed"); }
static int count = 0;
template<class F> static void test(const char* id, F f) { f(); ++count; std::cout << "PASS " << id << '\n'; }
static void env(const char* value) {
    unsetenv("STRATA_DS4_COPY_PIN"); unsetenv("DS4_COPY_PIN");
    if (value) setenv("DS4_COPY_PIN", value, 1);
    pins = unpins = copy_calls = 0; pin_fail_at = copy_fail_at = -1; unpin_fail = false;
}
int main() {
    try {
        for (int nm : {1, 2, 3}) for (int parts : {1, 2}) for (bool file : {false, true}) {
            const std::string id = "member-" + std::to_string(nm) + "-numa-" + std::to_string(parts) + (file ? "-file" : "-RAM");
            test(id.c_str(), [&] {
                Harness h(nm, parts); if (file) h.L[0].ram[0] = -1;
                for (int m = 0; m < nm; ++m) {
                    auto want = h.expected(m); std::vector<uint8_t> stage(h.L[0].blob + 64, 0xA5), out(want.size() + 64, 0xA5);
                    std::string err; require(h.stage_streamed(h.L[0], m, 0, stage.data() + 32));
                    require(h.copy_streamed(h.L[0], m, 0, stage.data() + 32, out.data() + 32, 0, err));
                    require(std::equal(want.begin(), want.end(), out.begin() + 32));
                    require(std::all_of(out.begin(), out.begin() + 32, [](uint8_t v) { return v == 0xA5; }));
                    require(std::all_of(out.end() - 32, out.end(), [](uint8_t v) { return v == 0xA5; }));
                }
            });
        }
        for (int nm : {1, 2, 3}) test(("direct-" + std::to_string(nm)).c_str(), [&] {
            Harness h(nm); h.cp_dma = true;
            for (int m = 0; m < nm; ++m) {
                auto want = h.expected(m); std::vector<uint8_t> stage(h.L[0].blob), out(want.size()); std::string err;
                require(h.stage_needed(h.L[0], 0) == (nm > 1));
                require(h.stage_streamed(h.L[0], m, 0, stage.data()));
                require(h.copy_streamed(h.L[0], m, 0, nm > 1 ? stage.data() : nullptr, out.data(), 0, err));
                require(out == want);
            }
        });
        test("file-read-fault", [] { Harness h; h.L[0].ram[0] = -1; h.file_fail = true; std::vector<uint8_t> b(h.L[0].blob); require(!h.stage_streamed(h.L[0], 0, 0, b.data())); });
        test("direct-copy-fault", [] { env(nullptr); Harness h; h.cp_dma = true; auto out = h.expected(0); std::vector<uint8_t> stage(h.L[0].blob); copy_fail_at = 0; std::string err; require(!h.copy_streamed(h.L[0], 0, 0, stage.data(), out.data(), 0, err)); require(!err.empty()); env(nullptr); });
        test("pin-unset-no-side-effect", [] { env(nullptr); Harness h; std::string e; require(h.cp_pin(e) && !h.cp_dma && pins == 0); });
        test("pin-zero-no-side-effect", [] { env("0"); Harness h; std::string e; require(h.cp_pin(e) && pins == 0); });
        test("pin-malformed-refused", [] { env("yes"); Harness h; std::string e; require(!h.cp_pin(e) && pins == 0 && !e.empty()); });
        test("pin-all-success", [] { env("1"); Harness h; std::string e; require(h.cp_pin(e) && h.cp_dma && pins == 2 && unpins == 0); });
        test("pin-partial-rollback", [] { env("1"); pin_fail_at = 0; Harness h; std::string e; require(h.cp_pin(e) && !h.cp_dma && pins == 2 && unpins == 1); require(std::count(h.cp_chunk.begin(), h.cp_chunk.end(), 1) == 0); });
        test("pin-rollback-error-terminal", [] { env("1"); pin_fail_at = 0; unpin_fail = true; Harness h; std::string e; require(!h.cp_pin(e) && !h.cp_dma && !e.empty()); });
        test("pin-no-copy-mode", [] { env("1"); Harness h; h.copy_mode = false; std::string e; require(h.cp_pin(e) && pins == 0); });
        test("pin-no-chunk", [] { env("1"); Harness h; h.chunk = 0; std::string e; require(h.cp_pin(e) && pins == 0); });
        test("pin-alias-precedence", [] { env("1"); setenv("STRATA_DS4_COPY_PIN", "0", 1); Harness h; std::string e; require(h.cp_pin(e) && pins == 0); });
        test("draft-unset", [] { unsetenv("DS4_DRAFT_VRAM"); unsetenv("STRATA_DS4_DRAFT_VRAM"); Harness h; std::string e; require(h.draft_caps(e) && h.draft_vram.empty()); });
        for (const char* value : {"0", "128", "96,48,32"}) test((std::string("draft-valid-") + value).c_str(), [&] {
            setenv("DS4_DRAFT_VRAM", value, 1); Harness h; std::string e; require(h.draft_caps(e) && h.draft_vram.size() == 3);
            require(h.vram_cap(h.L[0]) == 128); require(h.vram_cap(h.L[1]) == h.draft_vram[0]);
        });
        for (const char* value : {"", "-1", "129", "1,2", "1,2,3,4", "1,", "1.5", " 1", "999999999999999999999"})
            test((std::string("draft-invalid-") + value).c_str(), [&] { setenv("DS4_DRAFT_VRAM", value, 1); Harness h; std::string e; require(!h.draft_caps(e) && h.draft_vram.empty() && !e.empty()); });
        test("draft-mixed-class-refused", [] { setenv("DS4_DRAFT_VRAM", "127", 1); Harness h; h.L[1].n_cls = 2; std::string e; require(!h.draft_caps(e) && h.draft_vram.empty()); });
        test("draft-mixed-full-valid", [] { setenv("DS4_DRAFT_VRAM", "128", 1); Harness h; h.L[1].n_cls = 2; std::string e; require(h.draft_caps(e)); });
        test("draft-no-block-refused", [] { setenv("DS4_DRAFT_VRAM", "0", 1); Harness h; h.g.n_mtp = 0; std::string e; require(!h.draft_caps(e)); });
        env(nullptr); unsetenv("DS4_DRAFT_VRAM");
        std::cout << "SUMMARY " << count << " controls passed\n"; return 0;
    } catch (const std::exception& e) { std::cerr << "FAIL " << e.what() << '\n'; return 1; }
}
