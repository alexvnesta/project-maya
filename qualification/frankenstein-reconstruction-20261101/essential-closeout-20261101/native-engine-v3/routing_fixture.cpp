// CPU-only checks of the actual helper templates used by the native engine.
#include "ds4_cpu_native.hpp"
#include <array>
#include <cassert>
#include <cstdlib>

struct Entry {
    int e = 0, n = 0, slot0 = 0;
    int tok[8]{};
    const uint8_t* src[3]{};
};

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const int control = std::atoi(argv[1]);
    if (control < 0 || control > 7) return 2;
    if (control == 7) {
        constexpr uint64_t need = 79265249280ull, margin = 8ull << 30, limit = 80ull << 30;
        assert(need + margin > limit); // The original deterministic refusal.
        assert(s2native::expert_ram_fits(need, limit, need + margin));
        assert(!s2native::expert_ram_fits(need, need - 1, need + margin));
        assert(!s2native::expert_ram_fits(need, limit, need + margin - 1));
        assert(!s2native::expert_ram_fits(limit + 1, 100ull << 30, 120ull << 30));
        assert(!s2native::expert_ram_fits(need, ~uint64_t{0}, 120ull << 30));
        assert(!s2native::expert_ram_fits(need, limit, ~uint64_t{0}));
        assert(!s2native::expert_ram_fits(~uint64_t{0}, limit, 120ull << 30));
        assert(!s2native::expert_ram_fits(0, limit, 120ull << 30));
        return 0;
    }
    uint8_t ordinary[1]{}, roles[6]{};
    if (control <= 2) {
        std::vector<Entry> source(6), native, iq;
        for (int i = 0; i < 6; ++i) {
            source[i].e = i; source[i].n = i + 1; source[i].slot0 = i * 8;
            for (int t = 0; t < 8; ++t) source[i].tok[t] = 90 - i * 8 - t;
            for (int r = 0; r < 3; ++r) source[i].src[r] = ordinary;
        }
        auto selected = [control](int e) { return control == 0 ? e % 2 == 0 : control == 1; };
        auto bind = [&](int e, int r) { return roles + (e % 2) * 3 + r; };
        s2native::partition_entries(source, selected, bind, native, iq);
        assert(native.size() + iq.size() == source.size());
        assert(native.size() == (control == 0 ? 3u : control == 1 ? 6u : 0u));
        std::array<int, 6> count{};
        for (const auto& group : {native, iq}) for (const Entry& en : group) {
            ++count[en.e];
            assert(en.n == source[en.e].n && en.slot0 == source[en.e].slot0);
            for (int t = 0; t < 8; ++t) assert(en.tok[t] == source[en.e].tok[t]);
            for (int r = 0; r < 3; ++r)
                assert(en.src[r] == (selected(en.e) ? bind(en.e, r) : ordinary));
        }
        for (int n : count) assert(n == 1);
        for (const Entry& en : source) for (int r = 0; r < 3; ++r) assert(en.src[r] == ordinary);
    } else {
        std::vector<int> host;
        std::vector<char> prefix(384, 0);
        std::array<int, 384> slots;
        slots.fill(-1);
        for (int e = 0; e < 384; ++e) host.push_back(e);
        auto cpu = [control](int e) { return control == 3 ? e % 3 == 0 : control == 4 ? true : false; };
        int first = 0;
        if (control == 6) { prefix[17] = prefix[199] = 1; slots[17] = first++; slots[199] = first++; }
        const int last = s2native::append_prompt_slots(host, prefix, cpu, first, slots.data());
        assert(last == 384);
        std::array<int, 384> seen{};
        int last_stream = -1, first_cpu = 384;
        for (int e : host) {
            assert(slots[e] >= 0 && slots[e] < 384);
            ++seen[slots[e]];
            if (cpu(e)) first_cpu = std::min(first_cpu, slots[e]);
            else last_stream = std::max(last_stream, slots[e]);
        }
        for (int n : seen) assert(n == 1);
        assert(last_stream < first_cpu);
        // Nonzero bounds for every virtual slot demonstrate that no CPU row
        // can become a hole within a streamed batch's interval.
        std::array<int, 385> bounds{};
        for (int i = 0; i < 384; ++i) bounds[i + 1] = bounds[i] + 1 + i % 7;
        for (int e : host) if (cpu(e)) assert(bounds[slots[e]] >= bounds[first_cpu]);
    }
    return 0;
}
