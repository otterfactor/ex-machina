"""Puts the repository's code folders on the module path for the tests and their harness: a test does `import paths` (a script's own folder,
tests/, is already on the path) and can then import the image builder (firmware/), the host library (host/), the emulator models (tools/emu/)
and the tools (tools/)."""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, 'tests')
FIRMWARE = os.path.join(ROOT, 'firmware')
HOST = os.path.join(ROOT, 'host')
EMU = os.path.join(ROOT, 'tools', 'emu')
TOOLS = os.path.join(ROOT, 'tools')
for _p in (TOOLS, EMU, HOST, FIRMWARE, TESTS):
    if _p not in sys.path: sys.path.insert(0, _p)
