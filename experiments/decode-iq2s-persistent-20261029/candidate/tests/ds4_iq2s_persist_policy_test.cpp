#include "../src/ds4/ds4_iq2s_persist_policy.hpp"
#include <cstdio>
#include <cstdlib>
namespace p = strata::ds4::gguf::iq::iq2s_policy;
int main() {
    int n = 0;
    auto check = [&](bool ok, const char* id) {
        ++n; std::printf("%s %s\n", ok ? "PASS" : "FAIL", id);
        if (!ok) std::exit(1);
    };
    check(p::env_mode(nullptr, nullptr) == 0, "default_off");
    check(p::env_mode("1", nullptr) == 1, "primary_on");
    check(p::env_mode(nullptr, "1") == 1, "secondary_on");
    check(p::env_mode("1", "1") == 1, "aliases_on");
    check(p::env_mode("0", "0") == 0, "aliases_off");
    check(p::env_mode("1", "0") == -1, "alias_conflict");
    check(p::env_mode("0", "1") == -1, "alias_conflict_reverse");
    const char* bad[] = {"", "2", "-1", "01", "1 ", " 1", "true", "1x", "1\n"};
    for (int i = 0; i < 9; ++i) {
        char id[64];
        std::snprintf(id, sizeof id, "invalid_mode_%d", i);
        check(p::env_mode(bad[i], nullptr) == -1 && p::env_mode("1", bad[i]) == -1, id);
        std::snprintf(id, sizeof id, "invalid_device_%d", i);
        check(p::check_device(bad[i]) == -1, id);
    }
    check(p::check_device(nullptr) == -1, "null_device");
    check(p::check_device("0") == 0 && p::check_device("1") == 1, "two_exact_devices");
    check(p::geometry(5120, 2304, 128), "actual_full_window_geometry");
    check(p::geometry(256, 256, 1), "small_geometry");
    check(!p::geometry(0, 256, 1), "zero_dimension");
    check(!p::geometry(256, -256, 1), "negative_dimension");
    check(!p::geometry(5121, 2304, 1), "unaligned_dimension");
    check(!p::geometry(5120, 2304, 0), "zero_groups");
    check(!p::geometry(5120, 2304, UINT_MAX), "group_product_overflow");
    check(p::resident_blocks(108, 4) == 432, "resident_product");
    check(p::resident_blocks(0, 4) == 0 && p::resident_blocks(108, 0) == 0, "failed_queries");
    check(p::resident_blocks(-1, 4) == 0 && p::resident_blocks(108, -1) == 0, "negative_queries");
    check(p::resident_blocks(INT_MAX, 2) == 0, "resident_overflow");
    check(p::grid_blocks(1, 432) == 1, "grid_under_capacity");
    check(p::grid_blocks(432, 432) == 432, "grid_at_capacity");
    check(p::grid_blocks(10000, 432) == 432, "grid_reuses_blocks");
    check(p::grid_blocks(0, 432) == 0 && p::grid_blocks(-1, 432) == 0, "empty_grid");
    check(p::grid_blocks((long long) INT_MAX + 1, 432) == 0, "item_overflow");
    check(p::grid_blocks(100, -1) == 0, "unknown_occupancy_fallback");
    check(p::grid_blocks(10000, 432, 1) == 1, "test_single_resident");
    check(p::grid_blocks(2, 432, 3) == 2, "test_cap_never_adds_work");
    std::printf("ALL %d policy checks passed\n", n);
}
