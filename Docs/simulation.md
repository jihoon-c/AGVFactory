# Worker B — 결정적 공정 시뮬레이션 및 파일 계약

## 실행 환경 / 담당

- Python 표준 라이브러리만 사용. 설치 의존성이 없으며 `python/factory_sim`이 공정 상태의 유일한 권위자다.
- `data/scenarios/agv_1.json`, `agv_2.json`은 `agv_count`, `scenario_id`를 제외하고 동일하다.
- 모든 수치는 가상 물류 셀의 **합성 시뮬레이션** 결과다. 실제 센서, MES, Isaac Sim, AGV 충돌 제어·pathfinding 데이터는 사용하지 않는다.

## Kit Worker A 호출 계약

실행 위치: 통합 프로젝트 루트 `FactoryTwinUE`, Python import 경로에 이 디렉터리의 `python` 포함. 초기 B 산출물 원본은 형제 폴더 `FactoryTwinUE_JobStack_OneWeek`에 보존되어 있다.

```python
from factory_sim import run_scenario
from factory_sim.runner import save_run

result = run_scenario("data/scenarios/agv_2.json", seed=42)
# result.config: validated dict; result.seed: int
# result.events: list[dict] / result.jsonl(): canonical replay bytes as UTF-8 str
# result.kpi: dict of 10 CSV columns; result.jobs: terminal job snapshots
save_run(result, out="Reports/run_agv_2_seed42.jsonl", kpi_out="Reports/kpi.csv")
completed = result.kpi["completed_jobs"]
throughput = result.kpi["throughput_per_hour"]
```

`run_scenario`는 동기식 함수다. Kit 앱 UI 응답성을 위해 extension 담당자가 Kit의 지원하는 별도 작업 실행 패턴을 선택하고, UI 객체 접근은 메인 스레드 규칙을 지켜야 한다.

## UE Worker C 이벤트 해석 계약

장비 ID는 `M01`, `M02`, `QC01`, `AGV01`, `AGV02`만 허용한다. 1 AGV scenario에서는 AGV02 이벤트가 존재하지 않으며 정적 USD asset의 AGV02는 숨긴다. `simulation_time_ms`는 가상 시간의 밀리초 정수로, 1초 tick이며 `event_id`는 1에서 시작하여 연속 증가한다. 같은 시간의 순서는 `(time, phase priority, equipment_id, sequence)`로 고정되어 있고 `event_id`를 최종 순서로 사용한다.

`state_changed`가 **상태/표시 변경 명령**이다. `state`는 기계에서 `Idle/Busy/Down`, 검사대에서 `Idle/Busy`, AGV에서 `Idle/Moving`만 가능하다. AGV 이벤트의 `waypoint`는 대상(`Moving`) 또는 도착지(`Idle`) ID이며 UE는 USD 배치의 대응 지점을 lookup하여 옮긴다. waypoint 자체는 월드 좌표가 아니다.

`job_arrived`, `job_completed` 이벤트는 **성과 재계산용 관찰 이벤트**다. `state`는 `null`이며 `job_id`가 존재한다. **상태 material에 적용하지 않고 skip**한다. 이 두 이벤트가 추가되어도 이벤트 필터는 record order와 ID 순서를 검증해야 한다.

JSONL 최소 예시(실제 시드 42 데이터의 처음 2개):

```jsonl
{"equipment_id":"AGV01","event_id":1,"event_type":"state_changed","job_id":null,"schema_version":1,"simulation_time_ms":0,"state":"Idle","waypoint":"INBOUND"}
{"equipment_id":"M01","event_id":2,"event_type":"state_changed","job_id":null,"schema_version":1,"simulation_time_ms":0,"state":"Idle"}
```

## 공정 모델 가정

`INBOUND → (M01 또는 M02) → QC01 → OUTBOUND` 흐름이다. 작업 생성 간격 12초, 운송 leg마다 12초, M01=30초, M02=40초, QC=8초. AGV는 한 번에 작업 하나를 맡는다. 모든 운송 요청은 생성 순서 FIFO, AGV 선택은 ID 순서다. AGV의 빈 차 복귀 거리/시간, 동적 경로계획, 물리 충돌은 계산하지 않으며 이동은 waypoint 기반 이벤트만 제공한다.

시드에 의해 작업별 M01/M02 선택 순서가 정해지므로 같은 시드의 1/2 AGV 실험은 유입 작업과 대상 설비가 동일하다. 고장 200초 `M01 Down` → 260초 `M01 Repair` 역시 양 조건이 같다. Down 동안 가공 타이머를 일시 정지하며 복구 후 남은 시간부터 재개한다. 같은 틱에서 고장과 가공 완료가 겹치면 고장이 우선이다.

CSV `event_hash`는 최종 JSONL UTF-8 bytes에 대한 SHA-256이며 줄 구분 `\n`, key 정렬, compact JSON serialization을 사용한다. `mean_lead_time_seconds`는 실제 완료한 작업의 `(완료 - 유입)` 평균이며 완료 0건이면 CSV 빈칸(`null`)이다. `m01/m02_busy_fraction`은 timestamp 구간별 `Busy` 시간 / 전체 실행시간(고장 `Down` 시간 제외). `arrived_jobs = completed_jobs + unfinished_jobs`를 검사한다.

