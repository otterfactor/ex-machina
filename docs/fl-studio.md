# Ex-Machina in FL Studio

A MIDI controller script for FL Studio (desktop, macOS and Windows) that turns the Mikro running Ex-Machina into an FL Studio controller. It rebuilds the Maschine functions that need NI's software (groups and sounds, patterns, the step sequencer, mute and solo, plug-in control, the browser, undo) on FL's own objects. The playing functions that the firmware already has stay on the device: Keyboard / Chords with the scales, Fixed Vel, Note Repeat and the arp, and the strip modes. The script lives in `integrations/fl_studio/Ex-Machina/`. The user's instructions are in `manual/10-fl-studio.md`.

**Status 2026-10-21:**
- The script is tested against a stand-in for FL's modules (`integrations/fl_studio/flsim.py`) and against the emulated firmware (`test_fl_script.py`).
- It has **not run in FL Studio yet**: that check is the user's (FL Studio 2026, All Plugins Edition).
- The firmware's host mode (generation 11) and the two modes (generation 12, `docs/midi-patch.md`) are **flashed (2026-10-21)**. **First run in FL Studio 2026 on macOS (2026-10-21, the user)**: after *Update MIDI scripts* FL found the script and set it as the controller type by itself (the `supportedDevices` line), and it worked; the individual buttons and modes are not all confirmed yet.
- On the generation 10 firmware now on the device, the script falls back to drawing pixels (below).

## What FL Studio's scripting offers (research, 2026-10-20)
- **Where scripts live.** FL Studio runs Python device scripts named `device_<name>.py` from `Documents/Image-Line/FL Studio/Settings/Hardware/<folder>/`.
- **Headers and modules.** A script carries `# name=` (the Controller type shown in MIDI Settings) and optionally `# supportedDevices=` (auto-linking by the USB name, here "Maschine Mikro MK3"). It can import modules from its own folder. Scripting needs the Fruity edition or higher; the All Plugins Edition has it.
- **Callbacks** (the script uses the starred ones):
  - lifecycle: `OnInit`★, `OnDeInit`★, `OnIdle`★ (about every 20 ms);
  - MIDI in: `OnMidiMsg`★, `OnSysEx`★;
  - FL state: `OnRefresh(flags)`★, `OnDoFullRefresh`★, `OnUpdateBeatIndicator`★, `OnProjectLoad`★, `OnDirtyChannel`, `OnDirtyMixerTrack`.
- **Modules.** `transport`, `channels` (the Channel Rack and its step grid), `mixer`, `patterns`, `playlist`, `arrangement`, `plugins` (parameters, presets, FPC pads), `ui` (windows, browser, hints), `general` (undo), `device` (MIDI and SysEx out) and `midi` (constants).
- **New in FL Studio 2026** (release notes):
  - `get_swing` / `set_swing` (named in the release notes; the 2026.1 build the user runs, v26.1.7, has no functions of that name the script could find: the script does not use them);
  - `setPatternLength` / `incrementPatternLength`;
  - clear-pattern and FPC "pad is empty" functions (2026.1.3 / .4; their names are not published);
  - `clonePattern` to a destination index (2026.1.1);
  - `duplicateMidiPatternData()`;
  - HW_Dirty flags for undo / redo;
  - a refresh flag for the Graph Editor;
  - `DisplayRect` limited to 2 s.

  Image-Line's API reference (IL-Group's FL-Studio-API-Stubs) does not document these yet. **The main swing** is reached instead through the API every FL version has: it is the REC event `REC_MainShuffle` (`REC_Global_First + 1`), turned with `mixer.automateEvent(id, delta, REC_MIDIController, 0, 1, 1/128)` exactly as Image-Line's Fire script turns its endless knobs, and read with `device.getLinkedValue` (0-1) / `getLinkedValueString` (FL's own text); without `automateEvent` the script falls back to `globalTransport(FPT_ShuffleJog)`.
