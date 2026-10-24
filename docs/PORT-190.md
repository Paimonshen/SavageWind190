# Porting Savage Wind to BotW 1.9.0 (route B)

Upstream SavageWindRecomp pins **1.8.2** everywhere. Our dump is **1.9.0**
(base + 1.8.2→1.9.0 update + DLC, pin-verified in the WinNativeGames P1 pipeline).
This branch (`port-190`, based on upstream `test`) moves every pin to 1.9.0.

## What is version-locked

| File | Lock | 1.9.0 status |
|---|---|---|
| `tools/layout.py` | module base addresses + NSO build ids | addresses from our loader measurements; ids from `sw_probe` on our exefs |
| `tools/gen.py:681` | strict build-id equality vs layout.py | comes free with layout.py |
| `tools/patches.py` | ~44 hardcoded 1.8.2 addresses | **re-derive** (Ghidra headless on 1.9.0, see `tools/ghidra/README.md`) |
| `runtime/hle/hle_symbols.txt` | symbol→address map for 1.8.2 | **re-derive** (same Ghidra project) |
| `tools/ghidra/` analysis scripts | may embed addresses | audit during B2 |

## Game data front-door (extraction/)

`extraction/` is the WinNativeGames P1 pipeline, self-contained:

- `extraction/build_app_win.py <botw.nsp> -k <prod.keys> --firmware <NCA dir>`
  → pinned hactool fetch+build, ExeFS extraction + SHA-256 pin check,
  RomFS BKTR merge (base+update), DLC split+import, font extraction.
  Outputs `work/extracted/botw190/{exefs,romfs,aoc,fonts}`.
- Toolchain: shared at `../../tools` (override `WNG_TOOLS`); work dir override `WNG_BOTW_WORK`.
- Expects the same `expected-v1.9.0.json` pins as WinNativeGames (kept in `extraction/games/botw/assets/`).

For `make gen` the repo-root `extracted/exefs` can be a junction to the
already-verified `WinNativeGames/work/BotW_build/extracted/botw190/exefs`
(the runtime launcher refuses symlinked `extracted/`, but gen only reads it).
At **run time** (B4) the launcher needs a real `extracted/` in the data root,
and romfs as a **directory tree** (`runtime/romfs_build.c` packs it itself;
our pipeline currently emits `romfs.bin` — a tree extractor is a B4 task).

## Milestones

- **B1** version pins — **turned out to be a non-issue**: the `test` branch already
  supports 1.9.0 (`tools/game_sites.py` `Version('1.9.0', 'cd57b23fa4bbad65', True)`,
  our main module's build id exactly; `layout.py` is fully dynamic; `patches.py` takes
  per-version sites from `game_sites.py`; `hle_symbols.txt` is a name list resolved
  through each NSO's dynsym at gen time). The "1.8.2 only" wording is the stale
  main-branch README. `sw_probe` on our exefs: version 1.9.0, all three modules load,
  0 unsupported instructions in main/subsdk0, 1 in sdk (`stg` at 0x7002b44050).
- **B2/B3** (patches/symbols re-derivation) — not needed, see B1.
- **B4** Windows build & run: `make gen` on our exefs → `swgame.dll`; MSYS2 toolchain
  via `tools/setup_windows.ps1`; romfs as a directory tree for the runtime setup;
  first boot. Known 1.9.0 gaps from sw_probe: 53 NVN entry points the runtime does
  not implement yet (516/569), 1 lifter gap (`stg`).

## Rules (unchanged from both parent projects)

BYO dump. No game files, keys or dumps in git. `D:\games` read-only.
