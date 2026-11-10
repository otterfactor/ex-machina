# Ex-Machina

Alternative firmware for the **Native Instruments Maschine Mikro MK3**: it turns the controller into a class-compliant USB-MIDI device
(so it works on iPadOS / iOS and with any MIDI software, without NI's drivers or software), and adds a standalone feature set: remappable
buttons with a Shift layer, drum / keyboard / chord pad modes with scales, velocity curves, an arpeggiator with tap tempo and MIDI clock, a 16-step
sequencer, mute / solo pads, strip modes, MIDI channel selection, four preset slots stored in the device, on-screen feedback, an FL Studio mode with
its own FL Studio script, and a browser tool to configure and flash it.

> [!WARNING]
> **Experimental software. Use it entirely at your own risk.**
> Ex-Machina is an unofficial hobby project. It is not made, endorsed or supported by Native Instruments. Installing it replaces your
> controller's firmware: it may misbehave, it may void your warranty, and it could leave your controller unusable. NI's bootloader is never
> written and NI's original firmware has been put back many times on the developer's unit, but nothing guarantees that every unit can be
> recovered: an image that hangs before its safety features start can only be fixed with a hardware debugger (SWD).
> The source code, the images it builds and the tools are provided **as is, without warranty of any kind** (see [`LICENSE`](LICENSE)).
> Whoever decides to build, flash or use them does so on their own responsibility and bears every risk and consequence alone,
> including a damaged or unusable device. Nobody owes you support, fixes or compensation.

**Status:** version **v0**, running on one real unit (used with a Mac, FL Studio and an iPad). Everything not listed as verified on the
hardware in [`docs/hardware-plan.md`](docs/hardware-plan.md) has only been tested in the emulator.

## Using it
Read the **[user manual](manual/README.md)**: what the firmware does, the button reference, presets, the setup page, flashing and getting
back to NI's firmware ([chapter 7](manual/07-flashing.md)), the command line, the MIDI reference and the FL Studio script.

## How it works
There are two images, both built from **your own copy of NI's firmware v1.20** (it is inside NI's updater; `tools/carve_fw.py` extracts it).
NI's firmware is proprietary and is **not in this repository**.
- **The patched image** = NI's firmware plus a patch: seven hooks into the stock code and our code appended (`firmware/translate.c`).
- **The standalone image** (`build_patch.py --native`, the one the developer's unit runs) contains no NI code: its own reset vector, drivers and USB stack
  (`firmware/native.c`, `hal.c`, `usb.c`). It still copies NI's LED colour tables from your image, which is why the build needs it.

`firmware/build_patch.py` builds either one. Everything is tested without hardware: an emulator (Unicorn) runs the real stock firmware and our
code against models of the chip's peripherals, USB and flash. The setup page builds the patched image from your NI image in the browser
(`tools/ui/patch_bundle.json` holds only our bytes and checksums); the standalone image is flashed from the command line for now.

**[`docs/architecture.md`](docs/architecture.md) explains how the pieces fit together.** [`docs/porting.md`](docs/porting.md) explains how
another controller, such as the Maschine MK3, could be added.

## Layout
| Path | What |
|---|---|
| `firmware/` | the firmware: the translator and features (`translate.c`), our drivers (`hal.c`), USB stack (`usb.c`), reset code (`native.c`), and the image builder (`build_patch.py`) |
| `host/` | the host library and command line (`mmk3_config.py`: the config layout, the SysEx protocol, the built-in presets; the one source the other tools generate their tables from), `mmk3_host.py` (LED / display probes) |
| `tests/` | `run_tests.sh` (builds the images and runs everything), the test suites, the emulator harness (`devsim.py`, `dispsim.py`, `replay.py`) and recorded fixtures |
| `tools/emu/` | the emulator: the Unicorn machine and the peripheral, USB and flash models |
| `tools/ui/` | the browser tool (setup page): mapping editor, presets, flashing and restoring (Web MIDI + WebUSB; Chrome or Edge) |
| `integrations/fl_studio/` | the FL Studio device script and its tests |
| `flasher/` | a self-contained DFU client for NI's bootloader (Python and WebUSB), with its own tests and protocol notes |
| `tools/` | firmware carving, the restore script, USB / HID / chip probes, `ghidra/` helpers used for the reverse engineering |
| `manual/` | the user manual |
| `docs/` | design notes and research: architecture, porting, protocol, reverse-engineering findings, sources, the hardware log |
| `research_notes/`, `reports/` | background research (other controllers' FL Studio and Bitwig integrations) |
| `proprietary/` | **not committed** (`.gitignore`): your local copies of NI's files (firmware, updaters, manual) |
| `CLAUDE.md` | working notes for the AI assistant used on this project |

## Getting started
```bash
python3 -m venv .venv && .venv/bin/pip install unicorn pyelftools usb-protocol pyusb mido python-rtmidi
python3 tools/carve_fw.py <path to NI's MM3Updater binary> proprietary/MM3_firmware_1.20_stock.bin
PYTHON=.venv/bin/python tests/run_tests.sh proprietary/MM3_firmware_1.20_stock.bin /tmp/exm-work
python3 tools/ui/serve.py        # the setup page, then open http://localhost:8765 in Chrome or Edge
```
The build needs clang with the ARM target (Apple's clang works); the page's tests need node. [`CONTRIBUTING.md`](CONTRIBUTING.md) has
the details and the rules for changes.

## License
The code and documentation in this repository are under the **MIT License** ([`LICENSE`](LICENSE)), which comes without any warranty.
Native Instruments, Maschine and Mikro are trademarks of Native Instruments GmbH, used here only to say which hardware this is for; NI's
firmware, manuals and software belong to NI and are not part of this repository or covered by its license.