- **Existing scripts for the Mikro.** Third-party FL scripts for the *stock* Mikro in NI's MIDI mode exist (a GitHub project and paid ones). They are limited by NI's MIDI mode: Shift and the arrows send nothing, and the screen cannot be written. Nothing was taken from them.

## How the pieces fit
- **The two modes (generation 12).** The device has a Standalone mode (its own mappings and slots) and an FL Studio mode; **Shift + Project** switches in every mapping (the firmware checks the physical Shift, so it works where Shift is a plain CC), SysEx `22` MODE switches or asks, and the mode is kept in the settings log across power cycles. FL Studio mode runs a mapping built into the firmware (`mmk3_config.fl_cfg()` = the preset below with Project as CC 38, written at `CFG_FL_ADDR`); the standalone mapping waits in RAM above the capture area (`FL_STASH`, `0x20004000`) and comes back exactly (unsaved edits, slot, name). Every switch is announced as `62 00 <mode>` (also the answer to MODE). A SET / RESET / slot load from a host goes back to Standalone first (and announces it); SAVE and SLOT STORE in FL Studio mode keep the standalone mapping. Leaving FL Studio mode ends host mode and releases everything that sounds.
- **The script follows the mode.** At `OnInit` it sends MODE and waits for `62`: in FL Studio mode it takes over (below), in Standalone it stays passive and swallows everything the controller sends, so FL sees nothing of it; each announcement switches it. With no answer within a second (a firmware without modes) it takes over as before.
- **The device side.** In FL Studio mode the device runs the mapping of the preset **FL Studio** (`mmk3_config._fl_studio()`):
  - Every button the script uses sends its NI CC as a gate (press 127, release 0), Play and Stop too, not MIDI Start / Stop.
  - With Shift held, a few buttons send a second CC 102-110 (`FL_SHIFT_CC`). Shift itself is the device's modifier, so the device's own Shift functions still work; the firmware reports it as CC 111.
  - Pad Mode / Keyboard / Chords stay the device's, but the firmware reports the resulting pad mode as **CC 116** (0 drums, 1 keyboard, 2 chords) on each press and on a scale step (Shift + Pad Mode / Keyboard, which switches to Keyboard), since 2026-10-21 (step 18). The script keeps it (`dev_padmode`) and keeps it from FL; it does nothing with it yet.
  - The encoder sends relative CC 7 (two's complement); its push is CC 8, its touch CC 9 (since 2026-10-21; before, it sent nothing). The script always handles CC 9, so FL's *Link to controller* should never see it and cannot learn the touch instead of the turn (to verify in FL: learn a parameter by turning the encoder).
  - The pads send notes 36-51; on an FPC or Slicex channel the script turns them into the plug-in's own notes (below).
  - Without the script, the preset is a plain CC controller.
- **The tables.** `gen_tables.py` copies what the script needs from the repository into `exm_tables.py`: the CC of every button with and without Shift, the pad and button LED indices, the font and the command numbers. FL cannot import the repository. `gen_tables.py --check` in `run_tests.sh` fails when the copy is stale.
- **Host mode and the fallback.** When it takes over, the script sends HOST (SCREEN).
  - **A firmware with host mode** answers `60`. From then on the script writes its four screen lines with TEXT (29 bytes per changed line). While a pad grid mode is on, or a drum layout plays (below), it sends HOST SCREEN | RAW, so the pads send notes 36-51 whatever the device's own pad mode. Otherwise the pads play whatever the device's mode is, Keyboard and Chords included.
  - **No answer within a second** (an older firmware): the script draws the same four lines as two pixel regions (SysEx 01, at least 12 ms apart, one per `OnIdle`). It draws them again every 2 s, because that firmware draws its own idle screen when its status changes. The grid modes then need the device in Pad Mode, since in Keyboard mode a pad's note is not its number.
- **The LEDs.** One Note On on channel 2 per LED that changed (velocity = colour code). The firmware makes a host-set colour the LED's resting colour, so its local hit / press flash still works on top. FL colours are matched to the nearest of the device's 16 hues, and greys become white.
- **The screen.**
  - Line 1: the mode, with its page and the encoder target.
  - Line 2: the selected channel.
  - Line 3: the pattern.
  - Line 4: the tempo and PLAY / STOP / REC.
  - A changed value replaces lines 2-3 for 1.5 s, for example `VOL KICK / 88%` or `OSC 2 COARSE / -12 ST`.
  - **Step overview** (`STEP_OVERVIEW`, 2026-10-21): in Step mode, line 3 is the whole pattern (the 128-step stretch holding the pads' page) as a strip: set steps tall, the pads' page bracketed, the playhead inverted while FL plays. The firmware draws it (SysEx 23 STEPS, `docs/remap-protocol.md`), because every TEXT redraws the whole picture and would wipe pixels the script drew. It is off while a message shows, so both message lines can be read. An older firmware ignores STEPS and keeps the text line.
- **Robustness.** FL keeps a script's imported modules across *Update MIDI scripts*, so `device_ExMachina.py` loads `exm_tables`, `exm_settings`, `exm_out` and `exm_core` again itself (`importlib.reload`); without that, a reload after an update can run the new device file on the old modules and stop the script (the likely cause of what was seen on 2026-10-21 after the step-17 update: the Step LED stayed lit and the device held none of the script's text). A settings file lacking newer settings gets their defaults (`exm_core.SETTINGS`). A HOST the device does not confirm (it drops a request that arrives while it is busy) is sent again after 0.5 s. Every FL function goes through `call()`, which returns a default when this FL version lacks the function or refuses the call. A missing 2026 function shows `NEEDS FL STUDIO 2026` instead of stopping the script. `OnDeInit` sends HOST 0, and a SET / RESET / slot load from another tool ends host mode too.

## The map
Shift + X means X pressed while Shift is held. "Device" means the firmware does it; the script never sees it.

| Button | FL Studio |
|---|---|
| Play / Stop / Rec | play-pause / stop / record; Play lit while playing, Rec while recording |
| Restart | back to the start and play |
| Shift + Play | the Score Log: `general.dumpScoreLog(SCORE_LOG_SECONDS, False)`, the last 5 minutes played go into the pattern |
| Shift + Rec / Shift + Restart | count-in (`FPT_CountDown`, printed *Count-in*) / loop recording (`FPT_LoopRecord`, printed *Loop*), state from `ui.isPrecountEnabled` / `isLoopRecEnabled` |
| Shift (reported as CC 111) | a help line on the screen while held (`SHIFT 1 UNDO 5 QUANT / 7/8 NUDGE 13-16 PITCH`); **Shift + pads** (any mode, after the printed labels): 1 / 3 undo, 2 / 4 redo, 9 clear the channel's steps, 11 / 12 `FPT_Copy` / `FPT_Paste`, and Maschine's edit pads 5 QUANTIZE, 6 QUANTIZE 50%, 7 NUDGE <, 8 NUDGE >, 13 / 14 SEMITONE − / +, 15 / 16 OCTAVE − / + (below); the pad's note goes nowhere |
| Tap / Shift + Tap | tap tempo (the beat blinks on Tap) / metronome |
| Follow | pattern / song mode (lit in song mode) |
| Shift + Left / Right | undo / redo |
| Left / Right | the page in a grid mode; the parameter in Plug-in; folders in Browser; on a drum-layout channel its banks first (FPC A / B, slice pages), then the previous / next channel; else the previous / next channel |
| Select | pads = channels 1-16 (pages of 16): select; colour = the channel's, the selected one bright |
| Mute / Solo | pads = channels: mute (dims) / solo (bright, the others dark); in Group mode: `mixer.muteTrack` / `soloTrack` of the selected insert |
| Shift + Solo | every mute and solo off (`isChannelSolo` / `soloChannel`, `isChannelMuted` / `muteChannel(i, 0)`; in Group mode the inserts) |
| Pattern | pads = the patterns of FL's selected pattern group (`getActivePatternGroup` / `getPatternsInGroup`, API 28), all patterns when none is selected (pages): jump; with all patterns, the next free one dim white and its pad makes a new pattern (not in a group: FL's API does not say which group a new pattern joins) |
| Group | pads = mixer inserts 1-16 (8 pages): select; Volume / Sampling then turn that insert's volume / pan |
| Step | pads = 16 steps of the selected channel (pages of 16 up to the pattern length); the playhead is a white pad; Erase = clear the channel, Shift + Erase = every channel; Shift + Step = the encoder sets the pattern length (FL 2026) |
| Step: hit / hold | a hit sets the step with the hit's velocity (`setStepParameterByIndex(getChannelIndex(c), patternNumber(), step, 1, vel, True)`, as Image-Line's Fire script does; `STEP_VELOCITY`); an on step hit again goes off on release unless edited; held steps are white; **hold + encoder** edits the step parameter Events chooses (velocity, pitch, fine pitch, pan, release, Mod X, Mod Y, shift; defaults and maxima as the Fire's), `showGraphEditor` on it (`GRAPH_EDITOR`); off steps dim in the channel colour |
| Duplicate, Shift + Pattern | clone the pattern |
| Volume / Sampling | the encoder turns the selected channel's volume / pan (push held: fine; Shift + push: back to the default) |
| Tempo | tempo jog (push held: 0.1 BPM); no value message, the status line (line 4) shows the tempo |
| Swing | the main swing (`REC_MainShuffle` via `mixer.automateEvent`, 1/128 per step, push held 1/1024), FL's own value text on the screen, a bar on the strip |
| Plug-in | the selected channel's plug-in: encoder = the value, push / arrows = the next / previous parameter that has a name; the screen shows its name and value text |
| Shift + Plug-in | its presets: encoder = next / previous |
| Browser / Shift + Browser | show and focus FL's browser: encoder = up / down, push = open / load, arrows = fold / unfold / hide it |
| Favorites | open the selected channel's plug-in window |
| Encoder over an FL popup menu (`ui.isInPopupMenu()`: Record's "what would you like to record" prompt, right-click menus) | before anything else: turn = `ui.down` / `ui.up` (the highlight), push = `ui.enter` (pick), Shift + push = `ui.closeActivePopupMenu`; the screen shows `MENU` and FL's hint for the item if FL gives one. **Rec's question what to record** (audio into Edison / the playlist, automation & score, everything) cannot be answered from the controller: while it is open FL runs no controller-script callback (seen 2026-10-23: the script got neither the turns nor the push; at the Rec press `isInPopupMenu()` was 0 and the piano roll had the focus, the question opens after `record()` returns), and no script function sets FL's recording filter. Unverified: that the encoder moves the highlight of other popup menus (right-click menus) |
| Encoder with no target | `ui.jog` in the focused window, push = enter; the screen shows FL's hint (`JOG / ...`) only when FL put one there itself (the script remembers what it wrote to the hint bar and never reads that back, and does not write jogs or browser moves to it) |
| Pad Mode / Keyboard / Chords / Fixed Vel / Note Repeat / Auto / Lock / Pitch / Mod / Perform / Notes, Shift + Volume / Swing, Shift + Mute | device (as in *Maschine-like modes*): the notes go to FL. Turn on *Send master sync* for the Mikro's output in FL's MIDI settings so the arp follows FL's tempo |
| Variation | pads = 16 parameters of the selected channel's plug-in (pages): the names `PLUGIN_PAGES` lists for that plug-in, in that order, else every parameter that has a name (the first 4,096 are searched, once per channel and plug-in); colours in turn red, orange, yellow, green, lime, cyan, violet, fuchsia, the chosen one bright; a pad chooses the parameter and makes the encoder's target Plug-in; the plug-in window comes forward (`FOCUS_WINDOWS`) |
| Encoder touch (CC 9) | shows what the encoder would change and its value without changing it (held steps: their parameter), on the screen while touched (`TOUCH_PREVIEW`) |
| Scene (Events outside Step mode) | not used: their CCs go to FL (MIDI learn / Link to controller) |
| Project | the Playlist and the Channel Rack in turn (FL Studio mode: CC 38); Shift + Project: the device's mode switch |

**Feedback and conveniences (2026-10-21, from the research in `reports/FL Studio integration ideas.md`).** The strip LEDs show the encoder target as a bar (pan bipolar from the centre) or the song position while playing (`STRIP_BAR`); Left / Right are dark where they cannot move; every message also goes to FL's hint bar (`ui.setHintMsg`, `HINT_BAR`); mode buttons bring the matching window forward (`FOCUS_WINDOWS`: Channel Rack, Mixer for Group, the plug-in window for Plug-in). Settings live in `Ex-Machina/exm_settings.py`. Every callback is guarded (`device_ExMachina.guarded`): an exception prints its traceback to *View > Script output*, the script stands down for good, the device keeps only its screen (HOST SCREEN, `SCRIPT ERROR`) and FL gets plain MIDI; OnDeInit still sends HOST 0.

**Shift + pads 5-8 and 13-16** (2026-10-23) work as in Maschine (NI's manual: on the selected events, on all of them when none is selected), on what is in front of the user:
- **The piano roll** (focused, or open while the script is not in Step mode): its selected notes, else all of them, **if** FL lets a controller script use the piano-roll scripting module `flpianoroll` (in the same engine, `FLEngine_x64.dylib`; FL's controller-script API itself has no piano-roll note functions, and its `FPT_NudgeMinus` / `Plus` nudge the tempo). **FL 2026.1 does not** (checked by the user on 2026-10-23: the import fails; the script tries once and prints the reason to *View > Script output*). The code for it stays (quantize to FL's snap via `ui.getSnapMode`, halves rounding up; 50 % halfway; nudge by one snap unit, never before 0; transpose 0-131) in case a later FL allows it.
- **Otherwise, and with the piano roll open but no `flpianoroll`**: the selected channel's steps, which are its notes on steps (the user saw the transpose reach the notes; in Step mode only the held steps, if any). **The step shift (`pShift`) is the note's position in the pattern in ticks** (step start + offset, as Image-Line's Fire script treats it: `(val // RecPPS) * RecPPS` is the step start), not an offset: the first version wrote 0 and moved every note to the start of the pattern (2026-10-23, fixed; the script now reads and writes the offset within the step, `mixer.getRecPPS()` ticks per step). Notes are moved **only through that position**: FL then moves the note itself and it keeps its length; switching steps off and on (the second version's nudge) made new notes without a length, which FL shows as "Infinite" (seen 2026-10-23). Quantize: each note onto the nearest step line (halves round up; 50 %: halfway); nudge: by `NUDGE_STEPS` (default half a step, Maschine's nudge grid) earlier / later, round the pattern (Maschine wraps nudged notes too); transpose: each step's pitch (`pPitch`, 0-127). A note is found by its step, so the moves run in an order that never finds a moved note again (going right the later steps first, going left the earlier ones, what goes round the end last). Chords and several notes in one step are only partly reachable this way.
- **Undo.** Every edit saves an undo point first (`general.saveUndo('Ex-Machina: ...', UF_PR)`, as the Fire does): the Shift + pad edits, a step set or cleared from a pad, the first encoder edit of a hold, Erase / Clear. Without it FL's undo took back the edit together with the recording before it (seen 2026-10-23).
- In Bitwig, DrivenByMoss maps the same pads (quantize 100 / 50 %, transpose −1 / +1 / −12 / +12, on the whole clip); Maschine and this script use the selection.

**Swing.** FL's main swing is a step-sequencer setting: it delays every second 16th **step of the Channel Rack**, scaled by each channel's swing mix; steps on the beat do not move and piano-roll notes are not swung by it (to confirm in FL), so it is only audible on a pattern with off-beat steps (for example hi-hats on every step). FL 2026 also has `channels.getSwing` / `setSwing` (changelog item 21791, names in FL's engine library); they are undocumented and not used.

**Play mode** (no grid mode): the pads go straight to FL, so the selected channel plays them, and take the channel's colour. **Drum layouts** (`DRUM_LAYOUTS`, as FLkey's Drum mode): on an **FPC** channel pad *n* plays FPC's pad *n* (its note from `plugins.getPadInfo(c, -1, 1, k)`, bottom left = pad 1 as in FPC), in FPC's pad colours, 16 pads per bank (A, B); on **Slicex / Fruity Slicer** pad 1 plays slice 1 = note 60, as Image-Line's Fire script plays them, 16 slices per page (5 pages up to note 127). The script changes the note (`event.data1`) and leaves the event to FL, as the Fire does; the release goes to the note the press started even if the bank changed in between. On such a channel the device's pads are a raw grid (HOST RAW), so the device's Keyboard / Chords modes do not apply; the title says the bank (`PLAY FPC BANK A`, `PLAY SLICES 17-32`).

**FL's groups.** The channel functions count within FL's Channel Rack group (`channelCount()`, `selectOneChannel(i)` and so on without the global flag), so Select / Mute / Solo / Step follow the group FL shows. When the group changes (OnRefresh `HW_Dirty_ChannelRackGroup`) the pages are brought back into range, held steps are dropped and the screen says how many channels the group has (FL's API has no group name); an empty group says so and the pads do nothing. Step parameters and the graph editor use `getChannelIndex` (the global index), as the Fire does.

## What is not covered, and why
- **Groups and sounds as in Maschine.** FL's Channel Rack has no groups of 16. Select / Mute / Solo work on pages of 16 channels of FL's Channel Rack group instead.
- **Curated plug-in pages.** `PLUGIN_PAGES` is empty: which parameters of FL's own instruments deserve the pads needs their exact names from FL (Link to controller lists them), which no document gives.
- **Scenes and the arranger.** Playlist performance mode and arrangement markers exist in the API but are left for later.
- **Automation recording (AUTO).** The device uses Auto for the arp octaves.
- **Note Repeat in FL's own sequencer.** (Per-step velocity and the step parameters are edited from the pads and the encoder since 2026-10-21.)
- **Clear pattern and the FPC empty-pad check.** The 2026 functions are not named in any document, so the script does not use them yet: Erase clears the steps itself, and an empty FPC pad still shows FPC's colour.
- **Unverified until it runs in FL.** That `automateEvent` on `REC_MainShuffle` moves the main swing (the Fire uses the call for channel and mixer events). The step size of `FPT_TempoJog` (10 = 1 BPM is assumed). Whether `getPatternLength` counts beats (assumed: 4 steps per beat). The colour order of `getChannelColor` (FL's own `utils.ColorToRGB` order, `0xRRGGBB`, is used).

## Testing
- `integrations/fl_studio/test_fl_script.py`:
  - **Part 1** runs the real script against `flsim.py`. That is a small project (4 channels, an FPC, a 3x Osc with parameters, 2 patterns, pattern groups, mixer inserts) behind the signatures of FL's API reference, with every call logged.
  - **Part 2** (with `patched.bin data_init.bin`) connects the script to the emulated firmware both ways. The device's MIDI goes to the script, and the script's LEDs, HOST and TEXT go to the device. It then compares the LEDs and the screen pixels the device ends up with against what the script meant, with host mode and with the pixel fallback. In particular, Step mode on the device while the device's Keyboard mode is on still sets steps 1 and 16 from pads 1 and 16.
- `tests/test_host.py` tests the firmware side.
- Both run in `run_tests.sh`.
