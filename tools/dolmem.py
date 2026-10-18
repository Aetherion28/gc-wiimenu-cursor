"""Read/write Dolphin's emulated RAM via its shared-memory mapping (Windows).

Dolphin names the mapping "dolphin-emu.<pid>". MEM1 (24 MB, 0x80000000) sits at offset 0.
Usage: python tools/dolmem.py read 0x81330000 0x40
"""
import ctypes
import struct
import subprocess
import sys
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenFileMappingW.restype = wintypes.HANDLE
k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
FILE_MAP_WRITE, FILE_MAP_READ = 2, 4
MEM1_SIZE = 0x1800000


def dolphin_pid():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Dolphin.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if parts[0].lower() == "dolphin.exe":
            return int(parts[1])
    raise RuntimeError("Dolphin is not running")


class Mem:
    def __init__(self, write=False):
        pid = dolphin_pid()
        access = FILE_MAP_READ | (FILE_MAP_WRITE if write else 0)
        h = k32.OpenFileMappingW(access, False, f"dolphin-emu.{pid}")
        if not h:
            raise OSError(f"OpenFileMapping failed ({ctypes.get_last_error()}); is emulation running?")
        self.base = k32.MapViewOfFile(h, access, 0, 0, MEM1_SIZE)
        if not self.base:
            raise OSError(f"MapViewOfFile failed ({ctypes.get_last_error()})")

    def _ptr(self, addr):
        phys = addr & 0x3FFFFFFF
        if phys >= MEM1_SIZE:
            raise ValueError(f"{addr:#x} is outside MEM1")
        return self.base + phys

    def read(self, addr, n):
        return ctypes.string_at(self._ptr(addr), n)

    def write(self, addr, data):
        ctypes.memmove(self._ptr(addr), data, len(data))

    def u32(self, addr):
        return struct.unpack(">I", self.read(addr, 4))[0]


if __name__ == "__main__":
    m = Mem()
    if sys.argv[1] == "read":
        a, n = int(sys.argv[2], 0), int(sys.argv[3], 0)
        b = m.read(a, n)
        for i in range(0, n, 16):
            print(f"{a+i:08x}: {b[i:i+16].hex(' ')}")
