# FactoryTwin UE5.8 — factory/AGV visual model swap

## Current richer prefab catalog (2026-10-20)

The current A-owned `data/visual_assets.json` maps M01/M02 to `usd/prefabs/factory_machine.usda`, QC01 to `usd/prefabs/factory_inspection.usda`, and AGV01/AGV02 to `usd/prefabs/factory_agv.usda`. The default `usd/factory_scene.usda` has been regenerated with those references. Older runs and `usd/_preview_swap/` were made with the previous simple Cube catalog and remain historical evidence; the old preview does **not** match the current catalog, so validating it using the current expected references fails as intended.

For an up-to-date isolated comparison with the rich catalog, Worker A generated `usd/_preview_swap_current/factory_scene.usda` and sibling preview manifest/layout. Its M01 references `usd/prefabs/alternate_sphere.usda`, while M02/QC01/AGVs retain the new richer assets. Use the current preview command and actual UE execution:

```powershell
& '.\.venv\Scripts\python.exe' python/tools/build_usd.py --validate-only --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap_current/factory_scene.usda --manifest usd/_preview_swap_current/equipment_manifest_preview.json
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQA -FactoryTwinVisualQATag=richalt '-FactoryTwinUsdRoot=usd/_preview_swap_current/factory_scene.usda' '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_swap_richalt_agv2_20261020.log'
```

Rich canonical UE D3D evidence is `Docs/unreal_d3d11_industrial_20261020.log` (2 AGVs), with 25 machine Gprims, 18 inspection Gprims, and 22 per AGV. The current-preview D3D evidence is `Docs/unreal_swap_richalt_agv2_20261020.log`: M01 Sphere 200×190.2×200cm, M02 remains the complex factory machine with 25 Gprims. The rich factory frame occludes some machinery in the default camera angle; the HUD/geometry tests still run, but a dedicated overview/cutaway camera can improve presentation.

## What changes and what stays fixed

All visual assets are configured in `data/visual_assets.json` and referenced from `usd/layout.usda`. For an equipment ID, the immutable parent prim remains `/World/Factory/Equipment/M01` (or `/World/Factory/AGVs/AGV01`), retaining its `twin:equipmentId`, manifest `equipment_id`, `kind`, `prim_path`, initial translation, and replay event contract. Its child `/Geometry` is a replaceable USD `Xform` reference anchor. A prefab has a USD `defaultPrim` and may contain `/Geometry/Visual`, nested Xforms, or multiple Gprims.

The UE `AUsdStageActor` opens the composed `usd/factory_scene.usda`. `AFactoryTwinDirector` validates the parent ID attribute, discovers **actual generated UE components for USD source prims inside that specific `/Geometry` subtree**, and rejects unrelated collapsed `/World` components. The C++ source has no serialized model name, Unreal StaticMesh hardcode, or asset-specific actor class. Its separate text/light status overlay remains driven by B's original JSONL (`Idle`, `Busy`, `Down`, `Moving`). AGV motion translates only the generated model roots (with all descendants) by the event's metre-to-centimetre displacement, preserving prefab-local offsets. AGV=1 hides both AGV02's status actor and all its generated geometry, leaving the original USD prim intact.

The model replacement is **file-based**: modify catalog/asset → regenerate USD and validate → close/restart UE game/Editor (or explicitly reload the Stage/Director) to recompose. There is no implemented instant in-game file watcher, Kit↔UE real-time sync, or live materials import from arbitrary FBX/GLB.

## Artist asset checklist

1. Export a valid `.usd`, `.usda` or `.usdc` with a `defaultPrim` Xform and one or more renderable Gprims. For FBX, GLB, STEP, etc., convert separately to USD; this project does not include a verified automatic conversion tool.
2. Use **Z-up**, `metersPerUnit=1`, a documented pivot (ideally ground center), and project-relative `usd/...` references. Do not place `twin:equipmentId` in the prefab; the parent anchor owns ID metadata.
3. Put its USD file and local dependencies in `usd/prefabs/` (or a project-relative nested USD directory). The catalog validates allowed paths, finite positive scales, rotations and referenced Gprims via pxr. Use `scale` and `rotation_deg` in `data/visual_assets.json` to fit the scene; the dimensions of a substituted model are allowed to differ from the placeholder cube.
4. Preserve stage root `usd/factory_scene.usda`, manifest IDs and scene positions. The Python runner JSONL and KPI CSV do not change with visual models. Earlier simple M01 cube measured 200×200×200cm; current rich M01 factory machine measures **200×221.1×199.2cm**. A different prefab is allowed to have different dimensions.

## Preview a swap while preserving canonical files

From `FactoryTwinUE` in Windows PowerShell, ask Worker A's generator to write an isolated preview; the following **historical simple-catalog example** writes under A-owned `usd/_preview_swap/` paths. Coordinate before running it during parallel work. For the current rich catalog, use `usd/_preview_swap_current/` and the current-catalog command above:

```powershell
py -3.14 python/tools/build_usd.py --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap/factory_scene.usda --manifest usd/_preview_swap/equipment_manifest_preview.json
py -3.14 python/tools/build_usd.py --validate-only --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap/factory_scene.usda --manifest usd/_preview_swap/equipment_manifest_preview.json
```

