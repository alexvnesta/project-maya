inline fd_t open_direct(const std::string& path) {
#if defined(_WIN32)
    (void) path;
    return kBadFd;
#else
    const int fd = ::open(path.c_str(), O_RDONLY | O_DIRECT);
    return fd < 0 ? kBadFd : (fd_t) fd;
#endif
}
/// [off, off + n) through an unbuffered descriptor into dst, a kDirectAlign-aligned buffer of at least
/// direct_span(off, n) bytes: the file read from off rounded down, so the bytes land at dst + (off % kDirectAlign).
/// False if a read fails (the caller reads buffered instead).
constexpr uint64_t kDirectAlign = 4096;
inline uint64_t direct_span(uint64_t off, uint64_t n) {
    const uint64_t a0 = off & ~(kDirectAlign - 1), a1 = (off + n + kDirectAlign - 1) & ~(kDirectAlign - 1);
    return a1 - a0;
}
inline bool pread_direct(fd_t f, void* dst, uint64_t n, uint64_t off) {
#if defined(_WIN32)
    (void) f, (void) dst, (void) n, (void) off;
    return false;
#else
    const uint64_t a0 = off & ~(kDirectAlign - 1), need = direct_span(off, n), want = (off - a0) + n;
    uint8_t* p = (uint8_t*) dst;
    uint64_t got = 0;
    while (got < need) {
        const ssize_t r = ::pread((int) f, p + got, (size_t) std::min<uint64_t>(need - got, 1ull << 30), (off_t) (a0 + got));
        if (r < 0) return false;
        if (r == 0) break;   // (the file's end: the last aligned read is short)
        got += (uint64_t) r;
        if ((uint64_t) r % kDirectAlign != 0) break;
    }
    return got >= want;
#endif
}
/// Read an arbitrarily aligned expert span through O_DIRECT into a reusable aligned staging buffer,
/// then copy its exact bytes to the NUMA destination. A failure leaves the caller to use buffered I/O.
inline bool copy_direct(fd_t f, uint64_t off, uint64_t n, void* dst, std::vector<uint8_t>& staging) {
    if (f == kBadFd || n == 0 || off > UINT64_MAX - n || off + n > (uint64_t) INT64_MAX - kDirectAlign) return false;
    const uint64_t span = direct_span(off, n);
    if (span > SIZE_MAX - kDirectAlign) return false;
    staging.resize((size_t) span + kDirectAlign);
    auto* aligned = reinterpret_cast<uint8_t*>((reinterpret_cast<uintptr_t>(staging.data()) + kDirectAlign - 1) & ~(uintptr_t)(kDirectAlign - 1));
    if (!pread_direct(f, aligned, n, off)) return false;
    std::memcpy(dst, aligned + off % kDirectAlign, (size_t) n);
    return true;
}
