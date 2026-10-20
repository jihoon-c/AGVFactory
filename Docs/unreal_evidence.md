# Worker C — Unreal 5.8 USD / replay verification

Date: 2026-10-20 (KST)

## Scope and integration inputs

- UE project: `FactoryTwinUE/FactoryTwin.uproject` (separate from the existing `OpenUSD_OmniverseKit.uproject`).
- Shared stage: `FactoryTwinUE/usd/factory_scene.usda` with `layout.usda`, Z-up, metersPerUnit=1.
- Manifest: `FactoryTwinUE/data/equipment_manifest.json`, with M01, M02, QC01, AGV01 and AGV02.
- Worker B's raw JSONL is now integrated at `FactoryTwinUE/Reports/run_agv_{1,2}_seed42.jsonl`, alongside the scenario runner and tests. The loader checks project-local `Reports/` first; its older shared-directory fallback remains available for compatibility.

## Behavior implemented

- `AUsdStageActor` loads the real USD file through the UE `USDImporter` plugin. Binding checks the USD prim's actual `twin:equipmentId` attribute against the manifest and resolves its authored meter-space translation. When UE collapses the generated component under `/World`, the overlay falls back to that validated prim transform rather than misidentifying `/World` as an individual equipment Actor. Disable prim-kind collapsing when staging. A separate color text/light overlay labels each bound prim without claiming automatic import of `twin:equipmentId` into actor metadata.
- `UFactoryEquipmentRegistrySubsystem` checks schema version, exact root, five expected IDs, duplicate ID/path, empty/invalid records and exact per-ID kind (M01/M02 machine, QC01 inspection, AGVs agv) before registering weak UE actor/component mappings.
- `UFactoryEventReplayComponent` reads actual JSONL lines, rejects malformed fields, invalid timestamps, unknown IDs, duplicate/gapped/out-of-order event IDs, unsupported states and waypoints. `job_arrived` / `job_completed` stay informational; only Python `state_changed` drives machine/AGV visuals. Actual generated USD AGV geometry is Movable, follows Python waypoint events, and stays aligned with the UE overlay. AGV=1 playback hides AGV02's indicator and USD-generated geometry without changing the authored USD asset.
- `AFactoryTwinDirector` starts from `AFactoryTwinGameMode`; SPACE play/pause, R reset, 1/2 select AGV scenario. HUD displays status, event cursor, virtual time and all five devices' colored state indicators. Text labels now face the camera. `-FactoryTwinSmoke` speeds up replay, `-FactoryTwinVisualQA` / `-FactoryTwinVisualQAAgvOne` capture actual D3D screenshots, and `-FactoryTwinNegativeQA` tests six invalid inputs against real UE parsers.

## Build environment and commands

- UE source/install: `F:\UE_5.8`; Windows Win64; Visual Studio MSVC 14.44.35207; Windows SDK 10.0.22621.0.
- Editor build command:

  ```powershell
  & 'F:\UE_5.8\Engine\Build\BatchFiles\Build.bat' FactoryTwinEditor Win64 Development '-Project=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -WaitMutex -NoHotReload -NoHotReloadFromIDE
  ```

  Result: **PASS**, `Result: Succeeded`, 2026-10-20. Final incremental Editor build after AGV mobility/static reset fix: 4 actions, 6.96 seconds. `-NoHotReloadFromIDE` avoids unrelated editor Live Coding mutex contention without terminating other projects. A separate Game target previously built successfully.

- Headless standalone invocation: `FactoryTwin.exe -nullrhi -nosound -unattended -FactoryTwinSmoke -log`. **FAIL** during uncooked game startup (pre-replay asset-registry read). `Docs/unreal_smoke_agv2_seed42.log` records `LogAssetRegistry: Failed to load premade asset registry` and `FBufferReaderBase::Serialize` assertion. This is not evidence that the USD/replay smoke ran.
- Earlier UE editor process `UnrealEditor-Cmd.exe FactoryTwin.uproject -game -nullrhi -nosound -unattended -log` produced `Docs/unreal_editor_runtime_smoke.log` with Stage-generated component collision `/World/Factory/Equipment/M01 -> /World`. The fallback patch validates actual USD prim IDs. Later Editor headless smoke, `Docs/unreal_editor_integration_smoke_20261020.log`, verifies `Stage loaded factory_scene`, `USD loaded; 5 manifest equipment IDs bound`, `Replay ready: 2410 ordered events`, and `FACTORYTWIN_SMOKE_PASS ... replayed 2410 events through 3601701ms`, with normal exit. The following real D3D11 runs independently verify display, scale, state colors, positions and visibility.

