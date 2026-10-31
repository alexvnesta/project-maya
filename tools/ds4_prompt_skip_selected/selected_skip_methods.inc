    static int yoco_mode() {
        static const int m = [] {
            const char* v = std::getenv("DS4_YOCO");
            if (v == nullptr) v = std::getenv("STRATA_DS4_PROMPT_SKIP");
            return v != nullptr ? std::atoi(v) : 1;
        }();
        return m;
    }

    bool yoco_one_gpu() const {
        for (int il = 0; il < g.nl; ++il)
            if (L[(size_t) il].nm != 1 || L[(size_t) il].dev != L[0].dev) return false;
        return true;
    }

    bool yoco_suffix_gpu(int yl) const {
        for (int il = 0; il < g.nl; ++il)
            if (L[(size_t) il].nm != 1 || (il >= yl && L[(size_t) il].dev != L[(size_t) yl].dev)) return false;
        return true;
    }

    int yoco_layer() const {
        if (yoco_mode() == 0 || chunk <= 0 || g.nl < 2 || (int) g.ratios.size() < g.nl) return -1;
        int yl = -1;
        for (int il = 0; il < g.nl && yl < 0; ++il)
            if (g.ratios[(size_t) il] == 1) yl = il;
        if (yl <= 0 || !L[(size_t) yl].kv_src) return -1;
        const bool one = yoco_one_gpu(), suffix = !one && yoco_suffix_gpu(yl);
        for (const auto& c : chunks)
            if (!one && !suffix && c != nullptr && c->flow) return -1;
        for (int il = 0; il < g.nl; ++il) {
            const Layer& l = L[(size_t) il];
            if (il > yl && (g.ratios[(size_t) il] != 1 || l.kv_src)) return -1;
            if (!one && il >= yl && l.eg >= 0) return -1;
        }
        return yl;
    }
