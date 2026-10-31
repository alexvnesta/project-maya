// Actual extracted startup method with a synthetic copy backend. No CUDA proof.
#include <algorithm>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
namespace gg {
constexpr int kFmtMXFP4 = 1;
struct Layout { int fmt = kFmtMXFP4; int type[3]{1, 1, 2}; };
int expert_type(const Layout& x, int r) { return x.type[r]; }
std::string type_name(int t) { return std::to_string(t); }
}
struct Layer {
    bool mtp = false;
    int nm = 1, il = 0, dev = 0, n_exp = 2, ffn = 256;
    gg::Layout lay;
    std::vector<int> ram{0, -1};
};
struct Harness {
    struct Chunk { void* stage = reinterpret_cast<void*>(1); bool flow = false; };
    struct Device { int id; };
    struct Geometry { int ff = 512; } g;
    bool cp_dma = true, fault = false, bad_bytes = false, bad_guard = false;
    std::vector<Layer> L, members;
    std::vector<std::unique_ptr<Chunk>> chunks;
    std::vector<Device> devs{{0}, {1}};
    std::vector<std::tuple<int, int, int>> checked;
    Harness() {
        L.resize(2); L[1].dev = 1; L[1].il = 1;
        for (int i = 0; i < 2; ++i) chunks.push_back(std::make_unique<Chunk>());
        members = L;
    }
    const Layer& member(const Layer& l, int m) const { return l.nm == 1 ? l : members.at(m); }
    bool stream_direct(const Layer&, int) const { return cp_dma; }
    bool tp_copy_member(const Layer& l, int m, int e, size_t& b, size_t& guard, std::string& err) {
        checked.emplace_back(l.il, member(l, m).dev, e);
        b = bad_bytes ? 1 : 0; guard = bad_guard ? 1 : 0;
        if (fault) { err = "scripted copy error"; return false; }
        return true;
    }
#include "ds4_prompt_copy_check.inc"
};
int count = 0;
void require(bool ok) { if (!ok) throw std::runtime_error("control failed"); }
template<class F> void test(const char* id, F f) { f(); ++count; std::printf("PASS %s\n", id); }
int main() {
    try {
        test("two-devices-ram-and-file", [] {
            Harness h; std::string e; require(h.prompt_copy_check(e));
            require(h.checked == std::vector<std::tuple<int,int,int>>{{0,0,0},{0,0,1},{1,1,0},{1,1,1}});
        });
        test("all-flow-pinned-not-applicable", [] {
            Harness h; for (auto& c : h.chunks) c->flow = true;
            std::string e; require(h.prompt_copy_check(e) && e.empty() && h.checked.empty());
        });
        test("mixed-flow-only-nonflow-checked", [] {
            Harness h; h.chunks[0]->flow = true; std::string e;
            require(h.prompt_copy_check(e) && h.checked == std::vector<std::tuple<int,int,int>>{{1,1,0},{1,1,1}});
        });
        test("unpinned-staged-path-checked", [] {
            Harness h; h.cp_dma = false; std::string e; require(h.prompt_copy_check(e) && h.checked.size() == 4);
        });
        test("no-staging-not-applicable", [] {
            Harness h; for (auto& c : h.chunks) c->stage = nullptr;
            std::string e; require(h.prompt_copy_check(e) && h.checked.empty());
        });
        test("missing-chunk-not-applicable", [] {
            Harness h; h.chunks.clear(); std::string e; require(h.prompt_copy_check(e) && h.checked.empty());
        });
        test("eligible-without-experts-refused", [] {
            Harness h; h.L[1].n_exp = 0; std::string e; require(!h.prompt_copy_check(e) && !e.empty());
        });
        test("copy-error-terminal", [] {
            Harness h; h.fault = true; std::string e;
            require(!h.prompt_copy_check(e) && !e.empty() && h.checked.size() == 1);
        });
        test("byte-error-terminal", [] {
            Harness h; h.bad_bytes = true; std::string e;
            require(!h.prompt_copy_check(e) && !e.empty() && h.checked.size() == 1);
        });
        test("guard-error-terminal", [] {
            Harness h; h.bad_guard = true; std::string e;
            require(!h.prompt_copy_check(e) && !e.empty() && h.checked.size() == 1);
        });
        test("repeated-device-format-deduplicated", [] {
            Harness h; h.L.push_back(h.L[0]); std::string e;
            require(h.prompt_copy_check(e) && h.checked.size() == 4);
        });
        test("new-device-format-covered", [] {
            Harness h; h.L.push_back(h.L[0]); h.L.back().lay.type[2] = 3;
            std::string e; require(h.prompt_copy_check(e) && h.checked.size() == 6);
        });
        test("both-split-rotations-and-members", [] {
            Harness h; for (auto& l : h.L) l.nm = 2;
            std::string e; require(h.prompt_copy_check(e) && h.checked.size() == 8);
        });
        test("drafter-excluded", [] {
            Harness h; for (auto& l : h.L) l.mtp = true;
            std::string e; require(h.prompt_copy_check(e) && h.checked.empty());
        });
        test("ram-only-member", [] {
            Harness h; h.L.resize(1); h.L[0].ram = {0, 1}; std::string e;
            require(h.prompt_copy_check(e) && h.checked.size() == 1 && std::get<2>(h.checked[0]) == 0);
        });
        test("file-only-member", [] {
            Harness h; h.L.resize(1); h.L[0].ram.clear(); std::string e;
            require(h.prompt_copy_check(e) && h.checked.size() == 1 && std::get<2>(h.checked[0]) == 0);
        });
        std::printf("SUMMARY %d controls passed; synthetic copy backend, no GPU proof\n", count);
        return 0;
    } catch (const std::exception& e) { std::fprintf(stderr, "FAIL %s\n", e.what()); return 1; }
}
