#!/usr/bin/env python3
"""Unpack a Switch RomFS image (the inner romfs: 0x50 header, file data from 0x200,
hash+meta tables at the end — the layout runtime/romfs_build.c writes and hactool's
romfs extraction produces) into a directory tree.

The reverse of Savage Wind's romfs_build: gives the runtime's "Set up game files"
its `romfs/` tree input from an already-merged image (our P1 pipeline's romfs.bin,
base + 1.9.0 update BKTR-merged), without re-running the NCA decryption.

usage: romfs_unpack.py <romfs.bin> <outdir>
"""
import os
import struct
import sys
import time

EMPTY = 0xFFFFFFFF
BUF = 4 << 20

# \\?\ so deep Pack/ paths (Switch names run long) never hit MAX_PATH
def win(p):
    p = os.path.abspath(p)
    return p if not os.name == 'nt' or p.startswith('\\\\?\\') else '\\\\?\\' + p


def entry_dir(tab, off):
    parent, sib, cdir, cfile, _h, nl = struct.unpack_from('<6I', tab, off)
    name = tab[off + 0x18: off + 0x18 + nl].decode('utf-8', 'surrogateescape')
    return parent, sib, cdir, cfile, name


def entry_file(tab, off):
    parent, sib = struct.unpack_from('<2I', tab, off)
    data_off, size = struct.unpack_from('<2Q', tab, off + 8)
    nl = struct.unpack_from('<I', tab, off + 0x1c)[0]
    name = tab[off + 0x20: off + 0x20 + nl].decode('utf-8', 'surrogateescape')
    return parent, sib, data_off, size, name


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    image, out = sys.argv[1], sys.argv[2]
    f = open(win(image), 'rb')
    hdr = struct.unpack('<10Q', f.read(0x50))
    (hsz, _dho, _dhs, dmo, dms, _fho, _fhs, fmo, fms, data_base) = hdr
    if hsz != 0x50:
        sys.exit(f'not an inner RomFS image (header_size {hsz:#x})')
    f.seek(dmo)
    dtab = f.read(dms)
    f.seek(fmo)
    ftab = f.read(fms)

    os.makedirs(win(out), exist_ok=True)
    ndirs = nfiles = nbytes = 0
    t0 = time.time()
    next_report = 0

    def walk(doff, path):
        nonlocal ndirs, nfiles, nbytes, next_report
        fo = entry_dir(dtab, doff)[3]  # first child file
        while fo != EMPTY:
            _, sib, data_off, size, name = entry_file(ftab, fo)
            dst = os.path.join(path, name)
            with open(win(dst), 'wb') as o:
                f.seek(data_base + data_off)
                left = size
                while left:
                    chunk = f.read(min(left, BUF))
                    if not chunk:
                        raise SystemExit(f'short read in image at {data_base + data_off:#x}')
                    o.write(chunk)
                    left -= len(chunk)
            nfiles += 1
            nbytes += size
            fo = sib
        co = entry_dir(dtab, doff)[2]  # first child dir
        while co != EMPTY:
            _, sib, _, _, name = entry_dir(dtab, co)
            dpath = os.path.join(path, name)
            os.makedirs(win(dpath), exist_ok=True)
            ndirs += 1
            walk(co, dpath)
            co = sib

    walk(0, out)
    dt = time.time() - t0
    print(f'[romfs] {nfiles} files, {ndirs} dirs, {nbytes / 2**30:.2f} GiB in {dt / 60:.1f} min')


if __name__ == '__main__':
    main()
