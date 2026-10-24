#!/usr/bin/env python3
"""Split a combined Breath of the Wild NSP into one standalone NSP per add-on content title.

The user's botw.nsp holds base + update + both DLC packs in one PFS0 container.
games/botw/scripts/extract_dlc.py requires exactly one Data NCA per container, so this
tool groups the combined package's entries by title ID (from decrypted NCA headers via
the upstream inventory code) and writes <output>/<titleid>.nsp holding that title's
NCA(s), cnmt NCA, cnmt XML, ticket and certificate.

The base and update Program NCAs are NOT split out: the extraction scripts read them
from the original container in place.

usage: split_dlc.py <combined.nsp> --keys <prod.keys> --output <new folder>
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'games' / 'totk' / 'scripts'))
from extract_exefs import load_keys, container_entries, nca_inventory, require  # noqa: E402

CHUNK = 4 * 1024 * 1024


def title_of(name, by_nca_name):
    """Title ID of a PFS0 entry name: .tik/.cert carry it in the first 16 hex chars of the
    rights-ID filename; .cnmt.xml shares its cnmt NCA's content-hash name; NCA headers are
    decrypted by the upstream inventory."""
    stem = name.lower()
    if stem.endswith('.tik') or stem.endswith('.cert'):
        return name[:16].upper() if len(name) >= 16 else None
    if stem.endswith('.cnmt.xml'):
        return by_nca_name.get(stem.replace('.cnmt.xml', '.cnmt.nca'))
    return by_nca_name.get(stem)


def is_dlc(title_id):
    if not title_id:
        return False
    return (int(title_id, 16) & 0xFFF) not in (0x000, 0x800)


def write_nsp(out, source, groups, title, names):
    entries = [(n, groups[title][n]['offset'], groups[title][n]['size']) for n in names]
    strings = b''.join(n.encode() + b'\0' for n in names)
    data_start = 16 + 24 * len(entries) + len(strings)
    with open(out, 'wb') as w:
        w.write(b'PFS0' + struct.pack('<III', len(entries), len(strings), 0))
        pos = 0
        for i, (_, _, size) in enumerate(entries):
            name_offset = sum(len(n.encode()) + 1 for n in names[:i])
            w.write(struct.pack('<QQII', pos, size, name_offset, 0))
            pos += size
        w.write(strings)
        with open(source, 'rb') as r:
            for _, off, size in entries:
                r.seek(off)
                left = size
                while left:
                    block = r.read(min(CHUNK, left))
                    require(block, f'short read at {off}')
                    w.write(block)
                    left -= len(block)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('game', type=Path)
    ap.add_argument('--keys', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    require(not args.output.exists(), 'Output already exists')
    args.output.mkdir(parents=True)
    keys = load_keys(args.keys)
    with args.game.open('rb') as f:
        _, entries = container_entries(f, args.game.stat().st_size)
        records = nca_inventory(f, entries, keys)
    by_nca_name = {r['name'].lower(): r['title_id'] for r, _ in records}
    groups = {}
    for name, offset, size in entries:
        title = title_of(name, by_nca_name)
        if title and is_dlc(title):
            groups.setdefault(title, {})[name] = {'offset': offset, 'size': size}
    require(groups, 'no add-on content titles found in the combined package')
    report = {}
    for title, files in sorted(groups.items()):
        names = sorted(files)
        out = args.output / f'{title}.nsp'
        write_nsp(out, args.game, groups, title, names)
        with out.open('rb') as f:
            _, sub_entries = container_entries(f, out.stat().st_size)
            sub_records = nca_inventory(f, sub_entries, keys)
        data = [r for r, _ in sub_records if r['content_type'] == 5]
        require(len(data) == 1, f'{out.name}: expected one Data NCA, got {len(data)}')
        report[title] = {'file': out.name, 'entries': len(names), 'bytes': out.stat().st_size,
                         'data_nca': data[0]['name'], 'size': data[0]['size']}
        print(f"{title}: {out.name} ({out.stat().st_size:,} bytes, {len(names)} entries)")
    (args.output / 'split-report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
