#pragma once

#include <array>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace strata::ds4 {

// A diagnostic snapshot after actual GPU allocation, before loading routed experts.
// Counts are the frozen public/owned-synthetic profile supplied to that private run.
struct PlacementPlanLayer {
    std::vector<int> slots;
    std::vector<uint32_t> counts;
    std::array<uint64_t, 3> role_bytes{};
    std::array<int, 3> role_types{};
    int members = 0;
};

inline uint64_t placement_role_bytes(int role, int type) {
    int per = 256, bytes = 0;
    switch (type) {
        case 10: bytes = 84; break; case 11: bytes = 110; break;
        case 12: bytes = 144; break; case 13: bytes = 176; break; case 14: bytes = 210; break;
        case 16: bytes = 66; break; case 17: bytes = 74; break; case 18: bytes = 98; break;
        case 19: bytes = 50; break; case 21: bytes = 110; break; case 22: bytes = 82; break;
        case 23: bytes = 136; break; case 29: bytes = 56; break;
        case 20: per = 32; bytes = 18; break; case 39: per = 32; bytes = 17; break;
        default: return 0;
    }
    if (role < 0 || role > 2) return 0;
    const uint64_t n = role < 2 ? 2304 : 5120, k = role < 2 ? 5120 : 2304;
    return n * (k / (uint64_t) per) * (uint64_t) bytes;
}

inline bool placement_plan_path(const std::string& path, std::string& err) {
    namespace fs = std::filesystem;
    const fs::path value(path);
    if (path.empty() || !value.is_absolute() || value.filename().empty() ||
        value.filename() == "." || value.filename() == "..") {
        err = "placement plan: absolute output file required"; return false;
    }
    fs::path current = value.root_path();
    std::error_code ec;
    const auto root_status = fs::symlink_status(current, ec);
    if (ec || !fs::is_directory(root_status) || fs::is_symlink(root_status)) {
        err = "placement plan: real output root required"; return false;
    }
    for (const auto& part : value.relative_path().parent_path()) {
        if (part == ".." || part == ".") { err = "placement plan: no relative path components"; return false; }
        current /= part;
        const auto status = fs::symlink_status(current, ec);
        if (ec || !fs::is_directory(status) || fs::is_symlink(status)) {
            err = "placement plan: real existing output parents required"; return false;
        }
    }
    return true;
}

inline bool placement_plan_json(int64_t context, int chunk, int drafter_blocks,
                                const std::vector<PlacementPlanLayer>& layers,
                                std::string& output, std::string& err) {
    output.clear();
    err.clear();
    auto fail = [&](const char* why) { err = why; return false; };
    if (context < 1 || context > 1048576 || chunk < 0 || chunk > 32768 ||
        drafter_blocks != 3 || layers.size() != 40)
        return fail("placement plan: bounded context/chunk and complete trunk/drafter required");
    uint64_t cpu_bytes = 0;
    int cpu_experts = 0, gpu_experts = 0;
    for (const auto& l : layers) {
        if (l.slots.size() != 384 || l.counts.size() != 384 || l.members < 1 || l.members > 16)
            return fail("placement plan: actual complete layer slot/count/member map required");
        std::set<int> slots;
        uint64_t hits = 0, bytes = 0;
        for (size_t r = 0; r < 3; ++r) {
            const uint64_t n = l.role_bytes[r];
            if (n == 0 || n != placement_role_bytes((int) r, l.role_types[r]))
                return fail("placement plan: invalid expert matrix byte geometry");
            bytes += n;
        }
        for (size_t e = 0; e < 384; ++e) {
            const int slot = l.slots[e];
            if (slot < -1 || slot >= 384 || (slot >= 0 && !slots.insert(slot).second))
                return fail("placement plan: duplicate or out-of-range actual GPU slot");
            hits += l.counts[e];
            if (slot < 0) { ++cpu_experts; cpu_bytes += bytes; }
            else ++gpu_experts;
        }
        if (!hits) return fail("placement plan: a routing profile is required for every layer");
    }
    std::ostringstream s;
    s << "{\"schema\":\"ds4-actual-placement-v1\",\"context_total\":" << context
      << ",\"prefill_chunk\":" << chunk << ",\"drafter_blocks\":" << drafter_blocks
      << ",\"routed_experts_loaded\":false,\"inference_executed\":false,\"expert_cache\":false"
      << ",\"CPU_experts\":" << cpu_experts << ",\"GPU_experts\":" << gpu_experts
      << ",\"CPU_base_payload_bytes\":" << cpu_bytes << ",\"layers\":[";
    for (size_t il = 0; il < layers.size(); ++il) {
        const auto& l = layers[il];
        if (il) s << ',';
        s << "{\"layer\":" << il << ",\"members\":" << l.members << ",\"role_bytes\":[";
        for (size_t r = 0; r < 3; ++r) s << (r ? "," : "") << l.role_bytes[r];
        s << "],\"role_types\":[";
        for (size_t r = 0; r < 3; ++r) s << (r ? "," : "") << l.role_types[r];
        s << "],\"slots\":[";
        for (size_t e = 0; e < 384; ++e) s << (e ? "," : "") << l.slots[e];
        s << "],\"counts\":[";
        for (size_t e = 0; e < 384; ++e) s << (e ? "," : "") << l.counts[e];
        s << "]}";
    }
    s << "]}\n";
    output = s.str();
    return true;
}

// Never replace an existing receipt. Failed/partial output remains for diagnosis.
inline bool placement_plan_write(const std::string& path, const std::string& json, std::string& err) {
    if (!placement_plan_path(path, err)) return false;
    if (json.empty()) { err = "placement plan: output body required"; return false; }
    std::FILE* file = std::fopen(path.c_str(), "wbx");
    if (!file) { err = "placement plan: cannot exclusively create output"; return false; }
    const bool wrote = std::fwrite(json.data(), 1, json.size(), file) == json.size();
    const bool closed = std::fclose(file) == 0;
    if (!wrote || !closed) { err = "placement plan: incomplete output retained"; return false; }
    return true;
}

}  // namespace strata::ds4
