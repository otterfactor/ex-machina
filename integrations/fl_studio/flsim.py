"""A stand-in for FL Studio's MIDI scripting modules (channels, patterns, mixer, transport, plugins, ui, general, device, midi), for testing the
Ex-Machina script without FL Studio. A small project (channels with step grids and plug-ins, patterns, mixer tracks, the transport) answers the
functions the script calls, with the signatures of FL's API reference (https://il-group.github.io/FL-Studio-API-Stubs/); every call is logged.
install() puts the modules into sys.modules, so `import channels` in the script gets them. The main swing is FL's REC event REC_MainShuffle
(mixer.automateEvent turns it, device.getLinkedValue / getLinkedValueString read it); install(fl2026=False) leaves out setPatternLength."""
import sys, types

class Project:
    def __init__(self):
        self.ch = [dict(name=n, color=c, vol=0.78, pan=0.0, mute=False, solo=False, grid=set(), plugin=p, params=[], fpc=[])
                   for n, c, p in (('Kick', 0xFF3030, 'FPC'), ('Clap', 0x30FF30, 'Sampler'), ('Hat', 0x3030FF, 'Sampler'), ('Bass', 0xFFFF00, '3x Osc'))]
        self.ch[0]['fpc'] = [(36 + i, 0x0000FF if i % 2 else 0x00FF00) for i in range(16)]
        self.ch[3]['params'] = [['Osc 1 coarse', 0.5], ['', 0.0], ['Osc 2 coarse', 0.25], ['Osc 3 coarse', 0.75]]
        self.ch[3]['presets'] = 0
        self.sel = 0
        self.pat = [dict(name='Pattern 1', color=0xFF8000, length=4), dict(name='Pattern 2', color=0x8000FF, length=4)]
        self.cur = 1
        self.tracks = [dict(name='Master' if i == 0 else 'Insert %d' % i, color=0x808080 if i == 0 else 0xFF0000 + i, vol=0.8, pan=0.0) for i in range(126)]
        self.track = 1
        self.playing = self.recording = False; self.loop = 0; self.pos = 0; self.step = 0
        self.tempo = 140.0; self.metronome = False; self.swing = 0.0
        self.hint = ''; self.log = []; self.out = []; self.windows = set()
        self.steps = {}; self.graph = False; self.precount = False; self.looprec = False; self.recpps = 24
        self.popup = None                                           # an open popup menu: [items, highlighted index], or None
        self.focused = None; self.snap = 8                          # the focused window, FL's snap (midi.Snap_Step)
        self.pgroup = -1; self.pgroups = []                         # FL's pattern groups: the selected one (-1 = all patterns), [(name, (pattern numbers))]

P = None

def _mod(name, **fns):
    m = types.ModuleType(name)
    for k, f in fns.items(): setattr(m, k, f)
    return m

