#!/usr/bin/env python3
"""WinNativeGames BOTW build orchestrator — Windows port of upstream build_app.py's BOTW path.

Differences from upstream (by design, for the Windows x64 JIT route):
- The D2R instruction rewriter (patch_nso.py) is NOT run: the loader binds to the ORIGINAL
  ExeFS modules, verified against expected-v1.9.0.json exefs_sha256 pins (the pin set holds
  both the original and the rewritten hashes; the originals are what dynarmic executes).
- The combined NSP (base + update + DLC in one PFS0) is accepted directly: the upstream
  extraction scripts select NCAs by title ID and BKTR presence; the DLC packs are split
  out per title by scripts/split_dlc.py.
- The work folder lives inside this repository (never next to the game file, which stays
  read-only).

usage: build_app_win.py <game file> -k <prod.keys> --firmware <NCA dir> [--work <dir>]
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
# shared toolchain (cmake/ninja/llvm-mingw/pyvenv) lives beside this repo: ../.. /tools
TOOLS = Path(os.environ.get('WNG_TOOLS') or (REPO.parent.parent / 'tools'))
PY = TOOLS / 'pyvenv/Scripts/python.exe'
HACTOOL = ('https://github.com/SciresM/hactool.git', '1d64a83450e025622f3468c28fc4164dad2c5ef6')
GAME_TITLE = '01007EF00011E000'
VERSIONS = {
    'botw190': json.loads((REPO / 'games/botw/assets/expected-v1.9.0.json').read_text()),
    'botw160': json.loads((REPO / 'games/botw/assets/expected-v1.6.0.json').read_text()),
}


class BuildError(Exception):
    pass


def say(msg):
    print(f'[build] {msg}', flush=True)


def check(what, got, want):
    if got != want:
        raise BuildError(f'{what}: got {got}, expected {want}')
    say(f'  ok: {what}')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(cmd, log, cwd=None, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    with open(log, 'ab') as f:
        f.write(f'\n$ {" ".join(str(c) for c in cmd)}\n'.encode())
        p = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT, cwd=cwd, env=e)
    if p.returncode:
        raise BuildError(f'command failed ({p.returncode}): {cmd} — see {log}')


def last_json(log):
    try:
        lines = Path(log).read_text(errors='replace').strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{'):
                return json.loads(line)
    except (OSError, ValueError):
        pass
    return None


def git_fetch(url, commit, dst, log):
    if (dst / '.git').is_dir():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(['git', 'init', '-q', dst], log)
    run(['git', '-C', dst, 'fetch', '-q', '--depth', '1', url, commit], log)
    run(['git', '-C', dst, 'checkout', '-q', 'FETCH_HEAD'], log)


# ---------------------------------------------------------------- hactool

def build_hactool(work, logs):
    """Pinned hactool with the upstream hooks, ported to Windows (fopencookie replaces the
    BSD funopen of the bounded base-file hook)."""
    source = work / 'src' / 'hactool'
    git_fetch(*HACTOOL, source, logs / 'fetch-hactool.log')
    run(['git', '-C', source, 'checkout', '--', '.'], logs / 'fetch-hactool.log')   # re-apply patches cleanly
    main = source / 'main.c'
    text = main.read_text()
    old = 'FILE *titlekeyfile = open_key_file("title");'
    new = 'FILE *titlekeyfile = getenv("MNG_TITLE_KEYS") ? fopen(getenv("MNG_TITLE_KEYS"), "rb") : open_key_file("title");'
    if new not in text:
        if text.count(old) != 1:
            raise BuildError('pinned hactool title-key hook changed')
        main.write_text(text.replace(old, new))
    text = main.read_text()
    hook = 'static FILE *mng_open_base(const char *path)'
    if os.name == 'nt':
        # llvm-mingw has no fopencookie/funopen: the bounded in-place base-file view is
        # not available. mng_open_base passes through, and this repo's extract_romfs.py
        # extracts the base NCA to a temporary file instead.
        passthrough = 'static FILE *mng_open_base(const char *path) { return fopen(path, "rb"); }\n'
        if hook not in text:
            marker = 'int main(int argc, char **argv)'
            if text.count(marker) != 1 or text.count('nca_ctx.tool_ctx->base_file = fopen(optarg, "rb")') != 2:
                raise BuildError('pinned hactool bounded base-file hook changed')
            main.write_text(text.replace(marker, passthrough + '\n' + marker).replace(
                'nca_ctx.tool_ctx->base_file = fopen(optarg, "rb")', 'nca_ctx.tool_ctx->base_file = mng_open_base(optarg)'))
    elif hook not in text:
        helper = r'''
typedef struct { FILE *file; long long start, size, position; } mng_base_range;
static ssize_t mng_base_read(void *cookie, char *buffer, size_t count) {
    mng_base_range *range = cookie;
    long long left = range->size - range->position;
    if ((long long)count > left) count = (size_t)left;
    if (!count) return 0;
    if (_fseeki64(range->file, range->start + range->position, SEEK_SET)) return -1;
    ssize_t got = (ssize_t)fread(buffer, 1, count, range->file);
    if (!got && ferror(range->file)) return -1;
    range->position += got;
    return got;
}
static int mng_base_seek(void *cookie, long long *offset, int whence) {
    mng_base_range *range = cookie;
    long long base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? range->position : whence == SEEK_END ? range->size : -1;
    if (whence == SEEK_END) base = range->size;
    if (base < 0 || *offset < -base || *offset > range->size - base) return -1;
    *offset = range->position = base + *offset;
    return 0;
}
static int mng_base_close(void *cookie) {
    mng_base_range *range = cookie;
    int result = fclose(range->file); free(range); return result;
}
static FILE *mng_open_base(const char *path) {
    const char *start = getenv("MNG_BASE_RANGE_OFFSET"), *size = getenv("MNG_BASE_RANGE_SIZE");
    if (!start && !size) return fopen(path, "rb");
    if (!start || !size) return NULL;
    char *end1, *end2;
    long long a = strtoll(start, &end1, 10), n = strtoll(size, &end2, 10);
    if (!*start || !*size || *end1 || *end2 || !n || n > (long long)9223372036854775807LL - a) return NULL;
    mng_base_range *range = calloc(1, sizeof(*range));
    if (!range) return NULL;
    range->file = fopen(path, "rb"); range->start = a; range->size = n;
    if (!range->file) { free(range); return NULL; }
    if (_fseeki64(range->file, 0, SEEK_END)) { mng_base_close(range); return NULL; }
    if (_ftelli64(range->file) < a + n) { mng_base_close(range); return NULL; }
    static cookie_io_functions_t funcs = {mng_base_read, NULL, mng_base_seek, mng_base_close};
    FILE *view = fopencookie(range, "rb", funcs);
    if (!view) mng_base_close(range);
    return view;
}
'''
        marker = 'int main(int argc, char **argv)'
        if text.count(marker) != 1 or text.count('nca_ctx.tool_ctx->base_file = fopen(optarg, "rb")') != 2:
            raise BuildError('pinned hactool bounded base-file hook changed')
        main.write_text(text.replace(marker, helper + '\n' + marker).replace(
            'nca_ctx.tool_ctx->base_file = fopen(optarg, "rb")', 'nca_ctx.tool_ctx->base_file = mng_open_base(optarg)'))
    nca = source / 'nca.c'
    text = nca.read_text()
    old = ('sb->relocation_header.offset + sb->relocation_header.size != sb->subsection_header.offset ||\n'
           '            sb->subsection_header.offset + sb->subsection_header.size != ctx->size')
    new = ('sb->relocation_header.offset + sb->relocation_header.size != sb->subsection_header.offset ||\n'
           '            sb->subsection_header.offset + sb->subsection_header.size > ctx->size ||\n'
           '            (ctx->size - (sb->subsection_header.offset + sb->subsection_header.size)) % 0x200 != 0')
    if new not in text:
        if text.count(old) != 1:
            raise BuildError('pinned hactool BKTR layout check changed')
        nca.write_text(text.replace(old, new))
    text = nca.read_text()
    old = 'if (ctx->bktr_ctx.subsection_block->total_size != sb->subsection_header.offset) {'
    new = ('if (ctx->bktr_ctx.subsection_block->total_size != sb->subsection_header.offset &&\n'
           '            (sb->relocation_header.size > sb->subsection_header.offset ||\n'
           '             ctx->bktr_ctx.subsection_block->total_size != sb->subsection_header.offset - sb->relocation_header.size)) {')
    if new not in text:
        if text.count(old) != 1:
            raise BuildError('pinned hactool BKTR total-size check changed')
        nca.write_text(text.replace(old, new))
    cmake = REPO / 'third_party/hactool/CMakeLists.txt'
    run([TOOLS / 'cmake-3.31.8-windows-x86_64/bin/cmake.exe', '-S', cmake.parent, f'-DHACTOOL_SRC_DIR={source.as_posix()}', '-B', work / 'build' / 'hactool',
         '-G', 'Ninja', f'-DCMAKE_MAKE_PROGRAM={TOOLS / "ninja.exe"}',
         f'-DCMAKE_C_COMPILER={TOOLS / "llvm-mingw-20261020-ucrt-x86_64/bin/x86_64-w64-mingw32-clang.exe"}',
         '-DCMAKE_BUILD_TYPE=Release'], logs / 'hactool-cmake.log')
    run([TOOLS / 'ninja.exe', '-C', work / 'build' / 'hactool'], logs / 'hactool-build.log')
    out = work / 'build' / 'hactool' / 'hactool.exe'
    require_file(out, 'hactool.exe')
    return out


def require_file(path, what):
    if not Path(path).is_file():
        raise BuildError(f'{what} not built: {path} missing')


# ---------------------------------------------------------------- steps

def ticket_title_ids(path):
    ids = []
    bodies = {0x10000: 0x240, 0x10001: 0x140, 0x10002: 0x80, 0x10003: 0x240, 0x10004: 0x140, 0x10005: 0x80}
    try:
        with Path(path).open('rb') as f:
            head = f.read(16)
            if len(head) < 16 or head[:4] != b'PFS0':
                return []
            count, strings_size = struct.unpack_from('<II', head, 4)
            table = f.read(count * 24)
            strings = f.read(strings_size)
            data_start = 16 + count * 24 + strings_size
            for i in range(count):
                offset, size, name_at, _ = struct.unpack_from('<QQII', table, i * 24)
                name = strings[name_at:strings.find(b'\0', name_at)] if name_at < len(strings) else b''
                if not name.lower().endswith(b'.tik') or size < 4:
                    continue
                f.seek(data_start + offset)
                sig = f.read(4)
                body = bodies.get(struct.unpack('<I', sig)[0]) if len(sig) == 4 else None
                if body is None or size < body + 0x168:
                    continue
                f.seek(data_start + offset + body + 0x160)
                rights = f.read(8)
                if len(rights) == 8:
                    ids.append(rights.hex().upper())
    except (OSError, struct.error):
        return []
    return ids


def identify(game, keys, logs):
    log = logs / 'identify-game.log'
    run([PY, REPO / 'games/totk/scripts/identify_game.py', game, '--keys', keys], log, cwd=REPO)
    report = last_json(log)
    if not report or 'botw' not in [t for t in report.get('titles', []) if t in ('01007EF00011E000', '01007EF00011E800')]:
        found = ticket_title_ids(game)
        say(f'  titles from tickets: {found}')
        if '01007EF00011E000' not in found and '01007EF00011E800' not in found:
            raise BuildError(f'the game file is not Breath of the Wild (see {log})')
    say('1/4 identified: Breath of the Wild')


def step_code(work, game, keys, logs, version):
    expected = VERSIONS[version]
    exefs = work / f'extracted/{version}/exefs'
    want = expected['exefs_sha256']
    have = all((exefs / n).is_file() and sha256(exefs / n) == h for n, h in want.items())
    if not have:
        say(f'1/4 code: extracting the ExeFS ({expected.get("display_version", version)}) from the game file')
        if exefs.exists():
            shutil.rmtree(exefs)
        run([PY, REPO / 'games/botw/scripts/extract_exefs.py', game, '--keys', keys, '--output', exefs],
            logs / f'extract_exefs-{version}.log', cwd=REPO)
    for n, h in want.items():
        if not (exefs / n).is_file():
            raise BuildError(f'ExeFS {n} missing: not Breath of the Wild {expected.get("display_version", version)}')
        check(f'ExeFS {n}', sha256(exefs / n), h)
    say(f'1/4 code: ExeFS verified against {version} pins (original modules; no rewrite on the x64 route)')
    return exefs


def romfs_valid(folder, expected):
    try:
        report = json.loads((folder / 'index.json').read_text())
        return (report.get('status') == 'pass' and report['romfs_sha256'] == expected['romfs']['sha256']
                and (folder / 'romfs.bin').stat().st_size == expected['romfs']['size'])
    except (OSError, ValueError, KeyError):
        return False


def step_data(work, game, keys, logs, version, dlc_files):
    expected = VERSIONS[version]
    hactool = None
    folder = work / f'extracted/{version}/romfs'
    if not romfs_valid(folder, expected):
        hactool = build_hactool(work, logs)
        if folder.exists():
            shutil.rmtree(folder)
        say('2/4 data: merging base + update RomFS and verifying all IVFC levels (15 GB; this takes a while)')
        run([PY, REPO / 'games/botw/scripts/extract_romfs.py', game, '--keys', keys, '--hactool', hactool,
             '--output', folder], logs / 'botw-romfs.log', cwd=REPO)
        report = json.loads((folder / 'index.json').read_text())
        check('RomFS sha256', report['romfs_sha256'], expected['romfs']['sha256'])
        check('RomFS size', report['romfs_size'], expected['romfs']['size'])
    else:
        say('2/4 data: RomFS already extracted and pinned')
    # add-on content: standalone per-title NSPs (from the combined package via split_dlc.py)
    aoc = work / f'extracted/{version}/aoc'
    pins = expected['aoc']
    titles = {pack['title_id']: i for i, pack in pins.items()}
    keep = set()
    for nsp in dlc_files:
        index = next((titles[t] for t in ticket_title_ids(nsp) if t in titles), None)
        if index is None:
            raise BuildError(f'{Path(nsp).name}: none of its titles {ticket_title_ids(nsp)} is an add-on pack of this version')
        pack_dir = aoc / index
        pack_ok = False
        try:
            report = json.loads((pack_dir / 'index.json').read_text())
            pack_ok = (report.get('status') == 'pass' and report['romfs_sha256'] == pins[index]['sha256']
                       and (pack_dir / 'runtime-index.bin').is_file()
                       and (pack_dir / 'romfs.bin').stat().st_size == pins[index]['size'])
        except (OSError, ValueError, KeyError):
            pass
        if pack_ok:
            keep.add(index)
            continue
        say(f'2/4 data: importing the add-on content {Path(nsp).name} (index {index})')
        hactool = hactool or build_hactool(work, logs)
        staging = aoc.with_name('aoc-import')
        shutil.rmtree(staging, ignore_errors=True)
        run([PY, REPO / 'games/botw/scripts/extract_dlc.py', nsp, '--keys', keys, '--output', staging],
            logs / f'botw-dlc-{index}.log', cwd=REPO)
        (pack,) = list(staging.iterdir())
        report = json.loads((pack / 'index.json').read_text())
        check(f'add-on content {index}', report['romfs_sha256'], pins[index]['sha256'])
        if report['romfs_size'] != pins[index]['size']:
            raise BuildError(f'add-on content {index}: size {report["romfs_size"]} != {pins[index]["size"]}')
        shutil.rmtree(pack_dir, ignore_errors=True)
        pack_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pack), str(pack_dir))
        shutil.rmtree(staging, ignore_errors=True)
        keep.add(index)
    missing = [i for i in titles if i not in keep]
    if missing:
        say(f'2/4 data: note: add-on packs not provided: {missing} (the runtime takes the packs it finds)')
    # shared fonts
    fonts = work / 'extracted/firmware/shared-fonts'
    have = (fonts / 'manifest.json').is_file() and all((fonts / f"{f['type']}-{f['name']}.bfttf").is_file() for f in json.loads((fonts / 'manifest.json').read_text())['fonts']) if (fonts / 'manifest.json').is_file() else False
    if not have:
        say('2/4 data: extracting the system shared fonts from the firmware directory')
        if fonts.exists():
            shutil.rmtree(fonts)
        run([PY, REPO / 'games/totk/scripts/extract_shared_fonts.py', '--keys', keys, '--firmware', FIRMWARE,
             '--output', fonts], logs / 'shared_fonts.log', cwd=REPO)
    say('2/4 data: done')


def main():
    global FIRMWARE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('game', type=Path)
    ap.add_argument('-k', '--keys', required=True, type=Path)
    ap.add_argument('--firmware', required=True, type=Path)
    ap.add_argument('--work', type=Path, default=Path(os.environ.get('WNG_BOTW_WORK') or REPO / 'work' / 'BotW_build'))
    ap.add_argument('--skip-split', action='store_true', help='DLC NSPs were split already')
    args = ap.parse_args()
    FIRMWARE = args.firmware
    t0 = time.time()
    work = args.work
    logs = work / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    for tool in (PY, TOOLS / 'ninja.exe', TOOLS / 'cmake-3.31.8-windows-x86_64/bin/cmake.exe'):
        if not Path(tool).is_file():
            raise BuildError(f'tool missing: {tool} — run tools/download_tools.sh first')
    identify(args.game, args.keys, logs)
    # version from the update: the combined package's update ticket decides nothing by itself;
    # extraction picks the BKTR Program NCA and the pins confirm the version.
    version = 'botw190'
    exefs = step_code(work, args.game, args.keys, logs, version)
    containers = work / 'containers'
    if not args.skip_split:
        if containers.exists():
            shutil.rmtree(containers)
        run([PY, REPO / 'scripts/split_dlc.py', args.game, '--keys', args.keys, '--output', containers],
            logs / 'split_dlc.log', cwd=REPO)
    dlc_files = sorted(str(p) for p in containers.glob('*.nsp')) if containers.is_dir() else []
    step_data(work, args.game, args.keys, logs, version, dlc_files)
    (work / 'build-report.json').write_text(json.dumps(
        {'status': 'pass', 'version': version, 'game': str(args.game), 'minutes': round((time.time() - t0) / 60, 1)},
        indent=2) + '\n')
    say(f'done in {(time.time() - t0) / 60:.1f} min — work folder: {work}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        print(f'[build] FAIL: {e}', file=sys.stderr)
        sys.exit(1)
