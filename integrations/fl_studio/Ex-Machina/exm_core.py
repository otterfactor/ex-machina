"""The Ex-Machina controller in FL Studio: Maschine's own functions rebuilt on FL's objects (docs/fl-studio.md has the map).

The device has two modes, switched with Shift + Project on the device: Standalone (its own mappings; the script stays out of the way and FL sees
nothing of the controller) and FL Studio, where it runs its built-in FL mapping and tells the script (SysEx 62 00 <mode>, also the answer to MODE).
In FL Studio mode every button the script uses sends its CC as a gate, a few send a second CC with Shift held, the playing
modes (Keyboard, Chords, Fixed Vel, Note Repeat, the strip) stay on the device. The script answers with the LEDs (one Note On per LED that
changed) and the screen: four lines of text, as TEXT commands when the firmware has host mode (SysEx 20 answered), else as pixel regions.

Everything FL Studio offers is reached through call(), which turns a function this FL version lacks or refuses into a default: the pattern
length on the encoder needs a function new in FL Studio 2026 (setPatternLength)."""
import time
import channels, patterns, mixer, transport, plugins, ui, general, device, midi
import exm_tables as t
import exm_out as out
import exm_settings as cfg

# Every setting with its default: a settings file from an older version of the script (kept, or still loaded by FL) lacks the newer ones.
SETTINGS = dict(STEP_VELOCITY=True, FOCUS_WINDOWS=True, GRAPH_EDITOR=True, LOOP_RECORD_ON_CONNECT=False, SCORE_LOG_SECONDS=300, MESSAGE_SECONDS=1.5,
                STRIP_BAR=True, HINT_BAR=True, DRUM_LAYOUTS=True, STEP_OVERVIEW=True, TOUCH_PREVIEW=True, PLUGIN_PAGES={})
for _k, _v in SETTINGS.items():
    if not hasattr(cfg, _k): setattr(cfg, _k, _v)

def now(): return time.time()

def call(mod, name, *args, default=None):
    f = getattr(mod, name, None)
    if f is None: return default
    try: return f(*args)
    except Exception: return default

def has(mod, name): return callable(getattr(mod, name, None))

CC_NAME = {cc: n for n, cc in t.BUTTON_CC.items()}
CC_NAME.update({cc: 'Shift+' + n for n, cc in t.SHIFT_CC.items()})
NOTE_PAD = {note: pad for pad, note in t.PAD_NOTE.items()}
PUSH, TOUCH = t.BUTTON_CC.get('Encoder Push'), t.BUTTON_CC.get('Encoder Touch', 9)     # (a firmware before the touch was switched on sends no touch)
GRID = ('select', 'mute', 'solo', 'pattern', 'group', 'step', 'variation')
MODE_BUTTON = {'Select': 'select', 'Mute': 'mute', 'Solo': 'solo', 'Pattern': 'pattern', 'Group': 'group', 'Step': 'step', 'Variation': 'variation'}
TARGET_BUTTON = {'Volume': 'volume', 'Swing': 'swing', 'Tempo': 'tempo', 'Sampling': 'pan', 'Plug-in': 'plugin', 'Browser': 'browser',
                 'Shift+Plug-in': 'preset', 'Shift+Step': 'length'}
MODE_TITLE = {'play': 'PLAY', 'select': 'SELECT', 'mute': 'MUTE', 'solo': 'SOLO', 'pattern': 'PATTERN', 'group': 'MIXER', 'step': 'STEP', 'variation': 'PARAMS'}
MSG_S = cfg.MESSAGE_SECONDS                         # how long a value stays on the screen
# The step parameters a held step's encoder edits (Events cycles them): name, FL's parameter number, default, maximum, step per click.
# Numbers, defaults and maxima as FL's API reference and Image-Line's Akai Fire script use them.
STEP_PARAMS = (('VELOCITY', 1, 100, 127, 1), ('PITCH', 0, 60, 127, 1), ('FINE PITCH', 3, 120, 240, 2), ('PAN', 4, 64, 127, 2),
               ('RELEASE', 2, 64, 127, 2), ('MOD X', 5, 128, 255, 2), ('MOD Y', 6, 128, 255, 2), ('SHIFT', 7, 0, 255, 1))
# Shift + pad (in every mode), after the labels printed on the pads: 1 UNDO, 2 REDO, 3 STEP UNDO, 4 STEP REDO, 5 QUANTIZE, 6 QUANTIZE 50%, 9 CLEAR,
# 11 COPY, 12 PASTE. FL has one undo history, so 3 / 4 do what 1 / 2 do. A 50 % quantize (notes halfway to the grid) is not in FL's MIDI-script API
# (quickQuantize has only a start-only flag), so 6 quantizes the note starts only, and the screen says so.
SHIFT_PAD = {1: 'undo', 2: 'redo', 3: 'undo', 4: 'redo', 5: 'quantize', 6: 'quantize_starts', 9: 'clear', 11: 'copy', 12: 'paste'}
# Drum layouts in play mode: the pads follow the selected channel's plug-in. FPC: its own pad notes (plugins.getPadInfo), 16 pads per bank (A, B);
# Slicex / Fruity Slicer: slice 1 = note 60 (C5) on pad 1, 16 slices per page, as Image-Line's Akai Fire script plays them.
SLICERS = ('Slicex', 'Fruity Slicer')
SLICE_NOTE0 = 60
PARAM_COLOURS = (1, 2, 5, 7, 6, 9, 13, 16)          # Variation: the pads' colours, in turn (red, orange, yellow, green, lime, cyan, violet, fuchsia)
PARAM_SCAN = 4096                                   # Variation: how many of a plug-in's parameters are searched for names (VSTs report thousands)
STRIP_COLOUR = {'volume': 7, 'pan': 9, 'tempo': 2, 'swing': 13, 'plugin': 11, 'preset': 11, 'length': 5}   # the strip bar's hue per encoder target
# The main swing (the Channel Rack's) is a REC event: turned like Image-Line's Fire script turns its endless knobs (mixer.automateEvent, relative,
# REC_MIDIController) and read back as 0..1 and as FL's own text (device.getLinkedValue / getLinkedValueString). Values from FL's API reference.
SWING_EVENT = getattr(midi, 'REC_MainShuffle', 0x40000001)
REC_MIDI = getattr(midi, 'REC_MIDIController', 1005)
PROBE_S = 1.0                                       # how long the script waits for the answer to HOST before drawing pixels
HOST_RETRY_S = 0.5                                  # HOST not confirmed by then: sent again (the device drops a request that comes while it is busy)
REGION_S = 0.012                                    # pixel regions at least 10 ms apart (the firmware drops one that comes too soon)
PLAY_REFRESH_S = 0.05                               # while FL plays: the playhead, the transport LEDs, the tempo
PIXEL_REFRESH_S = 2.0                               # without host mode the firmware may draw its own screen: draw ours again this often

