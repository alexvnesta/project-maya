#pragma once
#include <cstring>

namespace strata::ds4::head_batch {
// This is a strict experimental opt-in, independent of all Q8/IQ settings.
inline int flag(const char* value) {
    if (!value || std::strcmp(value, "0") == 0) return 0;
    return std::strcmp(value, "1") == 0 ? 1 : -1;
}
inline int width(const char* primary, const char* alias) {
    const int a = flag(primary), b = flag(alias);
    if (a < 0 || b < 0 || (primary && alias && a != b)) return -1;
    return (primary ? a : b) == 1 ? 8 : 4;
}
inline int check_device(const char* value) {
    if (value && std::strcmp(value, "0") == 0) return 0;
    if (value && std::strcmp(value, "1") == 0) return 1;
    return -1;
}
inline bool required_one(const char* primary, const char* alias) {
    return (primary || alias) && (!primary || flag(primary) == 1) && (!alias || flag(alias) == 1);
}
// The production GGUF head and fixture both use this exact loop. No GPU math,
// allocation, stream, gather, synchronization or sampling policy lives here.
template <class Call>
bool each(int rows, int per, Call&& call) {
    if (rows < 0 || rows > 16 || (per != 4 && per != 8)) return false;
    for (int first = 0; first < rows; first += per) {
        const int left = rows - first;
        if (!call(first, left < per ? left : per)) return false;
    }
    return true;
}
} // namespace strata::ds4::head_batch
