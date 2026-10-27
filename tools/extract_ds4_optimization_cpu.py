"""Extract exact production methods for the fake-device CPU tests; never runs an engine."""
import argparse
import hashlib
import json
import re
from pathlib import Path

METHODS = [
    "    static const char* ds4_env(",
    "    bool read_mx_member(", "    void mx_down_member(",
    "    bool stream_direct(", "    bool stage_needed(", "    bool stage_streamed(",
    "    bool copy_streamed(", "    int vram_cap(", "    bool draft_caps(",
    "    bool cp_pin(",
]


def extract(source):
    result = []
    for marker in METHODS:
        if source.count(marker) != 1:
            raise ValueError(f"ambiguous or missing method: {marker}")
        start = source.index(marker)
        # Mask comments and literals while retaining offsets; methods may be one line.
        masked = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                        lambda m: " " * len(m[0]), source[start:], flags=re.S)
        opening = masked.index("{")
        depth, end = 0, None
        for i in range(opening, len(masked)):
            depth += (masked[i] == "{") - (masked[i] == "}")
            if depth == 0:
                end = start + i + 1
                break
        if end is None:
            raise ValueError(f"unclosed method: {marker}")
        if source[end:end + 1] != "\n":
            raise ValueError(f"unexpected method ending: {marker}")
        result.append(source[start:end] + "\n")
    return "".join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/ds4/ds4_model.cu").read_bytes()
    fragment = extract(source.decode()).encode()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "ds4_optimization_methods.inc"
    with path.open("xb") as f:
        f.write(fragment)
    print(json.dumps({"source_sha256": hashlib.sha256(source).hexdigest(),
                      "fragment_sha256": hashlib.sha256(fragment).hexdigest(),
                      "methods": METHODS, "scope": "CPU fake-device tests only"}))


if __name__ == "__main__":
    main()
