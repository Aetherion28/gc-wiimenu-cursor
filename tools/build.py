"""Assemble asm/gc_hook.s for a given load address and build its data block.

  python tools/build.py [code_addr] [data_addr]     (defaults: live-test addresses)

Writes build/gc_hook.bin (code), build/gc_data.bin (data), build/gc_hook.json (symbols).
"""
import json
import re
import struct
import sys
from pathlib import Path

from capstone import CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN, Cs
from keystone import KS_ARCH_PPC, KS_MODE_BIG_ENDIAN, KS_MODE_PPC32, Ks

ROOT = Path(__file__).resolve().parent.parent

# menu v513 functions
SDK = dict(WPADProbe=0x8157AA24, KPADRead=0x81587984, PADRead=0x81576930, PADReset=0x815765C0,
           memset=0x81330334)
SITES = dict(probe=(0x81337584, 0x482434A1), kpad=(0x813375BC, 0x482503C9))  # (addr, original bl)

# dead functions in v513 used as code caves (found by tools/caves.py): (start, size)
# 0x80001800 is NOT usable: Dolphin's Gecko cheat handler lives there.
CAVES = dict(code=(0x8135A19C, 0x324), data=(0x814AE140, 0x274))

# tuning
DEADZONE = 12
SPEED = 4.5e-6          # per frame, times (|stick| - deadzone)^2  (~0.035 at full tilt)
LIMX, LIMY = 1.0, 1.0
HOLD = 10               # frames to keep the last GC status when PADRead has no new data
FLAGS = {"LED", "DEBUG"}  # debug build: disc slot LED + call counters; --release drops both

# data block layout
OFF = dict(CX=0x00, CY=0x04, PREV=0x08, RPT=0x0C, OVR=0x10, PCNT=0x14, MAGIC=0x18, TMP=0x20, ZERO=0x28,
           HALF=0x2C, THREEHALF=0x30, SPEED=0x34, LIMX=0x38, LIMY=0x3C, PADBUF=0x40, BTNTAB=0x70, KCNT=0x8C, LAST=0x90, MISS=0x9C, GOOD=0xA0)
DATA_SIZE = 0xA8

# GC PAD bit i -> Wii Remote bits
BTNTAB = [
    0x0001,  # 0  D-left   -> left
    0x0002,  # 1  D-right  -> right
    0x0004,  # 2  D-down   -> down
    0x0008,  # 3  D-up     -> up
    0x0010,  # 4  Z        -> +
    0x0010,  # 5  R        -> +
    0x1000,  # 6  L        -> -
    0x0000,  # 7  (unused)
    0x0800,  # 8  A        -> A
    0x0400,  # 9  B        -> B
    0x0200,  # 10 X        -> 1
    0x0100,  # 11 Y        -> 2
    0x8000,  # 12 Start    -> HOME
]


def data_block():
    d = bytearray(DATA_SIZE)
    struct.pack_into(">Q", d, OFF["MAGIC"], 0x4330000080000000)
    for k, v in (("HALF", 0.5), ("THREEHALF", 1.5), ("SPEED", SPEED), ("LIMX", LIMX), ("LIMY", LIMY)):
        struct.pack_into(">f", d, OFF[k], v)
    struct.pack_into(">13H", d, OFF["BTNTAB"], *BTNTAB)
    return bytes(d)


def read_sections():
    """asm source -> {section: [lines]}, applying @if/@endif and stripping comments."""
    secs, cur, keep = {"code": []}, "code", [True]
    for line in (ROOT / "asm" / "gc_hook.s").read_text().splitlines():
        if line.startswith("@section "):
            cur = line.split()[1]
            secs.setdefault(cur, [])
            continue
        if line.startswith("@if "):
            keep.append(keep[-1] and line[4:].strip() in FLAGS)
            continue
        if line.startswith("@endif"):
            keep.pop()
            continue
        line = line.split("#")[0].rstrip()
        if keep[-1] and line.strip():
            secs[cur].append(line)
    return secs


def is_label(line):
    return line.endswith(":") and not line.startswith(" ")


