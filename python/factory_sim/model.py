"""Deterministic one-second manufacturing-cell simulation.

All state transitions happen on integer virtual milliseconds. Transport is a
fixed-duration abstraction: there is no deadheading, path planning or physics.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .contracts import AGV_IDS, KPI_COLUMNS, MACHINE_IDS, load_scenario, validate_event_stream


@dataclass
class Job:
    job_id: str
    arrival_ms: int
    machine_id: str
    status: str = "waiting_pickup_machine"
    completed_ms: int | None = None


@dataclass
class Transport:
    job_id: str
    phase: str
    origin: str
    destination: str
    request_ms: int


@dataclass
class AGV:
    equipment_id: str
    location: str = "INBOUND"
    transport: Transport | None = None
    end_ms: int | None = None


@dataclass
class Station:
    equipment_id: str
    process_ms: int
    queue: deque[str] = field(default_factory=deque)
    job_id: str | None = None
    due_ms: int | None = None
    remaining_ms: int = 0
    down: bool = False


@dataclass(frozen=True)
class SimulationResult:
    """Immutable-to-consumers run payload; model retains no mutable global state.

    `events` and `kpi` are JSON-friendly snapshots. `jobs` is useful for
    independently checking conservation and throughput during testing.
    """

    config: dict[str, Any]
    seed: int
    events: list[dict[str, Any]]
    kpi: dict[str, Any]
    jobs: list[dict[str, Any]]

    def jsonl(self) -> str:
        return "".join(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n" for event in self.events)


def run_scenario(config: Mapping[str, Any] | str | Path, seed: int = 42) -> SimulationResult:
    """Run from a scenario mapping or path, returning events and measured KPIs.

    >>> result = run_scenario('data/scenarios/agv_2.json', seed=42)
    >>> result.kpi['arrived_jobs'] >= result.kpi['completed_jobs']
    True
    """
    config = load_scenario(config)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")

    randomizer = random.Random(seed)
    duration_ms = config["duration_seconds"] * 1000
    interval_ms = config["arrival_interval_seconds"] * 1000
    travel_ms = config["fixed_route_travel_seconds"] * 1000
    stations = {
        eq: Station(eq, config["machine_process_seconds"][eq] * 1000)
        for eq in MACHINE_IDS
    }
    qc = Station("QC01", config["inspection_seconds"] * 1000)
    agvs = [AGV(eq) for eq in AGV_IDS[: config["agv_count"]]]
    jobs: dict[str, Job] = {}
    requests: deque[Transport] = deque()
    states: dict[str, str] = {}
    pending: list[tuple[int, int, str, int, dict[str, Any]]] = []
    sequence = 0

    def emit(t: int, priority: int, eq: str, kind: str, state: str | None, job_id: str | None, **extra: Any) -> None:
        nonlocal sequence
        payload = {
            "schema_version": 1, "simulation_time_ms": t, "equipment_id": eq,
            "event_type": kind, "state": state, "job_id": job_id,
        }
        payload.update(extra)
        pending.append((t, priority, eq, sequence, payload))
        sequence += 1

    def transition(t: int, priority: int, eq: str, new_state: str, job_id: str | None, **extra: Any) -> None:
        if states.get(eq) != new_state:
            states[eq] = new_state
            emit(t, priority, eq, "state_changed", new_state, job_id, **extra)

    def request_transport(t: int, job_id: str, phase: str, origin: str, destination: str) -> None:
        requests.append(Transport(job_id, phase, origin, destination, t))

    for eq in sorted(list(stations) + ["QC01"] + [agv.equipment_id for agv in agvs]):
        transition(0, 0, eq, "Idle", None, **({"waypoint": "INBOUND"} if eq.startswith("AGV") else {}))

    fault_by_ms: dict[int, list[dict[str, Any]]] = {}
    for fault in config["scripted_faults"]:
        fault_by_ms.setdefault(fault["time_seconds"] * 1000, []).append(fault)

    for t in range(0, duration_ms + 1, 1000):
        # A fault at exactly a completion boundary preempts that completion.
        for fault in sorted(fault_by_ms.get(t, []), key=lambda value: value["equipment_id"]):
            station = stations[fault["equipment_id"]]
            if fault["action"] == "Down":
                station.down = True
                if station.due_ms is not None:
                    station.remaining_ms = max(0, station.due_ms - t)
                    station.due_ms = None
                transition(t, 10, station.equipment_id, "Down", station.job_id)
            else:
                station.down = False
                if station.job_id is not None:
                    station.due_ms = t + station.remaining_ms
                    transition(t, 10, station.equipment_id, "Busy", station.job_id)
                else:
                    transition(t, 10, station.equipment_id, "Idle", None)

        # Arrived AGV legs enter the next queue; jobs finish only at OUTBOUND.
        for agv in agvs:
            if agv.transport is None or agv.end_ms is None or agv.end_ms > t:
                continue
            leg = agv.transport
            agv.location = leg.destination
            agv.transport, agv.end_ms = None, None
            transition(t, 20, agv.equipment_id, "Idle", leg.job_id, waypoint=agv.location)
            job = jobs[leg.job_id]
            if leg.phase == "to_machine":
                assert job.status == "in_transit_machine"
                job.status = "queued_machine"
                stations[job.machine_id].queue.append(job.job_id)
            elif leg.phase == "to_qc":
                assert job.status == "in_transit_qc"
                job.status = "queued_qc"
                qc.queue.append(job.job_id)
            elif leg.phase == "to_outbound":
                assert job.status == "in_transit_outbound"
                job.status = "completed"
                job.completed_ms = t
                emit(t, 25, agv.equipment_id, "job_completed", None, job.job_id)
            else:
                raise AssertionError("unsupported transport phase")

        for station in [*stations.values(), qc]:
            if station.down or station.job_id is None or station.due_ms is None or station.due_ms > t:
                continue
            job = jobs[station.job_id]
            if station.equipment_id == "QC01":
                assert job.status == "processing_qc"
                job.status = "waiting_pickup_outbound"
                request_transport(t, job.job_id, "to_outbound", "QC01", "OUTBOUND")
            else:
                assert job.status == "processing_machine"
                job.status = "waiting_pickup_qc"
                request_transport(t, job.job_id, "to_qc", station.equipment_id, "QC01")
            station.job_id, station.due_ms, station.remaining_ms = None, None, 0
            transition(t, 30 if station.equipment_id != "QC01" else 35, station.equipment_id, "Idle", None)

        # Workload assignment depends only on seed and arrivals, never fleet size.
        if t < duration_ms and t % interval_ms == 0:
            machine_id = MACHINE_IDS[randomizer.randrange(len(MACHINE_IDS))]
            job_id = f"J{len(jobs) + 1:04d}"
            job = Job(job_id, t, machine_id)
            jobs[job_id] = job
            emit(t, 40, machine_id, "job_arrived", None, job_id)
            request_transport(t, job_id, "to_machine", "INBOUND", machine_id)

        # Machines and QC start immediately when they have a free work slot.
        for station in [*stations.values(), qc]:
            if station.down or station.job_id is not None or not station.queue:
                continue
            job_id = station.queue.popleft()
            station.job_id = job_id
            station.due_ms = t + station.process_ms
            station.remaining_ms = station.process_ms
            job = jobs[job_id]
            assert job.status == ("queued_qc" if station.equipment_id == "QC01" else "queued_machine")
            job.status = "processing_qc" if station.equipment_id == "QC01" else "processing_machine"
            transition(t, 50 if station.equipment_id != "QC01" else 55, station.equipment_id, "Busy", job_id)

        # FIFO transport queue, stable AGV ID order; leg duration independent of fleet size.
        for agv in agvs:
            if agv.transport is not None or not requests:
                continue
            leg = requests.popleft()
            job = jobs[leg.job_id]
            expected_status = {
                "to_machine": "waiting_pickup_machine", "to_qc": "waiting_pickup_qc",
                "to_outbound": "waiting_pickup_outbound",
            }[leg.phase]
            assert job.status == expected_status
            job.status = {
                "to_machine": "in_transit_machine", "to_qc": "in_transit_qc",
                "to_outbound": "in_transit_outbound",
            }[leg.phase]
            agv.transport = leg
            agv.end_ms = t + travel_ms
            transition(t, 60, agv.equipment_id, "Moving", job.job_id, waypoint=leg.destination)

    events = []
    for event_id, (_, _, _, _, event) in enumerate(sorted(pending, key=lambda item: item[:4]), 1):
        events.append({"event_id": event_id, **event})
    validate_event_stream(events, agv_count=config["agv_count"])

    # Busy utilization is reconstructed from exactly the stream given to consumers.
    current = {eq: "Idle" for eq in MACHINE_IDS}
    last = {eq: 0 for eq in MACHINE_IDS}
    busy_ms = {eq: 0 for eq in MACHINE_IDS}
    for event in events:
        eq = event["equipment_id"]
        if eq not in current or event["event_type"] != "state_changed":
            continue
        when = min(event["simulation_time_ms"], duration_ms)
        if current[eq] == "Busy":
            busy_ms[eq] += when - last[eq]
        last[eq] = when
        current[eq] = event["state"]
    for eq in MACHINE_IDS:
        if current[eq] == "Busy":
            busy_ms[eq] += duration_ms - last[eq]

    completed = [job for job in jobs.values() if job.completed_ms is not None]
    lead_mean = (sum((job.completed_ms - job.arrival_ms) / 1000 for job in completed) / len(completed)) if completed else None
    event_text = "".join(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n" for event in events)
    kpi: dict[str, Any] = {
        "scenario_id": config["scenario_id"], "seed": seed,
        "duration_seconds": config["duration_seconds"], "arrived_jobs": len(jobs),
        "completed_jobs": len(completed),
        "throughput_per_hour": len(completed) * 3600 / config["duration_seconds"],
        "mean_lead_time_seconds": lead_mean,
        "m01_busy_fraction": busy_ms["M01"] / duration_ms,
        "m02_busy_fraction": busy_ms["M02"] / duration_ms,
        "event_hash": hashlib.sha256(event_text.encode("utf-8")).hexdigest(),
    }
    assert set(kpi) == set(KPI_COLUMNS)
    job_snapshot = [
        {"job_id": job.job_id, "arrival_ms": job.arrival_ms,
         "machine_id": job.machine_id, "status": job.status, "completed_ms": job.completed_ms}
        for job in jobs.values()
    ]
    assert kpi["arrived_jobs"] == kpi["completed_jobs"] + sum(job["status"] != "completed" for job in job_snapshot)
    return SimulationResult(config, seed, events, kpi, job_snapshot)
