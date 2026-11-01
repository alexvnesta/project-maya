// Lossless original adjacent FP4 nibbles + E8M0 scales -> ggml MXFP4 blocks.
// Format reference: Maya tools/ds4/drafter_pack.py::fp4_to_mxfp4.
// Gate/up [2304,5120] AND down [5120,2304] are supported; no expert or role is skipped.
// stdin: complete weight plane followed by complete scale plane. stdout: blocks.
// No floating point, model execution, file mutation, CUDA or threading.
#include <charconv>
#include <cstdint>
#include <iostream>
#include <string_view>
#include <vector>

static bool number(const char* s, unsigned& v) {
    const std::string_view text(s);
    if (text.empty()) return false;
    for (char c : text) if (c < '0' || c > '9') return false;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), v);
    return result.ec == std::errc() && result.ptr == text.data() + text.size();
}

int main(int argc, char** argv) {
    unsigned rows = 0, k = 0;
    if (argc != 5 || std::string_view(argv[1]) != "--rows" || std::string_view(argv[3]) != "--k" ||
        !number(argv[2], rows) || !number(argv[4], k) || rows == 0 || rows > 5120 || k == 0 ||
        k > 5120 || k % 32 != 0) {
        std::cerr << "mxpack: bounded positive rows/k required\n";
        return 2;
    }
    const size_t blocks = static_cast<size_t>(rows) * (k / 32);
    std::vector<uint8_t> w(blocks * 16), scale(blocks), out(blocks * 17);
    std::cin.read(reinterpret_cast<char*>(w.data()), static_cast<std::streamsize>(w.size()));
    if (std::cin.gcount() != static_cast<std::streamsize>(w.size())) return 3;
    std::cin.read(reinterpret_cast<char*>(scale.data()), static_cast<std::streamsize>(scale.size()));
    if (std::cin.gcount() != static_cast<std::streamsize>(scale.size())) return 3;
    char extra = 0;
    if (std::cin.get(extra) || !std::cin.eof()) return 3;
    for (size_t b = 0; b < blocks; ++b) {
        if (scale[b] == 255) return 4; // E8M0 NaN is never silently accepted.
        out[b * 17] = scale[b];
        for (size_t j = 0; j < 16; ++j) {
            const unsigned shift = 4 * (j % 2);
            const uint8_t low = (w[b * 16 + j / 2] >> shift) & 15;
            const uint8_t high = (w[b * 16 + 8 + j / 2] >> shift) & 15;
            out[b * 17 + 1 + j] = low | static_cast<uint8_t>(high << 4);
        }
    }
    std::cout.write(reinterpret_cast<const char*>(out.data()), static_cast<std::streamsize>(out.size()));
    return std::cout.good() ? 0 : 5;
}
