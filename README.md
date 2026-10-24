# Savage Wind Recomp — SavageWind190（旷野之息 1.9.0 Windows 移植）

> **本仓库（`port-190` 分支）= 上游 [SavageWindRecomp](https://github.com/Revivedx/SavageWindRecomp) `test` 分支 + 1.9.0 移植验证与数据前置管线。**
> 上游 test 分支已原生支持 BOTW 1.9.0（`tools/game_sites.py` 登记 build id `cd57b23fa4bbad65`，与 1.9.0 更新包完全一致）；
> 本仓库补上了从**你自己的 `botw.nsp`** 到可玩状态的完整工具链，并在 Windows x64 + Vulkan（Intel Arc B580）上完成了实机验证。

## 功能状态（本机实测，2026-10-24）

| 已验证可用 | 说明 |
|---|---|
| 完整启动 | `nn::init::Start` 起全链路，标题流程正常进入 |
| 渲染 | Vulkan 1.4（管线缓存 + 13,997 着色器全量预编译，192MB 缓存） |
| 帧率 | 平均 ~54fps（160Hz 显示器，目标 60），异步着色器编译开启 |
| 音频 / 存档 / 输入 | 上游 Alpha 2 状态：开局+初始台地可玩（更远进度未验证，见 [docs/GAPS-1.9.0.md](docs/GAPS-1.9.0.md)） |
| 数据链 | botw.nsp →（pinned hactool）→ exefs/romfs/字体，SHA-256 全程校验 |

## 运行指南

### 路径 A：从本仓库源码运行（开发者/本机，推荐）

前置：Windows 10+ x64、AVX2 CPU、Vulkan 1.3 显卡、约 35GB 空闲磁盘、自己的 `botw.nsp`（本体+1.9.0 更新+DLC 合一包）、`prod.keys`、固件 NCA 目录。

```bat
:: 1. 一次性环境（装 MSYS2 全套工具链 + Python 3.12 + venv，可重跑）
powershell -ExecutionPolicy Bypass -File tools\setup_windows.ps1

:: 2. 数据提取（约 30-60 分钟；工具链默认取 ..\..\tools，可用 WNG_TOOLS 覆盖）
python extraction\build_app_win.py <botw.nsp 路径> -k <prod.keys 路径> --firmware <固件NCA目录>
::    产物: <work>\extracted\botw190\{exefs, romfs\romfs.bin, fonts}

:: 3. 布置 extracted/（exefs 拷贝 + romfs 解包成目录树 + 字体改名）
xcopy /E /I <work>\extracted\botw190\exefs extracted\exefs
python extraction\romfs_unpack.py <work>\extracted\botw190\romfs\romfs.bin extracted\romfs
copy <work>\extracted\botw190\fonts\0-standard.bfttf fonts\nintendo_udsg-r_std_003.bfttf
copy <work>\extracted\botw190\fonts\5-nintendo-extension.bfttf fonts\nintendo_ext_003.bfttf

:: 4. 构建（MSYS2 UCRT64 shell 或先把 C:\msys64\ucrt64\bin 放进 PATH）
make gen        :: 从 extracted\exefs 重编译游戏代码（617MB C，几分钟）
make -j         :: savagewind.exe + swgame.dll（约 10-20 分钟）
copy build\swgame.dll build\swgame.dll.id extracted\

:: 5. 打包数据镜像（15GB，约 10 分钟）——没有它启动器会一直要求"设置游戏文件"
build\savagewind.exe --build-romfs

:: 6. 以后每次启动：双击
play.cmd
```

常见坑（都踩过，详见 [docs/PORT-190.md](docs/PORT-190.md)）：
- **必须从仓库根目录启动**（`play.cmd` 已处理好）：工作目录里有 `extracted\` 才会跳过启动器直接进游戏；
- 启动器的"选择游戏文件"**不能选它自己数据根里面的文件夹**（防自删保护），本仓库布局下请直接用 `play.cmd`；
- `extracted\romfs.bin` 是"游戏就绪"判定的必要件，别跳过第 5 步。

### 路径 B：发行包运行（普通玩家）

下载 [Releases](https://github.com/Paimonshen/SavageWind190/releases) 里的 `SavageWind-*-windows.zip`，解压到可写文件夹（不要 Program Files），运行 `savagewind.exe`，首次按提示选择**你自己提取好的** `exefs/`+`romfs/` 所在文件夹（版本 1.9.0），它会校验、复制并在这台机器上重编译游戏代码（约 40 分钟，一次性）。之后双击即玩。**发行包不含任何游戏内容。**

### 性能建议

首次进入新区域会有一过性卡顿（资源流送+新着色器）；设置里 `async_shaders` 打开后新管线后台编译。可随时在游戏目录跑 `build\savagewind.exe --precompile-shaders` 全量预热（约 3 分钟）。游戏内暂停菜单 > 系统 > 选项里有语言、帧率、滤镜等全部 PC 选项（F1/Esc 呼出）。

## 本仓库相对上游的改动

- `extraction/`：P1 数据管线（pinned hactool 自动拉取构建、ExeFS/RomFS/DLC 提取与 SHA-256 pin、`romfs_unpack.py` 镜像→目录树）
- `docs/PORT-190.md`：1.8.2→1.9.0 移植全过程与结论（上游 test 已支持 1.9.0 的证据链）
- `docs/GAPS-1.9.0.md`：1.9.0 已知缺口清单（53 个 NVN 入口分类、lifter 边界、上游同步策略）
- `play.cmd`：dev 模式一键启动；`tools/retry_upload.sh`、`tools/make_release.sh`：发布工具链
- 其余与上游 `test` 完全一致（干净跟随，方便随时合并上游）

---

**以下为上游 README 原文（Alpha 2 发行版的权威使用说明）：**

# Savage Wind Recomp (upstream)

> [!IMPORTANT]
> **This project is made almost entirely with AI.** Nearly all of the code, tooling, reverse engineering and
> documentation here is written by an AI (Anthropic's Claude, through Claude Code), directed, tested and reviewed by
> a human. It builds on [LAS Recomp](https://github.com/peiikai/LASRecomp), which was made the same way. If you don't
> trust code written by AI, you can simply ignore this project. As with anything on the internet, you run the code at
> your own discretion.

**Savage Wind Recomp** is a work-in-progress static recompilation of *The Legend of Zelda: Breath of the Wild*
(Nintendo Switch, version 1.9.0) into a native application for Windows and Linux. The goal is a full PC
version of your own copy of the game: a launcher, PC-style graphics options, mods, any controller, keyboard and
mouse, and its text and voices in any of its languages.

> [!WARNING]
> **Playable, but how far is unknown.** Savage Wind plays the opening in the Shrine of Resurrection and the Great
> Plateau around it at 60 fps, with sound, voices, the HUD, saving and loading. Nobody has played past the Great
> Plateau on Savage Wind yet, so expect bugs or crashes further on. This is an alpha, a preview for testers. If you
> find a bug, please [report it on GitHub](https://github.com/Revivedx/SavageWindRecomp/issues/new/choose): every
> report shows how far the game really works.

> [!TIP]
> **Want to contribute? Look at the [`test`](https://github.com/Revivedx/SavageWindRecomp/tree/test) branch first.**
> It has every change that is implemented and being tested, ahead of the latest release, so you don't start on
> something that's already done or in progress. Base your work on `test` and open pull requests against it: `main`
> only moves for a release. See [CONTRIBUTING.md](CONTRIBUTING.md).

> [!NOTE]
> **No game files are included.** Savage Wind Recomp needs your own legally obtained copy of the game, updated to
> **version 1.9.0**, dumped from **your own** Nintendo Switch. This project does not include, and will not
> provide, game files, keys, firmware, dumping or decryption tools, or instructions on how to obtain any of them.
> Savage Wind never decrypts anything: it only reads files you have already extracted yourself. The recompilation of
> the game code happens locally, on your machine, from your files.

## Getting started (Alpha 2, Windows)

1. Download `SavageWind-0.2.0-alpha.2-windows.zip` from [Releases](https://github.com/Revivedx/SavageWindRecomp/releases)
   and extract it to a folder you can write to (not Program Files): your game files, saves and settings are kept in
   that folder.
2. Run `savagewind.exe`. The first time it asks for your game files: pick the folder with your own extracted game
   (`exefs/` and `romfs/`, version 1.9.0, see below) and choose **Set up game files**. It checks the
   version, copies the files, builds the data image and recompiles the game code on your machine - once, and it takes
   a while (about 40 minutes with a 12-thread CPU). Your own files aren't changed. When it's done the game starts.
3. From then on `savagewind.exe` goes straight into the game. The settings, including the text and voice languages,
   are in the game's Options (pause menu > System > Options, or Options on the title screen).
4. **Savage Wind Configuration** (`Savage Wind Configuration.exe`, in the same folder) opens the configuration
   screen: Play, Settings, your game files (set them up again, rebuild the game code, delete them) and Quit. In
   game, Quit to Start Screen also comes back to it. (Built from source on Linux or macOS: `--config`, the
   AppImage's **Savage Wind Configuration** desktop action, or Option held while opening the Mac app.)

The setup and configuration screens show Savage Wind's own art. To see a picture of your own there instead, put it
next to `savagewind.exe` as `splash.jpg` or `splash.png`; it's only read from your folder and never part of
Savage Wind.

Needs Windows 10 or later, a CPU with AVX2, a GPU with Vulkan 1.3 and about 35 GB of free disk space.

## What you need

- Your own *Breath of the Wild* (cartridge or digital) and its **1.9.0 update**, the latest, extracted from your own
  console:
  - the **ExeFS** of that version (`main`, `main.npdm`, `rtld`, `sdk`, `subsdk0`)
  - the **RomFS** with that update applied (base game and update merged)
- DLC: not supported yet (planned, see the roadmap); the title screen's Downloadable Content entry is hidden until then.
- Windows 10 or later (x86-64, a CPU with AVX2) or Linux (x86-64), and a GPU with Vulkan 1.3.

The files go in `extracted/` next to the program (git ignores this folder):

```
extracted/
  exefs/   main, main.npdm, rtld, sdk, subsdk0
  romfs/   the complete RomFS (base game + the 1.9.0 update merged)
```

The `main` module's build id tells the exact version; `python tools/sw_probe.py` (it reads `extracted/exefs`)
prints it and what the recompiler will find there.

## Status

Estimates of where each part stands. "Tested in game" is how much of the game has been played through on Savage Wind so far.

| | Part | Progress | What it means |
|---|---|---|---|
| ✅ | **Recompiler** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | The whole game (main, sdk and multimedia modules) recompiles to native code |
| ✅ | **Game files setup** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Version check, copy, data image and code build, all from your own files |
| ✅ | **Text and voice languages** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Any of the game's 15 text languages (16 with 1.9.0's Thai) with any of its 8 voice languages |
| ✅ | **Voices in another language: crash fix** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Fixed ([#2](https://github.com/Revivedx/SavageWindRecomp/issues/2)): the game now sets aside enough memory for voice banks bigger than its own, so any voice language works with any text language |
| ✅ | **Menus in 12 languages** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Savage Wind's own screens follow the text language |
| ✅ | **Sound and voices** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Mixed by the game SDK's own audio renderer, with room reverb |
| ✅ | **Keyboard and mouse** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Every key and mouse button remappable, mouse camera |
| ✅ | **Settings in the game's Options** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Video, audio, controls and language pages drawn by the game itself |
| ✅ | **Direct start + Configuration** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | savagewind.exe goes straight into the game; Savage Wind Configuration has the rest |
| ✅ | **Window sizes and fullscreen** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | The sizes your display can show; windowed, borderless or exclusive |
| ✅ | **Internal resolution and FSR 1** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Native resolution up to 4K, or AMD FSR 1 quality modes |
| ✅ | **Anisotropic filtering and sharpening** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Ground and paths sharp at a distance (2x to 16x); AMD CAS sharpening of the 3D image, useful with FSR 1 |
| ✅ | **Higher-resolution shadows** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Sun shadows at the console's 896x896, or sharper at 2048, 4096 or 8192 (Video > Shadow resolution) |
| ✅ | **Shader and pipeline cache** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Places you've already seen don't stutter again |
| ✅ | **Full shader precompilation** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Optional and on by default, at setup or later in Savage Wind Configuration: all of the game's ~14,000 shaders are translated and compiled ahead of time, so new places and effects don't stutter the first time |
| ✅ | **Faster game code build** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | The one-time setup takes about 15 minutes instead of about 40 (12 threads) from the next release: the game code builds in about 6 minutes instead of 30 ([#43](https://github.com/Revivedx/SavageWindRecomp/pull/43), by [@adriadam10](https://github.com/adriadam10)) |
| ✅ | **Frame rate** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | 60 fps by default, or 30, 90, 120 or no limit, with the game at the same speed; menus, cutscenes and conversations at 30, as on the console |
| ✅ | **Steady 60 fps in the open world** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | Holds 60 fps in real play on the Great Plateau (RTX 3060, Ryzen 5 5600X); steady 120 fps (8 ms frames) is the next goal |
| ✅ | **Game version 1.9.0** | ![100%](https://progress-bar.xyz/100/?width=150&style=square&progress_color=5cb85c) | The latest version and the supported one (its Thai text isn't offered yet). 1.8.2 still sets up and runs, but isn't supported: a bug is only fixed if it also happens on 1.9.0 |
| 🔧 | **Horizon OS services** | ![90%](https://progress-bar.xyz/90/?width=150&style=square&progress_color=5cb85c) | Threads, files, controllers, applets and time: all the opening and the Great Plateau use |
| 🔧 | **Maxwell shader translator** | ![90%](https://progress-bar.xyz/90/?width=150&style=square&progress_color=5cb85c) | Every shader seen so far translates to Vulkan |
| 🔧 | **Graphics (NVN on Vulkan)** | ![80%](https://progress-bar.xyz/80/?width=150&style=square&progress_color=5cb85c) | Shrine and Great Plateau look right, shadows included; far parts of the map can still be missing ([#20](https://github.com/Revivedx/SavageWindRecomp/issues/20)) |
| 🔧 | **Controllers** | ![70%](https://progress-bar.xyz/70/?width=150&style=square&progress_color=5cb85c) | Any controller SDL knows, by button position; automatic recognition is next, then camera speed set apart for each axis |
| 🔧 | **Motion controls (gyro)** | ![80%](https://progress-bar.xyz/80/?width=150&style=square&progress_color=5cb85c) | The controller's gyroscope and accelerometer (DualSense, DualShock 4, Switch controllers, Steam Deck) for motion aiming and the tilt shrines; without one, hold T and move the mouse to tilt. Sensitivity and inversion in Options > Controls. Not yet tried with a real controller or in a shrine |
| 🔧 | **Button icons for your device** | ![80%](https://progress-bar.xyz/80/?width=150&style=square&progress_color=5cb85c) | The game's button prompts show your bound keys and mouse buttons, or Xbox / PlayStation / Nintendo buttons, switching with the device you use |
| 🔧 | **Variable refresh rate (VRR)** | ![80%](https://progress-bar.xyz/80/?width=150&style=square&progress_color=5cb85c) | Video > VSync: On lets G-SYNC and FreeSync displays show every frame as soon as it's ready, a little under the refresh rate; Fast (the default), Adaptive and Off too. Still to be tried on a VRR display |
| 🔧 | **Tested in game** | ![10%](https://progress-bar.xyz/10/?width=150&style=square&progress_color=d9534f) | The Shrine of Resurrection and the Great Plateau; the rest of Hyrule is untested: [report what breaks](https://github.com/Revivedx/SavageWindRecomp/issues/new/choose) |
| 🗺️ | **Linux** | ![30%](https://progress-bar.xyz/30/?width=150&style=square&progress_color=f0ad4e) | Builds and runs on x86-64 (from LAS Recomp); not yet tested with this game |
| 🗺️ | **AMD FSR 3 + frame generation** | ![5%](https://progress-bar.xyz/5/?width=150&style=square&progress_color=d9534f) | Planned: motion vectors from depth and the camera, FidelityFX SDK |
| 🗺️ | **NVIDIA DLSS (RTX)** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned, after FSR 3; under NVIDIA's own SDK license |
| 🗺️ | **Colour grading and HDR** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: exposure, contrast and saturation settings, colour presets, fog and bloom on or off, and real HDR output on HDR displays |
| 🗺️ | **Ultrawide (21:9)** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: a wider field of view instead of the 16:9 image with bars |
| 🗺️ | **Field of view** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: a wider or narrower view in play, while cutscenes keep their framing |
| 🗺️ | **Draw distance and detail** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: trees, grass and objects drawn farther away on strong PCs, or nearer for more fps, and a fixed level of detail (the most detailed models at any distance) |
| 🗺️ | **Free camera and photo mode** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: a free camera with the HUD hidden and its own speed and sensitivity, for screenshots, and camera paths through keyframes for videos |
| 🗺️ | **Effects on or off** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: a Video page that turns each of the game's own effects on or off, where BOTW has them: ambient occlusion, volumetric fog, grass (3 layers), character light (normal and custom), tone mapper, fragment and main lighting, bloom (3 layers), lens flare, cel shading, fog effects, water, torch fire, the sword sheath, depth of field (also when aiming the bow), screen-space reflections, global illumination and far lights |
| 🗺️ | **Graphics extras** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Later: ambient occlusion, volumetric fog and depth of field |
| 🗺️ | **Built-in benchmark** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: fixed camera routes that measure fps and frame times and save the results, to compare settings |
| 🗺️ | **GPU readings on AMD and Intel (Windows)** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: the performance overlay's GPU use and VRAM for any GPU on Windows ([#58](https://github.com/Revivedx/SavageWindRecomp/issues/58)); today only NVIDIA, and AMD on Linux |
| 🗺️ | **Mods** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned |
| 🗺️ | **Accessibility and assists** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: text size, colour-blind filters and toggles in place of held buttons; enemy and Link health, damage dealt and taken, weapon durability and stamina use on screen; optional assists: infinite stamina, health or weapon durability, arrows and rupees, no damage at all, no fall damage, health that refills over time, nearby enemies defeated at once, and multipliers for weapon durability, stamina use, damage dealt and taken, and walking, running, climbing, swimming and gliding speed |
| 🗺️ | **Teleport with bookmarks** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned: save places and travel back to them |
| 🗺️ | **DLC** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Later |
| 🗺️ | **amiibo rewards without figures** | ![0%](https://progress-bar.xyz/0/?width=150&style=square&progress_color=d9534f) | Planned |

✅ done · 🔧 in progress · 🗺️ roadmap

## Controls

Any controller SDL knows works, by button position; one with a gyroscope (DualSense, DualShock 4, Switch controllers,
Steam Deck) also aims and tilts by motion. Keyboard and mouse defaults:

| Action | Key | Action | Key |
|---|---|---|---|
| Move | W A S D | Camera | Mouse (or I J K L) |
| Walk (hold) | C | Crouch | Left Ctrl |
| Jump (X) | Space | Sprint / back (B) | Left Shift |
| Interact / confirm (A) | E | Attack (Y) | Left click |
| Shield / lock on (ZL) | Right click | Bow (ZR) | F |
| Rune (L) | Q | Throw (R) | R |
| Look (right stick press) | Middle click | D-pad | Arrow keys |
| Inventory (Plus) | Tab | Map (Minus) | M |
| Tilt the controller (hold, motion puzzles) | T + mouse | | |

Every key and mouse button can be remapped in the game's Options (the Keyboard pages), next to the mouse sensitivity
and Y inversion, motion sensitivity and inversion and the tilt key (Controls). The game's button prompts show the
keys you bound, or your controller's own buttons (Controls > Button icons: Automatic follows the device you use).
Esc frees the cursor, a click in the window takes it back. F10 cycles the performance
overlay (off, FPS, full).

## Building from source

### Windows

More detail in [docs/BUILD-windows.md](docs/BUILD-windows.md).

1. One-time setup, in PowerShell from the repository root:
   `powershell -ExecutionPolicy Bypass -File tools\setup_windows.ps1`.
   It installs MSYS2 (UCRT64: clang, make, SDL3, FFmpeg, Vulkan, shaderc) and Python for the tools, and switches
   the clone to LF line endings.
2. From an MSYS2 UCRT64 shell (or Git Bash with `export PATH="/c/msys64/ucrt64/bin:/c/msys64/usr/bin:$PATH"`):
   - `make -j` builds the app, `build/savagewind.exe`.
   - Put your files in `extracted/` (above), then `make gen` (recompiles the game code into `generated/`, about a
     minute) and `make -j` again (builds it into `build/swgame.dll`; the first build takes 15-20 minutes).
   - `build/savagewind.exe extracted --build-romfs` packs your RomFS into the image the runtime reads
     (`extracted/romfs.bin`, about 15 GB).
3. Run: `build/savagewind.exe extracted --play`, from a shell with `C:\msys64\ucrt64\bin` on PATH.

### Linux

See [docs/linux.md](docs/linux.md): the same steps with the distribution's clang, SDL 3, FFmpeg, shaderc and Vulkan
Memory Allocator (`build/savagewind`, `build/swgame.so`).

Developer notes (in Spanish) - what was changed from LAS Recomp, how the boot got this far, and the debugging
switches - are in [docs/SAVAGE-WIND.md](docs/SAVAGE-WIND.md).

## Respect copyright

- *The Legend of Zelda: Breath of the Wild* is © Nintendo. This is a fan project. It is not affiliated with,
  endorsed by or sponsored by Nintendo. *Nintendo Switch* and *The Legend of Zelda* are trademarks of Nintendo.
- This repository contains no game files, no game code (also not the C code the recompiler generates from it), no
  assets, no fonts, no keys - and release builds won't either.
- The game code you generate and the build made from it contain Nintendo's code. They are for your own use only:
  don't share them, upload them or ship them.
- Issues, pull requests or discussions that contain game files, keys, generated code or links to pirated copies
  will be removed. Piracy is not supported in any way.
- Follow the copyright laws of your country. Dumping a game you own for personal use is legal in some countries and
  not in others; that is your responsibility.

## Credits

- **[LAS Recomp](https://github.com/peiikai/LASRecomp)** by peiikai - the recompiler, the runtime and most of what
  this project is built on (MIT).
- [Ryujinx](https://github.com/Ryujinx/Ryujinx) (MIT) - its shader decoder was the reference for instruction field
  layouts.
- [envytools](https://github.com/envytools/envytools) - NVIDIA GPU documentation used for the shader translator.
- The Switch homebrew community's documentation ([Switchbrew](https://switchbrew.org)).
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra) and the
  [Switch Loader](https://github.com/Adubbz/Ghidra-Switch-Loader) - used for reverse engineering (not bundled).
- Libraries: [SDL 3](https://libsdl.org) (zlib), [FFmpeg](https://ffmpeg.org) (LGPL),
  [Dear ImGui](https://github.com/ocornut/imgui) (MIT),
  [Vulkan Memory Allocator](https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator) (MIT),
  [SMAA](https://github.com/iryoku/smaa) (MIT), [AMD FidelityFX Super Resolution 1](https://github.com/GPUOpen-Effects/FidelityFX-FSR)
  (MIT), [AMD FidelityFX CAS](https://github.com/GPUOpen-Effects/FidelityFX-CAS) (MIT),
  [Fira Sans](https://github.com/mozilla/Fira) (SIL OFL 1.1), [Noto Sans Thai](https://github.com/notofonts/thai)
  (SIL OFL 1.1), [stb_image / stb_image_write](https://github.com/nothings/stb)
  (public domain / MIT), [shaderc](https://github.com/google/shaderc)
  (Apache 2.0), [Zig](https://ziglang.org) (MIT), [Capstone](https://www.capstone-engine.org) (BSD),
  [Unicorn](https://www.unicorn-engine.org) (GPL 2.0), [python-lz4](https://github.com/python-lz4/python-lz4) (BSD).

## License

Savage Wind Recomp's own code is open source under the [MIT License](LICENSE), as is LAS Recomp's, on which it
builds. Third-party components in `third_party/` keep their own licenses. The license covers this project's code
only: it grants nothing for Nintendo's game, which you must supply yourself.

The Windows release zip also bundles, unchanged unless noted, under their own licenses:

- FFmpeg 9.0.2 (libavcodec, libavformat, libavutil, libswscale), LGPL 2.1 or later: built from the official
  [source](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz) as LGPL only, without GPL or nonfree parts, by
  [tools/build_deps_windows.sh](tools/build_deps_windows.sh). They are separate DLLs: you can replace them with your
  own build of the same version.
- From [MSYS2](https://packages.msys2.org) (UCRT64, sources there): SDL 3.4.18 (zlib), shaderc 2026.4 (Apache 2.0),
  libiconv 1.19 (LGPL 2.1 or later), the GCC 16.2 runtime (libgcc, libstdc++: GPL 3 with the GCC Runtime Library
  Exception) and winpthreads (MIT and BSD).
- Zig 0.17.0 (MIT; its bundled LLVM, Clang and LLD: Apache 2.0 with LLVM Exceptions; the MinGW-w64 headers and
  runtime: their own permissive licenses), trimmed to what the game code build uses.
- `swgen/`, this project's generator frozen with PyInstaller 6.22 (GPL 2.0 with the bootloader exception): Python
  3.14 (PSF License), Capstone 5.0.9 (BSD), [Unicorn 2.1.4](https://github.com/unicorn-engine/unicorn/tree/2.1.4)
  (GPL 2.0, source at that link) and python-lz4 4.4.5 (BSD).
- The Fira Sans font, Medium and SemiBold (SIL OFL 1.1, `FiraSans-OFL.txt`), and the Noto Sans Thai font, Medium,
  for the menus in Thai (SIL OFL 1.1, `NotoSansThai-OFL.txt`).
