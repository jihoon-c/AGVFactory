"""FactoryTwin NVIDIA Kit Extension.

Run inside a real Kit app with `omni.ext`, `omni.usd` and `omni.ui` available.
The Python `factory_sim.runner` (owned by worker B) is the single source of
state/KPIs. This module never synthesizes or displays fabricated results.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib
import importlib.util
import json
import logging
from pathlib import Path
import sys
from typing import Any

import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Gf, Usd, UsdGeom


LOGGER = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[4]
ROOT_USD = PROJECT / "usd" / "factory_scene.usda"
MANIFEST = PROJECT / "data" / "equipment_manifest.json"
SIM_PYTHON = PROJECT / "python"

ID_TO_PATH = {
    "M01": "/World/Factory/Equipment/M01",
    "M02": "/World/Factory/Equipment/M02",
    "QC01": "/World/Factory/Equipment/QC01",
    "AGV01": "/World/Factory/AGVs/AGV01",
    "AGV02": "/World/Factory/AGVs/AGV02",
}
STATE_COLORS = {
    "Idle": (0.48, 0.48, 0.48),
    "Busy": (0.25, 0.78, 0.35),
    "Down": (0.90, 0.20, 0.23),
    "Moving": (0.20, 0.50, 0.95),
}


def validate_scene_and_manifest() -> dict[str, str]:
    """Read actual composed USD attributes; reject stale/ambiguous IDs."""
    if not ROOT_USD.is_file() or not MANIFEST.is_file():
        raise FileNotFoundError("Generate the USD scene and equipment_manifest.json first")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("usd_root") != "usd/factory_scene.usda":
        raise ValueError("unsupported manifest version or root")
    rows = data.get("equipment")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("manifest must contain exactly five equipment records")
    stage = Usd.Stage.Open(str(ROOT_USD))
    if not stage:
        raise ValueError(f"Usd.Stage.Open failed: {ROOT_USD}")
    if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        raise ValueError("stage upAxis is not Z")
    if abs(UsdGeom.GetStageMetersPerUnit(stage) - 1.0) > 1e-9:
        raise ValueError("stage metersPerUnit is not 1.0")
    ids: dict[str, str] = {}
    used_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid manifest equipment object")
        identity, path = row.get("equipment_id"), row.get("prim_path")
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError(f"empty or duplicate equipment_id: {identity!r}")
        if not isinstance(path, str) or not path or path in used_paths:
            raise ValueError(f"empty or duplicate prim_path: {path!r}")
        if path != ID_TO_PATH.get(identity):
            raise ValueError(f"unexpected path for {identity}: {path}")
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid():
            raise ValueError(f"missing USD prim: {path}")
        attr = prim.GetAttribute("twin:equipmentId")
        if not attr.IsValid() or not attr.IsCustom() or attr.Get() != identity:
            raise ValueError(f"USD equipmentId mismatch: {identity} at {path}")
        ids[identity] = path
        used_paths.add(path)
    if set(ids) != set(ID_TO_PATH):
        raise ValueError("missing expected equipment ID")
    for prim in stage.Traverse():
        attr = prim.GetAttribute("twin:equipmentId")
        if attr.IsValid() and (prim.GetPath().pathString not in used_paths or not attr.IsCustom()):
            raise ValueError(f"unexpected tagged USD prim: {prim.GetPath()}")
    return ids


def _mapping(value: Any) -> dict:
    """Accept B runner dict/dataclass/object for display, without making values up."""
    if isinstance(value, dict):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value)
    return {}


def _normalize_events(events: Any) -> list[dict[str, Any]]:
    if events is None:
        return []
    if isinstance(events, (str, Path)):
        path = Path(events)
        if not path.is_file():
            raise ValueError(f"event file does not exist: {path}")
        with path.open("r", encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    if not isinstance(events, (list, tuple)):
        raise ValueError("runner events must be list/tuple or existing JSONL path")
    result: list[dict[str, Any]] = []
    last_key = (-1, -1)
    for i, event in enumerate(events):
        row = _mapping(event)
        moment, event_id = row.get("simulation_time_ms"), row.get("event_id")
        if (not isinstance(moment, int) or isinstance(moment, bool) or moment < 0 or
                not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0):
            raise ValueError(f"malformed replay timestamp/event ID at row {i}")
        key = (moment, event_id)
        if key <= last_key:
            raise ValueError(f"out-of-order/duplicate event at row {i}")
        if event_id != i + 1:
            raise ValueError(f"event_id must be sequential from 1, row {i}: {event_id}")
        last_key = key
        identity = row.get("equipment_id")
        if identity is not None and identity not in ID_TO_PATH:
            raise ValueError(f"unknown equipment ID in event: {identity}")
        if row.get("event_type") == "state_changed":
            if identity not in ID_TO_PATH:
                raise ValueError(f"state_changed must include known equipment_id at row {i}")
            if row.get("state") not in STATE_COLORS:
                raise ValueError(f"unknown state for {identity}: {row.get('state')}")
        result.append(row)
    return result


def _run_worker_b(count: int) -> tuple[dict, list[dict[str, Any]], Path, Path, str]:
    """Run B03, publish through B's verified save_run API, then return evidence.

    A pre-existing canonical event JSONL is only overwritten if its raw
    event_hash equals this deterministic run. Otherwise Kit writes separately
    named outputs, leaving another worker's replay evidence intact.
    """
    config_path = PROJECT / "data" / "scenarios" / f"agv_{count}.json"
    if not config_path.is_file():
        raise RuntimeError(f"B03 BLOCKED: missing scenario JSON: {config_path}")
    if str(SIM_PYTHON) not in sys.path:
        # Inserted also on startup; guard supports direct function tests.
        sys.path.insert(0, str(SIM_PYTHON))
    try:
        runner = importlib.import_module("factory_sim.runner")
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("B03 BLOCKED: factory_sim.runner is unavailable") from exc
    run_scenario = getattr(runner, "run_scenario", None)
    save_run = getattr(runner, "save_run", None)
    if not callable(run_scenario):
        raise RuntimeError("B03 BLOCKED: run_scenario(config, seed) is not callable")
    if not callable(save_run):
        raise RuntimeError("B03 BLOCKED: save_run(result, out, kpi_out) is unavailable")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("agv_count") != count:
        raise ValueError(f"scenario agv_count mismatch: {config_path}")
    raw = run_scenario(config, 42)
    result = _mapping(raw)
    if not result:
        raise ValueError("runner returned no structured result; measured KPI unavailable")
    kpi = _mapping(result.get("kpi", result.get("kpis", result)))
    # The run must actually produce numerical KPI; do not mistake an object for a measurement.
    if not any(isinstance(kpi.get(k), (int, float)) and not isinstance(kpi.get(k), bool)
               for k in ("completed_jobs", "throughput_per_hour", "mean_lead_time_seconds")):
        raise ValueError("runner returned no measured KPI fields")
    events = result.get("events", result.get("event_log", result.get("events_path")))
    replay = _normalize_events(events)
    digest = kpi.get("event_hash")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("runner did not return an event_hash SHA-256 digest")
    if not callable(getattr(raw, "jsonl", None)):
        raise ValueError("runner result cannot be serialized by B's canonical jsonl()")
    if hashlib.sha256(raw.jsonl().encode("utf-8")).hexdigest() != digest:
        raise ValueError("runner event hash mismatch before file write")
    reports = PROJECT / "Reports"
    canonical = reports / f"run_agv_{count}_seed42.jsonl"
    kpi_path = reports / "kpi.csv"
    output = canonical
    if canonical.exists() and hashlib.sha256(canonical.read_bytes()).hexdigest() != digest:
        # Previous output belongs to a different config/code version. Keep it.
        output = reports / f"kit_run_agv_{count}_seed42.jsonl"
        kpi_path = reports / "kit_kpi.csv"
    save_run(raw, out=output, kpi_out=kpi_path)
    written_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    if written_hash != digest or not kpi_path.is_file():
        raise RuntimeError("B03 save_run outputs could not be verified")
    return kpi, replay, output, kpi_path, digest


def _generate_scene_from_shared_builder() -> str:
    """Execute the authored A02 OpenUSD generator; no mock USD stage."""
    builder = PROJECT / "python" / "tools" / "build_usd.py"
    spec = importlib.util.spec_from_file_location("factorytwin_usd_builder", builder)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"USD generator import failed: {builder}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate(ROOT_USD, MANIFEST)


class FactoryTwinExtension(omni.ext.IExt):
    """Kit lifecycle + async stage opening + deterministic B03 UI adapter."""

    def on_startup(self, ext_id: str) -> None:
        self._ext_id = ext_id
        self._active = True
        self._tasks: set[asyncio.Task] = set()
        self._window = None
        self._agv_count = 1
        self._run_inflight = False
        self._run_generation = 0
        self._events: list[dict[str, Any]] = []
        self._display_ids: dict[str, str] = {}
        self._current_time_ms = 0
        self._current_duration_seconds = 3600
        self._inserted_sys_path = False
        if str(SIM_PYTHON) not in sys.path:
            sys.path.insert(0, str(SIM_PYTHON))
            self._inserted_sys_path = True
        self._window = ui.Window("FactoryTwin | OpenUSD & Scenarios", width=500, height=430)
        with self._window.frame:
            with ui.VStack(spacing=9):
                ui.Label("FactoryTwin — shared USD factory cell", height=25)
                with ui.HStack(height=30):
                    ui.Button("Generate USD", clicked_fn=self._request_generate_scene)
                    ui.Button("Load USD", clicked_fn=self._request_open_scene)
                self._scene_label = ui.Label("USD: not loaded", word_wrap=True, height=38)
                with ui.HStack(height=32):
                    ui.Label("AGV count", width=95)
                    ui.Button("1", clicked_fn=lambda: self._select_agv(1), width=45)
                    ui.Button("2", clicked_fn=lambda: self._select_agv(2), width=45)
                    self._agv_label = ui.Label("selected: 1", height=24)
                ui.Button("Run Scenario (seed 42)", clicked_fn=self._request_run, height=32)
                self._status_label = ui.Label("Ready; load USD, select AGVs, and run scenario", word_wrap=True, height=45)
                self._kpi_label = ui.Label("KPI: no measured results", word_wrap=True, height=48)
                self._output_label = ui.Label("Replay file: not generated", word_wrap=True, height=42)
                ui.Label("Replay time (virtual seconds; events from actual runner):", height=20)
                self._slider = ui.IntSlider(min=0, max=3600, height=20)
                self._slider.model.add_value_changed_fn(self._time_changed)
                self._time_label = ui.Label("0 s / 3600 s; no events", height=23)
        LOGGER.info("FactoryTwin extension started: %s", ext_id)

    def on_shutdown(self) -> None:
        self._active = False
        for task in tuple(getattr(self, "_tasks", ())):
            task.cancel()
        self._tasks.clear()
        if getattr(self, "_window", None) is not None:
            self._window.visible = False
            # NVIDIA's official UI-window extension destroys native windows on
            # shutdown; hiding alone can leave a duplicate on re-enable.
            self._window.destroy()
            self._window = None
        self._slider = None
        self._scene_label = None
        self._status_label = None
        self._kpi_label = None
        self._output_label = None
        self._agv_label = None
        self._time_label = None
        self._events = []
        self._display_ids = {}
        if getattr(self, "_inserted_sys_path", False) and str(SIM_PYTHON) in sys.path:
            sys.path.remove(str(SIM_PYTHON))
        LOGGER.info("FactoryTwin extension shut down: %s", getattr(self, "_ext_id", "unknown"))

    def _set_status(self, message: str) -> None:
        LOGGER.info("FactoryTwin: %s", message)
        if self._active and self._status_label is not None:
            self._status_label.text = message

    def _start_task(self, coroutine: Any) -> None:
        if not self._active:
            return
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _request_open_scene(self) -> None:
        self._start_task(self._open_scene())

    def _request_generate_scene(self) -> None:
        self._start_task(self._generate_scene())

    async def _generate_scene(self) -> None:
        self._set_status("Generating authored USD scene and equipment manifest...")
        try:
            loop = asyncio.get_running_loop()
            writer = await loop.run_in_executor(None, _generate_scene_from_shared_builder)
            if self._active:
                self._set_status(f"USD authored via {writer}; loading into Kit...")
                await self._open_scene()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("FactoryTwin USD generation failed")
            self._set_status(f"USD GENERATION ERROR: {exc}")

    async def _open_scene(self) -> None:
        self._set_status("Validating USD and 5 equipment IDs...")
        try:
            ids = validate_scene_and_manifest()
            # omni.usd stage must be opened in the app, not merely in standalone pxr.
            result = await omni.usd.get_context().open_stage_async(str(ROOT_USD))
            success, reason = result if isinstance(result, tuple) else (bool(result), "")
            if not success:
                raise RuntimeError(f"Kit omni.usd.open_stage_async failed: {reason}")
            stage = omni.usd.get_context().get_stage()
            if stage is None or not stage.GetPrimAtPath(ids["M01"]).IsValid():
                raise RuntimeError("Kit stage missing /World/Factory/Equipment/M01")
            # A user may have replaced a prefab in visual_assets.json and
            # regenerated layout.usda while this USD file remains cached.
            # The Load USD button explicitly refreshes composed references.
            stage.Reload()
            for identity, path in ids.items():
                attr = stage.GetPrimAtPath(path).GetAttribute("twin:equipmentId")
                if not attr.IsValid() or attr.Get() != identity:
                    raise ValueError(f"Kit USD metadata mismatch: {identity}")
            if not self._active:
                return
            self._display_ids = ids
            self._scene_label.text = f"USD loaded in Kit | Z-up | 1m | {len(ids)} equipment IDs"
            self._set_status("Kit USD Stage.Open: 5 identities verified")
            self._apply_timeline(self._current_time_ms)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("FactoryTwin USD scene open failed")
            self._set_status(f"USD ERROR: {exc}")

    def _select_agv(self, count: int) -> None:
        if count not in (1, 2):
            raise ValueError("AGV count must be 1 or 2")
        self._agv_count = count
        self._run_generation += 1
        self._events = []
        self._current_time_ms = 0
        self._agv_label.text = f"selected: {count}"
        self._kpi_label.text = "KPI: run this AGV scenario for measured results"
        self._output_label.text = "Replay file: not generated for selected scenario"
        self._slider.model.set_value(0)
        self._set_status(f"Selected AGV={count}; run to obtain measured KPI")
        self._apply_timeline(self._current_time_ms)

    def _request_run(self) -> None:
        if self._run_inflight:
            self._set_status("Scenario still running; complete it before starting another")
            return
        self._run_inflight = True
        self._start_task(self._run_scenario())

    async def _run_scenario(self) -> None:
        count = self._agv_count
        generation = self._run_generation
        self._kpi_label.text = "KPI: running verified B03 scenario..."
        self._output_label.text = "Replay file: pending verified save_run output"
        self._set_status(f"Running worker B scenario AGV={count}, seed=42...")
        try:
            loop = asyncio.get_running_loop()
            kpi, events, event_file, kpi_file, digest = await loop.run_in_executor(None, _run_worker_b, count)
            if not self._active:
                return
            if generation != self._run_generation:
                self._set_status("Scenario selection changed; previous run saved, select Run again")
                return
            self._events = events
            config_path = PROJECT / "data" / "scenarios" / f"agv_{count}.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            duration = config.get("duration_seconds", 3600)
            if not isinstance(duration, int) or duration <= 0:
                raise ValueError("scenario duration_seconds must be positive int")
            self._current_duration_seconds = duration
            self._slider.max = duration
            self._current_time_ms = 0
            self._slider.model.set_value(0)
            # An actual returned KPI field appears only when B produced one.
            labels = [("completed_jobs", "completed"),
                      ("throughput_per_hour", "jobs/h"),
                      ("mean_lead_time_seconds", "mean lead s")]
            fields = [f"{label}={kpi[key]}" for key, label in labels if kpi.get(key) is not None]
            self._kpi_label.text = " | ".join(fields)
            self._output_label.text = (
                f"Replay: {event_file.name} | KPI: {kpi_file.name} | SHA256: {digest[:12]}..."
            )
            self._set_status(f"Real B runner and saved JSONL: AGV={count} seed=42; {len(events)} events")
            # Changing slider or replay only reads B's events. No local factory simulation.
            self._apply_timeline(self._current_time_ms)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("FactoryTwin runner invocation failed")
            if self._active and generation == self._run_generation:
                self._kpi_label.text = "KPI: no current measured result"
                self._output_label.text = "Replay file: save not confirmed"
            self._set_status(f"RUN BLOCKED/ERROR: {exc}")
        finally:
            self._run_inflight = False

    def _time_changed(self, model: Any) -> None:
        if self._active:
            self._apply_timeline(model.get_value_as_int() * 1000)

    def _apply_timeline(self, moment_ms: int) -> None:
        if not self._active:
            return
        self._current_time_ms = max(0, moment_ms)
        states = {identity: "Idle" for identity in ID_TO_PATH}
        applied = 0
        for event in self._events:
            if event["simulation_time_ms"] > self._current_time_ms:
                break
            if event.get("event_type") == "state_changed":
                states[event["equipment_id"]] = event["state"]
                applied += 1
        self._time_label.text = (
            f"{self._current_time_ms // 1000} s / {self._current_duration_seconds} s"
            f" | {applied} recorded state transitions"
        )
        if not self._display_ids:
            return
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        edit_target = stage.GetEditTarget()
        try:
            # Session layer prevents replay colors being saved into the authored USD files.
            stage.SetEditTarget(stage.GetSessionLayer())
            # Do not delete AGV02 from shared USD asset: only hide it in Kit
            # for the AGV=1 scenario. Toggle back for AGV=2.
            second_agv = stage.GetPrimAtPath(self._display_ids["AGV02"])
            if second_agv.IsValid():
                UsdGeom.Imageable(second_agv).CreateVisibilityAttr().Set(
                    UsdGeom.Tokens.invisible if self._agv_count == 1 else UsdGeom.Tokens.inherited
                )
            for identity, path in self._display_ids.items():
                anchor = stage.GetPrimAtPath(path + "/Geometry")
                if not anchor.IsValid() or not anchor.IsA(UsdGeom.Xform):
                    raise ValueError(f"Kit Geometry Xform anchor missing for {identity}")
                # Swapped USD prefabs can contain Cube, Mesh, Sphere or deeply
                # nested Gprims. Author color overrides in *session* layer so
                # model files and materials remain untouched on disk.
                render_prims = [prim for prim in Usd.PrimRange(anchor) if prim.IsA(UsdGeom.Gprim)]
                if not render_prims:
                    raise ValueError(f"Kit Geometry reference has no renderable prims: {identity}")
                for visual in render_prims:
                    UsdGeom.Gprim(visual).CreateDisplayColorAttr().Set(
                        [Gf.Vec3f(*STATE_COLORS[states[identity]])]
                    )
        except Exception:
            LOGGER.exception("FactoryTwin timeline color replay failed")
            self._set_status("Replay visualization ERROR; see Kit log")
        finally:
            stage.SetEditTarget(edit_target)