class Controller:
    def __init__(self):
        self.mode = 'play'; self.target = None
        self.page = {m: 0 for m in GRID}
        self.param = 0; self.push = False
        self.used = set()                                            # buttons whose press the script took
        self.host_ok = None; self.probe_t = 0.0                     # None: not known yet, True: the firmware has host mode, False: pixels
        self.leds = {}; self.lines = [''] * 4; self.sent_lines = [None] * 4; self.sent_steps = None    # sent_steps: the last STEPS (overview) message
        self.msg = None; self.msg_t = 0.0                            # temporary lines 2-3 (a value), until msg_t
        self.hint_sent = None                                       # what the script last put in FL's hint bar (never read back as FL's own hint)
        self.beat = 0; self.dirty = True; self.refresh_t = 0.0
        self.px_queue = []; self.px_t = 0.0; self.px_drawn = 0.0
        self.host_flags = None; self.host_want = None; self.host_t = 0.0   # the flags the device confirmed, those last sent and when
        self.active = None; self.mode_t = 0.0                       # None: the device's mode not known yet, True: FL Studio mode, False: Standalone
        self.broken = False                                         # an error stopped the script (fail())
        self.win = None                                             # the window Project showed last (Playlist / Channel Rack)
        self.dev_padmode = None                                     # the device's own pad mode (0 drums, 1 keyboard, 2 chords) as it last reported it, None: not yet
        self.shift = False                                          # Shift is held (the device reports it as SHIFT_REPORT_CC)
        self.shift_pads = set()                                     # pads pressed with Shift held: their release is ours too
        self.held = {}                                              # Step mode: held steps -> 'new' (set by this press) / 'on' (was on: off on release, unless edited) / 'edited'
        self.step_param = 0                                         # which STEP_PARAMS entry the encoder edits on held steps
        self.bank = 0; self.bank_chan = None                        # play mode: the drum layout's bank (FPC A / B, slice page) and the channel it is for
        self.sounding = {}                                          # play mode: pad -> the note it started (its Note Off goes to the same note)
        self.touch = False                                          # the encoder is touched (its value stays on the screen)
        self.params = None; self.params_key = None                  # Variation: the plug-in parameters on the pads (indexes), and what they were found for

    # ---- FL Studio callbacks --------------------------------------------------------------------------------------------------------------------
    def init(self):
        """Asks the device for its mode; the script takes over only in FL Studio mode (or, with no answer, a firmware without modes)."""
        self.active = None; self.mode_t = now(); self.sysex(out.mode_query())
        if cfg.LOOP_RECORD_ON_CONNECT and not call(ui, 'isLoopRecEnabled', default=True): call(transport, 'globalTransport', midi.FPT_LoopRecord, 1)

    def activate(self):
        self.active = True; self.sent_steps = None
        self.leds = {}; self.sent_lines = [None] * 4; self.host_ok = None; self.host_flags = None; self.host_want = None; self.px_queue = []
        self.probe_t = now(); self.send_host()
        self.refresh(full=True)

    def deactivate(self):
        """Standalone mode: the device has ended host mode and gone back to its own mapping, LEDs and screen; the script forgets them."""
        self.active = False; self.sent_steps = None
        self.leds = {}; self.sent_lines = [None] * 4; self.host_ok = None; self.host_flags = None; self.host_want = None; self.px_queue = []
        self.mode = 'play'; self.target = None; self.msg = None; self.used = set(); self.shift = False; self.shift_pads = set(); self.held = {}
        self.sounding = {}; self.touch = False

    def fail(self):
        """An error in a callback (device_ExMachina.guarded): stand down for good. The device keeps its screen for the message (host mode SCREEN only, so
        the pads are its own again) and the script lets every MIDI message through to FL from now on."""
        self.broken = True
        try:
            if self.active and self.host_ok is not False:            # (also before the answer to HOST: a firmware without it ignores both)
                self.sysex(out.host(t.HOST_SCREEN))
                for n, line in enumerate(('SCRIPT ERROR', 'SEE FL STUDIO:', 'VIEW > SCRIPT OUTPUT', 'PLAIN MIDI NOW')): self.sysex(out.text_line(n, line))
        except Exception: pass

    def deinit(self):
        if not self.active: return
        if self.host_ok: self.sysex(out.host(0))
        for led in list(self.leds): self.led(led, 0)

    def midi(self, ev):
        """OnMidiMsg: controls of the script are handled (FL does not see them), pads in a grid mode too; everything else goes on to FL.
        In Standalone mode (and until the device has said which mode it is in) nothing goes to FL: the controller is not FL's then."""
        if not self.active: ev.handled = True; return
        st = ev.status & 0xF0; ch = ev.status & 15
        if ch != t.CHANNEL: return
        if st == 0xB0:
            n = ev.data1; v = ev.data2
            if n == t.SHIFT_REPORT_CC: ev.handled = True; self.shift_btn(v > 0); return
            if n == t.PADMODE_REPORT_CC: ev.handled = True; self.dev_padmode = v; return       # (kept for later use; FL never sees it)
            if n == t.ENC_CC: ev.handled = True; self.turn(v if v < 64 else v - 128); return
            if n == PUSH: ev.handled = True; self.push_btn(v > 0); return
            if n == TOUCH: ev.handled = True; self.touch_enc(v > 0); return
            name = CC_NAME.get(n)
            if name and self.button(name, v > 0): ev.handled = True
        elif st in (0x80, 0x90):
            pad = NOTE_PAD.get(ev.data1); down = st == 0x90 and ev.data2 > 0
            if pad and (pad in self.shift_pads or (down and self.shift)):     # Shift + pad: the printed function; its release goes nowhere
                ev.handled = True
                if down: self.shift_pads.add(pad); self.shift_pad(pad)
                else: self.shift_pads.discard(pad)
                return
            if pad and not down and pad in self.sounding:                     # a drum pad let go: the note it started, whatever changed since
                ev.data1 = self.sounding.pop(pad); return
            if self.mode not in GRID:
                if pad and down and self.layout():                            # a drum layout: the pad plays the plug-in's pad / slice
                    nt = self.drum_note(pad)
                    if nt is None: ev.handled = True; return
                    ev.data1 = self.sounding[pad] = nt
                return
            ev.handled = True
            if not pad: return
            if down: self.pad(pad, ev.data2)
            else: self.pad_up(pad)

    def sysex(self, msg): call(device, 'midiOutSysex', bytes(msg))

    def on_sysex(self, ev):
        m = out.mode_msg(getattr(ev, 'sysex', b'') or b'')
        if m is not None:                                            # the answer to MODE, or the device switched (Shift + Project)
            ev.handled = True
            if m == 1 and not self.active: self.activate()
            elif m == 0 and self.active is not False: self.deactivate()
            return
        if not self.active: return
        r = out.is_host_reply(getattr(ev, 'sysex', b'') or b'')
        if r is None: return
        ev.handled = True
        if self.host_ok is None or not self.host_ok:
            self.host_ok = r[0]; self.sent_lines = [None] * 4; self.sent_steps = None; self.dirty = True
        self.host_flags = r[1]

    def idle(self):
        tm = now()
        if self.active is None and tm - self.mode_t > PROBE_S: self.activate()      # no answer to MODE: a firmware without modes, run as before
        if not self.active: return
        if self.host_ok is None and tm - self.probe_t > PROBE_S: self.host_ok = False; self.sent_lines = [None] * 4
        if self.host_ok and self.host_want is not None and self.host_flags != self.host_want and tm - self.host_t > HOST_RETRY_S: self.send_host()
        if self.msg and tm > self.msg_t: self.msg = None; self.dirty = True
        if self.dirty or (tm - self.refresh_t > PLAY_REFRESH_S and call(transport, 'isPlaying', default=False)): self.refresh()
        if self.host_ok is False and tm - self.px_drawn > PIXEL_REFRESH_S: self.sent_lines = [None] * 4; self.draw()
        if self.px_queue and tm - self.px_t >= REGION_S:
            self.sysex(self.px_queue.pop(0)); self.px_t = tm

    def beat_indicator(self, value): self.beat = value; self.dirty = True

    # ---- buttons --------------------------------------------------------------------------------------------------------------------------------
    def button(self, name, down):
        """True if the script uses this button (then FL does not see its CC)."""
        if not down: return name in self.used                      # (a release goes where its press went)
        if name == 'Play': transport.start()
        elif name == 'Stop': transport.stop()
        elif name == 'Rec': transport.record()
        elif name == 'Restart':
            call(transport, 'setSongPos', 0)
            if not call(transport, 'isPlaying', default=False): transport.start()
        elif name == 'Shift+Play':                                 # the Score Log: what was just played goes into the pattern
            call(general, 'dumpScoreLog', cfg.SCORE_LOG_SECONDS, False); self.message('SCORE LOG', 'TO ' + self.pattern_name())
        elif name == 'Shift+Rec':                                  # printed "Count-in"
            call(transport, 'globalTransport', midi.FPT_CountDown, 1); self.message('COUNT-IN', 'ON' if call(ui, 'isPrecountEnabled', default=False) else 'OFF')
        elif name == 'Shift+Restart':                              # printed "Loop": loop recording
            call(transport, 'globalTransport', midi.FPT_LoopRecord, 1); self.message('LOOP RECORD', 'ON' if call(ui, 'isLoopRecEnabled', default=False) else 'OFF')
        elif name == 'Shift+Solo': self.clear_mute_solo()
        elif name in ('Mute', 'Solo') and self.mode == 'group':  # the Mixer: mute / solo the selected insert
            tr = self.track()
            if name == 'Mute': call(mixer, 'muteTrack', tr); self.message('MUTE ' + str(call(mixer, 'getTrackName', tr, default='')), 'ON' if call(mixer, 'isTrackMuted', tr, default=False) else 'OFF')
            else: call(mixer, 'soloTrack', tr); self.message('SOLO ' + str(call(mixer, 'getTrackName', tr, default='')), 'ON' if call(mixer, 'isTrackSolo', tr, default=False) else 'OFF')
        elif name == 'Events' and self.mode == 'step':           # what the encoder edits on held steps
            self.step_param = (self.step_param + 1) % len(STEP_PARAMS); self.message('STEP EDIT', STEP_PARAMS[self.step_param][0])
        elif name == 'Tap': call(transport, 'globalTransport', midi.FPT_TapTempo, 1); self.message('TAP TEMPO', self.tempo_text())
        elif name == 'Shift+Tap':
            call(transport, 'globalTransport', midi.FPT_Metronome, 1)
            self.message('METRONOME', 'ON' if call(ui, 'isMetronomeEnabled', default=False) else 'OFF')
        elif name == 'Follow':
            call(transport, 'setLoopMode'); self.message('MODE', 'SONG' if call(transport, 'getLoopMode', default=0) else 'PATTERN')
        elif name == 'Shift+Left': call(general, 'undoUp'); self.message('UNDO', self.fl_hint())
        elif name == 'Shift+Right': call(general, 'undoDown'); self.message('REDO', self.fl_hint())
        elif name in ('Left', 'Right'): self.arrow(-1 if name == 'Left' else 1)
        elif name in MODE_BUTTON:
            m = MODE_BUTTON[name]; self.mode = 'play' if self.mode == m else m; self.held = {}; self.send_host()
            if self.mode == 'variation':
                self.params = None
                if cfg.FOCUS_WINDOWS and call(plugins, 'isValid', self.chan(), default=False): call(channels, 'showEditor', self.chan(), 1); call(channels, 'focusEditor', self.chan())
            elif self.mode != 'play': self.focus(midi.widMixer if self.mode == 'group' else midi.widChannelRack)
            self.message(MODE_TITLE[self.mode], self.mode_hint())
        elif name in TARGET_BUTTON:
            tg = TARGET_BUTTON[name]; self.target = None if self.target == tg else tg
            if self.target == 'browser': call(ui, 'showWindow', midi.widBrowser); call(ui, 'setFocused', midi.widBrowser)
            if self.target == 'plugin': self.param = self.next_param(self.param, 0)
            if self.target in ('plugin', 'preset') and cfg.FOCUS_WINDOWS: call(channels, 'showEditor', self.chan(), 1); call(channels, 'focusEditor', self.chan())
            elif self.target in ('volume', 'pan') and self.mode == 'group': self.focus(midi.widMixer)
            self.show_value()
        elif name == 'Shift+Browser': call(ui, 'hideWindow', midi.widBrowser); self.target = None if self.target == 'browser' else self.target
        elif name == 'Favorites': call(channels, 'showEditor', self.chan())
        elif name == 'Project':                                    # the Playlist and the Channel Rack in turn, shown and focused
            self.win = midi.widChannelRack if self.win == midi.widPlaylist else midi.widPlaylist
            call(ui, 'showWindow', self.win); call(ui, 'setFocused', self.win)
            self.message('WINDOW', 'CHANNEL RACK' if self.win == midi.widChannelRack else 'PLAYLIST')
        elif name in ('Duplicate', 'Shift+Pattern'):
            call(patterns, 'clonePattern'); self.message('DUPLICATE', self.pattern_name())
        elif name == 'Erase':
            if self.mode == 'step': self.clear_steps([self.chan()]); self.message('ERASE', self.chan_name())
        elif name == 'Shift+Erase':
            self.clear_steps(range(call(channels, 'channelCount', default=0))); self.message('ERASE', 'ALL CHANNELS')
        elif name == 'Shift+Encoder Push': self.reset_value()
        else: self.used.discard(name); return False
        self.used.add(name); self.dirty = True
        return True

    def arrow(self, d):
        if self.mode in GRID:
            n = self.pages(); self.page[self.mode] = max(0, min(n - 1, self.page[self.mode] + d))
            self.message(MODE_TITLE[self.mode], 'PAGE %d/%d' % (self.page[self.mode] + 1, n))
        elif self.target == 'plugin': self.param = self.next_param(self.param, d); self.show_value()
        elif self.target == 'browser': call(ui, 'left' if d < 0 else 'right')
        elif self.layout() and 0 <= self.cur_bank() + d < self.banks():      # a drum layout: its banks first, then the next channel
            self.bank = self.cur_bank() + d; self.message(self.chan_name(), self.bank_text())
        else:
            c = max(0, min(call(channels, 'channelCount', default=1) - 1, self.chan() + d))
            call(channels, 'selectOneChannel', c); self.message('CHANNEL', self.chan_name())

    def push_btn(self, down):
        self.push = down
        if not down: return
        if self.target == 'plugin': self.param = self.next_param(self.param, 1); self.show_value()
        elif self.target in (None, 'browser'): call(ui, 'enter')

    # ---- pads in a grid mode --------------------------------------------------------------------------------------------------------------------
    def pad(self, n, vel=100):
        i = self.page[self.mode] * 16 + n - 1
        if self.mode in ('step', 'select', 'mute', 'solo') and not call(channels, 'channelCount', default=0):
            self.message(MODE_TITLE[self.mode], 'NO CHANNELS IN GROUP'); return
        if self.mode == 'step':                                    # a step: on at once (with the hit's velocity); an on step goes off when let go,
            c = self.chan()                                        # unless the encoder edited it while held
            if call(channels, 'getGridBit', c, i, default=False): self.held[i] = 'on'
            else:
                call(channels, 'setGridBit', c, i, 1); self.held[i] = 'new'
                if cfg.STEP_VELOCITY: self.set_step(c, i, 1, vel)
                self.message('STEP %d' % (i + 1), 'VELOCITY %d' % (vel if cfg.STEP_VELOCITY else 100))
        elif self.mode == 'pattern':
            pl = self.pattern_list()
            if i < len(pl): call(patterns, 'jumpToPattern', pl[i]); self.message('PATTERN', self.pattern_name())
            elif i == len(pl) and self.pattern_group() < 0:                # the pad after the last pattern: a new one (only when all patterns show)
                call(patterns, 'jumpToPattern', (call(patterns, 'patternCount', default=0) or 0) + 1); self.message('PATTERN', 'NEW ' + self.pattern_name())
        elif self.mode == 'variation':
            pl = self.param_list()
            if i < len(pl): self.param = pl[i]; self.target = 'plugin'; self.show_value()
        elif self.mode == 'group': call(mixer, 'setTrackNumber', i + 1); self.message('MIXER', call(mixer, 'getTrackName', i + 1, default=''))
        elif i < call(channels, 'channelCount', default=0):
            if self.mode == 'select': call(channels, 'selectOneChannel', i); self.message('CHANNEL', call(channels, 'getChannelName', i, default=''))
            elif self.mode == 'mute': call(channels, 'muteChannel', i)
            elif self.mode == 'solo': call(channels, 'soloChannel', i)
        self.dirty = True

    def pad_up(self, n):
        if self.mode != 'step': return
        i = self.page[self.mode] * 16 + n - 1; h = self.held.pop(i, None)
        if h == 'on': call(channels, 'setGridBit', self.chan(), i, 0); self.dirty = True

    def set_step(self, c, i, param, value):
        call(channels, 'setStepParameterByIndex', call(channels, 'getChannelIndex', c, default=c), call(patterns, 'patternNumber', default=1), i, param, value, True)

    def step_value(self, c, i, k):
        name, param, dflt, hi, inc = STEP_PARAMS[k]
        v = call(channels, 'getCurrentStepParam', c, i, param, default=-1)
        return dflt if v is None or v < 0 else v

    def edit_steps(self, d):
        """The encoder on held steps: the chosen step parameter of every held step, the graph editor on it."""
        c = self.chan(); k = self.step_param; name, param, dflt, hi, inc = STEP_PARAMS[k]
        if param == 7: hi = max(1, (call(mixer, 'getRecPPS', default=hi) or hi) - 1)     # (a shift stays within its step)
        for i in list(self.held):
            v = clamp(self.step_value(c, i, k) + d * inc, 0, hi); self.set_step(c, i, param, v); self.held[i] = 'edited'
        i0 = min(self.held)
        if cfg.GRAPH_EDITOR: call(channels, 'showGraphEditor', False, param, i0, call(channels, 'getChannelIndex', c, default=c), True)
        self.message('STEP %d %s' % (i0 + 1, name), self.step_text(k, self.step_value(c, i0, k)))

    def step_text(self, k, v):
        name = STEP_PARAMS[k][0]
        if name == 'PITCH': return out.note_name(v)
        if name == 'FINE PITCH': return '%+d CENTS' % ((v - 120) * 10)
        if name == 'PAN': return pan_text((v - 64) / 64.0)
        return str(v)

    def shift_btn(self, down):
        self.shift = down
        if down: self.msg = ('SHIFT PADS', '1 UNDO 2 REDO 5 QUANT'); self.msg_t = now() + 3600; self.dirty = True   # a help line while Shift is held
        elif self.msg and self.msg[0] == 'SHIFT PADS': self.msg = None; self.dirty = True

    def touch_enc(self, down):
        """The encoder touched: what it would change and its value, without changing it; on the screen while it is touched."""
        self.touch = down and cfg.TOUCH_PREVIEW                       # (while touched, message() keeps what it shows)
        if not cfg.TOUCH_PREVIEW: return
        if down:
            if self.mode == 'step' and self.held:
                c = self.chan(); k = self.step_param; i0 = min(self.held)
                self.message('STEP %d %s' % (i0 + 1, STEP_PARAMS[k][0]), self.step_text(k, self.step_value(c, i0, k)))
            else: self.show_value()
        elif self.msg: self.msg_t = now() + MSG_S

    # ---- drum layouts (play mode) ---------------------------------------------------------------------------------------------------------------
    def layout(self):
        """'fpc' or 'slicer' when the selected channel's plug-in has a drum layout (and DRUM_LAYOUTS is on), else None."""
        if not cfg.DRUM_LAYOUTS: return None
        name = call(plugins, 'getPluginName', self.chan(), default='') if call(plugins, 'isValid', self.chan(), default=False) else ''
        return 'fpc' if name == 'FPC' else 'slicer' if name in SLICERS else None

    def cur_bank(self):
        """The bank of the selected channel (a new channel starts at the first)."""
        if self.bank_chan != self.chan(): self.bank_chan = self.chan(); self.bank = 0
        return max(0, min(self.bank, self.banks() - 1))

    def banks(self):
        lay = self.layout()
        if lay == 'fpc': return max(1, ((call(plugins, 'getPadInfo', self.chan(), -1, 0, default=16) or 16) + 15) // 16)
        if lay == 'slicer': return (128 - SLICE_NOTE0 + 15) // 16
        return 1

    def drum_note(self, pad):
        """The note pad 1..16 plays in the drum layout's bank, or None (no such FPC pad, beyond note 127)."""
        k = self.cur_bank() * 16 + pad - 1
        if self.layout() == 'fpc':
            if k >= (call(plugins, 'getPadInfo', self.chan(), -1, 0, default=16) or 0): return None
            nt = call(plugins, 'getPadInfo', self.chan(), -1, 1, k, default=-1)
        else: nt = SLICE_NOTE0 + k
        return nt if isinstance(nt, int) and 0 <= nt <= 127 else None

    def bank_text(self):
        b = self.cur_bank()
        if self.layout() == 'fpc': return 'FPC BANK ' + 'AB'[b] if b < 2 else 'FPC PADS %d-%d' % (16 * b + 1, 16 * b + 16)
        return 'SLICES %d-%d' % (16 * b + 1, 16 * b + 16)

    # ---- FL's groups: Channel Rack group (the channel functions count within it), pattern groups (API 28) ----------------------------------------
    def pattern_group(self): return call(patterns, 'getActivePatternGroup', default=-1) if has(patterns, 'getActivePatternGroup') else -1

    def pattern_list(self):
        """The patterns the Pattern mode's pads show: those of FL's selected pattern group, else all."""
        g = self.pattern_group()
        if isinstance(g, int) and g >= 0:
            pl = call(patterns, 'getPatternsInGroup', g, default=None)
            if pl is not None: return [p for p in pl if isinstance(p, int)]
        return list(range(1, (call(patterns, 'patternCount', default=0) or 0) + 1))

    def on_refresh(self, flags):
        """OnRefresh: redraw; a change of Channel Rack group also ends held steps and says how many channels the group has."""
        self.dirty = True
        if flags & getattr(midi, 'HW_Dirty_ChannelRackGroup', 32768) and self.active:
            self.held = {}; self.bank_chan = None
            n = call(channels, 'channelCount', default=0) or 0
            self.message('CHANNEL RACK', '%d CHANNEL%s' % (n, '' if n == 1 else 'S') if n else 'GROUP IS EMPTY')
        if flags & getattr(midi, 'HW_Dirty_Names', 16384): self.params = None

    # ---- Variation: plug-in parameters on the pads ----------------------------------------------------------------------------------------------
    def param_list(self):
        """The selected channel's plug-in parameters for the pads: the names PLUGIN_PAGES lists for this plug-in (those it has), else every parameter
        that has a name, in FL's order. Found once per channel and plug-in."""
        c = self.chan()
        if not call(plugins, 'isValid', c, default=False): return []
        name = call(plugins, 'getPluginName', c, default='') or ''; n = call(plugins, 'getParamCount', c, default=0) or 0
        key = (call(channels, 'getChannelIndex', c, default=c), name, n)
        if self.params is None or self.params_key != key:
            names = {}
            for q in range(min(n, PARAM_SCAN)):
                pn = call(plugins, 'getParamName', q, c, default='') or ''
                if pn.strip() and pn.strip().lower() not in names: names[pn.strip().lower()] = q
            want = [names.get(w.strip().lower()) for w in cfg.PLUGIN_PAGES.get(name, ())]
            want = [q for q in want if q is not None]
            self.params = want or sorted(names.values()); self.params_key = key
        return self.params

    def shift_pad(self, n):
        f = SHIFT_PAD.get(n); c = self.chan()
        if f == 'undo': call(general, 'undoUp'); self.message('UNDO', self.fl_hint())
        elif f == 'redo': call(general, 'undoDown'); self.message('REDO', self.fl_hint())
        elif f in ('quantize', 'quantize_starts'):
            call(channels, 'quickQuantize', c, 1 if f == 'quantize_starts' else 0); self.message('QUANTIZE' if f == 'quantize' else 'QUANTIZE STARTS', self.chan_name())
        elif f == 'clear': self.clear_steps([c]); self.message('CLEAR', self.chan_name())
        elif f in ('copy', 'paste'): call(transport, 'globalTransport', midi.FPT_Copy if f == 'copy' else midi.FPT_Paste, 1); self.message(f.upper(), '')
        self.dirty = True

    def clear_mute_solo(self):
        """Shift + Solo: every mute and solo off (the channels; in the Mixer the inserts)."""
        if self.mode == 'group':
            for tr in range(1, 126):
                if call(mixer, 'isTrackSolo', tr, default=False): call(mixer, 'soloTrack', tr, 0)
                if call(mixer, 'isTrackMuted', tr, default=False): call(mixer, 'muteTrack', tr, 0)
        else:
            for i in range(call(channels, 'channelCount', default=0) or 0):
                if call(channels, 'isChannelSolo', i, default=False): call(channels, 'soloChannel', i)
            for i in range(call(channels, 'channelCount', default=0) or 0):
                if call(channels, 'isChannelMuted', i, default=False): call(channels, 'muteChannel', i, 0)
        self.message('MUTE / SOLO', 'ALL CLEARED')

    def focus(self, wid):
        if cfg.FOCUS_WINDOWS: call(ui, 'showWindow', wid); call(ui, 'setFocused', wid)

    def mode_hint(self):
        h = {'step': 'HOLD STEP + ENCODER', 'select': 'PAD = CHANNEL', 'mute': 'PAD = MUTE', 'solo': 'PAD = SOLO', 'pattern': 'PAD = PATTERN',
             'group': 'PAD = MIXER INSERT', 'variation': 'PAD = PARAMETER', 'play': self.chan_name()}.get(self.mode, '')
        if self.mode == 'pattern' and self.pattern_group() >= 0: return 'GROUP ' + str(call(patterns, 'getPatternGroupName', self.pattern_group(), default=''))
        if self.mode == 'variation' and not self.param_list(): return 'NO PLUG-IN PARAMETERS'
        return h

    def pages(self):
        if self.mode == 'step': return max(1, (self.steps() + 15) // 16)
        if self.mode == 'pattern': return max(1, min(64, (len(self.pattern_list()) + (1 if self.pattern_group() < 0 else 0) + 15) // 16))
        if self.mode == 'variation': return max(1, (len(self.param_list()) + 15) // 16)
        if self.mode == 'group': return 8
        return max(1, (call(channels, 'channelCount', default=1) + 15) // 16)

    def steps(self):
        beats = call(patterns, 'getPatternLength', call(patterns, 'patternNumber', default=1), default=0) or 0
        return max(16, int(beats) * 4)

    def clear_steps(self, chans):
        for c in chans:
            for i in range(self.steps()): call(channels, 'setGridBit', c, i, 0)

    # ---- the encoder ----------------------------------------------------------------------------------------------------------------------------
    def turn(self, d):
        if self.mode == 'step' and self.held: self.edit_steps(d); return
        tg, fine = self.target, self.push
        c = self.chan()
        if tg is None: call(ui, 'jog', d)
        elif tg == 'volume':
            if self.mode == 'group': tr = self.track(); call(mixer, 'setTrackVolume', tr, clamp(call(mixer, 'getTrackVolume', tr, default=0.8) + d * (0.002 if fine else 0.01), 0, 1))
            else: call(channels, 'setChannelVolume', c, clamp(call(channels, 'getChannelVolume', c, default=0.78) + d * (0.002 if fine else 0.01), 0, 1))
        elif tg == 'pan':
            if self.mode == 'group': tr = self.track(); call(mixer, 'setTrackPan', tr, clamp(call(mixer, 'getTrackPan', tr, default=0) + d * (0.005 if fine else 0.02), -1, 1))
            else: call(channels, 'setChannelPan', c, clamp(call(channels, 'getChannelPan', c, default=0) + d * (0.005 if fine else 0.02), -1, 1))
        elif tg == 'tempo': call(transport, 'globalTransport', midi.FPT_TempoJog, d * (1 if fine else 10))
        elif tg == 'swing':
            if has(mixer, 'automateEvent'): call(mixer, 'automateEvent', SWING_EVENT, d, REC_MIDI, 0, 1, 1 / 1024.0 if fine else 1 / 128.0)
            else: call(transport, 'globalTransport', getattr(midi, 'FPT_ShuffleJog', 122), d)
        elif tg == 'plugin':
            if call(plugins, 'isValid', c, default=False):
                p = self.param; v = call(plugins, 'getParamValue', p, c, default=0.0)
                call(plugins, 'setParamValue', clamp(v + d / (1024.0 if fine else 128.0), 0.0, 1.0), p, c)
        elif tg == 'preset':
            if call(plugins, 'isValid', c, default=False): call(plugins, 'nextPreset' if d > 0 else 'prevPreset', c)
        elif tg == 'browser':
            for _ in range(min(abs(d), 8)): call(ui, 'next' if d > 0 else 'previous')
        elif tg == 'length':
            if not has(patterns, 'setPatternLength'): self.message('LENGTH', 'NEEDS FL STUDIO 2026'); return
            pat = call(patterns, 'patternNumber', default=1)
            call(patterns, 'setPatternLength', pat, max(1, int(call(patterns, 'getPatternLength', pat, default=4) or 4) + d * (1 if fine else 4)))
        self.show_value()

    def reset_value(self):
        c = self.chan(); tg = self.target
        if tg == 'volume': (call(mixer, 'setTrackVolume', self.track(), 0.8) if self.mode == 'group' else call(channels, 'setChannelVolume', c, 0.78))
        elif tg == 'pan': (call(mixer, 'setTrackPan', self.track(), 0.0) if self.mode == 'group' else call(channels, 'setChannelPan', c, 0.0))
        self.show_value()

    def next_param(self, p, d):
        """The next parameter of param_list() (those with a name: VST plug-ins list thousands, most of them empty), d = 0: p itself if it is
        one of them, else the first."""
        pl = self.param_list()
        if not pl: return 0
        if p not in pl: return pl[0] if d >= 0 else pl[-1]
        return pl[(pl.index(p) + d) % len(pl)]

    # ---- what the screen and the LEDs show ------------------------------------------------------------------------------------------------------
    def chan(self): return call(channels, 'selectedChannel', default=0) or 0
    def chan_name(self): return call(channels, 'getChannelName', self.chan(), default='') or ''
    def track(self): return call(mixer, 'trackNumber', default=0) or 0
    def pattern_name(self): return call(patterns, 'getPatternName', call(patterns, 'patternNumber', default=1), default='') or ''
    def tempo_text(self):
        v = call(mixer, 'getCurrentTempo', default=None)
        return '%.1f BPM' % v if isinstance(v, (int, float)) and v < 1000 else ('%.1f BPM' % (v / 1000.0) if v else '')

    def value_lines(self):
        c = self.chan(); tg = self.target
        if tg == 'volume':
            if self.mode == 'group': tr = self.track(); return 'VOL ' + str(call(mixer, 'getTrackName', tr, default='')), '%d%%' % round(100 * call(mixer, 'getTrackVolume', tr, default=0))
            return 'VOL ' + self.chan_name(), '%d%%' % round(100 * call(channels, 'getChannelVolume', c, default=0))
        if tg == 'pan':
            v = call(mixer, 'getTrackPan', self.track(), default=0) if self.mode == 'group' else call(channels, 'getChannelPan', c, default=0)
            return 'PAN ' + (call(mixer, 'getTrackName', self.track(), default='') if self.mode == 'group' else self.chan_name()), pan_text(v)
        if tg == 'tempo': return None                               # (the status line shows the tempo already)
        if tg == 'swing':
            v = self.swing_value()
            return 'SWING', call(device, 'getLinkedValueString', SWING_EVENT, default='') or ('%d%%' % round(100 * v) if v is not None else '')
        if tg in ('plugin', 'preset'):
            if not call(plugins, 'isValid', c, default=False): return 'PLUG-IN', 'NONE ON THIS CHANNEL'
            if tg == 'preset': return call(plugins, 'getPluginName', c, default=''), 'PRESET ' + str(call(plugins, 'getName', c, -1, 6, 0, default='') or '')
            return call(plugins, 'getParamName', self.param, c, default=''), call(plugins, 'getParamValueString', self.param, c, default='') or '%d%%' % round(100 * call(plugins, 'getParamValue', self.param, c, default=0))
        if tg == 'browser': return 'BROWSER', self.fl_hint()
        if tg == 'length': return 'LENGTH', '%s BEATS' % call(patterns, 'getPatternLength', call(patterns, 'patternNumber', default=1), default='?')
        h = self.fl_hint()
        return ('JOG', h) if h else None                            # (a plain jog: only what FL itself says about it, if anything)

    def swing_value(self):
        v = call(device, 'getLinkedValue', SWING_EVENT, default=None)
        return clamp(v, 0.0, 1.0) if isinstance(v, (int, float)) and v >= 0 else None

    def fl_hint(self):
        """FL's hint bar, unless it is the script's own last message (else 'JOG: JOG: ...' feeds on itself)."""
        h = call(ui, 'getHintMsg', default='') or ''
        return '' if h == self.hint_sent else h

    def show_value(self):
        v = self.value_lines(); self.dirty = True
        if v: self.message(v[0], v[1], hint=self.target not in (None, 'browser'))   # (FL's own hint stays FL's: jog, browser)

    def message(self, a, b='', hint=True):
        self.msg = (str(a), str(b)); self.msg_t = now() + (3600 if self.touch else MSG_S); self.dirty = True   # (stays while the encoder is touched)
        if cfg.HINT_BAR and hint: self.hint_sent = ('%s: %s' % (a, b)) if b else str(a); call(ui, 'setHintMsg', self.hint_sent)

    def screen(self):
        pn = call(patterns, 'patternNumber', default=1)
        play = 'PLAY' if call(transport, 'isPlaying', default=False) else 'STOP'
        if call(transport, 'isRecording', default=False): play = 'REC'
        title = MODE_TITLE[self.mode]
        if self.mode in GRID: title += ' %d/%d' % (self.page[self.mode] + 1, self.pages())
        elif self.layout(): title += ' ' + self.bank_text()
        if self.target: title = (title + ' ' * 21)[:13] + self.target.upper()[:8]
        l1, l2 = self.msg if self.msg else (self.chan_name(), 'PAT %d %s' % (pn, self.pattern_name()))
        return [title, l1, l2, (self.tempo_text() + ' ' * 21)[:16] + play.rjust(5)]

    def pad_leds(self):
        """The 16 pad LEDs of the current mode (pad 1..16 -> code)."""
        m = self.mode; base = self.page.get(m, 0) * 16; cols = {}
        n_ch = call(channels, 'channelCount', default=0) or 0
        sel = self.chan(); pats = self.pattern_list() if m == 'pattern' else None
        for p in range(1, 17):
            i = base + p - 1; v = 0
            if m == 'play':
                c = self.chan(); lay = self.layout(); k = self.cur_bank() * 16 + p - 1
                if lay == 'fpc':
                    if self.drum_note(p) is not None: v = out.code(out.nearest(call(plugins, 'getPadInfo', c, -1, 2, k, default=0) or 0), 2)
                elif lay == 'slicer':
                    if self.drum_note(p) is not None: v = out.code(out.nearest(call(channels, 'getChannelColor', c, default=0) or 0), 3 if p in self.sounding else 1)
                elif call(plugins, 'getPluginName', c, default='') == 'FPC':                       # (DRUM_LAYOUTS off: FPC's colours on the plain notes)
                    v = out.code(out.nearest(call(plugins, 'getPadInfo', c, -1, 2, p - 1, default=0) or 0), 2)
                else: v = out.code(out.nearest(call(channels, 'getChannelColor', c, default=0) or 0), 1)
            elif m in ('select', 'mute', 'solo'):
                if i < n_ch:
                    col = out.nearest(call(channels, 'getChannelColor', i, default=0) or 0)
                    if m == 'select': v = out.code(col, 3 if i == sel else 1)
                    elif m == 'mute': v = out.code(col, 0 if call(channels, 'isChannelMuted', i, default=False) else 2)
                    else: v = out.code(col, 3 if call(channels, 'isChannelSolo', i, default=False) else 0)
            elif m == 'pattern':
                pl = pats; cur = call(patterns, 'patternNumber', default=1)
                if i < len(pl): v = out.code(out.nearest(call(patterns, 'getPatternColor', pl[i], default=0) or 0), 3 if pl[i] == cur else 1)
                elif i == len(pl) and self.pattern_group() < 0: v = out.code(out.WHITE, 0)
            elif m == 'variation':
                pl = self.param_list()
                if i < len(pl): v = out.code(PARAM_COLOURS[i % len(PARAM_COLOURS)], 3 if pl[i] == self.param and self.target == 'plugin' else 1)
            elif m == 'group':
                v = out.code(out.nearest(call(mixer, 'getTrackColor', i + 1, default=0) or 0), 3 if i + 1 == self.track() else 1)
            elif m == 'step':
                on = call(channels, 'getGridBit', sel, i, default=False); col = out.nearest(call(channels, 'getChannelColor', sel, default=0) or 0)
                v = out.code(col, 3) if on else (out.code(out.WHITE, 0) if i % 4 == 0 else out.code(col, 0))   # on bright, off dim, every 4th step dim white
                if i == self.playhead() or i in self.held: v = out.code(out.WHITE, 3)
            cols[p] = v
        return cols

    def playhead(self):
        if not call(transport, 'isPlaying', default=False): return -1
        v = call(mixer, 'getSongStepPos', default=-1)
        return int(v) % max(16, self.steps()) if isinstance(v, (int, float)) and v >= 0 else -1

    def button_leds(self):
        on, dim = 0x7F, 0x7C
        L = {}
        lit = lambda name, cond: L.__setitem__(name, on if cond else dim)
        lit('Play', call(transport, 'isPlaying', default=False)); lit('Rec', call(transport, 'isRecording', default=False)); lit('Stop', False)
        lit('Restart', False); lit('Tap', self.beat in (1, 2)); lit('Follow', call(transport, 'getLoopMode', default=0) == 1)
        for b, m in MODE_BUTTON.items(): lit(b, self.mode == m)
        for b, tg in TARGET_BUTTON.items():
            if not b.startswith('Shift+'): lit(b, self.target == tg)
        for b in ('Favorites', 'Duplicate', 'Erase'): lit(b, False)
        lo, hi = self.can_move()
        L['Left'] = dim if lo else 0; L['Right'] = dim if hi else 0                 # the arrows are dark where they cannot go
        return {t.BUTTON_LED[n]: v for n, v in L.items() if n in t.BUTTON_LED}

    def can_move(self):
        if self.mode in GRID: return self.page[self.mode] > 0, self.page[self.mode] < self.pages() - 1
        if self.target in ('plugin', 'browser'): return True, True
        c = self.chan(); n = call(channels, 'channelCount', default=1) or 1; b = self.cur_bank() if self.layout() else 0
        return c > 0 or b > 0, c < n - 1 or b < self.banks() - 1

    def strip_leds(self):
        """The 25 strip LEDs: the encoder target's value as a bar (pan from the centre), else the song position while FL plays."""
        n = t.STRIP_LEDS; bar = [0] * n
        if not cfg.STRIP_BAR: return {}
        v = self.target_fraction()
        if v is not None:
            col = STRIP_COLOUR.get(self.target, 17)
            if self.target == 'pan':
                mid = n // 2; end = int(round(mid + v * mid))
                for k in range(min(mid, end), max(mid, end) + 1): bar[k] = out.code(col, 2)
            else:
                for k in range(int(round(v * n))): bar[k] = out.code(col, 2)
        elif call(transport, 'isPlaying', default=False):
            pos = call(transport, 'getSongPos', default=0) or 0
            bar[min(n - 1, int(pos * n))] = out.code(out.WHITE, 2)
        return {t.STRIP_LED0 + k: bar[k] for k in range(n)}

    def target_fraction(self):
        """The encoder target's value as 0..1 (pan: -1..1), or None."""
        c = self.chan(); tg = self.target; g = self.mode == 'group'
        if tg == 'volume': return call(mixer, 'getTrackVolume', self.track(), default=0) if g else call(channels, 'getChannelVolume', c, default=0)
        if tg == 'pan': return call(mixer, 'getTrackPan', self.track(), default=0) if g else call(channels, 'getChannelPan', c, default=0)
        if tg == 'tempo':
            v = call(mixer, 'getCurrentTempo', default=None)
            if isinstance(v, (int, float)): v = v / 1000.0 if v >= 1000 else v; return clamp((v - 10) / 512.0, 0, 1)
        if tg == 'plugin' and call(plugins, 'isValid', c, default=False): return call(plugins, 'getParamValue', self.param, c, default=0)
        if tg == 'swing': return self.swing_value()
        return None

    def refresh(self, full=False):
        if not self.active: return
        self.dirty = False; self.refresh_t = now()
        if full: self.leds = {}
        if self.mode in GRID: self.page[self.mode] = max(0, min(self.page[self.mode], self.pages() - 1))   # (a group, a pattern or a plug-in changed under it)
        self.send_host()
        want = {t.PAD_LED[p]: v for p, v in self.pad_leds().items()}
        want.update(self.button_leds()); want.update(self.strip_leds())
        for led, v in sorted(want.items()):
            if self.leds.get(led) != v: self.led(led, v)
        self.lines = self.screen()
        self.draw(); self.send_steps()

    def led(self, led, v):
        st, d1, d2 = out.led_msg(led, v)
        call(device, 'midiOutMsg', st | (d1 << 8) | (d2 << 16)); self.leds[led] = v

    def draw(self):
        if self.host_ok is None: return                              # (waiting for the answer to HOST)
        lines = [out.clean(x) for x in self.lines]
        if self.host_ok:
            for n in range(4):
                if self.sent_lines[n] != lines[n]: self.sysex(out.text_line(n, lines[n])); self.sent_lines[n] = lines[n]
        elif lines != self.sent_lines:
            changed = [h for h in (0, 1) if lines[2 * h:2 * h + 2] != self.sent_lines[2 * h:2 * h + 2]]
            self.px_queue = [m for h in changed for m in out.regions(lines, h)]
            self.sent_lines = lines; self.px_drawn = now()

    def overview(self):
        """Step mode: (steps, set steps, first visible, count, playhead) of the 128-step stretch holding the pads' page, for the firmware's overview
        in place of screen line 3; None otherwise, and while a message needs both lines."""
        if not (cfg.STEP_OVERVIEW and self.host_ok and self.mode == 'step' and not self.msg): return None
        total = self.steps()
        start = self.page['step'] * 16; base = start // 128 * 128; n = min(128, total - base); c = self.chan()
        on = {k for k in range(n) if call(channels, 'getGridBit', c, base + k, default=False)}
        ph = self.playhead() - base
        return n, on, start - base, min(16, n - (start - base)), ph if 0 <= ph < n else None

    def send_steps(self):
        ov = self.overview()
        m = out.steps_msg(*ov) if ov else (out.steps_msg(0) if self.sent_steps not in (None, out.steps_msg(0)) else None)
        if m is not None and m != self.sent_steps: self.sysex(m); self.sent_steps = m

    def send_host(self):
        """Host mode: our text on the screen, and the pads as a grid while a grid mode is on or a drum layout plays (else they play whatever the
        device's mode is: Keyboard, Chords ...)."""
        f = t.HOST_SCREEN | (t.HOST_RAW if self.mode in GRID or self.layout() else 0)
        if self.host_ok is False: return
        if f == self.host_want and (f == self.host_flags or now() - self.host_t < HOST_RETRY_S): return
        self.sysex(out.host(f)); self.host_want = f; self.host_t = now()     # (the answer confirms it: host_flags)

def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v
def pan_text(v):
    p = int(round(abs(v) * 100))
    return 'CENTRE' if p == 0 else ('%d%% LEFT' % p if v < 0 else '%d%% RIGHT' % p)
