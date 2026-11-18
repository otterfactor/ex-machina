#!/usr/bin/env python3
"""Carve the Mikro MK3 firmware 1.20 out of NI's firmware updater.
Usage: carve_fw.py <NI updater> <out.bin>

<NI updater> can be any of: the Mac updater's binary (MM3Updater.app/Contents/MacOS/MM3Updater), the app itself (MM3Updater.app), the
Windows updater (MM3Updater.exe), or the .zip NI ships either of them in. The image (40,392 bytes) is found by the start of its vector table
and accepted only if its SHA-256 is the one of firmware 1.20, the version the patch is made for; anything else is refused, never written.
Output is NI's proprietary firmware: keep it local, never commit or redistribute it."""
import hashlib, io, os, sys, zipfile

STOCK_LEN = 0x9DC8
STOCK_SHA256 = '76ebf72d33961639a0bd042ba32354dd8dc07569be69175546eb9fc06e5c5917'
SIGNATURE = bytes([0x18, 0x1C, 0x00, 0x20, 0xC1, 0x31, 0x00, 0x08])   # initial SP 0x20001c18, reset vector 0x080031c1 (as tools/ui/patch.js)


def find_image(data):
    """The stock image inside `data` (any container that holds it uncompressed), or None."""
    i = data.find(SIGNATURE)
    while i >= 0:
        cand = data[i:i + STOCK_LEN]
        if len(cand) == STOCK_LEN and hashlib.sha256(cand).hexdigest() == STOCK_SHA256:
            return cand
        i = data.find(SIGNATURE, i + 1)
    return None


def candidates(path):
    """(name, bytes) of every file worth searching: the file itself, the files inside a directory (the .app), the members of a zip."""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in sorted(files):
                p = os.path.join(root, f)
                if os.path.isfile(p) and os.path.getsize(p) >= STOCK_LEN:
                    yield p, open(p, 'rb').read()
        return
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for m in z.infolist():
                if not m.is_dir():
                    yield f'{path}:{m.filename}', z.read(m)
        return
    yield path, open(path, 'rb').read()


def carve(path):
    """The image and where it was found; raises ValueError with a hint when it is not there."""
    if not os.path.exists(path):
        raise ValueError(f'no such file: {path}')
    for name, data in candidates(path):
        img = find_image(data)
        if img is not None:
            return img, name
        if data[:4] == b'PK\x03\x04':                                       # a zip inside the zip (or inside the app)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for m in z.infolist():
                    if not m.is_dir():
                        img = find_image(z.read(m))
                        if img is not None:
                            return img, f'{name}:{m.filename}'
    raise ValueError(f"NI's Mikro MK3 firmware 1.20 was not found in {path}. Give it NI's firmware updater 1.20 for the Mikro MK3: "
                     'the Mac app (MM3Updater.app) or its binary, the Windows MM3Updater.exe, or the .zip either comes in.')


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        img, where = carve(sys.argv[1])
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        sys.exit(f'carve_fw: {e}')
    os.makedirs(os.path.dirname(os.path.abspath(sys.argv[2])), exist_ok=True)     # proprietary/ is ignored by git: a fresh clone has none
    with open(sys.argv[2], 'wb') as f:
        f.write(img)
    print(f'found firmware 1.20 in {where}; wrote {len(img)} bytes to {sys.argv[2]} (SHA-256 {STOCK_SHA256[:16]}...)')


if __name__ == '__main__':
    main()