def install(fl2026=True):
    global P
    P = Project()
    log = lambda *a: P.log.append(a)
    C = lambda i: P.ch[i]
    def setgrid(i, pos, v, g=False):
        log('setGridBit', i, pos, v); (C(i)['grid'].add if v else C(i)['grid'].discard)(pos)
    def mute(i, value=-1, g=False): C(i)['mute'] = (not C(i)['mute']) if value == -1 else bool(value); log('muteChannel', i)
    def solo(i, g=False):
        on = not C(i)['solo']
        for c in P.ch: c['solo'] = False
        C(i)['solo'] = on; log('soloChannel', i)
    def sel1(i, g=False): P.sel = i; log('selectOneChannel', i)
    def stepset(index, patNum, step, param, value, g=False):          # (FL's step parameters; `index` is global with useGlobalIndex)
        i = index - GLOBAL if g else index; log('setStepParameterByIndex', i, patNum, step, param, value); P.steps[(i, patNum, step, param)] = value
        to = value // P.recpps if param == 7 else step                  # the shift is the note's position in the pattern: FL moves the note there,
        if to != step and step in C(i)['grid']:                          # with everything it has (its length too); seen with FL 2026.1
            for key in [k for k in P.steps if k[:3] == (i, patNum, step)]: P.steps[(i, patNum, to, key[3])] = P.steps.pop(key)
            C(i)['grid'].discard(step); C(i)['grid'].add(to)
    def stepget(i, step, param, g=False): return P.steps.get((i, P.cur, step, param), -1)
    def graph(temporary, param, step, index, g=True): P.graph = True; log('showGraphEditor', param, step, index - GLOBAL if g else index)
    def setvol(i, v, pick=0, g=False): C(i)['vol'] = v; log('setChannelVolume', i, v)
    def setpan(i, v, pick=0, g=False): C(i)['pan'] = v; log('setChannelPan', i, v)
    channels = _mod('channels', selectedChannel=lambda canBeNone=False, offset=0, g=False: P.sel, channelCount=lambda g=False: len(P.ch),
                    getChannelName=lambda i, g=False: C(i)['name'], getChannelColor=lambda i, g=False: C(i)['color'],
                    isChannelMuted=lambda i, g=False: C(i)['mute'], muteChannel=mute, isChannelSolo=lambda i, g=False: C(i)['solo'], soloChannel=solo,
                    selectOneChannel=sel1, getChannelVolume=lambda i, mode=False, g=False: C(i)['vol'], setChannelVolume=setvol,
                    getChannelPan=lambda i, g=False: C(i)['pan'], setChannelPan=setpan,
                    getGridBit=lambda i, pos, g=False: pos in C(i)['grid'], setGridBit=setgrid, showEditor=lambda i, v=-1, g=False: log('showEditor', i),
                    getChannelIndex=lambda i: i + GLOBAL, getCurrentStepParam=stepget, setStepParameterByIndex=stepset,
                    showGraphEditor=graph, isGraphEditorVisible=lambda: P.graph, quickQuantize=lambda i, startOnly=1, g=False: log('quickQuantize', i, startOnly),
                    focusEditor=lambda i, g=False: log('focusEditor', i))
    def jump(i): log('jumpToPattern', i); P.cur = i; (P.pat.append(dict(name='Pattern %d' % i, color=0x5F748B, length=4)) if i == len(P.pat) + 1 else None)
    def clone(index=None): log('clonePattern', index); P.pat.append(dict(P.pat[P.cur - 1])); P.cur = len(P.pat)
    pat_fns = dict(patternNumber=lambda: P.cur, patternCount=lambda: len(P.pat), patternMax=lambda: 999, getPatternName=lambda i: P.pat[i - 1]['name'],
                   getPatternColor=lambda i: P.pat[i - 1]['color'], getPatternLength=lambda i: P.pat[i - 1]['length'], jumpToPattern=jump, clonePattern=clone)
    if fl2026:
        def setlen(i, n): log('setPatternLength', i, n); P.pat[i - 1]['length'] = n
        pat_fns['setPatternLength'] = setlen
        pat_fns.update(getActivePatternGroup=lambda: P.pgroup, getPatternGroupCount=lambda: len(P.pgroups),     # (API 28)
                       getPatternGroupName=lambda i: P.pgroups[i][0], getPatternsInGroup=lambda i: tuple(P.pgroups[i][1]))
    patterns = _mod('patterns', **pat_fns)
    T = lambda i: P.tracks[i]
    def settv(i, v, pick=0): T(i)['vol'] = v; log('setTrackVolume', i, v)
    def settp(i, v, pick=0): T(i)['pan'] = v; log('setTrackPan', i, v)
    def settn(i, flags=0): P.track = i; log('setTrackNumber', i)
    def automate(index, value, flags, speed=0, isIncrement=0, res=1 / 24):
        log('automateEvent', index, value, flags, speed, isIncrement, res)
        if index == REC_MainShuffle: P.swing = min(1.0, max(0.0, (P.swing + value * res) if isIncrement else value / 1073741824.0))
        return 1
    mixer = _mod('mixer', automateEvent=automate, trackNumber=lambda: P.track, setTrackNumber=settn, getTrackName=lambda i: T(i)['name'], getTrackColor=lambda i: T(i)['color'],
                 getTrackVolume=lambda i, mode=0: T(i)['vol'], setTrackVolume=settv, getTrackPan=lambda i: T(i)['pan'], setTrackPan=settp,
                 getCurrentTempo=lambda asInt=False: int(P.tempo * 1000) if asInt else P.tempo, getSongStepPos=lambda: P.step, getRecPPS=lambda: P.recpps,
                 muteTrack=lambda i, value=-1: (T(i).__setitem__('mute', (not T(i).get('mute')) if value == -1 else bool(value)), log('muteTrack', i, value)),
                 isTrackMuted=lambda i: bool(T(i).get('mute')), isTrackSolo=lambda i: bool(T(i).get('solo')),
                 soloTrack=lambda i, value=-1, mode=-1: (T(i).__setitem__('solo', (not T(i).get('solo')) if value == -1 else bool(value)), log('soloTrack', i, value)))
    def gt(cmd, value, pme=0, flags=0):
        log('globalTransport', cmd, value)
        if cmd == FPT_Metronome: P.metronome = not P.metronome
        if cmd == FPT_TempoJog: P.tempo += value / 10.0
        if cmd == FPT_CountDown: P.precount = not P.precount
        if cmd == FPT_LoopRecord: P.looprec = not P.looprec
        if cmd == FPT_ShuffleJog: P.swing = min(1.0, max(0.0, P.swing + value / 128.0))
        return 1
    def start(): P.playing = not P.playing; log('start')
    def stop(): P.playing = False; P.pos = 0; log('stop')
    def record(): P.recording = not P.recording; log('record')
    def setpos(p, mode=-1): P.pos = p; log('setSongPos', p)
    def setloop(): P.loop ^= 1; log('setLoopMode')
    tr = dict(start=start, stop=stop, record=record, isPlaying=lambda: P.playing, isRecording=lambda: P.recording, setSongPos=setpos,
              getSongPos=lambda mode=-1: P.pos, globalTransport=gt, getLoopMode=lambda: P.loop, setLoopMode=setloop)
    transport = _mod('transport', **tr)
    def params(i): return C(i)['params']
    def setparam(v, p, i, slot=-1, pick=0, g=False): params(i)[p][1] = v; log('setParamValue', v, p, i)
    def nextp(i, slot=-1, g=False): C(i)['presets'] = C(i).get('presets', 0) + 1; log('nextPreset', i)
    def prevp(i, slot=-1, g=False): C(i)['presets'] = C(i).get('presets', 0) - 1; log('prevPreset', i)
    def padinfo(i, slot=-1, opt=0, idx=-1):
        f = C(i)['fpc']
        return len(f) if opt == 0 else f[idx][0] if opt == 1 else f[idx][1]
    plugins = _mod('plugins', isValid=lambda i, slot=-1, g=False: C(i)['plugin'] is not None, getPluginName=lambda i, slot=-1, user=False, g=False: C(i)['plugin'],
                   getParamCount=lambda i, slot=-1, g=False: len(params(i)), getParamName=lambda p, i, slot=-1, g=False: params(i)[p][0],
                   getParamValue=lambda p, i, slot=-1, g=False: params(i)[p][1], setParamValue=setparam,
                   getParamValueString=lambda p, i, slot=-1, pick=0, g=False: '%d st' % round(params(i)[p][1] * 48 - 24),
                   nextPreset=nextp, prevPreset=prevp, getPadInfo=padinfo, getName=lambda i, slot=-1, flag=0, p=0, g=False: 'Preset %d' % C(i).get('presets', 0))
    def win(name): return lambda *a: log(name, *a)
    def menu_move(d):
        def f(value=1):
            log('down' if d > 0 else 'up')
            m = P.popup
            if m: m[1] = max(0, min(len(m[0]) - 1, m[1] + d)); P.hint = m[0][m[1]]
        return f
    def enter(*a):
        log('enter')
        if P.popup: P.chosen = P.popup[0][P.popup[1]]; P.popup = None
    def closemenu(): log('closeActivePopupMenu'); P.popup = None
    ui = _mod('ui', jog=win('jog'), next=win('next'), previous=win('previous'), enter=enter, up=menu_move(-1), down=menu_move(1),
              isInPopupMenu=lambda: P.popup is not None, closeActivePopupMenu=closemenu, left=win('left'), right=win('right'),
              showWindow=lambda w: (P.windows.add(w), log('showWindow', w)), hideWindow=lambda w: (P.windows.discard(w), log('hideWindow', w)),
              setFocused=lambda w: (setattr(P, 'focused', w), log('setFocused', w)), getFocused=lambda w: P.focused == w,
              getVisible=lambda w: w in P.windows, getSnapMode=lambda: P.snap, getHintMsg=lambda: P.hint, isMetronomeEnabled=lambda: P.metronome, setHintMsg=lambda m: setattr(P, 'hint', m),
              isPrecountEnabled=lambda: P.precount, isLoopRecEnabled=lambda: P.looprec)
    general = _mod('general', saveUndo=lambda name, flags, update=True: log('saveUndo', name, flags), undoUp=win('undoUp'), undoDown=win('undoDown'), getVersion=lambda: 40, dumpScoreLog=lambda time, silent=False: log('dumpScoreLog', time, silent))
    device = _mod('device', midiOutMsg=lambda m, *a: P.out.append(('msg', m)), midiOutSysex=lambda b: P.out.append(('sysex', bytes(b))),
                  isAssigned=lambda: True, getName=lambda: 'Maschine Mikro MK3',
                  getLinkedValue=lambda e: P.swing if e == REC_MainShuffle else -1.0,
                  getLinkedValueString=lambda e: '%d%%' % round(P.swing * 100) if e == REC_MainShuffle else '')
    midi = _mod('midi', REC_MainShuffle=REC_MainShuffle, REC_MIDIController=1005, FPT_ShuffleJog=FPT_ShuffleJog, FPT_TapTempo=106, FPT_Metronome=110, FPT_TempoJog=105, FPT_CountDown=115, FPT_LoopRecord=113, FPT_Copy=51, FPT_Paste=52,
                HW_Dirty_Patterns=1024, HW_Dirty_Names=16384, HW_Dirty_ChannelRackGroup=32768, widMixer=0, widChannelRack=1, widPlaylist=2, widPianoRoll=3, widBrowser=4, widPluginEffect=6, widPluginGenerator=7)
    for m in (channels, patterns, mixer, transport, plugins, ui, general, device, midi): sys.modules[m.__name__] = m
    return P

