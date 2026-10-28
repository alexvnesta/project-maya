// CPU-only fixture around byte-exact selected production method extracts.
// Not a model, CUDA, numerical-equivalence or capacity test.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

struct Layer { int nm = 1, dev = 0, eg = -1; bool kv_src = false; };
struct Chunk { bool flow = true; };
struct Run {
    std::vector<int64_t> p0;
    std::vector<int> T;
    std::vector<uint64_t> seq;
    int yoco = -1, cut_k = 0, cut_r = 0;
};
struct Model {
    struct { int nl = 40, win = 128; std::vector<int> ratios; } g;
    std::vector<Layer> L;
    std::vector<Chunk*> chunks;
    Chunk streamed;
    int chunk = 1024;
    int64_t pos = 0;
    uint64_t win_seq = 100;
    static constexpr int kWin = 16, kYocoMin = 1024;
    Model() : L(40) {
        g.ratios.assign(40, 2);
        g.ratios[0] = g.ratios[1] = 0;
        for (int i = 20; i < 40; ++i) g.ratios[(size_t)i] = 1;
        for (int i : {2, 8, 14, 20}) L[(size_t)i].kv_src = true;
        L[1].eg = 0; L[14].eg = 1;
    }
    void split(int boundary, bool flow = true) {
        for (int i = 0; i < 40; ++i) L[(size_t)i].dev = i < boundary ? 0 : 1;
        chunks.clear(); if (flow) chunks.push_back(&streamed);
    }
#include "selected_skip_methods.inc"
    Run plan(int n, int logits_rows) {
        // Preconditions belong to forward_chunks' outer validation, not the extract.
        if (n <= 0 || pos < 0 || pos + n > 1048576) throw std::invalid_argument("fixture input");
#include "selected_skip_plan.inc"
        return run;
    }
};

