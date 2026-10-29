#pragma once
#include <climits>

namespace strata::ds4::gguf::iq::iq2s_policy {
// Pure policy used by production dispatch and CPU controls. Invalid text fails off.
inline int literal_mode(const char* p) {
    return p && p[0] && !p[1] && (p[0] == '0' || p[0] == '1') ? p[0] - '0' : -1;
}
inline int env_mode(const char* primary, const char* secondary) {
    if (!primary && !secondary) return 0;
    const int a = primary ? literal_mode(primary) : literal_mode(secondary);
    if (a < 0 || (primary && secondary && literal_mode(secondary) != a)) return -1;
    return a;
}
inline bool geometry(int d, int f, unsigned groups) {
    return d > 0 && f > 0 && d % 256 == 0 && f % 256 == 0 && groups > 0 &&
           groups <= (unsigned) (INT_MAX / (d / 16)) && groups <= (unsigned) (INT_MAX / (f / 8));
}
inline int resident_blocks(int sms, int per) {
    return sms > 0 && per > 0 && sms <= INT_MAX / per ? sms * per : 0;
}
inline unsigned grid_blocks(long long items, int resident, unsigned test_cap = 0) {
    if (items <= 0 || items > INT_MAX || resident <= 0) return 0;
    unsigned n = (unsigned) (items < resident ? items : resident);
    if (test_cap && test_cap < n) n = test_cap;
    return n;
}
inline int check_device(const char* p) { return literal_mode(p); }
} // namespace strata::ds4::gguf::iq::iq2s_policy
