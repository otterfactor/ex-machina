#!/usr/bin/env python3
"""carve_fw.py finds NI's firmware 1.20 in every form of NI's updater and refuses anything else (it used to copy a fixed Mac file offset,
which wrote 40 KB of garbage from the Windows .exe or a .zip without a word), and build_patch.py refuses a source that is not that image.
Usage: test_carve_fw.py <stock.bin>   (the containers are synthetic: the stock image wrapped in filler bytes, a fake .app, zips)"""
import io, os, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CARVE = os.path.join(HERE, 'carve_fw.py')
BUILD = os.path.join(ROOT, 'firmware', 'build_patch.py')
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  {detail}'))
    fails += not ok


def run(*args):
    p = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


stock = open(sys.argv[1], 'rb').read()
filler = bytes(range(256)) * 400
with tempfile.TemporaryDirectory() as t:
    def path(n): return os.path.join(t, n)
    exe = filler + stock[:8] + filler[:100] + stock + filler        # a decoy vector table first, then the image
    open(path('MM3Updater.exe'), 'wb').write(exe)
    app = path('MM3Updater.app/Contents/MacOS'); os.makedirs(app)
    open(os.path.join(app, 'MM3Updater'), 'wb').write(filler + stock + filler)
    open(path('MM3Updater.app/Contents/Info.plist'), 'wb').write(b'<plist/>')
    with zipfile.ZipFile(path('win.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('readme.txt', 'x' * 50000); z.writestr('MM3Updater.exe', exe)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('MM3Updater.app/Contents/MacOS/MM3Updater', exe)
    with zipfile.ZipFile(path('mac.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('MM3Updater.pkg.zip', inner.getvalue())
    for src in ('MM3Updater.exe', 'MM3Updater.app', 'MM3Updater.app/Contents/MacOS/MM3Updater', 'win.zip', 'mac.zip'):
        out = path('out.bin')
        if os.path.exists(out): os.remove(out)
        rc, msg = run(CARVE, path(src), out)
        check(f'carved from {src}', rc == 0 and os.path.exists(out) and open(out, 'rb').read() == stock, (rc, msg))

    rc, msg = run(CARVE, path('mac.zip'), path('proprietary/stock.bin'))
    check('the output folder is created (proprietary/ is not in a fresh clone)', rc == 0 and open(path('proprietary/stock.bin'), 'rb').read() == stock, (rc, msg))

    other = bytearray(stock); other[0x1000] ^= 0xFF                 # another version (or a broken copy): same vector table, other bytes
    open(path('other.exe'), 'wb').write(filler + other + filler)
    for src in ('other.exe', 'MM3Updater.app/Contents/Info.plist'):
        rc, msg = run(CARVE, path(src), path('bad.bin'))
        check(f'refused: {src}, nothing written', rc != 0 and not os.path.exists(path('bad.bin')) and 'not found' in msg, (rc, msg))
    rc, msg = run(CARVE, path('missing.exe'), path('bad.bin'))
    check('refused: a missing file', rc != 0 and 'no such file' in msg, (rc, msg))

    open(path('other.bin'), 'wb').write(bytes(other))
    for extra in ([], ['--native']):
        rc, msg = run(BUILD, path('other.bin'), path('img.bin'), *extra)
        check('build_patch refuses an image that is not firmware 1.20' + (' (--native)' if extra else ''),
              rc != 0 and not os.path.exists(path('img.bin')) and 'carve_fw' in msg, (rc, msg[-300:]))

    # without clang (a Windows machine with no LLVM): a message saying what to install, not a FileNotFoundError traceback
    env = {k: v for k, v in os.environ.items() if k not in ('CLANG', 'ProgramFiles', 'ProgramFiles(x86)')}
    env['PATH'] = t                                                  # a folder with no clang in it
    p = subprocess.run([sys.executable, BUILD, sys.argv[1], path('img.bin')], capture_output=True, text=True, env=env)
    msg = p.stdout + p.stderr
    check('build_patch without clang says what to install', p.returncode != 0 and 'clang was not found' in msg and 'winget' in msg
          and 'Traceback' not in msg and not os.path.exists(path('img.bin')), msg[-400:])

    # clang versions differ in when they turn a switch into a lookup table in .rodata (LLVM 23 did in translate_report, Apple's clang 21
    # did not), which the object must not have: build_patch's flags prevent it, and anything left is named in the error
    sys.path.insert(0, os.path.join(ROOT, 'firmware'))
    import build_patch as bp
    from elftools.elf.elffile import ELFFile
    open(path('sw.c'), 'w').write('unsigned sw(unsigned x) { switch (x) { case 0: return 7; case 1: return 19; case 2: return 3; case 3: return 88;'
                                  ' case 4: return 41; case 5: return 2; case 6: return 77; default: return 0; } }\n')
    probs = {}
    for name, flags in (('without', [f for f in bp.CFLAGS if f != '-fno-jump-tables']), ('with', bp.CFLAGS)):
        subprocess.check_call([bp.find_clang()] + flags + [path('sw.c'), '-o', path(name + '.o')])
        with open(path(name + '.o'), 'rb') as f:
            probs[name] = bp.object_problems(ELFFile(f))
    check("build_patch's flags keep a switch out of .rodata", probs['with'] == [], probs['with'])
    check('... and without them the problem is named (.rodata, the table)', any('.rodata' in p for p in probs['without'])
          and any('switch.table' in p for p in probs['without']), probs['without'])

print('ALL PASS' if not fails else f'{fails} FAILED')
sys.exit(1 if fails else 0)
