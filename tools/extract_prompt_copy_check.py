"""Extract the exact non-flow startup copy guard for synthetic CPU controls."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def extract(source):
    marker = "    bool prompt_copy_check("
    if source.count(marker) != 1:
        raise ValueError("One production method required")
    start = source.index(marker)
    masked = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: " " * len(m[0]), source[start:], flags=re.S)
    opening = masked.index("{")
    depth = 0
    for i in range(opening, len(masked)):
        depth += (masked[i] == "{") - (masked[i] == "}")
        if depth == 0:
            return source[start:start + i + 1] + "\n"
    raise ValueError("Unclosed method")


def check_startup(source):
    pin = "        if (cp_pin_last()) cp_pin();"
    call = "        if (!prompt_copy_check(err)) return false;"
    timing = "        tune_lane();"
    if source.count(pin) != 1 or source.count(call) != 1 or source.count(timing) != 1:
        raise ValueError("Unique final pin, check and calibration required")
    if not source.index(pin) < source.index(call) < source.index(timing):
        raise ValueError("Copy guard must follow final pin and precede calibration")
    if source.count("!prompt_copy_check(err)") != 1:
        raise ValueError("No duplicate or pre-pin check allowed")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    raw = a.source.read_bytes()
    source = raw.decode()
    check_startup(source)
    fragment = extract(source).encode()
    with a.out.open("xb") as f:
        f.write(fragment)
    print(json.dumps({"source_sha256": hashlib.sha256(raw).hexdigest(),
                      "fragment_sha256": hashlib.sha256(fragment).hexdigest(),
                      "startup_order": "final-pin/check/calibration", "gpu_proof": False}))


if __name__ == "__main__":
    main()
