# FactoryTwin — Blender factory art source

This is an optional, original Blender art-production source for the FactoryTwin
UE / OpenUSD demo. The canonical **working** visuals currently come from
`usd/prefabs/factory_machine.usda`, `usd/prefabs/factory_inspection.usda`,
`usd/prefabs/factory_agv.usda` and `usd/factory_environment.usda`.
The script here is an independent replacement-asset authoring pipeline: its
exports are not inserted into the live USD stage until someone explicitly
updates `data/visual_assets.json` and rebuilds that stage. The catalog loader
requires model paths to start with `usd/`, so `.glb` assets under `art/blender`
cannot be referenced directly by that catalog.

## Build in Blender (Windows)

Install Blender 4.1 or newer with the glTF 2.0 and USD exporters available.
The project must also have `FactoryTwinUE/.venv/Scripts/python.exe` with
`pxr` installed (`usd-core`); the generator uses this environment to finalize
and verify each USD prefab, even when Blender's bundled Python lacks `pxr`.
From the parent `/openusd_omniverse-kit` workspace directory, run:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' `
  --background --factory-startup --python `
  FactoryTwinUE/python/tools/generate_blender_assets.py -- `
  --output FactoryTwinUE/art/blender `
  --usd-export-dir FactoryTwinUE/usd/prefabs/blender --format both --render
```

Adjust the Blender executable path to the version actually installed. To
generate only USD, use `--format usd`; to skip rendering, omit `--render`.
Run again to regenerate the `.blend` and exports from code. The generator
does not touch simulation events, manifests, UE sources or canonical USD assets.
Only the generated subtree `usd/prefabs/blender/` is a permitted USD output
location; `--usd-export-dir` can name a child folder in that subtree.

## Files the Blender run will produce

| Source collection in `.blend` | Export basename | Asset meaning | Placement (metres; XYZ) | Final scene bounding target |
| --- | --- | --- | --- | --- |
| `M01_CNC` | `M01_CNC` | Pearl CNC, teal accents | `(-2, 2, 1)` | approx. 2 × 2 × 2 m |
| `M02_CNC` | `M02_CNC` | Pearl CNC, blue accents | `(2, 2, 1)` | approx. 2 × 2 × 2 m |
| `QC01_Inspection` | `QC01_Inspection` | Vision inspection gantry | `(4, -2, .75)` | approx. 1.5 × 1.5 × 1.5 m |
| `AGV01` | `AGV01` | Low AGV with teal top and LiDAR | `(-2, -2, .3)` | approx. 1 × .7 × .6 m |
| `AGV02` | `AGV02` | Low AGV with amber top and LiDAR | `(0, -2, .3)` | approx. 1 × .7 × .6 m |
| `Factory_Environment` | `Factory_Environment` | Factory floor, aisles, loading docks, windows, lighting props | `(0, 0, 0)` | approx. 19.4 × 13.6 m floor |

Generated `art/blender` files: `FactoryTwin_ArtDirection.blend`, optional
`FactoryTwin_hero.png`, and `exports/{basename}.glb`. Six independent asset
roots are included in the editable Blender scene, with separately named meshes.

After the Blender USD exporter succeeds, each `.usdc` is placed in a temporary
directory. The generator launches **FactoryTwinUE/.venv Python with pxr** to
write and reopen a valid Xform `defaultPrim`, enforce Z-up/metresPerUnit=1,
check renderable geometry and identity root, reject identity metadata and
external asset dependencies. Only if **every** USD passes this check will it
publish files into the following project-valid paths:

| Blender root | Verified USD catalog path |
| --- | --- |
| `M01_CNC` | `usd/prefabs/blender/M01.usdc` |
| `M02_CNC` | `usd/prefabs/blender/M02.usdc` |
| `QC01_Inspection` | `usd/prefabs/blender/QC01.usdc` |
| `AGV01` | `usd/prefabs/blender/AGV01.usdc` |
| `AGV02` | `usd/prefabs/blender/AGV02.usdc` |
| `Factory_Environment` | `usd/prefabs/blender/Factory_Environment.usdc` (not a device catalog entry) |

Missing `.venv`/`pxr`, a failed USD parse, missing `defaultPrim`, unsafe
dependencies or invalid units **blocks publishing** and leaves canonical
assets intact. Each verified copy is checksum checked and atomically renamed.

## Edit / swap a model

1. Open `FactoryTwin_ArtDirection.blend`. Under the object collections, change
   a particular device's mesh children, materials or proportions. Retain the
   collection's root name and its model pivot at the **local origin**.
2. Keep model-space axes Z-up and model-space dimensions near 1 × 1 × 1 metre.
   Scene positions/scales in the source `.blend` are previews only; export
   temporarily sets the asset root's location to zero and scale to one.
3. Run the generator if the model was changed **in the generator source**. To
   preserve manual GUI edits, save the `.blend`, then rerun the **export-only**
   mode below. It loads all the edited objects, exports each ID independently,
   and leaves the saved `.blend` unchanged:

   ```powershell
   & 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' `
     --background --factory-startup --python `
     FactoryTwinUE/python/tools/generate_blender_assets.py -- `
     --source-blend FactoryTwinUE/art/blender/FactoryTwin_ArtDirection.blend `
     --output FactoryTwinUE/art/blender `
     --usd-export-dir FactoryTwinUE/usd/prefabs/blender --format both --render
   ```

   Running the normal generator again will recreate the procedural artwork,
   overwriting previous edits to its generated `.blend`.
4. After **USD_FINALIZED_AND_VERIFIED** and **USD_PUBLISHED_VERIFIED** appear
   in the successful Blender command output, the **USD owner** can point the
   desired ID's `data/visual_assets.json` `model_path` to e.g.
   `usd/prefabs/blender/M01.usdc`, `usd/prefabs/blender/QC01.usdc`, or
   `usd/prefabs/blender/AGV01.usdc`, retaining `scale`, `rotation_deg`,
   `equipment_id` and `prim_path`.
5. Before adopting the swap, run the canonical USD builder's prefab validation
   in the **project .venv** (the `--validate-only` option validates the current
   composed stage; use an isolated preview root/manifest for any override).
   For example, from `FactoryTwinUE/`, this creates a separate preview for
   `M01` and validates its USD references without changing the canonical stage:

   ```powershell
   .\.venv\Scripts\python.exe python\tools\build_usd.py `
     --out usd\_preview_blender\factory_scene.usda `
     --manifest usd\_preview_blender\equipment_manifest.json `
     --model-override M01=usd/prefabs/blender/M01.usdc
   ```

   Check the composed stage in Kit/UE and preserve the current canonical floor
   rather than layering a second copy of `Factory_Environment`.

The model asset pipeline is visual-only. It does not set ID metadata, move an
AGV based on simulation time, change the Python state model or export a new KPI.

## Actual environment status (2026-10-20)

`blender` was not found on the Windows PATH, in the default Blender Foundation
installation directory, or via the connected tool catalog. The system Python's
`importlib.util.find_spec('bpy')` returned `False`; the **project .venv**
contains working `pxr` 26.8. **No Blender run, `.blend`, rendered PNG, `.usdc`
or `.glb` exports have been verified** in this environment. The paths above
are intended generated outputs until an actual Blender run completes. Script
syntax and the USD verification helper can be tested without Blender.
