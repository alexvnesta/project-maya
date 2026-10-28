        const int yl = logits_rows > kWin ? -1 : yoco_layer();
        // (DS4_YOCO_KEEP=<rows>: fewer - DeepSeek's own serving replays the last 128 tokens through those layers
        //  (DeepInfer's "SWA bounded replay"), which shifts the answers a little; at least one window)
        static const int keep_env = std::getenv("DS4_YOCO_KEEP") ? std::atoi(std::getenv("DS4_YOCO_KEEP")) : 0;
        const int keep = yl <= 0 ? 0
                         : keep_env > 0 ? std::max(keep_env, g.win)
                         : yoco_mode() == 2 ? g.win : (g.nl - yl) * (g.win - 1) + g.win;
        const int a = yl > 0 && n - keep >= kYocoMin ? n - keep : 0;
        const bool cut_rows = a > 0 && (yoco_one_gpu() || yoco_suffix_gpu(yl));
        Run run;
        int per = 0;   // (the widest chunk)
        auto part = [&](int a0, int a1) {   // rows [a0, a1) in equal chunks of at most `chunk`
            if (a1 <= a0) return;
            const int nc = (a1 - a0 + chunk - 1) / chunk, w = (a1 - a0 + nc - 1) / nc;
            for (int x = a0; x < a1; x += w) {
                run.p0.push_back(pos + x);
                run.T.push_back(std::min(w, a1 - x));
                run.seq.push_back(++win_seq);
            }
            per = std::max(per, w);
        };
        if (a > 0 && !cut_rows) {
            part(0, a);
            run.yoco = yl;
            run.cut_k = (int) run.T.size();
            run.cut_r = 0;
            part(a, n);
        } else {
            part(0, n);
            if (a > 0) {
                run.yoco = yl;
                run.cut_k = a / per;
                run.cut_r = a - run.cut_k * per;
            }
        }
