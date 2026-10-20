# FactoryTwinUE — A02–A06 actual evidence and Kit smoke status

2026-10-20 KST. Worker A, new project `FactoryTwinUE/` under `F:\GitHubRep\OpenUSD_Omniverse Kit`. Parent `OpenUSD_OmniverseKit.uproject` was not edited. All commands below were run in **PowerShell 5.1** with the working directory set to `FactoryTwinUE` unless stated. Project Python `.venv` is local; `usd-core==26.8` was installed into it, not global Python.

## What actually succeeded

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --only-binary=:all: usd-core==26.8
.\.venv\Scripts\python.exe -c "from pxr import Usd; print('pxr USD version', Usd.GetVersion())"
.\.venv\Scripts\python.exe python/tools/build_usd.py --out usd/factory_scene.usda --manifest data/equipment_manifest.json
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only --out usd/factory_scene.usda --manifest data/equipment_manifest.json
.\.venv\Scripts\python.exe -m py_compile exts/com.factory.twin/factory/twin/extension.py exts/com.factory.twin/factory/twin/__init__.py python/tools/build_usd.py
```

Actual relevant stdout (all commands above exited 0):

```text
Successfully installed usd-core-26.8
pxr USD version (0, 26, 8)
USD root: F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\usd\factory_scene.usda
USD sublayer: F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\usd\layout.usda
Manifest: F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\data\equipment_manifest.json (5 equipment IDs)
Writer: pxr.Usd/UsdGeom
Manifest structural validation: PASS
Usd.Stage.Open / 7 locations and equipment prims / metadata: PASS
Manifest structural validation: PASS; USD Stage validation: PASS
```

Actual independent `pxr` probe:

```powershell
.\.venv\Scripts\python.exe -c "from pxr import Usd,UsdGeom; s=Usd.Stage.Open('usd/factory_scene.usda'); print('STAGE',bool(s),'sublayers',s.GetRootLayer().subLayerPaths,'up',UsdGeom.GetStageUpAxis(s),'meters',UsdGeom.GetStageMetersPerUnit(s)); print([(str(p.GetPath()),p.GetAttribute('twin:equipmentId').Get()) for p in s.Traverse() if p.HasAttribute('twin:equipmentId')])"
```

```text
STAGE True sublayers ['layout.usda'] up Z meters 1.0
[('/World/Factory/Equipment/M01', 'M01'), ('/World/Factory/Equipment/M02', 'M02'), ('/World/Factory/Equipment/QC01', 'QC01'), ('/World/Factory/AGVs/AGV01', 'AGV01'), ('/World/Factory/AGVs/AGV02', 'AGV02')]
```

Python stdin negative probes imported the actual `build_usd` module and compared mutated manifests against `read_ids_with_pxr` from the real stage. Results:

```text
PASS reject duplicate ID: duplicate equipment_id: M01
PASS reject duplicate prim: duplicate prim_path: /World/Factory/Equipment/M01
PASS reject empty ID: equipment[0] empty equipment_id
PASS reject missing prim: missing USD prim or equipmentId: /World/Factory/Equipment/NOT_THERE
PASS reject metadata mismatch: USD metadata mismatch at /World/Factory/Equipment/M01: 'M01' != 'M99'
PASS valid manifest and real USD Stage.Open
```

Static extension checks used `tomllib` against the real `extension.toml` and `py_compile` against the real code; both PASS. A standalone **non-Kit** probe injected dummy `omni.ext`, `omni.ui`, `omni.usd` module objects solely to import the extension and call its pure validation helpers. It did **not** instantiate the Kit UI or execute a real lifecycle. The observed output was:

```text
PASS independent Kit adapter pxr validator: 5 IDs
PASS accepted valid 1
PASS rejected unknown unknown equipment ID in event: NOPE
PASS rejected missing state_changed must include known equipment_id at row 0
PASS rejected out_of_order event_id must be sequential from 1, row 0: 2
PASS no simulated/placeholder KPI: B03 BLOCKED: missing scenario JSON: F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\data\scenarios\agv_1.json
```

## Actual NVIDIA Kit launch attempt and blockers

No Kit installation or `repo.bat` launcher was present on `PATH` or in the probed default locations (`%LOCALAPPDATA%\ov\pkg`, `C:\Program Files\NVIDIA Corporation\Omniverse`, `F:\Omniverse`, `F:\GitHubRep\kit-app-template`). `Get-StartApps | Where-Object { $_.Name -match 'Omniverse|Isaac|Kit SDK' }` returned no rows. Attempt:

```powershell
kit.exe --help
```

PowerShell actual output, **exit code 1**:

```text
'kit.exe' 용어가 cmdlet, 함수, 스크립트 파일 또는 실행할 수 있는 프로그램 이름으로 인식되지 않습니다. 이름이 정확한지 확인하고 경로가 포함된 경우 경로가 올바른지 검증한 다음 다시 시도하십시오.
```

`Get-Command kit.exe,repo.bat -ErrorAction SilentlyContinue` produced no commands (exit 1). Consequently, **no NVIDIA Kit app was launched, no extension was enabled, no `omni.ui` window appeared, and no screenshots/Kit runtime logs exist**. V03 and V04 are **NOT RUN**, A04 lifecycle and A05 buttons/timeline are **NOT RUN in real Kit**. Local `pxr` Stage.Open PASS is not Kit stage PASS.

**Historical status (before B03 landed):** `python/factory_sim/runner.py` and `data/scenarios/agv_{1,2}.json` were absent, and `_run_worker_b(1)` rejected the missing config. This was superseded by the successful B03 handoff and new headless A05 adapter integration detailed below. Kit GUI runtime remains untested.

## Reproduce remaining Kit smoke once a compatible runtime is installed

1. Build or install a suitable official NVIDIA Kit app, note SDK version/path and API differences. These steps remain **instructions for future verification**; no such app was available here. Add `FactoryTwinUE/exts` as an extension search root with the installed app's documented `--ext-folder` option or equivalent Extension Manager setting.
2. Enable `com.factory.twin` in Kit Extension Manager. Verify `FactoryTwin | OpenUSD & Scenarios` window appears exactly once; disable and re-enable to check `on_shutdown` cleanup and absence of duplicates. Capture actual Kit console log and two screenshots **only after executing**.
3. Click **Generate USD** / **Load USD**. Confirm stage `/World/Factory/Equipment/M01` with `twin:equipmentId = M01`, all five manifest identities, `upAxis=Z`, `metersPerUnit=1.0`; confirm both locations and cube meshes. `omni.usd.get_context().open_stage_async` currently follows documented `(success,error)` tuple form and reads `get_stage()` afterward; recheck against installed Kit version.
4. With the now implemented Worker B `run_scenario(config, seed)` and `save_run(...)`, click **AGV=1**, **Run Scenario**, inspect actual KPI and saved `Reports/run_agv_1_seed42.jsonl` / `Reports/kpi.csv`; repeat **AGV=2**. Change replay time slider and verify authored state events alter *session-layer* display colors. For AGV=1, `AGV02` must remain in static USD but be invisible in Kit; AGV=2 should restore its visibility. If canonical JSONL hash differs, the extension preserves it and instead writes `Reports/kit_run_agv_{count}_seed42.jsonl` with `Reports/kit_kpi.csv` through B's public `save_run` API.
5. Preserve real console log/screenshots alongside timestamp, Kit build, GPU driver, selected seed/scenario, and output data location. If the actual installed Kit API differs, patch `extension.py` and rerun.

## Status (binary verification gates)

| Gate | Status | Evidence or limitation |
|---|---|---|
| A01 environment probes | PASS | `Docs/kit_environment.md` command outputs; 3.14, MSVC, UE, GPU, Kit absence |
| V01 / A02 USD Stage.Open | PASS in stand-alone `pxr` | Above command/actual five IDs, Z-up, unit=1.0, two locations |
| V02 / A03 metadata identity | PASS | Five manifests equal actual USD custom IDs; negative probes reject duplicates, missing and mismatch |
| V03 / A04 actual Kit lifecycle | NOT RUN | No `kit.exe`; extension code/TOML merely compiled |
| V03 / A05 buttons, runner, KPI | Kit NOT RUN; headless B adapter PASS | B03 runner/scenario and real JSONL/KPI passed after follow-up; UI buttons not tested in a Kit app |
| V04 / A06 stage/screenshots | NOT RUN | No Kit screenshot or Kit run log was generated |
| UE import/scale test | NOT RUN | Owned by Worker C; no UE action claimed here |
| CAD STEP P1 / Isaac Sim P2 | NOT RUN | Not part of Worker A P0 execution |

No actual Kit screenshot or Kit runtime result is claimed by this file; headless measured KPIs are independently identified below.

## Follow-up: real Worker B API integration, 2026-10-20 KST

Only `exts/**` and the two A-owned Kit evidence documents were edited in this follow-up. Worker B's source (`python/factory_sim/**`), scenarios, manifest and coordinator's progress ledger were read only. As requested for the real Kit→JSONL→UE bridge, the Extension calls **Worker B's own** `runner.save_run(SimulationResult, out=..., kpi_out=...)` to produce the measured replay and KPI files. The standalone adapter test invoked the same production method, so the two scenario reports were produced through B's public writer; they were not handwritten or synthetic fixtures.

PowerShell test (project root), using the project-local Python/`pxr` installation, injected **stub Python module objects for `omni.ext`, `omni.ui`, `omni.usd` solely to import the extension outside Kit**. Real USD reading, B's actual `run_scenario` and `save_run`, SHA-256 comparison, and generated JSONL/CSV remained real. The test then called `_run_worker_b(1)` and `_run_worker_b(2)` and checked returned `.is_file()`, event hash, count and KPI:

```text
PASS pxr ID validation 5
PASS AGV=1 jobs=49 events=1450 sha256=af9fa4a5e33c590d file=run_agv_1_seed42.jsonl kpi=kpi.csv
PASS AGV=2 jobs=153 events=2410 sha256=3fc6c37be2a6476f file=run_agv_2_seed42.jsonl kpi=kpi.csv
```

These are actual B03 model results for seed 42, not Kit UI observations. Complete digests are stored in each returned KPI entry and may be recomputed over the real JSONL. Both runs used the actual `data/scenarios/agv_{1,2}.json` configs with deterministic seed 42. Existing canonical `run_agv_X_seed42.jsonl` files are only overwritten if their SHA-256 matches the new run. If they differ, Kit writes separately named `kit_run_...` and `kit_kpi.csv` reports to preserve previously created B/C evidence.

A second standalone OpenUSD probe opened the **actual authored scene** through `pxr.Usd.Stage.Open`, assigned the stage to a stub `omni.usd.get_context()` solely for `_apply_timeline`, and loaded real B events. It found:

```text
PASS standalone pxr stage session layer M01 Down at t=220s, AGV02 hidden
PASS standalone pxr stage AGV02 visible at AGV=2; time: 220 s / 3600 s | 105 recorded state transitions
```

The first check asserted M01's red Down displayColor at virtual 220s, `AGV02` invisible with AGV=1, and color authored to the session layer rather than root USD. The second verified AGV02 visibility restores with AGV=2. **All Kit GUI behaviors, extension enable/disable/re-enable, and actual on-screen playback remain NOT RUN.**

The Extension now destroys `ui.Window` on shutdown (per NVIDIA's official UI Window sample) to prevent stale native windows after reenable, clears stale KPI output when AGV selection changes or a run fails, prevents overlapping Run requests, uses a verified hash before claiming a saved run, and shows actual JSONL/KPI filenames and the hash prefix on successful completion. Pure `py_compile` and the two headless probes are not substitutes for Kit UI startup evidence.

An additional pure Python test (same stub-import setup) called `_request_run()` twice before allowing the first task to start, and asserted a single task plus a second-request error. Observed stdout, process exit 0:

```text
PASS consecutive Run clicks: one task only, second rejected: Scenario still running; complete it before starting another
```

This guards B's documented single-writer `kpi.csv` constraint; it does not simulate actual Kit clicks. The `finally` branch of `_run_scenario` clears the guard after success, failure or cancellation.

## Follow-up: official NVIDIA Kit App Template bootstrap and licensing gate

Official template and documentation consulted:

- https://github.com/NVIDIA-Omniverse/kit-app-template (clone, template creation and prerequisites)
- https://github.com/NVIDIA-Omniverse/kit-app-template/blob/main/readme-assets/additional-docs/kit_app_template_tooling_guide.md (repo.bat build and launch)
- https://docs.omniverse.nvidia.com/kit/docs/omni.usd/latest/omni.usd/omni.usd.UsdContext.html (`open_stage_async` returns `(bool, str)`)
- https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/configuring.html (`--enable` and `--ext-folder` options)
- https://docs.omniverse.nvidia.com/kit/docs/omni.ui/3.3.10/omni.ui/omni.ui.IntSlider.html (`min`/`max` keyword API)
- https://github.com/NVIDIA-Omniverse/kit-extension-sample-ui-window/blob/main/exts/omni.example.ui_window/omni/example/ui_window/extension.py (`ui.Window.destroy()` on shutdown)
- https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html (2026 Kit minimum resources and current validated GPU driver families)

Actual command attempts, with the working directory set to `FactoryTwinUE` for the clone and `FactoryTwinUE/exts/_kit_app_template_probe` for the other commands:

```powershell
git --version
git ls-remote --heads https://github.com/NVIDIA-Omniverse/kit-app-template.git main
git clone --depth 1 https://github.com/NVIDIA-Omniverse/kit-app-template.git exts/_kit_app_template_probe
.\repo.bat --help
.\repo.bat template new --help
.\repo.bat template new
```

Results: Git 2.53.0.windows.2, remote `main` resolved to `9cc43b764e6d4cd86cb6296a8440665c3c4f4843`, clone exit 0. Repo bootstrap `--help` exited 0 and printed **Repo Tool (repoman) 2.9.6**, with `template` v2.4.3, `repo_kit_tools` v1.21.4; `template new --help` exited 0. The actual `template new` displayed **NVIDIA Software License Agreement** and **Product-Specific Terms for NVIDIA Omniverse**, then an explicit `Do you accept the governing terms? Yes / No` prompt. We sent **Ctrl+C** without accepting on the user's behalf. Interactive output included `Exiting`; the PTY launcher reported exit code 0 after Ctrl+C, which does **not** signify application/template creation. `repo.bat build` and `repo.bat launch` were **NOT RUN** because the template creation/license step did not complete. No Kit app was launched and there are no real Kit screenshots.

Side effect to disclose: the official `repo.bat` bootstrap printed `Setting user environment variable PM_PACKAGES_ROOT to F:\packman-repo` and created a Packman cache outside `FactoryTwinUE`. This is an automatic NVIDIA bootstrap behavior rather than an authored project file. The **user-scoped environment variable was then restored to its previously absent value** with `[Environment]::SetEnvironmentVariable('PM_PACKAGES_ROOT',$null,'User')`; a subsequent read returned empty. The downloaded `F:\packman-repo` cache remains intact because deleting an external cache was outside this worker's ownership. The template clone itself resides exclusively under A-owned `exts/_kit_app_template_probe/`. The location is deep and contains spaces; if later Kit dependency tooling fails on path length, consider a new shallow install location after coordinating ownership and user preferences.

If the user accepts NVIDIA's terms separately, the official continuation from the cloned folder is:

```powershell
.\repo.bat template new  # choose Application -> Kit Base Editor; user handles NVIDIA license prompt
.\repo.bat build
.\repo.bat launch -- --ext-folder "F:\GitHubRep\OpenUSD_Omniverse Kit\FactoryTwinUE\exts" --enable com.factory.twin
```

Run actual Kit enable/disable/re-enable and screenshot/log capture after successful build/launch. Do not present this unexecuted procedure as validation. Note the hardware: RTX 3070 Ti 8GB/driver 560.94 meets the **template README's** stated Windows driver threshold 551.78 and its RTX 3070 recommended GPU class, while the current Omniverse technical requirements list newer 581.42 or 595.97 as validated Ampere GeForce Windows branches; actual compatibility of 560.94 with the future Kit build remains untested. Current minimum Kit storage is listed as 250GB in official requirements; available free space may influence local installation feasibility. No GPU driver or OS change was attempted.

**Tickets unchanged:** A04 implementation 8/8, Kit runtime verification **0/8**. A05 implementation 9/9, real Python adapter PASS but Kit UI verification **0/9**. A06 implementation/verification **0/3** until real Kit stage, log and screenshot evidence. Coordinator retains sole authority for full A/P0 progress ledger changes. P1 CAD / P2 Isaac: NOT RUN in this A assignment.

## 2026-10-20: model swapping enhancement (outside scored P0)

New A-owned `data/visual_assets.json`, `usd/prefabs/{machine,inspection,agv,alternate_sphere}.usda`, `python/tools/set_visual_asset.py`, `python/tools/test_model_swap.py`, and `Docs/model_swap_usd.md` implement changeable visual USD references under fixed equipment parent prims. `python/tools/build_usd.py` now generates `/Geometry` as `Xform` with **one** reference to a prefab's `defaultPrim`, while identity, world position, root sublayer and unit convention remain fixed. `exts/com.factory.twin/factory/twin/extension.py` Kit state replay now applies a **session-layer** color to every descendant Gprim, supporting swapped arbitrary Mesh/Cube/Sphere model hierarchies; Load USD explicitly calls `stage.Reload()` for asset refresh.

Actual commands and results, from `FactoryTwinUE` project root with the existing isolated Python 3.14 `usd-core 26.8` environment:

```text
.\.venv\Scripts\python.exe python/tools/test_model_swap.py
test_cli_override_only_in_preview ... ok
test_model_path_and_transform_validation_without_writes ... ok
test_one_command_helper_commit_restore_only_on_isolated_preview ... ok
test_one_command_helper_dry_run_and_invalid_model_leave_canonical_unchanged ... ok
test_swap_preserves_identity_transform_and_changes_visual_shape ... ok
Ran 5 tests in 3.522s
OK

.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only
Manifest structural validation: PASS; USD Stage validation: PASS

.\.venv\Scripts\python.exe python/tools/set_visual_asset.py --id M01 --asset usd/prefabs/alternate_sphere.usda --scale 2,2,2 --rotation 0,0,0 --dry-run
DRY RUN PASS M01 -> usd/prefabs/alternate_sphere.usda; canonical catalog/USD unchanged

.\.venv\Scripts\python.exe python/tools/set_visual_asset.py --id M01 --asset ../../Windows/System32/evil.usda --dry-run
MODEL SWAP REJECTED: model_path must be under usd/ and point to a USD file: '../../Windows/System32/evil.usda'
```

The invalid-path command intentionally exited **1**; successful py_compile, test suite, validate-only and dry-run exited **0**. The fifth test invokes the helper's **real commit/restore** path against an isolated test USD root/catalog (temporary A-owned directory) and checks that a failed missing-model request does not change any of its four files. No production canonical swap was committed. A second pure Python test composed the canonical referenced USD with actual B events and printed:

```text
PASS canonical referenced Cube Gprim session color M01 Down / AGV02 hidden
PASS AGV2 visible and kit adapter replay from B actual events
```

The same headless pxr scene/replay check was also executed on the isolated Sphere preview with real B seed42 events and yielded `PASS swapped M01 Sphere referenced Gprim session-layer Down color with real B event at t220s; AGV02 hide`, and preview `build_usd.py --validate-only` with matching `--model-override M01=usd/prefabs/alternate_sphere.usda` reported `Manifest structural validation: PASS; USD Stage validation: PASS` (exit 0).

Coordinator-requested reproducible **isolated D3D preview** was later created, without touching canonical stage, by:

```powershell
.\.venv\Scripts\python.exe python/tools/build_usd.py --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap/factory_scene.usda --manifest usd/_preview_swap/equipment_manifest_preview.json
.\.venv\Scripts\python.exe -c "from pxr import Usd; s=Usd.Stage.Open('usd/_preview_swap/factory_scene.usda'); assert s and s.GetPrimAtPath('/World/Factory/Equipment/M01/Geometry/Visual').GetTypeName()=='Sphere'; assert s.GetPrimAtPath('/World/Factory/Equipment/M02/Geometry/Visual').GetTypeName()=='Cube'; print('PASS preview sphere M01 / cube M02 / sublayers',s.GetRootLayer().subLayerPaths)"
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only --out usd/factory_scene.usda --manifest data/equipment_manifest.json
```

All three commands exited **0**. The first reported generated USD and manifest PASS, the second printed `PASS preview sphere M01 / cube M02 / sublayers ['layout.usda']`, and the third printed `Manifest structural validation: PASS; USD Stage validation: PASS`. `FactoryTwinUE/usd/_preview_swap/` remains as an A-owned preview artifact until C finishes Unreal reference swap QA; C's `-FactoryTwinUsdRoot` override can point to this exact stage. UE behavior for the preview is not yet claimed PASS.

Only A-owned canonical USD/manifest was regenerated once before coordinator's notification that Worker C's UE Editor D3D QA should have uncontested access. Thereafter only temporary test stages were written; **no real canonical swap `set_visual_asset.py` commit was attempted while UE was running**. The new helper's commit/rollback path is implemented but its production commit is **NOT RUN pending C synchronization**. Existing B simulation source/events were not edited. `GetGeneratedComponent(.../Geometry)` compatibility on the new Xform anchor is subject to real Worker C UE QA; no UE acceptance claimed. Original P0 official progress remains A32/35 implemented, 8/35 verified; total93%/64% (coordinator record). Kit runtime remains NOT RUN due NVIDIA licensing gate.

### New richer-prefab catalog: 2026-10-20 KST post-final follow-up

Concurrent changes were observed **read-only**: `data/visual_assets.json` was modified at 16:49:19 KST to select `usd/prefabs/factory_machine.usda`, `factory_inspection.usda`, and `factory_agv.usda`. Canonical `usd/layout.usda` was modified 16:49:29. The three detailed prefab files first appeared with 16:50:34 timestamps and were **observed updated again at 16:54:52 and 16:57:23 KST during this review**. Both canonical and current-preview `--validate-only` checks remained PASS after the later update. The project folder itself has no `.git`, so **there is no local commit provenance to identify the modifying worker**. These concurrently authored sources were not edited or replaced by this investigation.

The historical `usd/_preview_swap/layout.usda` (16:42:54 KST) still references `../prefabs/machine.usda` for M02. Running `build_usd.py --validate-only --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap/factory_scene.usda --manifest usd/_preview_swap/equipment_manifest_preview.json` **actually exited 1** with `ERROR: unexpected USD references for M02: ['../prefabs/machine.usda'] != ['../prefabs/factory_machine.usda']`. The historical file is retained as an old-generation artifact, not represented as current compatibility evidence.

A **new isolated preview** was generated against the current detailed models:

```powershell
.\.venv\Scripts\python.exe python/tools/build_usd.py --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap_current/factory_scene.usda --manifest usd/_preview_swap_current/equipment_manifest_preview.json
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap_current/factory_scene.usda --manifest usd/_preview_swap_current/equipment_manifest_preview.json
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only
.\.venv\Scripts\python.exe python/tools/test_model_swap.py
```

**All commands exited 0**. Preview generation reported `Usd.Stage.Open / 7 locations and equipment prims / metadata / references: PASS`; both validate-only runs printed `Manifest structural validation: PASS; USD Stage validation: PASS`; model swap test suite finished **Ran 5 tests in 2.547s, OK**. After the concurrent 16:54:52 prefab edits, the preview and canonical `--validate-only` commands were **run again and both PASS**, with the same 1/25/18/22/22 composed Gprim counts. An additional real `pxr` inspection of both preview and canonical stages checked unchanged `twin:equipmentId` and parent Xform transforms, Z-up/metersPerUnit=1, both location prims, one authored reference per `/Geometry` anchor, and renderable Gprims:
**All commands exited 0**. Preview generation reported `Usd.Stage.Open / 7 locations and equipment prims / metadata / references: PASS`; both validate-only runs printed `Manifest structural validation: PASS; USD Stage validation: PASS`; model swap test suite initially finished **Ran 5 tests in 2.547s, OK**. After the concurrent 16:54:52 prefab edits, the preview and canonical `--validate-only` commands were **run again and both PASS**, with the same 1/25/18/22/22 composed Gprim counts, and the full model-swap test suite was **rerun with 5/5 PASS (2.775s)**. An additional real `pxr` inspection of both preview and canonical stages checked unchanged `twin:equipmentId` and parent Xform transforms, Z-up/metersPerUnit=1, both location prims, one authored reference per `/Geometry` anchor, and renderable Gprims:

| Prim | New preview reference | Composed Gprims |
| --- | --- | ---: |
| M01 | `../prefabs/alternate_sphere.usda` (Sphere) | 1 |
| M02 | `../prefabs/factory_machine.usda` | 25 |
| QC01 | `../prefabs/factory_inspection.usda` | 18 |
| AGV01 | `../prefabs/factory_agv.usda` | 22 |
| AGV02 | `../prefabs/factory_agv.usda` | 22 |

`usd/_preview_swap_current/factory_scene.usda` is ready for Worker C's explicit `-FactoryTwinUsdRoot` Unreal D3D test. **No new D3D or Kit runtime validation is claimed here.** Canonical/catalog/rich prefab files and B/C source and reports remained untouched; original P0 scored baseline stays A32/35 implemented, A8/35 verified, total P0 implementation 93%, verification 64%.