def assemble(code_addr, data_addr):
    """-> ({section: bytes}, {label: addr}). code2 is placed right after the data block."""
    bases = dict(code=code_addr, code2=data_addr + DATA_SIZE)
    secs = read_sections()
    # label addresses: every non-label line is exactly one instruction
    syms = {}
    for name, lines in secs.items():
        n = 0
        for line in lines:
            if is_label(line):
                syms[line[:-1]] = bases[name] + 4 * n
            else:
                n += 1
    lo = data_addr & 0xFFFF
    lo = lo - 0x10000 if lo & 0x8000 else lo
    ha = ((data_addr - lo) >> 16) & 0xFFFF
    subs = {k: hex(v) for k, v in {**SDK, **OFF, **syms}.items()}
    subs.update(DATA_HA=hex(ha), DATA_LO=str(lo), DEADZONE=str(DEADZONE), HOLD=str(HOLD))
    ks = Ks(KS_ARCH_PPC, KS_MODE_PPC32 | KS_MODE_BIG_ENDIAN)
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    out = {}
    for name, lines in secs.items():
        src = [re.sub(r"\b[rf](\d+)\b", r"\1", re.sub(r"\{(\w+)\}", lambda m: subs[m.group(1)], l))
               for l in lines]
        code = bytearray(ks.asm("\n".join(src), bases[name])[0]) if src else bytearray()
        insns = [l for l in src if not is_label(l)]
        assert len(code) == 4 * len(insns), f"{name}: instruction count mismatch"
        # keystone mis-encodes some branches to absolute addresses, so encode b/bl to a number
        # ourselves and verify every branch target against the source
        for i, line in enumerate(insns):
            m = BRANCH.match(line)
            if not m:
                continue
            pc, op, tgt = bases[name] + 4 * i, m.group(1), m.group(2)
            want = syms[tgt] if tgt in syms else int(tgt, 0)
            if op in ("b", "bl"):
                struct.pack_into(">I", code, 4 * i, branch(pc, want, link=op == "bl"))
            ins = next(md.disasm(bytes(code[4 * i:4 * i + 4]), pc))
            got = int(ins.op_str.split()[-1].rstrip(","), 0)
            assert got == want, f"{name} {pc:#x} '{line.strip()}': encodes {got:#x}, want {want:#x}"
        out[name] = bytes(code)
    return out, syms


BRANCH = re.compile(r"^\s*(b|bl|beq|bne|blt|bgt|ble|bge|bdnz)\s+(?:\d+,\s*)?(\w+)\s*$")


def branch(frm, to, link=True):
    off = to - frm
    assert -0x2000000 <= off < 0x2000000 and not off & 3
    return 0x48000000 | (off & 0x03FFFFFC) | int(link)


def bl(frm, to):
    return branch(frm, to)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--release" in sys.argv:
        FLAGS.clear()
    code_addr = int(args[0], 0) if args else CAVES["code"][0]
    data_addr = int(args[1], 0) if len(args) > 1 else CAVES["data"][0]
    secs, syms = assemble(code_addr, data_addr)
    code = secs["code"]
    data = data_block() + secs.get("code2", b"")    # data block, then the code2 section
    assert code_addr + len(code) <= data_addr or data_addr + len(data) <= code_addr, "code overlaps data"
    for name, size in (("code", len(code)), ("data", len(data))):
        start, room = CAVES[name]
        addr = code_addr if name == "code" else data_addr
        if addr == start:
            assert size <= room, f"{name} ({size:#x}) does not fit its cave ({room:#x})"
    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    (out / "gc_hook.bin").write_bytes(code)
    (out / "gc_data.bin").write_bytes(data)
    info = dict(code_addr=code_addr, data_addr=data_addr, code_size=len(code), data_size=len(data),
                flags=sorted(FLAGS), syms=syms,
                sites={k: dict(addr=a, orig=o, new=bl(a, syms["gc_" + k])) for k, (a, o) in SITES.items()})
    (out / "gc_hook.json").write_text(json.dumps(info, indent=1))
    print(f"code {code_addr:#x} size {len(code):#x}, data+code2 {data_addr:#x} size {len(data):#x}"
          f" (code2 at {data_addr + DATA_SIZE:#x}), flags {sorted(FLAGS)}")
    print({k: hex(v) for k, v in syms.items()})
    if "-v" in sys.argv:
        md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
        for base, blob in ((code_addr, code), (data_addr + DATA_SIZE, secs.get("code2", b""))):
            for i in md.disasm(blob, base):
                print(f"{i.address:08x}: {i.mnemonic:9} {i.op_str}")
