// Byte-priced admission for the existing expert-cache swap queue. No new tier or owner.
#pragma once
#include <cmath>
#include <cstddef>

namespace strata::ds4 {
inline bool cache_migration_worthwhile(float hot, float cold, float margin, float bonus,
                                      size_t expert_bytes, double mib_per_reuse) {
    // Zero preserves the original floating-point predicate exactly.
    if (!(hot > cold * margin + bonus)) return false;
    if (mib_per_reuse == 0.0) return true;
    if (!std::isfinite(mib_per_reuse) || mib_per_reuse < 0.0 || !std::isfinite(hot) ||
        !std::isfinite(cold) || expert_bytes == 0) return false;
    // The current exclusive tiers upload the new expert and download the displaced one.
    // Price those two transfers against the excess routing heat, in MiB per additional reuse.
    const double transfer_mib = 2.0 * static_cast<double>(expert_bytes) / (1024.0 * 1024.0);
    return static_cast<double>(hot) - static_cast<double>(cold) >= transfer_mib / mib_per_reuse;
}
}  // namespace strata::ds4
