# 1.9.0 status and known gaps (port-190)

Verified working on this port (2026-10-24, Intel Arc B580 / Vulkan 1.4, Windows 10 x64):

- `make gen` on the 1.9.0 ExeFS: 3 modules, 180k functions, 38 patch sites resolved, 0 lifter errors
  (main/subsdk0; 1 tolerated `stg` in sdk)
- Full boot through `nn::init::Start`, romfs serving, rendering at ~54 fps average (160 Hz display,
  vsync fast), pipeline cache + full shader precompilation (13,997 shaders, 192 MB cache)
- Launch via `play.cmd` (dev mode: repo root = data root)

## Missing NVN entry points (53 of 569; runtime implements 516, 69 as deliberate empty stubs)

Groups — none on the game's normal draw path; treat as "implement when a crash names one":

- Debug/checkpoints: `InsertCheckpoint{Static,Dynamic}`, `SetAutomaticCheckpoints*`,
  `SetCheckpointCallStacksEnable/MaxCallStacksDepth`, `InstallGlobalDebugCallback`,
  `DevtoolsBootstrap`, `BootstrapLoaderInternal`
- Interception family (NVX): `Interception*`
- Memory-pool native/interop handles (NVX): `MemoryPoolBuilder{Get,Set}NativeHandle*`,
  `MemoryPoolBuilder{Get,Set}{BlockLinear,Pitch,Special}Address*`, `DeviceBuilder*ReservedAddressRanges*`
- Deferred binds: `CommandBufferBind{Images,SeparateSamplers,SeparateTextures,StorageBuffers,
  UniformBuffers}Deferred`
- CUDA interop: `CUDAInteropFunction`
- Misc: `CopyTextureToTextureWithCopyEngineNVX`, `OverrideSubtileSize`, `SetControlMemoryCallbackEnabled`,
  `SetProvokingVertexMode`, `SetZCullZF32CompressionEnable`

## Other known gaps

- Lifter: one `stg x8, [x8]` at sdk+0x640050 (0.0001% of instructions); generation completed —
  verify nothing executed it (watch for a `stg` fault in the log)
- Shader precompile: 24/13,997 failed (0.17%) — first candidates if a specific effect misbehaves
- DLC (add-on content) not supported upstream; our dump contains it, extraction pipeline handles it,
  runtime does not mount it
- MSYS2 runtime DLLs currently needed at launch (`play.cmd` sets the PATH); `make deps-windows`
  + `make dist` produce a self-contained zip that runs without MSYS2

## Upstream sync policy

Branch `port-190` tracks upstream `test` (the active line; CONTRIBUTING directs PRs there).
Our additions are confined to `extraction/`, `docs/PORT-190.md`, this file, and `play.cmd`,
so upstream merges should stay clean. Anything generally useful (the romfs unpacker, build notes)
belongs upstream as a PR, not a local patch.
