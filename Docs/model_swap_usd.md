# FactoryTwinUE — 설비 3D 모델 교체 (OpenUSD Reference)

설비의 **ID, 위치, 상태 이벤트, 경로가 바뀌지 않도록** 외형만 교체하는 구조입니다. 외부 모델을 교체해도 C++ 소스 재컴파일은 필요하지 않습니다. Unreal/Kit USD Stage는 교체 후 **다시 로드**해야 합니다.

## 변경하지 않는 계약

`usd/factory_scene.usda`는 `usd/layout.usda`를 sublayer로 둡니다. 설비의 절대 prim 경로는 계속 `/World/Factory/Equipment/M01`, `M02`, `QC01`과 `/World/Factory/AGVs/AGV01`, `AGV02`이며, parent Xform의 authored translate와 `custom string twin:equipmentId`도 그대로입니다. `data/equipment_manifest.json`의 `equipment_id`와 `prim_path`는 그대로 유지합니다.

각 설비에는 항상 **`/Geometry`라는 이름의 Xform anchor**가 있습니다. 그 Xform에 **외부 USD 파일의 `defaultPrim`으로 향하는 단일 reference**가 기록되며, 예제 프리팹의 하위 Gprim 경로는 `/Geometry/Visual`입니다. 게임 이벤트/AGV 동작은 **설비 parent**에 적용합니다. 모델 교체는 하위 참조 프리팹/변환에만 적용됩니다.

```text
/World/Factory/Equipment/M01  (Xform, ID=M01, translate=(-2,2,1) metres)
  /Geometry                   (Xform, scale, rotateXYZ, reference @prefabs/factory_machine.usda@)
    /Visual                   (Cube/Mesh/Sphere/... from the referenced model)
```

## 모델 교체 한 줄 명령

1. 새 모델을 `usd/prefabs/` 또는 `usd/assets/` 등 **프로젝트 내부 `usd/` 폴더**에 `.usd`, `.usda`, `.usdc` 파일로 둡니다. 파일에는 `defaultPrim`이 지정된 **Xform root**가 있어야 하고, 그 하위에 최소 하나의 renderable `Gprim`(Mesh, Cube, Sphere 등)이 있어야 합니다. 모델의 **pivot은 중앙, 기준 길이는 미터, Z-up**, root 변환은 가능하면 identity로 정리합니다. 외부 텍스처/참조는 프로젝트 내부의 상대 경로를 사용합니다. 장비 ID 속성은 이 모델 파일에 넣지 않습니다.
2. 먼저 임시 검증 명령으로 모델을 확인합니다. 다음 명령들은 모두 `FactoryTwinUE` 폴더를 작업 디렉터리로 사용합니다.

```powershell
.\.venv\Scripts\python.exe python/tools/set_visual_asset.py --id M01 --asset usd/prefabs/alternate_sphere.usda --scale 2,2,2 --rotation 0,0,0 --dry-run
```

3. UE Editor와 NVIDIA Kit 등 USD Stage를 읽고 있는 앱을 종료한 다음, `--dry-run`을 빼고 실행하면 **모델 설정과 해당 USD Stage를 함께 갱신**합니다.

```powershell
.\.venv\Scripts\python.exe python/tools/set_visual_asset.py --id M01 --asset usd/prefabs/alternate_sphere.usda --scale 2,2,2 --rotation 0,0,0
```

`--scale`은 X,Y,Z 순서의 **양수 스케일**, `--rotation`은 XYZ 오일러 **각도(degrees)**입니다. 둘 모두 생략하면 해당 ID의 현재 카탈로그 값이 유지됩니다. 카탈로그는 `data/visual_assets.json`이고, 5개 설비 각각에 `model_path`, `scale`, `rotation_deg`가 있습니다. 서로 다른 설비가 동일 프리팹을 공유할 수 있습니다. **현재 정식 카탈로그(2026-10-20 16:49 KST 갱신)는** 상세 설비 프리팹인 `factory_machine.usda`, `factory_inspection.usda`, `factory_agv.usda`를 사용합니다. 이전 단순 플레이스홀더 `machine.usda`, `inspection.usda`, `agv.usda`도 파일로 남아 있으며, 교체 확인용 `alternate_sphere.usda`가 별도로 있습니다.

