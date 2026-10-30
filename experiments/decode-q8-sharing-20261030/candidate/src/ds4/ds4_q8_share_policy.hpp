#pragma once
#include <cstddef>
#include <cstring>

namespace strata::ds4::q8share {
constexpr int max_jobs = 8;
struct Key {
    const void* x;
    size_t stride;
    int rows, k;
};
// Match only within the current mv call. Effective stride is k for one row.
inline size_t effective_stride(int rows, size_t stride, int k) {
    return rows == 1 ? static_cast<size_t>(k) : stride;
}
inline bool same_input(const Key& a, const Key& b) {
    return a.x != nullptr && b.x != nullptr && a.rows > 0 && a.k > 0 &&
           a.x == b.x && a.stride == b.stride && a.rows == b.rows && a.k == b.k;
}
inline int first_match(const Key* keys, int n, const Key& key, bool enabled) {
    if (!enabled || keys == nullptr || n < 0 || n > max_jobs) return -1;
    for (int i = 0; i < n; ++i) if (same_input(keys[i], key)) return i;
    return -1;
}
// Opt-in only; the prefixed variable has priority even when it disables sharing.
inline bool enabled(const char* prefixed, const char* plain) {
    const char* v = prefixed != nullptr ? prefixed : plain;
    return v != nullptr && std::strcmp(v, "1") == 0;
}
inline int check_device(const char* s) {
    if (s != nullptr && std::strcmp(s, "0") == 0) return 0;
    if (s != nullptr && std::strcmp(s, "1") == 0) return 1;
    return -1;
}
inline bool required_flag(const char* prefixed, const char* plain) {
    const char* v = prefixed != nullptr ? prefixed : plain;
    return v != nullptr && std::strcmp(v, "1") == 0;
}
} // namespace strata::ds4::q8share
