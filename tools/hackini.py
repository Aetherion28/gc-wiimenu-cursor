"""Priiloader hacks_hash.ini helpers: parse like Priiloader does, locate patches in the v513 DOL."""
import re
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from ppc import Dol


def to_bytes(value):
    """Same rules as Priiloader's _processLine: '0x' + up to 8 hex digits, split into bytes."""
    out = bytearray()
    for seg in value.split(","):
        seg = seg.replace(" ", "")
        if len(seg) < 4 or len(seg) > 10 or not seg.startswith("0x"):
            raise ValueError(f"invalid segment {seg!r}")
        seg = seg[2:]
        out += bytes(int(seg[i:i + 2], 16) for i in range(0, len(seg), 2))
    return bytes(out)


def parse(text):
    """-> list of dict(name, min, max, patches=[dict(offset|hash, patch)])"""
    hacks = []
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            hacks.append(dict(name=line[1:-1], min=0, max=0, patches=[]))
            continue
        k, v = line.split("=", 1)
        h = hacks[-1]
        if k == "minversion": h["min"] = int(v)
        elif k == "maxversion": h["max"] = int(v)
        elif k in ("hash", "offset"):
            h["patches"].append({k: to_bytes(v) if k == "hash" else int(v, 16), "patch": b""})
        elif k == "patch" and h["patches"]:
            h["patches"][-1]["patch"] += to_bytes(v)
    return hacks


def resolve(hack, dol):
    """Memory address of each patch, searching hash patches the way Priiloader does
    (in the DOL file, continuing from the previous match within the same hack)."""
    out, pos = [], 0
    raw = dol.raw
    for p in hack["patches"]:
        if "offset" in p:
            out.append((p["offset"], p["patch"]))
            continue
        i = raw.find(p["hash"], pos)
        if i < 0:
            out.append((None, p["patch"]))
            pos = len(raw)
            continue
        pos = i
        for a, o, s in dol.sections:
            if o <= i < o + s:
                out.append((a + i - o, p["patch"]))
                break
    return out


if __name__ == "__main__":
    # usage: python tools/hackini.py <your hacks_hash.ini> [our .ini, default hack/gc_cursor_hack.ini]
    # Lists every hack that applies to v513 and flags any that write where ours does.
    from pathlib import Path
    ours_file = sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "hack" / "gc_cursor_hack.ini"
    (mine,) = parse(open(ours_file, encoding="latin-1").read())
    ours = [(p["offset"], len(p["patch"])) for p in mine["patches"]]
    hacks = parse(open(sys.argv[1], encoding="latin-1").read())
    dol = Dol()
    n = 0
    for h in hacks:
        if not h["min"] <= 513 <= h["max"] or h["name"] == mine["name"]:
            continue
        n += 1
        for addr, patch in resolve(h, dol):
            if addr is None:
                print(f"  [{h['name']}] a hash was not found in v513")
                continue
            for s, size in ours:
                if addr < s + size and s < addr + len(patch):
                    print(f"CONFLICT [{h['name']}] {addr:#x}+{len(patch):#x} overlaps ours {s:#x}+{size:#x}")
    print(f"checked {n} other hacks that apply to v513")