도구는 모델 경로/변환/ID 유효성과 **실제 pxr Stage.Open으로 모든 reference의 조합 결과**를 먼저 임시 USD/JSON에 생성·검증합니다. 문제가 있으면 정식 `usd/factory_scene.usda`, `usd/layout.usda`, `data/equipment_manifest.json`, `data/visual_assets.json`에 기록하지 않습니다. 정상 교체 후에도 마지막 검증에 실패하면 변경 전 파일 내용을 복구하도록 설계했습니다. `--dry-run`은 항상 정식 4개 파일을 보존합니다. **동일 파일에 대해 UE/Kit이 열려 있거나 다른 작업자가 편집 중이면 적용하지 말아야 합니다.** 다중 파일 쓰기가 하나의 원자적 파일시스템 트랜잭션은 아닙니다.

JSON 파일을 직접 수정하는 것도 가능합니다. `data/visual_assets.json`의 단일 ID 모델 경로/스케일/회전만 변경한 다음 다음을 실행하세요.

```powershell
.\.venv\Scripts\python.exe python/tools/build_usd.py --out usd/factory_scene.usda --manifest data/equipment_manifest.json
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only
```

원본을 건드리지 않고 임시 다른 모델을 확인하려면, `--model-override`와 **별도 `--out` 및 `--manifest`를 모두** 지정합니다. `--model-override`만 주고 정식 파일을 덮어쓰는 호출은 거절됩니다. 예를 들어 A 테스트 스크립트 `python/tools/test_model_swap.py`는 직접 임시 디렉터리를 만들고 이 경로에만 출력합니다.

**현재 상세 프리팹 기준** UE 비교 시연용 Stage는 다음처럼 독립 생성합니다. 생성된 `usd/_preview_swap_current/factory_scene.usda`를 Unreal `-FactoryTwinUsdRoot` 실행 옵션으로 지정합니다. M01만 Sphere이고 M02/QC01/AGV01/AGV02는 현재 카탈로그의 상세 모델을 유지합니다. 원본 `usd/factory_scene.usda`는 그대로 유지합니다.

```powershell
.\.venv\Scripts\python.exe python/tools/build_usd.py --model-override M01=usd/prefabs/alternate_sphere.usda --out usd/_preview_swap_current/factory_scene.usda --manifest usd/_preview_swap_current/equipment_manifest_preview.json
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only --out usd/_preview_swap_current/factory_scene.usda --manifest usd/_preview_swap_current/equipment_manifest_preview.json --model-override M01=usd/prefabs/alternate_sphere.usda
```

`usd/_preview_swap/`은 **16:42 KST에 만든 이전 세대 미리보기**입니다. 그 후 16:49에 카탈로그가, 16:50에 상세 프리팹이 갱신되었으며, 상세 프리팹의 16:54:52 및 16:57:23 추가 수정도 관측했습니다. 예전 `_preview_swap/layout.usda`는 M02에 `../prefabs/machine.usda`를 참조하므로, **현재 카탈로그와 비교하는 `--validate-only`는 의도대로 실패**합니다. 실제 실행은 `unexpected USD references for M02: ['../prefabs/machine.usda'] != ['../prefabs/factory_machine.usda']` (exit 1)을 출력했습니다. 이 파일은 과거 빌드의 재현 증거로 보존하고, 현재 C의 D3D 미리보기 검증에는 `_preview_swap_current`를 사용하세요. 프로젝트 폴더에 `.git` 기록이 없어 상세 프리팹 변경의 작업자 신원은 파일 타임스탬프만으로 확정할 수 없습니다.

## 검증/한계 (2026-10-20 KST 실제 실행)

```powershell
.\.venv\Scripts\python.exe -m py_compile python/tools/build_usd.py python/tools/set_visual_asset.py python/tools/test_model_swap.py exts/com.factory.twin/factory/twin/extension.py
.\.venv\Scripts\python.exe python/tools/test_model_swap.py
.\.venv\Scripts\python.exe python/tools/build_usd.py --validate-only
```

