# FactoryTwinUE — Worker A environment evidence (2026-10-20 KST)

The probes below were executed in Windows PowerShell 5.1, working directory `F:\GitHubRep\OpenUSD_Omniverse Kit` (`/openusd_omniverse-kit` in the linked workspace). This is a development environment report, **not** evidence of successful NVIDIA Kit runtime execution.

| Check | Actually observed | Status |
|---|---|---|
| Host OS | `Get-CimInstance Win32_OperatingSystem`: Windows 11 Pro, 10.0.26200, 64-bit | PASS (detected) |
| Existing repository / fresh project | `git status --short --branch` -> `fatal: not a git repository (or any of the parent directories): .git`; `Test-Path FactoryTwinUE` -> False at start | NOT A REPOSITORY / fresh project |
| Unreal | `Test-Path F:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe` -> True; `Engine\Build\Build.version`: 5.8.3, changelist 58210709 | PASS (files present); UE launch NOT RUN |
| Windows C++ toolchain | `vswhere -latest -products '*' -property installationPath` -> `C:\Program Files\Microsoft Visual Studio\18\Community`; MSVC Tools folder contains `14.51.36231` | PASS (files present); compiler invocation NOT RUN |
| Python launcher | `py -0p`: Python 3.14 and Anaconda Python 3.9; `py -3.14 --version` -> 3.14.5, Anaconda Python -> 3.9.13 | PASS |
| `python` shell alias | `Get-Command python` -> `C:\Users\hoon8\AppData\Local\Microsoft\WindowsApps\python.exe`; `python --version` showed `Python` without a numeric version | UNUSABLE as a reliable CLI; use `py -3.14` |
| pxr (global 3.14) | `py -3.14 -c "import importlib.util; print(importlib.util.find_spec('pxr'))"` -> `None` | MISSING globally |
| pxr (Anaconda 3.9) | `C:\Users\hoon8\anaconda3\python.exe -c "import importlib.util; print(importlib.util.find_spec('pxr'))"` -> `None` | MISSING |
| GPU | `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader` -> `NVIDIA GeForce RTX 3070 Ti, 560.94, 8192 MiB`; `--query-gpu=compute_cap` -> 8.6 | PASS (detected); Kit compatibility NOT RUN |
| NVIDIA Kit / template | `Get-Command kit.exe,kit,repo.bat` -> no output; targeted folder existence checks for `%LOCALAPPDATA%\ov\pkg`, `C:\Program Files\NVIDIA Corporation\Omniverse`, `F:\Omniverse`, `F:\GitHubRep\kit-app-template` -> all False | NOT FOUND in probed locations; Kit app startup NOT RUN |
| Unreal USDImporter | `Test-Path F:\UE_5.8\Engine\Plugins\Importers\USDImporter` -> True | Files present; USD Stage import NOT RUN |
| Project-local USD wheel | `py -3.14 -m venv .venv`; `.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --only-binary=:all: usd-core==26.8` -> `Successfully installed usd-core-26.8`; `.\.venv\Scripts\python.exe -c "from pxr import Usd; print(Usd.GetVersion())"` -> `(0, 26, 8)` | PASS, isolated install |
| Generated USD stage | `.\.venv\Scripts\python.exe python/tools/build_usd.py --out usd/factory_scene.usda --manifest data/equipment_manifest.json` -> `Writer: pxr.Usd/UsdGeom`; `Usd.Stage.Open / 7 locations and equipment prims / metadata: PASS` | PASS (`pxr` parsing on local Python) |

## Repeatable diagnostics

```powershell
git status --short --branch
py -0p
py -3.14 --version
py -3.14 -c "import importlib.util; print(importlib.util.find_spec('pxr'))"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
Get-Content 'F:\UE_5.8\Engine\Build\Build.version'
Get-Command kit.exe,repo.bat -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe python/tools/build_usd.py --out usd/factory_scene.usda --manifest data/equipment_manifest.json
```

**USD-only validation has now succeeded** using `usd-core==26.8` inside `FactoryTwinUE/.venv`. Kit `omni.ext.IExt` startup/shutdown, GUI capture, and UE stage size checks are **NOT RUN**. Nothing was installed into global Python, and the parent UE project was not modified. `build_usd.py` includes a deterministic USDA text fallback for environments without `pxr`, but fallback text generation is explicitly distinct from a real OpenUSD parser or Kit runtime PASS.

## Follow-up Kit machine/SDK probe (2026-10-20 KST)

The scope-expanded installation/registrations check still found **no previously installed Kit executable**: `Get-Command kit.exe,repo.bat,kit.cmd,isaac-sim.bat` produced no installation command; `Get-Process | Where-Object ProcessName -Match 'kit|omni|isaac'` found none; `Get-StartApps` Omniverse/Kit/Isaac name filter returned zero rows; HKLM/HKCU uninstall registry DisplayName Omniverse/Kit/Isaac filters returned zero. Targeted probes of `%LOCALAPPDATA%\ov`, `%LOCALAPPDATA%\ov\cache`, `%APPDATA%\Kit`, `C:\Program Files\NVIDIA Corporation\Kit`, `C:\Program Files\NVIDIA Corporation\Omniverse`, `C:\ProgramData\NVIDIA Corporation\Omniverse`, `F:\Kit` and `F:\Omniverse` were false. This is a targeted search of installed app conventions, **not** an exhaustive search of every disk byte.

Drive space measured with `Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'`: **C 27.5GB free (464.7GB total), D 227.6GB (931.5), E 208.1GB (953.9), F 146.4GB (1863), G 63.6GB (931.5)**. Host memory `Get-CimInstance Win32_ComputerSystem` = **31.9GB**. NVIDIA GeForce RTX3070Ti/driver 560.94 was confirmed earlier with `nvidia-smi`; official template states Windows driver >=551.78, while the 2026 technical requirements page lists validated Windows Ampere/GeForce driver versions 581.42 or 595.97. Installed driver is above the template's listed lower bound; **no current Kit binary launched, so do not infer full compatibility**.

Official docs:

- https://github.com/NVIDIA-Omniverse/kit-app-template (template, licensing, Windows prerequisites)
- https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html (October 2026 validated GPU drivers; Kit Windows 11, 16GB RAM, RTX3070 and 250GB storage minimum specification)

We cloned an **official** shallow `kit-app-template` at `FactoryTwinUE/exts/_kit_app_template_probe`. Its `repo.bat --help` bootstrapped Packman/Repo and passed (repoman 2.9.6), while `repo.bat template new` stopped at explicit NVIDIA software/product terms Yes/No license prompt; no user assent was entered. The generated `repo.bat` bootstrap automatically created `F:\packman-repo` and set the user-scoped `PM_PACKAGES_ROOT` variable to that path. The **new variable was explicitly restored to its previously absent state** via `[Environment]::SetEnvironmentVariable('PM_PACKAGES_ROOT',$null,'User')`, verified afterward by an empty user-scoped read. The Packman cache directory remains at `F:\packman-repo` because cleaning an external system cache was outside this work assignment. SDK build, Kit launch, real `omni.ext` lifecycle, real `omni.ui` and screenshots are **NOT RUN**. See `Docs/kit_evidence.md` for exact commands and runtime integration output.