## Validation matrix

| Check | Current status | Evidence requirement |
|---|---|---|
| UE editor C++ target compile (initial source) | PASS | UE Build.bat `Result: Succeeded` |
| Latest game C++ target compile (final source) | PASS | UE Build.bat `FactoryTwin Win64 Development`, `Result: Succeeded` |
| Latest editor C++ target compile | PASS | Incremental `FactoryTwinEditor` `Result: Succeeded`, 4 actions, 6.96 s |
| Standalone uncooked launch | FAIL | `Docs/unreal_smoke_agv2_seed42.log`, pre-replay asset-registry startup assertion |
| Editor USD initial mapping | PASS (headless fix regression) | New `Docs/unreal_editor_integration_smoke_20261020.log`: five USD manifest IDs bound; initial failing log retained |
| Editor USD and JSONL integration headless smoke | PASS | `FACTORYTWIN_SMOKE_PASS` 5 IDs / 2410 events / normal engine exit |
| Real UE D3D11 USD Stage and 1m scale (V09/C01) | PASS | `Docs/unreal_d3d11_final_agv2_20261020.log`; stage 5/5 IDs, INBOUND mesh 200×200×100cm and M01 200×200×200cm, 8 PNGs |
| Real GUI state and AGV replay (V10/C03) | PASS | `Docs/unreal_d3d11_final_agv{1,2}_20261020.log`, screenshot colors and AGV mesh coordinate checks at four virtual times |
| Manifest and JSONL negative inputs (V11/C02) | PASS | `Docs/unreal_negative_final_20261020.log`: six rejected cases, `FACTORYTWIN_NEGATIVE_QA_PASS` |
| Common A USD and B event integration (C04 source) | IMPLEMENTED; Kit GUI gate NOT RUN | Actual A USD/manifest and B AGV1/2 seed42 JSONL consumed in UE D3D, full Kit button-to-UE flow pending |
| 60–90 second final demo video (C05) | NOT RECORDED | Eight real D3D still PNGs exist, but no complete demonstration video |

Automatic propagation of `twin:equipmentId` from USD into UE actor tags/metadata is **not verified**; all binding uses the manifest and USD stage generated-component path. This is file-based replay; no Kit↔UE live synchronization or real MES claim is made.

## Final real-window commands and runtime evidence

Run each of the following in separate processes from the project root (the Editor takes about 10 seconds to initialize):

```powershell
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQA '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_d3d11_final_agv2_20261020.log'
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQAAgvOne '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_d3d11_final_agv1_20261020.log'
& '.\Docs\GenerateUnrealNegativeFixtures.ps1'
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -nullrhi -nosound -unattended -nop4 -FactoryTwinNegativeQA '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_negative_final_20261020.log'
```

The D3D11 logs include `verbatimrhiname="D3D11"`, `USD loaded; 5 manifest equipment IDs bound`, and a terminal `FACTORYTWIN_VISUAL_QA_PASS` after four screenshots each. The screenshots are **actually present**: `Docs/UnrealCaptures/FactoryTwin_agv2_idle.png`, `FactoryTwin_agv2_busy.png`, `FactoryTwin_agv2_down.png`, `FactoryTwin_agv2_repaired.png`, and the same four `FactoryTwin_agv1_*.png` paths. M01: 2,001ms Idle, 25,001ms Busy, 220,001ms Down, 270,001ms Busy. 2 AGV replay has 2,410 events, 1 AGV has 1,450. The D3D screenshots have a readable colored upper-right status panel and forward-facing 3D labels.

The geometry bounds from the **generated UE USD components** are INBOUND **200×200×100cm** (authored 2×2×1m) and M01 **200×200×200cm** (authored 2×2×2m). The final QA runs check imported AGV geometry center against the replay indicator center to a 1cm tolerance at every capture: for AGV01 positions in cm, `(-600,0,50)` at 2s, `(-200,200,100)` at 25s, `(400,-200,75)` at 220s, and `(-200,200,100)` at 270s. AGV02's imported geometry and indicator are invisible at each 1-AGV capture. **Neither final D3D run has `Mobility of ... has to be Movable` warnings** after the AGV-only component mobility fix.

The latest actual UE negative run ends with `FACTORYTWIN_NEGATIVE_QA_PASS: 6 invalid manifest/replay inputs rejected with actual UE parsers` and normal engine exit: duplicate manifest ID, wrong kind, malformed JSONL, unknown ID, out-of-order timestamps and duplicate event ID. The invalid fixture files are C-owned `Docs/UEQAInputs/*` and leave A/B source data unchanged. `-nullrhi` is used only for these parser assertions, never claimed as rendered GUI evidence.

