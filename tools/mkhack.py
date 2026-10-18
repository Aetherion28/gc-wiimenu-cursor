"""Turn the built hook into a Priiloader hacks_hash.ini entry.

  python tools/build.py --release && python tools/mkhack.py hack/gc_cursor_hack.ini
  python tools/build.py && python tools/mkhack.py            -> build/gc_cursor_hack.ini (debug build)
  python tools/mkhack.py apply [file.ini]                    -> parse the .ini like Priiloader
                                                                and write it into Dolphin RAM
                                                                (boot the menu paused first)
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hackini import parse

BUILD = Path(__file__).resolve().parent.parent / "build"
OUT = BUILD / "gc_cursor_hack.ini"
NAME = "GameCube Controller Cursor"   # Priiloader shows at most 39 characters
RELEASE = "1.0"
VERSION = 513                         # 4.3U only: every address in the hook is v513-specific


def words(b):
    assert len(b) % 4 == 0
    return ",".join(f"0x{w:08X}" for w in struct.unpack(f">{len(b)//4}I", b))


def make(out=OUT):
    info = json.loads((BUILD / "gc_hook.json").read_text())
    patches = [
        ("hook code (dead function)", info["code_addr"], (BUILD / "gc_hook.bin").read_bytes()),
        ("hook data + gc_probe (dead function)", info["data_addr"], (BUILD / "gc_data.bin").read_bytes()),
    ] + [(f"bl gc_{k}", s["addr"], struct.pack(">I", s["new"])) for k, s in info["sites"].items()]
    build = "DEBUG build (" + ", ".join(info["flags"]) + ")" if info.get("flags") else "release"
    lines = [f"[{NAME}]", f"maxversion={VERSION}", f"minversion={VERSION}", f"amount={len(patches)}",
             f"#v{RELEASE} {build}, System Menu 4.3U (v513) only",
             "#Stick moves the pointer, A/B/Start(HOME)/D-pad/L(-)/R+Z(+)/X(1)/Y(2) when no Wii Remote is on"]
    for desc, addr, data in patches:
        lines += [f"#{desc}", f"offset=0x{addr:08X}", f"patch={words(data)}"]
    text = "\n".join(lines) + "\n"
    assert max(len(l) for l in lines) < 0x2000, "line too long for Priiloader"
    Path(out).write_text(text, newline="\n")
    return text


def apply(path=OUT):
    from dolmem import Mem
    from ppc import Dol
    (hack,) = parse(Path(path).read_text())
    m, dol = Mem(write=True), Dol()
    assert hack["min"] <= VERSION <= hack["max"]
    for p in hack["patches"]:   # same order as Priiloader's loader
        a, data = p["offset"], p["patch"]
        if m.read(a, len(data)) != dol.read(a, len(data)):
            raise SystemExit(f"RAM at {a:#x} isn't the stock menu (already patched, or not paused at boot?)")
    for p in hack["patches"]:
        m.write(p["offset"], p["patch"])
        print(f"wrote {len(p['patch']):#5x} bytes at {p['offset']:#x}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        apply(sys.argv[2] if len(sys.argv) > 2 else OUT)
    else:
        out = sys.argv[1] if len(sys.argv) > 1 else OUT
        t = make(out)
        print(f"wrote {out} ({len(t)} bytes)")
        print("\n".join(l if len(l) < 110 else l[:100] + " ..." for l in t.splitlines()))
