"""CLI and atomic JSONL/KPI output for the shared simulator.

From project root (FactoryTwinUE_JobStack_OneWeek):
  $env:PYTHONPATH='python'
  py -m factory_sim.runner --scenario data/scenarios/agv_1.json --seed 42 \
    --out Reports/run_agv_1_seed42.jsonl --kpi-out Reports/kpi.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import tempfile
from pathlib import Path

from .contracts import KPI_COLUMNS
from .model import SimulationResult, run_scenario


def _atomic_write(path: str | Path, contents: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as temp:
            temp_name = temp.name
            temp.write(contents)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, target)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def save_run(result: SimulationResult, *, out: str | Path, kpi_out: str | Path) -> None:
    """Validate paths and write a replay file plus an upserted KPI summary.

    For the demo all runs are sequential; concurrent writers must synchronize
    access to the shared KPI CSV in their own orchestration.
    """
    events_target = Path(out).resolve()
    kpi_target = Path(kpi_out).resolve()
    if events_target == kpi_target:
        raise ValueError("event and KPI paths must differ")
    stream = result.jsonl()
    if not stream:
        raise ValueError("empty replay stream")
    if hashlib.sha256(stream.encode("utf-8")).hexdigest() != result.kpi["event_hash"]:
        raise ValueError("KPI event_hash differs from serialized JSONL")
    kpi_rows: dict[tuple[str, int], dict[str, str]] = {}
    if kpi_target.exists():
        with kpi_target.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if tuple(reader.fieldnames or ()) != KPI_COLUMNS:
                raise ValueError("existing KPI CSV has incompatible columns")
            for row in reader:
                if None in row.values():
                    raise ValueError("malformed existing KPI row")
                key = (row["scenario_id"], int(row["seed"]))
                if key in kpi_rows:
                    raise ValueError("duplicate KPI scenario/seed")
                kpi_rows[key] = row
    key = (str(result.kpi["scenario_id"]), int(result.kpi["seed"]))
    kpi_rows[key] = {
        name: "" if result.kpi[name] is None else str(result.kpi[name])
        for name in KPI_COLUMNS
    }
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=KPI_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for key in sorted(kpi_rows):
        writer.writerow(kpi_rows[key])

    # Validate both payloads before publishing. The two file renames are not a
    # multi-file transaction; if interrupted the KPI row can be regenerated.
    _atomic_write(events_target, stream)
    _atomic_write(kpi_target, csv_buffer.getvalue())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FactoryTwin deterministic AGV scenario runner")
    parser.add_argument("--scenario", required=True, help="agv_1.json or agv_2.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True, help="Replay JSONL file")
    parser.add_argument("--kpi-out", required=True, help="Append/upsert KPI CSV")
    args = parser.parse_args(argv)
    result = run_scenario(args.scenario, args.seed)
    save_run(result, out=args.out, kpi_out=args.kpi_out)
    print(
        f"PASS scenario={result.kpi['scenario_id']} seed={args.seed} "
        f"arrived={result.kpi['arrived_jobs']} completed={result.kpi['completed_jobs']} "
        f"events={len(result.events)} sha256={result.kpi['event_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