## 표준 CLI (PowerShell)

```powershell
$env:PYTHONPATH='python'
py -m factory_sim.runner --scenario data/scenarios/agv_1.json --seed 42 --out Reports/run_agv_1_seed42.jsonl --kpi-out Reports/kpi.csv
py -m factory_sim.runner --scenario data/scenarios/agv_2.json --seed 42 --out Reports/run_agv_2_seed42.jsonl --kpi-out Reports/kpi.csv
py python/tools/compare.py --csv Reports/kpi.csv --out Reports/compare.md
py -m unittest discover -s tests -v
```

실험 B04는 42, 43, 44를 양 시나리오에서 모두 실행하고 `compare.py`로 **동일 시드 paired** 평균·차이를 계산한다. 한쪽 실행 누락이나 인위적인 KPI 수정 값은 거부한다. JSONL과 KPI의 파일 쓰기는 각각 임시 파일 + `os.replace`이며 다중 파일 전체를 하나의 원자적 트랜잭션으로 묶지는 않는다. 공통 `kpi.csv`에 여러 프로세스가 동시에 쓰지 않도록 각 CLI 실행을 순차 수행한다.

## 검증 범위

`tests/test_factory_sim.py`는 V05(결정성), V06(작업 보존), V07(고장 및 상태), V08(시드 실험), V11(JSONL malformed/중복·누락 ID) 검증을 목적으로 한다. Manifest ↔ USD custom attr의 실제 대조는 A의 `pxr` 검증, UE replay 실행은 C의 UE QA이며 이 테스트로 대신할 수 없다.

## 2026-10-20 B01~B05 실행 증거 / coordinator 인수인계

- 환경: Windows PowerShell, `py -V` → `Python 3.14.5`; `python --version`은 실행 불가(exit 9009), `py` 런처 사용.
- Git: 선택된 `/openusd_omniverse-kit`는 `git status --short`에서 `fatal: not a git repository`(exit 128). 기존 UE 루트 프로젝트의 파일은 변경하지 않았다. 초기 B 구현은 독립 지시서 디렉터리에 작성되었고, 2026-10-20 coordinator가 파일 충돌 없이 `FactoryTwinUE` 프로젝트 로컬로 복사 통합했다.
- `py -m unittest discover -s tests -v` → **23 tests, OK / PASS**. V05 결정성, V06 작업 보존, V07 M01 Down/Repair, V11 malformed/duplicate ID/unsorted 등의 입력 실패 검증, V08 A/B 샘플 및 비교 테스트를 수행했다.
- `py -m compileall -q python/factory_sim python/tools/compare.py tests` → **PASS (exit 0)**.
- `py -m factory_sim.runner` 1/2 AGV × seeds 42,43,44 → **6/6 PASS**. `Reports/run_agv_{1,2}_seed{42,43,44}.jsonl`, `Reports/kpi.csv` 실제 생성.
- `py python/tools/compare.py --csv Reports/kpi.csv --out Reports/compare.md` → **PASS**. `Reports/compare.md`는 CSV에서 재계산한 평균/차이이며 KPI 필드의 `event_hash`는 해당 JSONL의 SHA-256과 6/6 일치함.

| 시드 | AGV 1 완료 | AGV 2 완료 | 각 조건 유입 |
|---:|---:|---:|---:|
| 42 | 49 | 153 | 300 |
| 43 | 48 | 155 | 300 |
| 44 | 48 | 154 | 300 |
| 평균 | 48.3333 | 154.0000 | 300 |

평균 완료 리드타임: AGV1 1575.0187초, AGV2 916.1403초. 가상 1시간 모델의 예시 결과이며 성능 우위를 산업 환경으로 일반화할 수 없다.

**Worker B 검증·점수 승인 요청(원본 보고):** B01 11점, B02 7점, B03 4점, B04 4점, B05 4점. 구현 합계 **30/30 (100%)**, 검증 합계 **30/30 (100%)**의 근거 파일/테스트를 제출한다. 아래는 작성 당시의 Worker B 독립 보고이며 공식 승인치는 항상 `FactoryTwinUE_JobStack_OneWeek/07_PROGRESS.md`를 참조한다. **P1 CAD: NOT RUN / P2 Isaac: NOT RUN**.

### A/C에 넘길 구체 인터페이스

- A: `from factory_sim import run_scenario` → `SimulationResult.events / .kpi`; `from factory_sim.runner import save_run`으로 바로 JSONL/CSV 저장. 시작 시 `PYTHONPATH=python` 확인.
- C: `Reports/run_agv_2_seed42.jsonl`로 우선 replay 확인. `state_changed`는 apply, `job_arrived`/`job_completed`는 통계 기록용으로 skip; `job_id`는 작업 연결 식별자로만 사용. AGV 상태 이벤트의 `waypoint`는 대상 위치 ID이며 실제 좌표계 변환은 USD scene에 따름. 동일 시각의 여러 이벤트는 파일 순서(`event_id`)로 처리.
- **통합 미검증:** A의 `pxr`/Kit 앱 실행 및 manifest ↔ 실제 USD attr, C의 UE USD Stage/replay 화면, 전체 Kit→UE smoke는 각 소유자의 결과가 필요하며 이 문서는 이를 PASS라고 주장하지 않는다.