The preview manifest retains the immutable `usd_root=usd/factory_scene.usda` contract. The UE QA loader accepts `-FactoryTwinUsdRoot=usd/_preview_swap_current/factory_scene.usda`, loads that preview Stage, and still checks the canonical manifest root plus live composed USD `twin:equipmentId` attributes for all five equipment parent prims. That override chooses a file on startup; it does not mutate the canonical stage. **In PowerShell 5.1, quote the entire `'-FactoryTwinUsdRoot=...usda'` argument exactly as below.** An unquoted form was observed splitting `.usda` into a separate native argv token; the attempted launch failed safely with `FACTORYTWIN_VISUAL_QA_FAIL`.

Run the two real graphical replay scenarios **sequentially**:

```powershell
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQA -FactoryTwinVisualQATag=alternate '-FactoryTwinUsdRoot=usd/_preview_swap/factory_scene.usda' '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_swap_alternate_agv2_quoted_20261020.log'
& 'F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\FactoryTwin.uproject' -game -dx11 -windowed -ResX=1280 -ResY=720 -nosound -nop4 -FactoryTwinVisualQAAgvOne -FactoryTwinVisualQATag=alternate '-FactoryTwinUsdRoot=usd/_preview_swap/factory_scene.usda' '-abslog=F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\Docs\unreal_swap_alternate_agv1_20261020.log'
```

Each successful run should write four real 1280×720 screenshots under `Docs/UnrealCaptures/FactoryTwin_alternate_agv{1,2}_{idle,busy,down,repaired}.png`, capturing M01 `Idle` at 2s, `Busy` at 25s, `Down` at 220s and `Busy` at 270s. `FACTORYTWIN_VISUAL_BIND` reports each exact-source Geometry subtree; `FACTORYTWIN_MODEL_GEOMETRY` lists actual post-import dimensions and primitive count. `FACTORYTWIN_VISUAL_QA_AGV_GEOMETRY` verifies each generated AGV root is movable and stays within 1cm of the expected translation at each replay waypoint; the AGV=1 run confirms AGV02's entire generated visual subtree is invisible. The last `FACTORYTWIN_VISUAL_QA_PASS` is emitted only after four capture files exist. **Do not treat a source-file-only result as screenshot proof.**

For **historical simple-catalog** comparison, `Docs/unreal_swap_canonical_agv{1,2}_20261020.log` contains eight `FactoryTwin_refcanonical_agv{1,2}_*.png` images. Those old canonical dimensions were M01 cube 200×200×200cm, AGV cube 100×70×60cm. Historical alternate `Docs/unreal_swap_alternate_agv2_quoted_20261020.log` measures M01 **200×190.2×200cm** and leaves the *old simple* M02 Cube. For the **current rich-catalog** comparison use `Docs/unreal_d3d11_industrial_20261020.log` and `Docs/unreal_swap_richalt_agv2_20261020.log` instead.

## Commit a permanent visual asset change

When the artist is satisfied with the preview, **close all UE/Kit processes that have the Stage open**, and use the safe A-owned catalog updater:

```powershell
py -3.14 python/tools/set_visual_asset.py --id M01 --asset usd/prefabs/alternate_sphere.usda --scale 2,2,2 --rotation 0,0,0 --dry-run
py -3.14 python/tools/set_visual_asset.py --id M01 --asset usd/prefabs/alternate_sphere.usda --scale 2,2,2 --rotation 0,0,0
py -3.14 python/tools/build_usd.py --validate-only
```

The updater preflights composition and validates before changing the canonical visual catalog and USD layers. Restart the Unreal Editor project and Play; the Stage Actor loads the same `usd/factory_scene.usda` path with newly referenced Geometry. If multiple workers have open scenes, coordinate changes to A-owned files; C workers should not directly edit `usd/`, `data/`, `python/` or `Reports/`. To restore the **current rich** canonical M01 model, repeat the updater with `--asset usd/prefabs/factory_machine.usda`.

## Failure and regression evidence

- Missing parent ID/`twin:equipmentId`, missing `/Geometry` anchor, non-rendering/unresolved external USD, or components that only map to `/World` fail the bind with explicit `ERROR`/`FACTORYTWIN_SMOKE_FAIL`; they must not silently borrow another device's mesh.
- Preview Stage override still validates the manifest's canonical `usd_root` and checks all actual composed prim IDs. Asset generation rejects external/traversal paths, absent USD prefab Gprims and invalid scales/rotations separately (see A's builder validation).
- C's UE malformed/duplicate/unknown/timestamp regression harness is `-FactoryTwinNegativeQA` with `Docs/GenerateUnrealNegativeFixtures.ps1`. Original B run events contain 1,450 events (AGV=1) and 2,410 (AGV=2) for seed42. Logs and screenshots, not source inspection, determine UE state/color/AGV PASS.
- Kit app GUI and Kit Python Extension integration is separately blocked on an approved installed Kit runtime. The 60–90s combined video remains `NOT RECORDED`; P1 CAD and P2 Isaac remain `NOT RUN`. The established official P0 baseline is **93% implemented and 64% verified**, and model-swap support is additive to those gates.