FPT_TapTempo, FPT_Metronome, FPT_TempoJog, FPT_CountDown, FPT_LoopRecord, FPT_ShuffleJog = 106, 110, 105, 115, 113, 122   # (FL's values: API stubs midi/__gt_commands.py)
REC_MainShuffle = 0x4000 * 0x10000 + 1              # (REC_Global_First + 1: midi/__rec_events)
GLOBAL = 100                                        # the stand-in's global channel index = the Channel Rack position + 100, so a mix-up shows

class PRNote:
    """A note of FL's piano-roll scripting module (flpianoroll.Note), as far as the script uses it."""
    def __init__(self, time, number, selected=False, length=24): self.time, self.number, self.selected, self.length = time, number, selected, length

def piano_roll(notes, ppq=96):
    """Makes FL's piano-roll scripting module importable (flpianoroll.score with these notes); piano_roll(None) takes it away again (an FL that
    does not let a controller script use it)."""
    if notes is None: sys.modules.pop('flpianoroll', None); return None
    m = types.ModuleType('flpianoroll'); m.score = _Score(ppq, notes); sys.modules['flpianoroll'] = m
    return m.score

class _Score:
    def __init__(self, ppq, notes): self.PPQ, self.notes = ppq, list(notes)
    @property
    def noteCount(self): return len(self.notes)
    def getNote(self, i): return self.notes[i]

class Event:
    """FL's event object, as far as the script reads it."""
    def __init__(self, status, data1=0, data2=0, sysex=b''):
        self.status, self.data1, self.data2, self.sysex, self.handled = status, data1, data2, bytes(sysex), False
