#pragma once
// CPU-only sidecar descriptor and routing helpers. No file I/O, allocation of model payload,
// CUDA, or inference here. The caller must separately verify the complete artifact's
// SHA/provenance; a format/placement check does not authenticate model weights.
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

namespace s2native {
// The process/cgroup budget and the host's free reserve are separate envelopes.
// ram_avail() is already capped by the tightest cgroup; subtracting the host
// reserve from it again would reject a 73.8 GiB payload inside an 80 GiB fence.
inline bool expert_ram_fits(uint64_t need, uint64_t process_room, uint64_t host_room) {
    constexpr uint64_t process_limit = 80ull << 30, host_margin = 8ull << 30;
    return need > 0 && need <= process_limit && process_room != ~uint64_t{0} &&
           host_room != ~uint64_t{0} && process_room >= need && host_room >= need + host_margin;
}
class Plan {
public:
    static constexpr int Layers = 40, Experts = 384, Dim = 5120, FF = 2304, Count = 1870;
    static constexpr uint64_t HeaderBytes = 102400;
    static constexpr uint64_t MatrixBytes = uint64_t(FF) * (Dim / 32) * 17;
    static constexpr uint64_t ExpertBytes = 3 * MatrixBytes;
    static constexpr uint64_t PayloadBytes = uint64_t(Count) * ExpertBytes;
    static constexpr uint64_t FileBytes = HeaderBytes + PayloadBytes;
    static constexpr size_t CountsAt = 120;
    static constexpr size_t SlotsAt = CountsAt + Layers * Experts * 4;
    static constexpr size_t IdsAt = SlotsAt + Layers * Experts * 2;
    static constexpr size_t PaddingAt = IdsAt + Count * 4;

    Plan() { index_.fill(-1); }

    static bool parse(const std::vector<uint8_t>& bytes, uint64_t actual_file_bytes,
                      const std::array<uint8_t, 32>& expected_source_map, Plan& out, std::string& error) {
        out = Plan(); // Never leave a previously verified plan usable after a failed reload.
        auto fail = [&](const char* why) { error = why; return false; };
        if (bytes.size() != HeaderBytes || actual_file_bytes != FileBytes)
            return fail("native CPU sidecar: exact header and complete three-role payload size required");
        if (std::memcmp(bytes.data(), "MAYACPU1", 8) != 0 || u32(bytes, 8) != 1 ||
            u32(bytes, 12) != Layers || u32(bytes, 16) != Experts || u32(bytes, 20) != Dim ||
            u32(bytes, 24) != FF || u32(bytes, 28) != Count ||
            u64(bytes, 32) != HeaderBytes || u64(bytes, 40) != PayloadBytes)
            return fail("native CPU sidecar: fixed original geometry/version/count required");
        if (std::memcmp(bytes.data() + 48, "1bae0e1088993b9b82de08f59de5be5a34e42170", 40) != 0 ||
            std::all_of(expected_source_map.begin(), expected_source_map.end(), [](uint8_t b) { return b == 0; }) ||
            !std::equal(expected_source_map.begin(), expected_source_map.end(), bytes.begin() + 88))
            return fail("native CPU sidecar: exact original revision and externally pinned source map required");
        Plan value;
        value.counts_.resize(Layers * Experts);
        value.slots_.resize(Layers * Experts);
        for (int layer = 0; layer < Layers; ++layer) {
            uint64_t sum = 0;
            std::array<bool, Experts> used{};
            int resident = 0;
            for (int expert = 0; expert < Experts; ++expert) {
                const size_t i = size_t(layer) * Experts + expert;
                value.counts_[i] = u32(bytes, CountsAt + i * 4); sum += value.counts_[i];
                const uint16_t slot = u16(bytes, SlotsAt + i * 2);
                if (slot == 0xffff) value.slots_[i] = -1;
                else {
                    if (slot >= Experts || used[slot]) return fail("native CPU sidecar: unique bounded actual GPU slots");
                    used[slot] = true; ++resident; value.slots_[i] = slot;
                }
            }
            if (sum == 0) return fail("native CPU sidecar: actual nonempty trunk routing profile required");
            for (int slot = 0; slot < resident; ++slot)
                if (!used[slot]) return fail("native CPU sidecar: initial static GPU slots must be contiguous");
        }
        std::pair<int, int> last{-1, -1};
        for (int i = 0; i < Count; ++i) {
            const int layer = u16(bytes, IdsAt + size_t(i) * 4);
            const int expert = u16(bytes, IdsAt + size_t(i) * 4 + 2);
            const std::pair<int, int> id{layer, expert};
            if (layer >= Layers || expert >= Experts || !(last < id) ||
                value.slots_[size_t(layer) * Experts + expert] >= 0)
                return fail("native CPU sidecar: exactly1870 ordered unique CPU-only trunk IDs");
            value.index_[size_t(layer) * Experts + expert] = i;
            value.ids_.push_back(id); last = id;
        }
        for (int layer = 24; layer <= 28; ++layer)
            for (int expert = 0; expert < Experts; ++expert) {
                const size_t i = size_t(layer) * Experts + expert;
                if (value.slots_[i] < 0 && value.index_[i] < 0)
                    return fail("native CPU sidecar: every sensitive-layer CPU expert must be native");
            }
        if (std::any_of(bytes.begin() + PaddingAt, bytes.end(), [](uint8_t b) { return b != 0; }))
            return fail("native CPU sidecar: reserved header bytes must be zero");
        value.parsed_ = true; out = std::move(value); error.clear(); return true;
    }

