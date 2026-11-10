# Architecture

How Ex-Machina is put together: the firmware on the controller, the tools on the computer, and the tests that keep both honest. For using the
firmware read the [user manual](../manual/README.md); for adding another controller read [`porting.md`](porting.md).

## The pieces
```
                    ┌──────────────────────────── on the controller ─────────────────────────────┐
  pads, buttons,    │  drivers (hal.c)  →  reports  →  translator (translate.c)  →  USB-MIDI out  │  →  any MIDI app
  encoder, strip    │                                      ↑ config, modes, sequencer, arp        │
                    │  LEDs, display    ←  LED shadow / screen renderer  ←  MIDI / SysEx in       │  ←  apps, setup page,
                    │  USB stack (usb.c), flash storage, safety (watchdog guard, DFU entry)       │     FL Studio script
                    └─────────────────────────────────────────────────────────────────────────────┘
  on the computer:  host/mmk3_config.py (library + CLI)   tools/ui/ (setup page)   integrations/fl_studio/ (FL script)   flasher/ (DFU)
  for development:  tests/ (suites + harness)   tools/emu/ (emulated chip, USB, flash)   firmware/build_patch.py (images)
```

## The firmware (`firmware/`)
**One translation unit.** `translate.c` includes `hal.c`, `usb.c` and `native.c` at its end and is compiled as one object
(`clang --target=thumbv7m-none-eabi -Os`, see `build_patch.py compile_c`). The object may have no `.rodata` and no relocations, because it is
placed at a fixed address in an image the linker never sees: every address is a constant, constant data (texts, the font, scale masks, velocity
tables, the default configs, USB descriptors) is written into flash by `build_patch.py` at fixed addresses, and texts are referred to by number
(the `T_*` enum). Switch statements can compile into a lookup table in `.rodata`; use `if` chains where that happens (the build refuses it).

