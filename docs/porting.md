# Adding another controller

Ex-Machina runs on one device, the Maschine Mikro MK3, and its code says so in many places. This guide is for someone who wants to bring it
to another NI controller, such as the **Maschine MK3**: what can be reused, what has to be found out first, and how this project went about it,
so the same path can be followed. Read [`architecture.md`](architecture.md) first.

> Working on firmware for hardware you own is at your own risk (see the [README](../README.md)). Keep NI's material out of the repository:
> firmware images, decompilations and manuals stay local (`proprietary/`, scratch folders); the repository holds our code, tests and notes.

## What carries over, and what does not
**Reusable as it is, or nearly:** the translator's logic (MIDI out of pad, button, encoder and strip events), the run-time features (pad modes,
scales, chords, arp, sequencer, clock, mute / solo, presets, Shift layer), the configuration and SysEx protocol machinery, the flash storage with
its power-cut safety, the host library's structure, the setup page, the FL Studio script's logic, the flasher (if the device has a DFU bootloader
like the Mikro's), and the whole testing approach (emulator, harness, comparison of our drivers against the stock routines).

**Device-specific** (the table at the end of `architecture.md`): drivers, USB, memory map, report formats, the numbers of pads, buttons and
LEDs, the screen, and the host-side tables describing the controller.

**The Maschine MK3 is a much bigger step than another Mikro.** From NI's published specifications it has, beyond the Mikro: two high-resolution
colour displays, eight touch-sensitive knobs, a four-direction push encoder, more buttons, and a built-in audio interface. A class-compliant MK3
would want USB Audio as well as USB-MIDI, and colour screens need a very different display path from the Mikro's 128 x 32 monochrome one.
Its processor, memory, bootloader and update mechanism have not been examined in this project: finding them out is the first step.

## The path this project took (and a new device would take)
1. **Recovery first.** Before anything is written to the device, know how to get back: the Mikro has a DFU bootloader that NI's updater uses and
   that is never overwritten (`flasher/PROTOCOL.md`), and its chip has an SWD debug port (`docs/hardware-map.md`). Keep an untouched copy of the
   stock firmware (`tools/restore_stock.sh`), and flash in stages that each prove one thing (`docs/hardware-plan.md`).
2. **Get the firmware.** NI ships it inside its updater; `tools/carve_fw.py` found the Mikro's image there by its size and vector table. The
   updater is also where the bootloader's protocol shows (`flasher/PROTOCOL.md`).
3. **Read it.** Ghidra (`tools/ghidra/`, notes in `docs/firmware-notes.md`): the chip, the memory map, the start-up, the main loop, how input
   becomes USB reports, how LEDs and the display are driven. Keil's compressed `.data` needed `tools/decompress_data.py`.
4. **Look at the device without changing it.** USB descriptors (`tools/usb_dump.py`), live input reports (`tools/hid_capture.py`, whose
   recordings became the fixtures in `tests/fixtures/`), and later the chip's own configuration (`tools/probe_chip.py`, `tools/periph_dump.py`).
5. **Emulate it.** `tools/emu/` runs the stock firmware under Unicorn with models of the peripherals, USB and flash; once the stock firmware
   enumerates and reacts in the emulator, every change can be tested there before it touches the device.
6. **Patch, then replace.** The first working Ex-Machina was NI's firmware with a few calls redirected into our code (the patched image). Our own
   drivers then replaced NI's routines one at a time, each tested against the routine it replaced, until the standalone image had none of NI's
   code left (`docs/clean-firmware-plan.md`). The same order keeps a new port safe.

## Making the code ready for a second device
Today the Mikro's numbers are spread through the code. Before a second device lands, these steps would separate them (none is done yet):
- **Firmware:** move the board-specific parts into `firmware/<device>/` (drivers, USB descriptors, memory map, the report decoding into a common
  event form), and keep the translator, features, config and storage in a shared part that only talks to a small board interface (read events,
  set an LED, draw a screen region, send MIDI, read / write flash). The single-translation-unit build rule stays: the board's files are included
  into one object.
- **Config:** the config block has fixed-size arrays for the Mikro's 41 buttons and 16 pads; a device with more controls needs a larger layout
  (with a new protocol version in INFO, so the tools can tell them apart).
- **Host:** a device profile in `host/` (button names and ids, LED indices, pad order, CC defaults, screen size) that `mmk3_config.py`, the
  generators for the setup page and the FL script, and the flasher's profile (`flasher/dfu_client.py`) read, instead of the module-level tables
  they use now.
- **Tests:** the emulator models and the harness are device-specific too (addresses, peripherals); the test suites' expectations (pads, LEDs,
  screens) would follow the profile.

If you start on this, open an issue first to agree on the split: it touches every part of the project.
