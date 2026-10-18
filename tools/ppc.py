"""Small static-analysis helpers for the System Menu DOL (PowerPC, big-endian).

Usage examples:
  python tools/ppc.py dis 0x81330000 40          # disassemble 40 instructions
  python tools/ppc.py callers 0x8150abcd         # who does `bl` to this address
  python tools/ppc.py func 0x8150abcd            # find start of the containing function
  python tools/ppc.py sda 0x81698178             # code that loads this address via r13/r2
"""
import struct
import sys
from pathlib import Path

from capstone import CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN, Cs

DOL = Path(__file__).resolve().parent.parent / "bin" / "sysmenu_v513.dol"
R13 = 0x8169E040  # _SDA_BASE_, set at 0x8133012C
R2 = 0x8169C400   # _SDA2_BASE_, set at 0x81330124


class Dol:
    def __init__(self, path=DOL):
        self.raw = Path(path).read_bytes()
        h = struct.unpack(">64I", self.raw[:0x100])
        self.sections = [(h[18 + i], h[i], h[36 + i]) for i in range(18) if h[36 + i]]  # (addr, off, size)
        self.md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)

    def off(self, addr):
        for a, o, s in self.sections:
            if a <= addr < a + s:
                return o + addr - a
        raise ValueError(f"{addr:#x} not in DOL")

    def read(self, addr, n):
        o = self.off(addr)
        return self.raw[o:o + n]

    def word(self, addr):
        return struct.unpack(">I", self.read(addr, 4))[0]

    def words(self):
        """Yield (addr, word) for every aligned word in every section."""
        for a, o, s in self.sections:
            data = self.raw[o:o + s]
            for i in range(0, s - 3, 4):
                yield a + i, struct.unpack_from(">I", data, i)[0]

    def dis(self, addr, count):
        out = []
        for i in self.md.disasm(self.read(addr, count * 4), addr):
            out.append(f"{i.address:08x}: {i.bytes.hex()}  {i.mnemonic:9} {i.op_str}")
        return "\n".join(out)

    def callers(self, target):
        """Addresses of `bl target` (and plain `b target`)."""
        hits = []
        for a, w in self.words():
            if w >> 26 == 18 and not (w & 2):  # I-form branch, relative
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                if (a + li) & 0xFFFFFFFF == target:
                    hits.append((a, "bl" if w & 1 else "b"))
        return hits

    def func_start(self, addr):
        """Walk back to the nearest `stwu r1,-X(r1)` (function prologue)."""
        a = addr & ~3
        while a > addr - 0x4000:
            if self.word(a) >> 16 == 0x9421:
                return a
            a -= 4
        return None

    def sda_refs(self, target):
        """Instructions that reach `target` as d(r13) or d(r2)."""
        hits = []
        for base, reg in ((R13, 13), (R2, 2)):
            d = target - base
            if not -0x8000 <= d < 0x8000:
                continue
            for a, w in self.words():
                op = w >> 26
                if op in (14, 32, 34, 36, 38, 40, 44, 48, 50, 52, 54) and (w >> 16) & 31 == reg:
                    if struct.unpack(">h", struct.pack(">H", w & 0xFFFF))[0] == d:
                        hits.append(a)
        return hits


if __name__ == "__main__":
    d = Dol()
    cmd, args = sys.argv[1], [int(x, 0) for x in sys.argv[2:]]
    if cmd == "dis":
        print(d.dis(args[0], args[1] if len(args) > 1 else 32))
    elif cmd == "callers":
        for a, k in d.callers(args[0]):
            print(f"{a:08x} {k}  (in func {d.func_start(a) or 0:08x})")
    elif cmd == "func":
        print(f"{d.func_start(args[0]):08x}")
    elif cmd == "sda":
        for a in d.sda_refs(args[0]):
            print(f"{a:08x}  (in func {d.func_start(a) or 0:08x})")
