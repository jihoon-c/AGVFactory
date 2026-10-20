"""Shared replay, manifest, and scenario validators used by the Python producer.

Kit and Unreal are consumers. They must still validate untrusted inputs themselves.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

EQUIPMENT_IDS = frozenset({"M01", "M02", "QC01", "AGV01", "AGV02"})
MACHINE_IDS = ("M01", "M02")
AGV_IDS = ("AGV01", "AGV02")
EXPECTED_PRIMS = {
    "M01": "/World/Factory/Equipment/M01",
    "M02": "/World/Factory/Equipment/M02",
    "QC01": "/World/Factory/Equipment/QC01",
    "AGV01": "/World/Factory/AGVs/AGV01",
    "AGV02": "/World/Factory/AGVs/AGV02",
}
WAYPOINTS = frozenset({"INBOUND", "OUTBOUND", "M01", "M02", "QC01"})
EVENT_TYPES = frozenset({"state_changed", "job_arrived", "job_completed"})
KPI_COLUMNS = (
    "scenario_id", "seed", "duration_seconds", "arrived_jobs", "completed_jobs",
    "throughput_per_hour", "mean_lead_time_seconds", "m01_busy_fraction",
    "m02_busy_fraction", "event_hash",
)


def _int(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'} integer")
    return value


def load_scenario(config: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    """Validate a JSON scenario and return a normalized owned dictionary."""
    if isinstance(config, (str, Path)):
        config = json.loads(Path(config).read_text(encoding="utf-8"))
    if not isinstance(config, Mapping):
        raise ValueError("scenario must be a JSON object")
    required = {
        "schema_version", "scenario_id", "duration_seconds", "fixed_step_ms",
        "agv_count", "arrival_interval_seconds", "machine_process_seconds",
        "inspection_seconds", "fixed_route_travel_seconds", "dispatch_policy", "scripted_faults",
    }
    if set(config) != required or config["schema_version"] != 1:
        raise ValueError("scenario must have exactly the v1 contract fields")
    scenario_id = config["scenario_id"]
    if not isinstance(scenario_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", scenario_id):
        raise ValueError("invalid scenario_id")
    step = _int(config["fixed_step_ms"], "fixed_step_ms", positive=True)
    if step != 1000:
        raise ValueError("P0 requires 1000 ms fixed step")
    duration = _int(config["duration_seconds"], "duration_seconds", positive=True)
    arrival = _int(config["arrival_interval_seconds"], "arrival_interval_seconds", positive=True)
    inspection = _int(config["inspection_seconds"], "inspection_seconds", positive=True)
    travel = _int(config["fixed_route_travel_seconds"], "fixed_route_travel_seconds", positive=True)
    agv_count = _int(config["agv_count"], "agv_count", positive=True)
    if agv_count not in (1, 2):
        raise ValueError("only AGV=1 or AGV=2 is supported")
    machine = config["machine_process_seconds"]
    if not isinstance(machine, Mapping) or set(machine) != set(MACHINE_IDS):
        raise ValueError("machine_process_seconds must specify M01 and M02")
    normalized_machine = {eq: _int(machine[eq], f"process {eq}", positive=True) for eq in MACHINE_IDS}
    if config["dispatch_policy"] != "FIFO":
        raise ValueError("P0 supports FIFO only")
    faults = config["scripted_faults"]
    if not isinstance(faults, list):
        raise ValueError("scripted_faults must be a list")
    normalized_faults: list[dict[str, Any]] = []
    down = set()
    prev = -1
    for fault in faults:
        if not isinstance(fault, Mapping) or set(fault) != {"time_seconds", "equipment_id", "action"}:
            raise ValueError("fault must have time_seconds, equipment_id, action")
        when = _int(fault["time_seconds"], "fault time")
        eq = fault["equipment_id"]
        action = fault["action"]
        if when >= duration or when < prev or eq not in MACHINE_IDS or action not in ("Down", "Repair"):
            raise ValueError("invalid fault schedule, time, equipment or action")
        if (action == "Down" and eq in down) or (action == "Repair" and eq not in down):
            raise ValueError("faults must alternate Down and Repair per equipment")
        (down.add if action == "Down" else down.remove)(eq)
        normalized_faults.append({"time_seconds": when, "equipment_id": eq, "action": action})
        prev = when
    return {
        "schema_version": 1, "scenario_id": scenario_id, "duration_seconds": duration,
        "fixed_step_ms": step, "agv_count": agv_count,
        "arrival_interval_seconds": arrival, "machine_process_seconds": normalized_machine,
        "inspection_seconds": inspection, "fixed_route_travel_seconds": travel,
        "dispatch_policy": "FIFO", "scripted_faults": normalized_faults,
    }


def validate_manifest(manifest: Mapping[str, Any] | str | Path) -> dict[str, str]:
    """Check ID/prim uniqueness; USD custom-attribute validation belongs to Worker A."""
    if isinstance(manifest, (str, Path)):
        manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if manifest.get("usd_root") != "usd/factory_scene.usda":
        raise ValueError("manifest usd_root mismatch")
    rows = manifest.get("equipment")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_PRIMS):
        raise ValueError("missing or extra equipment IDs")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"equipment_id", "prim_path", "kind"}:
            raise ValueError("manifest equipment row malformed")
        eq, path, kind = row["equipment_id"], row["prim_path"], row["kind"]
        if not isinstance(eq, str) or eq not in EXPECTED_PRIMS or eq in seen_ids:
            raise ValueError("unknown or duplicate equipment ID")
        if not isinstance(path, str) or path != EXPECTED_PRIMS[eq] or path in seen_paths:
            raise ValueError("unknown or duplicate prim path")
        expected_kind = "agv" if eq.startswith("AGV") else "inspection" if eq == "QC01" else "machine"
        if kind != expected_kind:
            raise ValueError("equipment kind mismatch")
        seen_ids.add(eq)
        seen_paths.add(path)
    return {row["equipment_id"]: row["prim_path"] for row in rows}


def validate_event_stream(events: list[dict[str, Any]], *, agv_count: int | None = None) -> None:
    """Fail fast on invalid replay, unknown IDs, and non-monotonic ordering."""
    if not isinstance(events, list) or not events:
        raise ValueError("empty or invalid replay event array")
    previous_time = -1
    arrived: set[str] = set()
    completed: set[str] = set()
    for event_id, event in enumerate(events, 1):
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        required = {"schema_version", "event_id", "simulation_time_ms", "equipment_id", "event_type", "state", "job_id"}
        if not required <= set(event) or type(event["schema_version"]) is not int or event["schema_version"] != 1 or type(event["event_id"]) is not int or event["event_id"] != event_id:
            raise ValueError("invalid event schema or non-contiguous event_id")
        ms = _int(event["simulation_time_ms"], "simulation_time_ms")
        if ms % 1000 or ms < previous_time:
            raise ValueError("unsorted or sub-tick event timestamp")
        eq, kind, state = event["equipment_id"], event["event_type"], event["state"]
        if not isinstance(eq, str) or not isinstance(kind, str) or eq not in EQUIPMENT_IDS or kind not in EVENT_TYPES:
            raise ValueError("unknown equipment ID or event type")
        if agv_count == 1 and eq == "AGV02":
            raise ValueError("inactive AGV02 event in one-AGV scenario")
        if kind == "state_changed":
            valid_states = {"Idle", "Moving"} if eq in AGV_IDS else {"Idle", "Busy", "Down"} if eq in MACHINE_IDS else {"Idle", "Busy"}
            if state not in valid_states:
                raise ValueError("invalid state for equipment")
        elif state is not None or not isinstance(event["job_id"], str):
            raise ValueError("job event must have null state and nonempty job_id")
        if event["job_id"] is not None and (not isinstance(event["job_id"], str) or not re.fullmatch(r"J\d{4,}", event["job_id"])):
            raise ValueError("invalid job_id")
        if kind == "job_arrived":
            if eq not in MACHINE_IDS or event["job_id"] in arrived:
                raise ValueError("invalid or duplicate job arrival")
            arrived.add(event["job_id"])
        elif kind == "job_completed":
            if eq not in AGV_IDS or event["job_id"] not in arrived or event["job_id"] in completed:
                raise ValueError("invalid or duplicate job completion")
            completed.add(event["job_id"])
        if "waypoint" in event and (eq not in AGV_IDS or not isinstance(event["waypoint"], str) or event["waypoint"] not in WAYPOINTS):
            raise ValueError("invalid AGV waypoint")
        previous_time = ms


def read_events(path: str | Path, *, agv_count: int | None = None) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as file:
        events = [json.loads(line) for line in file if line.strip()]
    validate_event_stream(events, agv_count=agv_count)
    return events