    bool verify_placement(const std::vector<uint32_t>& actual_counts,
                          const std::vector<int>& actual_slots, std::string& error) {
        placement_ = false;
        if (!parsed_ || actual_counts != counts_ || actual_slots != slots_) {
            error = "native CPU sidecar: actual profile or post-allocation GPU placement changed";
            return false;
        }
        placement_ = true; error.clear(); return true;
    }

    bool placement_verified() const { return parsed_ && placement_; }
    bool selected(int layer, int expert) const {
        return placement_verified() && layer >= 0 && layer < Layers && expert >= 0 && expert < Experts &&
               index_[size_t(layer) * Experts + expert] >= 0;
    }
    bool role_range(int layer, int expert, int role, uint64_t& offset, uint64_t& size, std::string& error) const {
        offset = size = 0;
        if (!selected(layer, expert) || role < 0 || role >= 3) {
            error = "native CPU sidecar: verified selected expert and complete w1/w3/w2 role required";
            return false;
        }
        offset = HeaderBytes + uint64_t(index_[size_t(layer) * Experts + expert]) * ExpertBytes +
                 uint64_t(role) * MatrixBytes;
        size = MatrixBytes;
        if (offset > FileBytes - size) { offset = size = 0; error = "native CPU sidecar: payload range overflow"; return false; }
        error.clear(); return true;
    }
    const std::vector<std::pair<int, int>>& ids() const { return ids_; }

private:
    static uint16_t u16(const std::vector<uint8_t>& b, size_t p) {
        return uint16_t(b[p]) | uint16_t(uint16_t(b[p + 1]) << 8);
    }
    static uint32_t u32(const std::vector<uint8_t>& b, size_t p) {
        uint32_t value = 0;
        for (int i = 0; i < 4; ++i) value |= uint32_t(b[p + size_t(i)]) << (8 * i);
        return value;
    }
    static uint64_t u64(const std::vector<uint8_t>& b, size_t p) {
        return uint64_t(u32(b, p)) | (uint64_t(u32(b, p + 4)) << 32);
    }
    bool parsed_ = false, placement_ = false;
    std::array<int, Layers * Experts> index_{};
    std::vector<uint32_t> counts_;
    std::vector<int> slots_;
    std::vector<std::pair<int, int>> ids_;
};
// Copy entries into disjoint representations without changing output slots or
// token rows. Original scheduling indices do not apply to either subset.
template<class Entry, class Selected, class Bind>
void partition_entries(const std::vector<Entry>& source, Selected selected, Bind bind,
                       std::vector<Entry>& native, std::vector<Entry>& iq) {
    native.clear(); iq.clear();
    for (const Entry& original : source) {
        Entry en = original;
        if (selected(en.e)) {
            for (int role = 0; role < 3; ++role) en.src[role] = bind(en.e, role);
            native.push_back(en);
        } else iq.push_back(en);
    }
}

// Streamed virtual slots must remain contiguous; CPU prompt slots trail them.
// The speculative prefix has already been assigned before this function runs.
template<class Selected>
int append_prompt_slots(const std::vector<int>& host, const std::vector<char>& prefix,
                        Selected cpu, int first, int* slots) {
    for (int e : host) if (!prefix[(size_t) e] && !cpu(e)) slots[e] = first++;
    for (int e : host) if (cpu(e)) slots[e] = first++;
    return first;
}
} // namespace s2native