void check(bool value, const char* id) {
    if (!value) { std::fprintf(stderr, "FAIL %s\n", id); std::exit(1); }
    std::printf("PASS %s\n", id);
}
bool covers(const Run& run, int64_t pos, int n, int width) {
    if (run.T.empty() || run.p0.size() != run.T.size() || run.seq.size() != run.T.size()) return false;
    int64_t next = pos; uint64_t seq = 100;
    for (size_t i = 0; i < run.T.size(); ++i) {
        if (run.p0[i] != next || run.T[i] < 1 || run.T[i] > width || run.seq[i] != ++seq) return false;
        next += run.T[i];
    }
    return next == pos + n;
}
void geometry() {
    Model selected; selected.split(19);
    check(selected.yoco_layer() == 20, "G01_selected_19_21_and_Engram_prefix");
    for (int boundary : {1, 10, 19, 20}) {
        Model m; m.split(boundary);
        check(m.yoco_layer() == 20, ("G02_prefix_split_" + std::to_string(boundary)).c_str());
    }
    for (int boundary : {21, 30, 39}) {
        Model m; m.split(boundary);
        check(m.yoco_layer() == -1, ("G03_flow_crosses_suffix_" + std::to_string(boundary)).c_str());
        m.chunks.clear();
        check(m.yoco_layer() == 20, ("G04_no_flow_crosses_suffix_" + std::to_string(boundary)).c_str());
    }
    Model one; check(one.yoco_layer() == 20, "G05_one_GPU");
    Model tp; tp.split(19, false); tp.L[20].nm = 2;
    check(tp.yoco_layer() == 20, "G06_TP_without_flow_is_eligible_source_fact");
    tp.chunks.push_back(&tp.streamed);
    check(tp.yoco_layer() == -1, "G07_TP_with_flow_refused");
    Model eg; eg.split(19); eg.L[25].eg = 2;
    check(eg.yoco_layer() == -1, "G08_suffix_Engram_split_refused");
    Model own; own.split(19); own.L[25].kv_src = true;
    check(own.yoco_layer() == -1, "G09_suffix_owns_KV_refused");
    Model ratio; ratio.split(19); ratio.g.ratios[25] = 2;
    check(ratio.yoco_layer() == -1, "G10_suffix_compression_refused");
    Model missing; missing.L[20].kv_src = false;
    check(missing.yoco_layer() == -1, "G11_missing_source_refused");
    Model short_meta; short_meta.g.ratios.resize(25);
    check(short_meta.yoco_layer() == -1, "G12_short_metadata_refused");
    Model first; first.g.ratios[0] = 1; first.L[0].kv_src = true;
    check(first.yoco_layer() == -1, "G13_source_zero_refused");
    Model window; window.chunk = 0;
    check(window.yoco_layer() == -1, "G14_window_path_refused");
}
void plans() {
    for (int n : {1, 16, 1024, 3691, 3692, 4096, 5000, 8192, 32761}) {
        Model m; m.split(19);
        Run r = m.plan(n, 1);
        check(covers(r, 0, n, 1024), ("P01_cover_" + std::to_string(n)).c_str());
        if (n <= 3691) check(r.yoco == -1, ("P02_short_no_skip_" + std::to_string(n)).c_str());
        else {
            check(r.yoco == 20, ("P03_source20_" + std::to_string(n)).c_str());
            const int64_t cut = r.p0[(size_t)r.cut_k] + r.cut_r;
            check(n - cut == 2668, ("P04_keep2668_" + std::to_string(n)).c_str());
        }
    }
    Model m; m.split(19);
    Run r = m.plan(8192, 1);
    check(r.cut_k == 5 && r.cut_r == 404, "P05_exact_8K_partial_chunk_cut");
    Model irregular; irregular.split(19); r = irregular.plan(5000, 1);
    check(r.cut_k == 2 && r.cut_r == 332, "P06_exact_irregular_chunk_cut");
    Model ledger; ledger.split(19); r = ledger.plan(32761, 1);
    check(r.cut_k == 29 && r.cut_r == 397, "P07_frozen_32761_cut");
    Model full_logits; full_logits.split(19); r = full_logits.plan(8192, 17);
    check(r.yoco == -1, "P08_full_row_logits_disable_skip");
    Model appended; appended.split(19); appended.pos = 6144; r = appended.plan(8192, 16);
    check(covers(r, 6144, 8192, 1024) && r.yoco == 20, "P09_append_positions_and_logits16");
    Model split_suffix; split_suffix.split(21); r = split_suffix.plan(8192, 1);
    check(r.yoco == -1, "P10_ineligible_plan_does_full_work");
    // An independent dependency expansion: final128 rows, then each decoder
    // layer's127-token lookback. This checks the mathematical span, not CUDA.
    int first = 8192 - 128;
    for (int layer = 39; layer >= 20; --layer) first -= 127;
    check(first == 5524 && 8192 - first == 2668, "P11_dependency_cone");
    check(8192 - 1 >= first, "P12_prefinal_checkpoint_in_replayed_tail");
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string group = argv[1];
    if (group == "geometry") geometry();
    else if (group == "plans") plans();
    else if (group == "off") {
        Model m; m.split(19); check(m.yoco_layer() == -1 && m.plan(8192, 1).yoco == -1, "E01_mode0_off");
    } else if (group == "on") {
        Model m; m.split(19); check(m.yoco_layer() == 20, "E02_mode1_on");
    } else if (group == "short_keep") {
        Model m; m.split(19); auto r = m.plan(8192, 1);
        check(8192 - (r.p0[(size_t)r.cut_k] + r.cut_r) == 128, "E03_mode2_or_KEEP_changes_dependency_span");
    } else if (group == "long_keep") {
        Model m; m.split(19); auto r = m.plan(8192, 1);
        check(8192 - (r.p0[(size_t)r.cut_k] + r.cut_r) == 4096, "E04_KEEP_override_is_real_must_be_forbidden");
    } else return 2;
}
