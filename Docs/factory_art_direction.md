# FactoryTwin — factory exterior, equipment and AGV visual pass

Date: 2026-10-20. The existing factory replay is a file-driven digital-twin demonstration, and its equipment identities and coordinates remain authoritative.

## Implemented in the live shared USD stage

The view now loads `usd/factory_scene.usda` composed from independent `layout.usda` and `factory_environment.usda` layers. `factory_environment.usda` contains an **open factory cutaway**: a raised floor slab, safety floor markings, inbound/outbound dock zones, racks, crates, machine-bay outlines, a vehicle transit lane, and low perimeter rails. A high wall was tried in a real D3D11 run but hid the equipment from the existing camera; the final stage uses low rails and an open roof so all five status labels remain visible.

Replaceable authored `defaultPrim=/Model` Z-up, metre-scale USD prefabs:

| Runtime ID(s) | Visual prefab (relative project path) | Model | Canonical parent position (metres) |
| --- | --- | --- | --- |
| `M01`, `M02` | `usd/prefabs/factory_machine.usda` | 25-component CNC enclosure, observation door, control panel and stack light | `(-2,2,1)` / `(2,2,1)` |
| `QC01` | `usd/prefabs/factory_inspection.usda` | 18-component inspection station, conveyor, overhead camera and light bar | `(4,-2,.75)` |
| `AGV01`, `AGV02` | `usd/prefabs/factory_agv.usda` | 22-component cargo AGV, chassis, wheels, bumpers and LiDAR mast | `(-2,-2,.3)` / `(0,-2,.3)` |

The independent environment contains 67 Gprims. The USD prefab origins are designed around the **already-fixed centre-height parent Xforms**, so the visible machinery stands on the stage floor. Individual stage parent `/Geometry` references are driven by `data/visual_assets.json`; the manifest and `twin:equipmentId` stay on the same parent Xforms. AGV visual geometry remains strictly under its own Geometry subtree for UE replay movement and one-AGV visibility control. Do not add decorative AGV duplicates to the environment.

The vehicle path markings are visual guides; the 1-vs-2 AGV motion uses the original simulation JSONL waypoints. Some service positions occur at the centre of machines with higher Z coordinates, reflecting the original abstract replay rather than a physically validated collision-free robot route.

## Regenerate and verify

Run from `FactoryTwinUE` with the pinned pxr-enabled Python environment:

```powershell
.\.venv\Scripts\python.exe python/tools/build_factory_visuals.py
.\.venv\Scripts\python.exe python/tools/build_usd.py --out usd/factory_scene.usda --manifest data/equipment_manifest.json
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only
.\.venv\Scripts\python.exe python/tools/test_factory_appearance.py
.\.venv\Scripts\python.exe python/tools/test_model_swap.py
```

The first command regenerates only the three detailed prefabs and the separate background USD. It never creates/churns IDs or simulation events. The second command rebuilds the layout's validated references and the scene root. The last checks verify all five unchanged ID/prim/position bindings, usable renderable subtree references, environment separation, near-floor bounding boxes, and asset swap failure/rollback cases.

For a single equipment change, use `python/tools/set_visual_asset.py --id AGV01 --asset usd/prefabs/another_agv.usda --dry-run` first. If the validation succeeds, remove `--dry-run` and reload the Stage in Kit/UE. See `Docs/model_swap_usd.md` for relative USD path and transform validation details.

### Actual Unreal D3D11 visual acceptance (new art pass)

The final open-view geometry was reopened by UE 5.8.3 through the real `AUsdStageActor`. The Windows Editor command line used `-game -dx11 -windowed -ResX=1280 -ResY=720 -FactoryTwinVisualQATag=factoryfinal` and either `-FactoryTwinVisualQA` (two AGVs) or `-FactoryTwinVisualQAAgvOne` (one AGV), with a separate quoted `-abslog` path for each process. Both processes exited 0 and wrote `FactoryTwin: USD loaded; 5 manifest equipment IDs bound` and `FACTORYTWIN_VISUAL_QA_PASS: 4 rendered screenshots verified on disk; five USD bindings`.

Evidence: `Docs/unreal_d3d11_factory_final_agv2.log`, `Docs/unreal_d3d11_factory_final_agv1.log`, and eight `Docs/UnrealCaptures/FactoryTwin_factoryfinal_agv{1,2}_{idle,busy,down,repaired}.png`. The actual AGV=1 busy screenshot was inspected and shows `AGV02 Inactive` with the second vehicle hidden; AGV=2 displays both. Status colors are shown by the separate UE labels/HUD, while the USD primitive models use mostly default grey imported shading pending artist-authored materials. These are real UE screenshots, not Blender renders.

## Blender artist handoff / MCP availability

`python/tools/generate_blender_assets.py` authors a separate editable Blender scene with independent M01/M02, QC01, AGV01/AGV02 and factory environment source collections. `art/blender/README.md` documents the Blender background command, `.blend` export, USD/GLB variants, and manually-edited `.blend` re-export mode. The canonical stage remains usable from the pxr-authored USD assets even while Blender is unavailable.

At this session, a Blender executable was not found on PATH/default Blender install locations, `bpy` was unavailable under local Python, and **no Blender MCP action was available to this chat**. The Blender generator was syntax checked but its `.blend`, USD-from-Blender, GLB, and Blender hero render execution are **NOT RUN**. Do not claim Blender itself was connected or that its planned export files already exist.

## Scope and verification accounting

This is an additional visual-art pass, outside existing P0 A/B/C acceptance tickets. The authoritative P0 ledger remains implementation **A 32/35, B 30/30, C 31/35 = 93/100 (93.0%)** and verification **A 8/35, B 30/30, C 26/35 = 64/100 (64.0%)**. The existing Kit UI evidence gate and 60–90-second video are still pending. CAD P1 and Isaac Sim P2 are NOT RUN. See `FactoryTwinUE_JobStack_OneWeek/07_PROGRESS.md` for exact ticket scoring rules.
