# Technical notes: System Menu 4.3U (v513) and 4.3E (v514)

Everything below is for the v513 menu DOL (SHA-1 `26116613f624061ba99c8d1a299aaa6efa85670d`) unless it says otherwise. Addresses are virtual (`0x8xxxxxxx`). The 4.3E addresses are in [System Menu 4.3E (v514)](#system-menu-43e-v514).

## Menu DOL layout

- Title `00000001-00000002`, TMD version 513, boot content index 8 (`00000098.app`, or `10000098.app` when Priiloader is installed).
- T0 `0x80003400`, size `0x400`: BAT setup stub (entry `0x00003400`).
- D0 `0x8132FFE0`-`0x816DFFE0` (size `0x3B0000`, file offset `0x500`): all of the menu's code and data.
- `r13` (`_SDA_BASE_`) = `0x8169E040`, `r2` (`_SDA2_BASE_`) = `0x8169C400`, both set at `0x81330124`.
- SDK: `release build: Apr 20 2010 (0x4199_60831)` for PAD, WPAD, KPAD, SI and OS.

## SDK functions

Identified by the version strings each library registers with `OSRegisterVersion` (`0x8152C7D8`) and by call patterns.

| Function | Address | Notes |
|---|---|---|
| `PADInit` | `0x815767D4` | registers `<< RVL_SDK - PAD`, ends with `PADReset(0xF0000000)` |
| `PADReset` | `0x815765C0` | `(u32 chanMask)` |
| `PADRead` | `0x81576930` | `(PADStatus[4])`, returns per-port err at `+0xA` |
| `WPADProbe` | `0x8157AA24` | `(chan, u32 *type)`; -1 = no controller |
| `KPADInit` | `0x815880B0` | |
| `KPADRead` | `0x81587984` | `(chan, KPADStatus *buf, len)`; internal state `chan * 0x528` |
| `KPADSetBtnRepeat` | `0x815856B0` | called every frame with (0.5 s, 0.1 s) |
| `memset` | `0x81330334` | |
| `OSReport` | `0x8152E6A0` | |

## How the menu uses the GameCube pad

`PADInit` and `PADRead` are each called **once**, in the boot function `0x81379D38` (`0x8137A7C8` and `0x8137AAA4`). That read is the recovery-mode check: port 4, `err == 0` and `(buttons & 0xF) == 0xF`, i.e. **all four D-pad directions held**. The pad library is initialized, but nothing reads it after boot.

`PADRead` error codes: `-1` no controller, `-2` not ready, `-3` transfer (no new response from `SIGetResponse`, at `0x81576B20`). A pad that wasn't present at boot is only detected after the caller runs `PADReset` on its port, which the menu never does.

`PADStatus` (12 bytes): `+0 u16 buttons, +2 s8 stickX, +3 s8 stickY, +4 s8 substickX/Y, +6 u8 triggerL/R, +8 u8 analogA/B, +A s8 err`.

## Controller manager update: `0x81337500` (runs every frame)

`this` = r24. For each channel 0..3:

1. Sensor-bar setting → `0x815858EC(chan, f1)`.
2. `r = WPADProbe(chan, &type)` at **`0x81337584`**. If `r == -1`, `r < -3` or `r >= 1`: `KPADRead` at `0x8133777C`, then `this[chan] = NULL`, which means no controller object and no pointer.
3. Otherwise `n = KPADRead(chan, this + 0xD8 + chan*0x84, 1)` at **`0x813375BC`**. If `n > 0`, `wpad_err != -4` and `type != 0xFD`, a controller object is created or kept at `this + 0x10 + chan*0x30`, chosen by `type`:
   - `0` (core), `0xFB`, `0xFC`, `0xFF`: Wii Remote object (vtable `0x8163499C`)
   - `1`: Nunchuk object (vtable `0x81634910`)
   - `2`: Classic Controller object
   - `n == 0` for 60 frames: disconnect + NULL. `n < 0`: NULL.
4. `KPADSetBtnRepeat(chan, 0.5, 0.1)`.

Afterwards, each non-NULL object's `vtable[0x88]` runs. It reads the KPAD buffer through small getters (for example "is A held"). The HOME Menu reads the same objects.

## KPADStatus (0x84 bytes), confirmed by RAM dumps

| Offset | Field |
|---|---|
| `+0x00` | hold (u32) |
| `+0x04` | trigger |
| `+0x08` | release |
| `+0x0C..+0x14` | acc x/y/z (at rest: 0, -1, 0) |
| `+0x18` | acc_value (1.0) |
| `+0x20/+0x24` | pos x/y, about -1..1 (overshoots slightly); **+inf when not pointing** |
| `+0x28/+0x2C` | vec (pos delta) |
| `+0x30` | speed (length of vec) |
| `+0x34` | horizon (1.0, ~0) |
| `+0x48` | dist (~1.95) |
| `+0x54` | acc_vertical |
| `+0x5C` | dev_type (u8) |
| `+0x5D` | wpad_err (s8) |
| `+0x5E` | dpd_valid_fg (s8): 2 while pointing |
| `+0x5F` | data_format (u8): 2 = core+acc+dpd, 5 = Nunchuk+acc+dpd |
| `+0x60...` | extension data (Nunchuk stick, acc) |

Buttons use standard WPAD bits: Left `0x1`, Right `0x2`, Down `0x4`, Up `0x8`, + `0x10`, 2 `0x100`, 1 `0x200`, B `0x400`, A `0x800`, − `0x1000`, HOME `0x8000`. **`0x80000000` is KPAD's repeat bit**: it's set on the press frame, then after 0.5 s, then every 0.1 s while held. trigger/release are set for one frame.

## The hook (`asm/gc_hook.s`)

- `0x81337584` `bl WPADProbe` → `bl gc_probe`
- `0x813375BC` `bl KPADRead` → `bl gc_kpad`

**gc_probe** (channel 0 only): calls the real `WPADProbe`. If the result is `-1`:

1. `PADRead` all ports, and `PADReset` every port that reports `-1` (hot-plug).
2. Take the first port with `err == 0` and copy its status to `LAST`. If no port is fresh this frame, keep using `LAST` for up to `HOLD` (10) frames, which covers `-3` "no new data".
3. If a pad was found, return 0 with `type = 0` (core) and set `OVR`.

**gc_kpad** (channel 0 only): calls the real `KPADRead`. If `OVR` is set, it `memset`s the buffer and fills it from `LAST`:

- buttons through `BTNTAB` (GC bit i → WPAD bits), with trigger = `now & ~prev`, release = `prev & ~now`, and the repeat bit (30 frames, then every 6)
- the stick moves a persistent cursor: quadratic response past the dead zone, clamped to ±`LIMX`/`LIMY`
- vec/speed from the cursor delta (`frsqrte` + one Newton step)
- fixed "remote at rest" values, `dpd_valid = 2`, `data_format = 2`
- it returns 1

A real Wii Remote always wins: the GC pad is only used when `WPADProbe` says no controller.

### Data block (`0x814AE140`)

| Offset | Field |
|---|---|
| `0x00/0x04` | cursor x/y (f32) |
| `0x08` | previous buttons |
| `0x0C` | repeat countdown |
| `0x10` | OVR |
| `0x14` | PCNT (debug) |
| `0x18` | int→float magic `0x4330000080000000` |
| `0x20` | temp double |
| `0x28..0x3C` | 0.0, 0.5, 1.5, speed, LIMX, LIMY |
| `0x40` | PADStatus[4] |
| `0x70` | BTNTAB[13] |
| `0x8C` | KCNT (debug) |
| `0x90` | LAST (12 bytes) |
| `0x9C` | MISS |
| `0xA0` | GOOD |

The `code2` section (gc_probe) follows at `0x814AE1E8`.

**Debug build** (`tools/build.py` without `--release`): call counters, and the disc slot LED (`HW_GPIOB_OUT` `0xCD0000C0`, bit `0x20`): solid when OVR is set, blinking about 2 Hz when the hook runs without a pad.

## Code caves

`tools/caves.py` collects every reachable address: b/bl/bc targets, raw 32-bit pointers anywhere in the DOL, and lis+addi/ori pairs. It reports dead ranges that run from an unreferenced `stwu r1` prologue to the last `blr` before anything reachable.

- `0x8135A19C`-`0x8135A4C0` (0x324): a complete menu function (0x420 stack frame) that is never called. It holds the hook code (gc_kpad, stick_delta).
- `0x814AE13C`-`0x814AE3B4` (0x278): an unreferenced leaf function. It holds the data block plus gc_probe, starting at `0x814AE140` (8-aligned for `lfd`).
- Others: `0x8151E680` (0x1A4), `0x815469B8` (0x150), `0x81576484` (0x13C, an unused PAD library function).

Low memory `0x80001800`-`0x80003000` is **not** usable. Dolphin's Gecko cheat handler lives there (magic `0xD01F1BAD`, reinstalled whenever it goes missing and called every frame), and something else in the boot path writes there too.

## Priiloader notes

Checked against DacoTaco/priiloader `master` and tag `0.9.1`.

- `offset=` patches are passed to the loader, which writes them **after** copying all DOL sections (BSS isn't cleared for the menu), then flushes the data cache and invalidates the instruction cache. The patch list is allocated in MEM2.
- `hash=` patches are searched in the DOL file in order, and the search position is **not reset between patches of one hack**. If one is missing, the rest are silently skipped while earlier ones stay applied. This hack only uses `offset=` patches.
- Each `0x........` value is split into bytes, so always write 8 hex digits. The maximum line length is 0x2000 characters, and a name can be at most 39 characters.
- `hacks_hash.ini` is read from `fat:/apps/priiloader/` (SD/USB), otherwise from NAND `/title/00000001/00000002/data/hackshas.ini`. Saving in the hacks menu copies the SD file to NAND, and the menu boot reads the NAND copy.
- Hack on/off states (`hacksh_s.ini`) are one byte per hack, **by index**. If the number of hacks changes, all states are reset to off.
- Every hack in the file is loaded, but the hacks menu only lists the ones whose `minversion`..`maxversion` contains the running menu, and the others are forced off at boot (`main.cpp`, `hacks.cpp` on `master`). That's why `gc_cursor_hack.ini` can hold a v513 and a v514 block with the same name.

## Testing in Dolphin

Dolphin can run the hook without Priiloader. `tools/dolmem.py` maps Dolphin's emulated RAM (shared memory `dolphin-emu.<pid>`) to read and write it.

1. Import a BootMii NAND backup. If Priiloader is installed on that NAND, booting it in Dolphin may hang. In Dolphin's NAND copy only, copy `10000098.app` over `00000098.app` and `title_or.tmd` over `title.tmd`, so the real menu boots directly.
2. Turn **off** *Enable Cheats*, which uses `0x80001800`. Turn on *Options → Boot to Pause*. Set Wii Remote 1 to *None* and Port 1 to *Standard Controller*.
3. Tools → Load Wii System Menu (it stops paused), then:
   ```
   python tools/mkhack.py apply hack/gc_cursor_hack.ini
   ```
   This parses the .ini the way Priiloader does and writes it into RAM. Then unpause.

Patching while the menu is running doesn't take effect: Dolphin's JIT keeps executing its cached copy, and *JIT → Clear Cache* during the menu froze it in testing. Patch while paused at boot instead. `tools/livepatch.py status` shows the call sites, the counters and the GC state.

Pitfalls found along the way:
- In PowerPC, `addi rD, r0, x` means `li rD, x`, so r0 is never used as a base register.
- keystone mis-encodes `bl <absolute address>` in some multi-label sources. `build.py` encodes b/bl itself and checks every branch target with capstone.

## System Menu 4.3E (v514)

DOL SHA-1 `2ebea6ed22473857ed64b12daa71ae2d1ed61708`, TMD version 514, boot content index 8 (`0000009b.app`, or `1000009b.app` with Priiloader). Same section layout as v513 (T0 `0x80003400` size `0x400`, D0 `0x8132FFE0` size `0x3B0000`) and the same SDK build: `WPADProbe`, `KPADRead`, `PADRead`, `PADReset` and `memset` are byte-identical to v513, only moved. So the KPADStatus/PADStatus layouts above apply unchanged. Everything else used here moved by `+0x70` to `+0xFC` (the controller manager by `+0x70`, the code cave by `+0xA8`, the data cave and the SDK by `+0xFC`), except `memset`, which stayed put.

| | v513 | v514 |
|---|---|---|
| `WPADProbe` | `0x8157AA24` | `0x8157AB20` |
| `KPADRead` | `0x81587984` | `0x81587A80` |
| `PADRead` | `0x81576930` | `0x81576A2C` |
| `PADReset` | `0x815765C0` | `0x815766BC` |
| `memset` | `0x81330334` | `0x81330334` |
| controller manager update | `0x81337500` | `0x81337570` |
| `bl WPADProbe` site | `0x81337584` | `0x813375F4` |
| `bl KPADRead` site | `0x813375BC` | `0x8133762C` |
| code cave | `0x8135A19C` (0x324) | `0x8135A244` (0x324) |
| data cave | `0x814AE13C` (0x278) | `0x814AE238` (0x278) |
| data block | `0x814AE140` | `0x814AE238` |

v514's data cave starts 8-aligned, so the data block sits at its start (v513 skips 4 bytes to get alignment). The EU hook is the same code as v513's: comparing the two patched DOLs, every instruction is identical except branch offsets (each target holds the same code in both menus) and the `lis`/`addi` of the data block address. It also doesn't overlap any of the official `hacks_hash.ini` hacks (`tools/hackini.py`).

How it was found: `tools/port.py` locates each v513 address in the v514 DOL by matching the surrounding instructions with address-dependent fields masked. All of them matched uniquely with a ±8-instruction window. The call sites were then checked with `ppc.py --menu 514 dis`, and the caves with `caves.py --menu 514`.

Not tested on 4.3E hardware or in Dolphin yet. One thing to watch: cursor speed and the button-repeat delays count frames, so a menu running at 50 Hz moves the cursor about 17% slower than at 60 Hz.

## Porting to another menu version

If the new menu uses the same SDK build (like 4.3E), start with `python tools/port.py bin/sysmenu_v<N>.dol`. It prints each v513 address's counterpart. Check the results the same way as for v514 above, then add a `MENUS` entry in `tools/build.py`. `mkhack.py` writes a block for every built version.

Otherwise, repeat the hunt in the new DOL:

1. Find PAD/WPAD/KPAD via their `<< RVL_SDK - ... >>` version strings → `OSRegisterVersion` callers → the neighbouring functions.
2. Find the controller manager by following `KPADRead`'s callers, and the `WPADProbe` + `KPADRead` call sites in its 4-channel loop.
3. Run `tools/caves.py --menu <N>` to find caves, then add `SDK`, `SITES` and `CAVES` for the version to `MENUS` in `tools/build.py`.
4. Confirm the KPADStatus layout with a RAM dump; it can change between SDK versions.
