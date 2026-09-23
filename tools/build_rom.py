"""Build a standard 8K cartridge: physical banks 0,1,2,3 in file order."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)
asl, p2bin = os.environ.get("ASL", "asl"), os.environ.get("P2BIN", "p2bin")


def assemble(source, output):
    subprocess.run([asl, "-cpu", "8048", "-L", str(source)], cwd=ROOT, check=True)
    subprocess.run([p2bin, str(source.with_suffix(".p")), str(output),
                    "-r", "1024-3071"], cwd=ROOT, check=True)
    data = output.read_bytes()
    assert len(data) == 2048
    return data


screen = (ROOT / "assets/g7400/screen.bin").read_bytes()
patterns = (ROOT / "assets/g7400/patterns.bin").read_bytes()
intro_rle = (ROOT / "assets/g7400/intro-rle.bin").read_bytes()
assert len(screen) == 1920 and len(patterns) == 960
assert len(intro_rle) <= 720
intro_rle = intro_rle.ljust(720, b"\xff")
banks = []
for bank, data in enumerate((screen[960:], screen[:960], patterns)):
    intro_block = intro_rle[(2 - bank) * 240:(3 - bank) * 240]
    lines = ['cpu 8048', 'include "../include/g7000.h"', 'org 0700h']
    for offset in range(0, 240, 16):
        lines.append("db " + ",".join(f"0{x:02x}h" for x in intro_block[offset:offset+16]))
    lines.append('include "../plus-loader.inc"')
    for page in range(4):
        lines.append(f"org 0{8+page:x}00h")
        block = data[page*240:(page+1)*240]
        for offset in range(0, 240, 16):
            lines.append("db " + ",".join(f"0{x:02x}h" for x in block[offset:offset+16]))
        lines.extend(["movp a,@a", "ret"])
    source = BUILD / f"bank{bank}.asm"
    source.write_text("\n".join("\t" + line for line in lines) + "\n")
    banks.append(assemble(source, BUILD / f"bank{bank}.bin"))
banks.append(assemble(ROOT / "bird-hunt.asm", BUILD / "bank3.bin"))
# Switch continuations must be byte-identical across all loader banks.
assert banks[0][:768] == banks[1][:768] == banks[2][:768]
assert banks[0][1008:1024] == banks[1][1008:1024] == banks[2][1008:1024]
(ROOT / "bird-hunt.bin").write_bytes(b"".join(banks))
print("BIRD HUNT: 8192 bytes, standard four-bank cartridge")
