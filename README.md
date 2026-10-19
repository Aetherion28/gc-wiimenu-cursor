<p align="center" width="100%">
  <img width="720" alt="fidget spinner" src="https://raw.githubusercontent.com/Zeldocto/gc-wiimenu-cursor/main/docs/Logo.png">
</p>

# GameCube Controller Cursor for the Wii System Menu

A [Priiloader](https://github.com/DacoTaco/priiloader) hack that lets a **GameCube controller** drive the Wii Menu pointer, with **no Wii Remote** connected. The control stick moves the cursor, and the GameCube buttons act as Wii Remote buttons, including the HOME Menu.

Tested on a real Wii and in Dolphin.

## Compatibility

| | |
|---|---|
| System Menu | **4.3U (v513) only** |
| Priiloader | tested with 0.9.1; current releases use the same hack format |
| Console | Wii (not tested on vWii / Wii U) |

To check your version, open **Wii Settings**: it's shown in the top right corner. It must say **4.3U**. Priiloader only lists the hack on v513, so other versions can't enable it by accident.

## Controls

| GameCube | Wii Remote |
|---|---|
| Control stick | Pointer |
| A | A |
| B | B |
| Start | HOME |
| D-pad | D-pad |
| L | − |
| R or Z | + |
| X | 1 |
| Y | 2 |

- Works from **any** GameCube port, and you can plug the controller in or out at any time.
- If a Wii Remote is turned on, the Wii Remote takes over and works normally. The GameCube controller is only used while no remote is connected.

## Install

You need a softmodded Wii with Priiloader and an SD card.

1. **Make sure you can reach Priiloader.** Power on the Wii while holding **RESET**. The Priiloader menu should appear. This is also how you turn the hack off if anything goes wrong.
2. **Write down which hacks you already have enabled.** In Priiloader, open **System Menu Hacks** and note every hack that is on (for example *Block Disc Updates*, *Block Online Updates* or a *Region Free* hack).
   > ⚠️ Priiloader remembers hacks by their position in the list. Adding a new hack changes the list, so **all your hacks get switched off**. You will turn them back on in step 6.
3. **Add the hack to your hacks file.** Put the SD card in your computer and open `SD:/apps/priiloader/hacks_hash.ini` in a text editor (in Notepad, turn off *Format → Word Wrap*). If the file doesn't exist, use the `hacks_hash.ini` that came with your Priiloader download.
4. Copy **all** of [`hack/gc_cursor_hack.ini`](hack/gc_cursor_hack.ini) and paste it at the very end of `hacks_hash.ini`, starting on a new line. Each `patch=` line is very long and must stay on **one line**, make sure to **turn off Word Wrap**. Save the file.
5. Put the SD card back in the Wii, hold **RESET** while powering on, and open **System Menu Hacks**.
6. Turn on **GameCube Controller Cursor**, and turn your other hacks *from step 2 back on*, then select **Save**.
7. Turn off your Wii Remotes, plug a GameCube controller into any port, and boot the System Menu.

## Uninstall / recovery

Power on holding **RESET**, open **System Menu Hacks**, turn off **GameCube Controller Cursor** and **Save**.

The hack only patches the System Menu in memory each time it starts. It does not modify any files on your NAND (apart from Priiloader saving its own settings).

## Troubleshooting

| Problem | Fix |
|---|---|
| The hack isn't in Priiloader's list | Check that the file is at `SD:/apps/priiloader/hacks_hash.ini`, that no `patch=` line got wrapped or cut, and that your menu is 4.3U. |
| It's listed and enabled, but nothing happens | Make sure you selected **Save**, and that every Wii Remote is off. |
| Region-free games or other hacks stopped working | Priiloader turned your other hacks off when the list changed (see install step 2). Turn them back on and **Save**. |
| Still not working | Use the debug build below and check the disc slot light. |

**Debug build:** [`hack/gc_cursor_hack_debug.ini`](hack/gc_cursor_hack_debug.ini) is the same hack, plus it uses the **blue disc slot light** to show what it's doing. Use it instead of the normal block (not both):

| Disc slot light | Meaning |
|---|---|
| Solid | Working: the GameCube controller is driving the menu |
| Blinking | The hack is running, but it doesn't see a GameCube controller |
| Off | The hack isn't running (not enabled or not saved, or the wrong menu version) |

## How it works

The menu already contains Nintendo's GameCube pad library, but it only reads the pad once at boot (for the recovery-mode check). Every frame, the menu's controller manager asks the Wii Remote library whether a remote is connected (`WPADProbe`), then reads its data (`KPADRead`). The hack redirects those two calls:

- **Probe:** if no Wii Remote is found, the hook reads the GameCube pads (`PADRead`, plus `PADReset` so controllers can be plugged in later). If one is present, it reports "Wii Remote connected".
- **Read:** the hook fills in the Wii Remote data the menu expects: pointer position (the stick moves a cursor, with a dead zone and acceleration), buttons, press/release events and button repeat.

The code lives in two functions of the menu that are never called. Priiloader writes it there at boot using `offset=` patches. See [docs/TECHNICAL.md](docs/TECHNICAL.md) for the addresses, data layouts and how everything was found.

## Building from source

The ready-made hack is in `hack/`, so you only need this to change the code or port it.

1. Install Python 3.10+, then run `pip install -r requirements.txt` (capstone + keystone).
2. To use the analysis tools (`ppc.py`, `caves.py`, `hackini.py`, `livepatch.py`), you need **your own** copy of the 4.3U menu DOL. It is not included. Make a BootMii NAND backup, import it into Dolphin (*Tools → Manage NAND → Import BootMii NAND Backup*), and copy the menu's boot content from `Wii/title/00000001/00000002/content/` in Dolphin's user folder to `bin/sysmenu_v513.dol`:
   - with Priiloader installed it is `10000098.app` (Priiloader moved it there)
   - without Priiloader it is `00000098.app`
   - SHA-1: `26116613f624061ba99c8d1a299aaa6efa85670d`
3. Build:
   ```
   python tools/build.py --release
   python tools/mkhack.py hack/gc_cursor_hack.ini
   ```
   Leave out `--release` for the debug build (disc light + counters).

Tuning values (cursor speed, dead zone, screen limits, button map) are at the top of `tools/build.py`. Testing in Dolphin without Priiloader is described in [docs/TECHNICAL.md](docs/TECHNICAL.md#testing-in-dolphin).

## Disclaimer

Not affiliated with or endorsed by Nintendo. No Nintendo code or files are included: the hack contains only original code and the branch instructions that call it. Use at your own risk; keep a BootMii NAND backup.

Thanks to DacoTaco and contributors for Priiloader, and to the Dolphin team.