## Coordinator-recognized score and remaining gates

- **Official C implementation:** C01 8/8, C02 8/8, C03 10/10, C04 5/5, C05 0/4 = **31/35 (88.6%)**. **C verification:** C01 8/8, C02 8/8, C03 10/10, C04 0/5, C05 0/4 = **26/35 (74.3%)**. At last coordinator update, total P0 implementation **93/100 (93%)**, verification **64/100 (64%)**; A 32/35 implemented 8/35 verified, B 30/30 implemented and verified.
- **C04 limitation:** A's Extension calls B's runner Python-side and B's raw 1,450/2,410 seed42 events are actually consumed and displayed in the UE app against the same A USD manifest. However, Kit runtime/GUI extension buttons have not executed on the target machine. Full Kit→UE integration verification remains **NOT RUN**, 0/5.
- **C05 limitation:** Eight real UE D3D11 1280×720 screenshots exist, but a final 60–90s Kit/USD/UE/KPI demo video file does not. The installed engine `/Engine/Maps/Templates/Template_Default` actually runs `AFactoryTwinGameMode` and auto-spawns the USD Stage/Director; no new `.umap` was needed. C05 video **NOT RECORDED**, 0/4.
- Actual official implementation and verification percentages must be read from the coordinator-controlled `FactoryTwinUE_JobStack_OneWeek/07_PROGRESS.md`. Neither this report nor a build success edits the ledger.
- **P1 CAD:** NOT RUN; **P2 Isaac:** NOT RUN; **video:** NOT RECORDED.

## 2026-10-20: model-swap extension, reference prefab D3D11 regression

Worker A now authors model paths/XYZ scale/rotation through `data/visual_assets.json` and references project-local USD prefabs at stable `/{ID}/Geometry` Xforms. The manifest's fixed parent ID paths and `twin:equipmentId` remain unchanged; no UE StaticMesh asset is serialized/hardcoded. UE C++ now walks real composed Stage prim descendants and binds only generated components whose `GetSourcePrimPath()` is within the exact `/Geometry` subtree, rejecting unrelated collapsed `/World`. A generated Xform with an inner `/Visual` Mesh is supported; multiple descendant meshes are handled as one movable/hidden subtree per AGV preserving prefab-local offsets. A missing/unresolved/no-rendered-Gprim reference causes an explicit error after limited Stage translation retries. Real UE setup logs `FACTORYTWIN_VISUAL_BIND` and `FACTORYTWIN_MODEL_GEOMETRY` show rendered primitive count, root count and measured centimetre dimensions.

- **PASS — Canonical referenced prefab:** D3D11 real viewport logs `Docs/unreal_swap_canonical_agv2_20261020.log` and `Docs/unreal_swap_canonical_agv1_20261020.log`, 4 captures each: `Docs/UnrealCaptures/FactoryTwin_refcanonical_agv{1,2}_{idle,busy,down,repaired}.png`. All five equipment anchors resolve an actual Xform+Visual generated subtree (2 source components each). M01 is a 200×200×200cm Cube; INBOUND remains 200×200×100cm. AGV mesh movement and 1-AGV AGV02 whole-geometry invisibility check both PASS; M01 states Idle→Busy→Down→Busy at virtual 2/25/220/270s.
- **PASS — Isolated alternate referenced prefab:** Worker A generated a **separate** `usd/_preview_swap/factory_scene.usda` and sibling `layout.usda` with M01's `/Geometry/Visual` authored as a **Sphere**, using `--model-override M01=usd/prefabs/alternate_sphere.usda`. Actual UE D3D11 logs `Docs/unreal_swap_alternate_agv2_quoted_20261020.log` and `Docs/unreal_swap_alternate_agv1_20261020.log` each end `FACTORYTWIN_VISUAL_QA_PASS` with four real screenshots: `Docs/UnrealCaptures/FactoryTwin_alternate_agv{1,2}_{idle,busy,down,repaired}.png`. The sphere is visually distinguishable in the images, and measured M01 dimensions changed to **200×190.2×200cm**; M02 stays a 200×200×200cm cube. Stage 5 IDs, original JSONL event cursor, real AGV waypoints and generated Geometry hiding remain PASS with zero mobility warnings. Actual alternative D3D images were inspected.
- **Command-line validation:** In Windows PowerShell 5.1, quote the entire argument `'-FactoryTwinUsdRoot=usd/_preview_swap/factory_scene.usda'`. An unquoted native argument was demonstrated by Python argv output to split into `factory_scene` and `.usda`, causing `FACTORYTWIN_VISUAL_QA_FAIL: USD root missing`. The final quoted execution log contains the complete `.usda` path. `-FactoryTwinVisualQATag=alternate` isolates screenshot filenames and preserves canonical evidence. This selects a preview Stage on launch; it is not an in-app hot-reload watcher.
- **Regression:** Earlier UE manifest/JSONL six invalid cases passed again as `Docs/unreal_swap_negative_20261020.log`; final CLI parser regression can be seen in `Docs/unreal_swap_negative_final_20261020.log`. Reproducible artist preview/commit commands and validation criteria are in `Docs/model_swap_unreal.md`. A-owned USD/catalog/code and B-owned source/runner/Reports were not edited by Worker C.