**Two images, one source.**
- *Patched* (`build_patch.py stock.bin out.bin`): NI's firmware v1.20 with `bl` instructions redirected into our code (`build_patch.py`,
  the `put(..., bl(...))` lines): the core hooks (the boot, the late boot, the main loop's watchdog kick, the report enqueue, the USB OUT callback)
  and, for each of our drivers, the call of the NI routine it replaces (LED refresh, display, scans, pad evaluation, report builders, the
  service routine...). Our drivers are switched on at run time (SysEx `1C`), NI's routine stays the default. `STOCK(addr)` calls NI's routines.
- *Standalone* (`--native`, `-DNATIVE`): our vector table and reset handler (`native.c`), our drivers for every peripheral (`hal.c`), our USB
  stack (`usb.c`); `STOCK()` points at a "return 0" stub. It keeps the stock RAM layout (the LED matrix, the display buffer, the USB library's
  flags live where NI's code had them) because the drivers replaced NI's routines one by one with the same behaviour
  (`docs/clean-firmware-plan.md`). It still copies NI's LED colour tables from the stock image (`LEDTAB`), so the build needs that image.

**The data flow.**
- *Input*: the drivers scan the pads (16 ADC channels, hit and pressure detection), the button matrix and encoder, and the touch strip, and
  build two report types (`translate.c` top comment: id 1 = buttons, encoder, strip; id 2 = pad events). `translate_report()` turns them into
  USB-MIDI packets according to the active config and the run-time modes, and puts them into the transmit ring (`ring_put`), which the USB stack
  sends.
- *Output*: MIDI from the host arrives in `rx_handle()`. Note On on the LED channel sets LEDs (a shadow of every LED, rewritten completely, so a
  frame can never be half applied), CCs give button feedback, SysEx goes to the protocol. The screen is drawn from state, column by column
  (`col_*` functions: idle screen, messages, sequencer grid, the host's text and step overview), and sent by the display driver in regions.
- *The main loop*: `tick_body()` (`mmk3_tick`) runs every pass: the watchdog, the pending SysEx request and its reply, flash writes, the
  24-ppqn grid for the arp, clock and sequencer, the display. Interrupts only store; the main loop acts.

**State and configuration.**
- `struct state` lives at `ST_ADDR` (`0x20004200`): run-time modes, LED shadow, sequencer, requests. `_Static_assert`s keep it inside its RAM.
- `struct cfg` (274 bytes) is the mapping: per-button actions and parameters (with a Shift layer), pad notes, encoder and strip settings, velocity
  curve, scale, chord type and so on. Its layout is mirrored in `host/mmk3_config.py` (`FIELDS`) and checked by the tests. The active config is a
  RAM copy: the defaults (`CFG_DEFAULTS` in flash), the record saved in the save page, a preset slot, or the built-in FL Studio mapping (`CFG_FL`).
- Flash pages (`translate.c` near `SAVE_PAGE`): the saved record, an append-only settings log (velocity curve, channel, mode), four preset slots,
  the step patterns. Every write is ordered so that a power cut leaves the old or the new data, never a broken one (tested with cuts at every write).

**Safety.** A crash-loop guard counts watchdog resets in RAM that survives a reset and, after three, enters NI's bootloader; Shift + Stop + Erase
held for 2 s does the same; `DFU_DETACH` over USB is how the flashers start (`docs/clean-firmware-plan.md` stage 0).

## The protocol
Everything the tools do goes through MIDI SysEx `F0 7D 4D 4B <cmd> ... F7` (`docs/remap-protocol.md`): INFO, GET / SET / SAVE / RESET of the
config, preset slots, host mode (`HOST`, `TEXT`, `STEPS`) for DAW scripts, the mode switch, and diagnostics (`PEEK`, captures). LEDs are plain
Note On messages on the LED channel (`manual/09-midi-reference.md`).

## On the computer
- **`host/mmk3_config.py`** is the single source of truth on the host side: the config layout, button names, NI's CC numbers, the built-in
  presets, the request / reply encoding, and a command line. Generated from it (and checked for staleness by `run_tests.sh`):
  `tools/ui/mmk3_data.js` (`gen_data.py`), `tools/ui/vectors.json` (`make_vectors.py`, the JS client is tested against these),
  `integrations/fl_studio/Ex-Machina/exm_tables.py` (`gen_tables.py`). `tools/ui/patch_bundle.json` (`make_bundle.py`) holds our bytes of the
  patched image and the checksums, so the page can build the image from the user's NI updater.
- **`tools/ui/`**: the setup page (plain ES modules, no build step): mapping editor, presets, slots, flashing (WebUSB, `flasher/dfu.js`).
- **`integrations/fl_studio/`**: the FL Studio device script (`docs/fl-studio.md`).
- **`flasher/`**: the DFU client, standalone on purpose (it must not import anything from the rest of the repository).

## The tests (`tests/`)
`tests/run_tests.sh <stock.bin> <workdir>` builds the images and runs everything; each suite prints PASS / FAIL lines and exits 1 on a failure.
- **The emulator** (`tools/emu/`): a Unicorn Cortex-M3 with models of the peripherals (GPIO, bit-band, ADC, SPI display, bit-banged I2C to the LED
  chips and the strip controller), the USB peripheral (good enough for the real USB library to enumerate) and the flash controller (which fails a
  test on any write outside the allowed pages).
- **The harness**: `devsim.py` runs the patched image's translator and main-loop hook with the stock code around them; `dispsim.py` draws the
  expected screens independently of the firmware's renderer; `replay.py` feeds recorded reports of a real unit (`fixtures/`); `paths.py` puts
  `firmware/`, `host/` and the emulator on the module path (`import paths`).
- **The suites**: feature behaviour (`test_features`, `test_modes`, `test_phase2`-`5`, `test_mode`, `test_host`), configuration and flash
  (`test_config`, `test_mmk3_config`, power-cut sweeps), our drivers against NI's routines on the same emulated hardware (`test_hal_*`), the
  standalone image booted from its reset vector (`test_native`), real recorded input (`test_real_*`), races (`test_led_race`,
  `test_display_race`), stack depth (`stack_depth`), the setup page (`tools/ui/*.mjs`), the FL script against a stand-in for FL
  (`integrations/fl_studio/test_fl_script.py`), the flasher against a mock device.

## What is specific to the Mikro MK3
Everything below would change for another controller; the rest (the translator's logic, the config and protocol machinery, the flash storage, the
tools' structure) carries over. [`porting.md`](porting.md) goes through it.

| Where | What |
|---|---|
| `firmware/hal.c` | pins, buses and chips: the pad ADC channels, the button matrix, the two LED matrix drivers, the display controller, the strip controller (`docs/hardware-map.md`) |
| `firmware/usb.c`, `build_patch.py descriptors()` | the STM32F1 full-speed USB peripheral, VID:PID `17cc:1700`, the DFU runtime interface |
| `firmware/native.c`, `build_patch.py` | the vector table, the memory map (application at `0x08003000`, settings pages, NI's bootloader handshake page), the stock RAM layout, the hook addresses |
| `firmware/translate.c` | the report formats, 16 pads, 41 button ids, 80 LED indices (39 buttons, 16 pads, 25 strip LEDs), the 128 x 32 monochrome screen, the encoder and the strip |
| `host/mmk3_config.py` | button names and ids, NI's CC numbers, the pad order, LED indices, presets |
| `tools/ui/` | the drawing of the controller in the mapping editor |
| `flasher/dfu_client.py` | the device profile `MIKRO_MK3` (ids, application area) |
