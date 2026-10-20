# FactoryTwinUE — 60–90s demo capture checklist

Status: **8 ACTUAL UE D3D11 STILL IMAGES CAPTURED**, 60–90s video **NOT RECORDED**. Kit GUI footage **NOT RUN**.

1. Start the NVIDIA Kit application and verify that the `com.factory.twin` Extension is actually enabled; show its USD scene and prim ID. This section is owned and evidenced by Worker A.
2. Use Worker B's *real* AGV=1 and AGV=2 seed-42 raw outputs and comparison CSV; do not substitute fictional KPI numbers.
3. Open `FactoryTwinUE/FactoryTwin.uproject` with UE5.8. Start Play in the default map, which uses `AFactoryTwinGameMode` to spawn `AUsdStageActor`. Ensure the HUD reports five stage bindings and no `ERROR`.
4. Press `1`, `2` to switch between the raw event files and `SPACE` to pause/resume, `R` to reset. Real 1280×720 D3D11 viewport captures at virtual 2s/25s/220s/270s now confirm M01 Idle/Busy/Down/Busy. Actual USD generated component scale measured: INBOUND box **200×200×100cm** for USD 2×2×1m, and M01 box **200×200×200cm** for USD 2×2×2m. See `Docs/unreal_d3d11_final_agv{1,2}_20261020.log`.
5. Eight screenshots were saved and checked on disk in `Docs/UnrealCaptures/`: `FactoryTwin_agv1_{idle,busy,down,repaired}.png` and `FactoryTwin_agv2_{idle,busy,down,repaired}.png`. The colored upper-right HUD and world labels are readable. The USD AGV meshes physically follow the event waypoints; in AGV=1 the original USD AGV02 stage geometry remains on disk but is hidden in-game. **60–90 second final video is NOT RECORDED**, and Kit application button activation/recording is NOT RUN.

Actual capture commands, launched sequentially from the FactoryTwinUE project directory:

```powershell
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQA '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_d3d11_final_agv2_20261020.log'
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQAAgvOne '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_d3d11_final_agv1_20261020.log'
```

Both actual D3D11 runs print `FACTORYTWIN_VISUAL_QA_PASS` only after all four screenshots exist. The screenshot intervals use deterministic virtual replay stepping for QA; they are not a 60–90s recording. `Docs/unreal_negative_final_20261020.log` separately verifies six invalid manifest/event cases are rejected in an actual UE runtime (headless parser smoke).

CLI for non-visual smoke (does **not** satisfy GUI footage requirements):

```powershell
& 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Binaries\Win64\FactoryTwin.exe' -nullrhi -nosound -unattended -FactoryTwinSmoke -log
```

The smoke prints `FACTORYTWIN_SMOKE_PASS` only after the USD Stage generated-components bind all five manifest IDs and the real JSONL cursor reaches its end. Any failure should print `FACTORYTWIN_SMOKE_FAIL` and the reason.

2026-10-20 runtime note: Direct uncooked `FactoryTwin.exe -nullrhi` terminated during asset-registry startup (`FBufferReaderBase::Serialize` assertion), before the smoke's startup marker. See `Docs/unreal_smoke_agv2_seed42.log`. This run is **FAIL**, not a completed USD/replay integration test. Use the Unreal Editor play path or cook the standalone project before reattempting runtime validation.

### Additional USD visual prefab swap evidence

Real D3D11 still frames were also recorded for a swappable `/Geometry` Xform+`/Visual` referenced USD model, including a preview **M01 Sphere** replacing the canonical **M01 Cube** without recompiling the C++ project between stage selections. The reference-scene baseline D3D stills are `Docs/UnrealCaptures/FactoryTwin_refcanonical_agv{1,2}_{idle,busy,down,repaired}.png` and alternate D3D stills are `Docs/UnrealCaptures/FactoryTwin_alternate_agv{1,2}_{idle,busy,down,repaired}.png`. Both captured four valid states per 1/2-AGV scenario with the same real replay JSONL. The M01 sphere measures 200×190.2×200cm after USD import vs reference cube 200×200×200cm. 1-AGV alternate verifies AGV02 source geometry and indicator are invisible; the AGV01 mesh moves with the replay route.

Actual run logs: `Docs/unreal_swap_canonical_agv{1,2}_20261020.log`, `Docs/unreal_swap_alternate_agv2_quoted_20261020.log`, `Docs/unreal_swap_alternate_agv1_20261020.log`. Detailed model replacement, PowerShell argument quoting and A's isolated preview workflow are documented at `Docs/model_swap_unreal.md`. Kit GUI proof and a single 60–90-second video remain **NOT RUN / NOT RECORDED**.
