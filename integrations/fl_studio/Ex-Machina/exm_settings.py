"""Settings of the Ex-Machina FL Studio script: edit the values here (in FL's Hardware folder) and reload the script (MIDI Settings > Update MIDI scripts)."""

STEP_VELOCITY = True            # a step set from a pad takes the pad's velocity (a hard hit makes an accent); False: FL's default velocity
FOCUS_WINDOWS = True            # Step / Select / Mute / Solo / Pattern bring the Channel Rack to the front, Group the Mixer, Plug-in the plug-in's window
GRAPH_EDITOR = True             # editing a held step with the encoder opens FL's graph editor on that parameter
LOOP_RECORD_ON_CONNECT = False  # switch FL's loop recording on when the script starts (as FLkey does); off by default: it changes a setting of FL's
SCORE_LOG_SECONDS = 300         # Shift + Play: how much of what was just played goes into the pattern
MESSAGE_SECONDS = 1.5           # how long a value or a message stays on the screen
STRIP_BAR = True                # the touch-strip LEDs show the encoder's value, or the song position while FL plays
HINT_BAR = True                 # messages also go to FL's hint bar
DRUM_LAYOUTS = True             # play mode follows the channel's plug-in: FPC plays its own pad notes (banks A / B on Left / Right), Slicex and Fruity Slicer
                                #   play slices 1-16, 17-32 ... (from note 60); the device's Keyboard / Chords modes do not apply to such a channel
STEP_OVERVIEW = True            # Step mode: the whole pattern (up to 128 steps) as a strip on the screen, the pads' page bracketed, the playhead
TOUCH_PREVIEW = True            # touching the encoder shows what it would change and the value, without changing it
# Variation: which parameters of a plug-in go on the 16 pads, by name as FL shows them (Link to controller lists them), in pad order (more than 16:
# Left / Right page). A plug-in not listed here gets every parameter that has a name. For example:
#   PLUGIN_PAGES = {'3x Osc': ['Osc 1 coarse', 'Osc 2 coarse', 'Osc 3 coarse']}
PLUGIN_PAGES = {}