- **PASS:** 실제 `pxr.Usd.Stage.Open`으로 5개 설비 ID, 2개 location, sublayer, 단일 reference/Geometry Xform, Z-up, `metersPerUnit=1.0` 확인.
- **PASS:** M01 Cube 모델을 임시 USD에서 Sphere 모델로 교체 시 실제 Gprim type과 `UsdGeom.BBoxCache` 월드 바운딩박스 변화, M01 ID/parent 위치 불변 확인.
- **PASS:** 같은 stage 파일을 반복 생성해도 이전 reference가 쌓이지 않음. USD `Sdf.Layer.Reload(force=True)`로 동일 Python 프로세스에서 기존 캐시가 남는 오류를 방지.
- **PASS:** 독립 preview stage를 실제 생성·재개방하여 `M01/Geometry/Visual=Sphere`, `M02/Geometry/Visual=Cube`, sublayer=`layout.usda` 확인. Unreal D3D 실제 비교는 Worker C의 별도 증거 필요.
- **PASS (상세 카탈로그 갱신 후 재검증):** 새 `_preview_swap_current`에 정확히 다섯 `/Geometry` reference가 구성됨을 실제 `pxr.Stage.Open`으로 확인했습니다. M01은 `alternate_sphere.usda` (Gprim 1개), M02는 `factory_machine.usda` (25개), QC01은 `factory_inspection.usda` (18개), AGV01/02는 `factory_agv.usda` (각 22개)입니다. 원본 Stage와 parent ID·Xform 위치가 같으며 2개 location·Z-up·1m 유지. 현재 카탈로그로 모델 교체 테스트 **5/5 PASS (2.547초)**.
- **PASS:** 경로 탈출/절대 경로/없는 USD/잘못된 scale·rotation 거부, CLI 임시 override가 정식 파일에 쓰지 못함, dry-run PASS/없는 프리팹 FAIL 후 정식 파일 SHA-256 동일.
- **PASS:** `set_visual_asset.py`의 실제 COMMITTED 교체와 원래 모델로의 복귀도 *독립 임시 stage/catalog*에 대해서만 실행해 검증했습니다. 그 사이 없는 모델 교체 요청이 실패해도 해당 임시 파일 4개의 SHA-256이 유지됨을 확인했습니다. 정식 Stage의 모델 교체는 C의 실행 검증이 끝날 때까지 실행하지 않았습니다.
- **PASS (Kit 외부 pxr headless):** B의 실제 이벤트로 M01 Down 시 Gprim 세션 색상 변경, AGV1에서 AGV02 hide / AGV2에서 show.
- **NOT RUN:** 실제 NVIDIA Kit Extension enable/disable/reload, Unreal USD importer의 reference Xform `/Geometry` generated component/visual bounds/AGV 이동 및 렌더링. C 담당 Unreal D3D QA 결과를 별도로 확인해야 합니다. 당시 Kit 앱 설치는 사용자 NVIDIA 약관 동의 단계에서 중단되었습니다.

현재 기존 P0 공식 수치 **A 구현 32/35, A 검증 8/35, 전체 구현 93%, 검증 64%**는 모델 교체 개선과 구분합니다. 새 테스트 PASS가 곧 기존 Kit/UE 실기기 PASS를 의미하지 않습니다.

## 공장 cutaway 및 상세 USD 프리팹 (후속 추가)

`python/tools/build_factory_visuals.py`를 실행하면 CNC·검사 장비·AGV 상세 프리팹과 공장 외관 `usd/factory_environment.usda`를 각각 갱신합니다. 최종 장면은 외관 안전 펜스·작업 구역·팔레트·차량 통로를 별도 sublayer로 유지하면서 가까운 외벽을 낮춰 UE 카메라에서 내부가 가려지지 않습니다. `python/tools/test_factory_appearance.py` 3/3 및 기존 모델 교체 테스트 5/5 PASS. 새 상세 모델의 Unreal D3D11 AGV 1대/2대 모드는 `Docs/unreal_d3d11_factory_final_agv{1,2}.log`에서 **각 4장 캡처 및 `FACTORYTWIN_VISUAL_QA_PASS`** 확인했습니다. 독립 Blender 에셋 생성기는 `python/tools/generate_blender_assets.py` 및 `art/blender/README.md` 참조, Blender MCP 실행은 연결되지 않아 NOT RUN입니다.
