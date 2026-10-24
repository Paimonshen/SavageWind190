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

- **B1** version pins: `sw_probe` → `tools/layout.py` build ids. *(done)*
- **B2** patches re-derivation: Ghidra headless `botw_1900` project, relocate the 44 addresses, port `hle_symbols.txt`.
- **B3** `make gen` on 1.9.0 exefs → `swgame.dll` builds and loads.
- **B4** Windows runtime: setup (MSYS2 via `tools/setup_windows.ps1`), romfs tree, first boot.

## Rules (unchanged from both parent projects)

BYO dump. No game files, keys or dumps in git. `D:\games` read-only.
