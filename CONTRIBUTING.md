# Contributing

Thanks for looking. Ex-Machina is a hobby project; changes are welcome, but please read this first.

**Experimental firmware, at your own risk.** Anything you build or flash from this repository, you do on your own responsibility (see the
[README](README.md) and [`LICENSE`](LICENSE)). Flash only units you own, keep a copy of NI's original firmware first ([manual chapter
7](manual/07-flashing.md)), and do not flash an image whose tests do not pass.

## Setting up
- **Python 3** with a virtual environment: `python3 -m venv .venv && .venv/bin/pip install unicorn pyelftools usb-protocol pyusb mido python-rtmidi`
  (`.venv/` is ignored by git).
- **clang** with the ARM target (`--target=thumbv7m-none-eabi`); Apple's clang works.
- **node** for the setup page's tests (optional: `run_tests.sh` skips them without it).
- **Your own copy of NI's firmware v1.20**, carved from NI's updater: `python3 tools/carve_fw.py <MM3Updater binary> proprietary/MM3_firmware_1.20_stock.bin`.
  Every build starts from it, and the tests run NI's code in the emulator to compare ours against it.

## Running the tests
```bash
PYTHON=.venv/bin/python tests/run_tests.sh proprietary/MM3_firmware_1.20_stock.bin /tmp/exm-work
```
It builds the patched and the standalone image and runs every suite; it stops at the first failing one. A single suite:
`.venv/bin/python tests/test_<name>.py <workdir>/patched.bin <workdir>/data_init.bin`. The FL Studio script's tests run alone too:
`python3 integrations/fl_studio/test_fl_script.py` (with an image and `data_init.bin` it also drives the emulated device).

## Where things are
[`docs/architecture.md`](docs/architecture.md) explains how the pieces fit; the README's layout table says what each folder holds.

## Rules for changes
- **No NI material in the repository.** NI's firmware, parts of it, decompilations, NI's manuals and software stay local (`proprietary/` and
  scratch folders are ignored). Patched and built images contain NI bytes or are derived from them: never commit an image. Describe what NI's
  code does in your own words; do not paste it.
- **Tests with every change.** A new behaviour gets a check that fails without it; a fixed bug gets a regression check. Firmware changes are
  tested in the emulator, host changes against the emulated firmware where they talk to it. Keep `run_tests.sh` passing.
- **Generated files stay current.** After changing `host/mmk3_config.py` (the config layout, presets, button tables), run
  `tools/ui/gen_data.py`, `tools/ui/make_vectors.py` and `integrations/fl_studio/gen_tables.py`; after a firmware change,
  `tools/ui/make_bundle.py <stock.bin> <patched.bin>`. `run_tests.sh` fails while any of them is stale.
- **Firmware constraints.** One translation unit, no `.rodata`, no relocations (`build_patch.py` refuses them; `architecture.md` says why);
  the state and the config are fixed-layout structs whose sizes are asserted, and `struct cfg` is mirrored in `host/mmk3_config.py`; keep the
  stack in bounds (`tests/stack_depth.py`); a flash write must leave the old or the new data after a power cut (the flash model checks it).
- **The flasher stays standalone.** `flasher/` must not import anything from the rest of the repository; it may become its own project.
- **Documentation.** User-visible changes go into the [manual](manual/README.md), design and protocol changes into `docs/`. Plain, concrete
  English: say what happens and why.
- **Hardware results are recorded.** What was tried on a real unit, and what was only emulated, goes into `docs/hardware-plan.md`.

## Sending a change
Open an issue for anything large (a new feature, a new device: see [`docs/porting.md`](docs/porting.md)) before writing much code. Pull
requests: one topic each, with the tests passing and a description of what was checked in the emulator and on hardware. Contributions are
under the MIT License, like the rest of the repository.