The model-swap work is additive to the coordinator-controlled P0 criteria. Last recognized P0 remains **93/100 implemented, 64/100 verified**; Worker C **31/35 implemented and 26/35 verified**. Full Kit application GUI enable/Run remains blocked pending external installation/license decision; C05 combined 60–90s video remains NOT RECORDED. P1 CAD / P2 Isaac NOT RUN.

## 2026-10-20: regenerated **current rich** catalog regression

The A-owned catalog changed again after the simpler prefab test. Its **current canonical** `data/visual_assets.json` maps M01/M02 to `usd/prefabs/factory_machine.usda`, QC01 to `usd/prefabs/factory_inspection.usda`, AGV01/AGV02 to `usd/prefabs/factory_agv.usda`; `usd/layout.usda` uses these richer referenced USD models. `build_usd.py --validate-only` was confirmed PASS by Worker A/coordinator. The old isolated `usd/_preview_swap` remains a valid historical scene, but it is **not** a validation fixture for the new catalog references. The current-catalog alternate fixture is A-owned `usd/_preview_swap_current/factory_scene.usda`, M01 Sphere only, the other four rich models unchanged; its `--validate-only --model-override M01=usd/prefabs/alternate_sphere.usda` was reported PASS by the owner.

- **PASS — current rich canonical D3D11, 2 AGVs:** `Docs/unreal_d3d11_industrial_20261020.log`, `Docs/UnrealCaptures/FactoryTwin_industrial_agv2_{idle,busy,down,repaired}.png`; `verbatimrhiname="D3D11"`, `FACTORYTWIN_VISUAL_QA_PASS`. The five `/Geometry` subtree bindings resolve **26, 26, 19, 23, 23** generated components respectively, containing **25, 25, 18, 22, 22** renderable Gprims; M01/M02 world box sizes 200×221.1×199.2cm, QC01 144×126.675×141.075cm, AGVs 96×72.87×46.341cm. Both 22-part AGV roots pass mobility/world-position checks at all four virtual snapshots (2/25/220/270s), with preserved state overlays and 2,410 original JSONL events.
- **PASS — current rich canonical D3D11, 1 AGV:** `Docs/unreal_swap_richcanonical_agv1_20261020.log`, `Docs/UnrealCaptures/FactoryTwin_richcanonical_agv1_{idle,busy,down,repaired}.png`; 4/4 snapshot pass, all four `FACTORYTWIN_VISUAL_QA_AGV_ONE` assert that AGV02's overlay and its **entire 22-renderable generated subtree** are hidden. AGV01's generated movement root stays within 1cm of replay coordinates.
- **PASS — current-catalog M01 alternate D3D11, 2 AGVs:** `Docs/unreal_swap_richalt_agv2_20261020.log`, `Docs/UnrealCaptures/FactoryTwin_richalt_agv2_{idle,busy,down,repaired}.png`; valid preview `-FactoryTwinUsdRoot=usd/_preview_swap_current/factory_scene.usda`. M01 changes to the one-Gprim Sphere **200×190.2×200cm**, while M02 continues to bind **25 rich factory-machine Gprims** and both AGVs retain **22 Gprims each**. Original states/AGV movement and 4 screenshots PASS; both the USD Stage and scene are actually rendered under D3D11.
- **Visual QA limitation:** Current `usd/factory_environment.usda` adds a large outer frame/wall that partially occludes machines/labels from the default elevated perspective in several PNGs. The screenshot proves geometry exists and the state HUD reads correctly, but the current camera composition should not be considered a polished unobstructed overview; camera/cutaway work is separate. No A-owned USD/runner changes were made by C for this regression. Official P0 recognition remains **93% implementation / 64% verification**.
