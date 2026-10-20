"""Runner contract/regression tests; no pxr, Kit, or Unreal dependency."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "python" / "tools"))

from factory_sim import run_scenario  # noqa: E402
from factory_sim.contracts import read_events, validate_event_stream, validate_manifest  # noqa: E402
from factory_sim.runner import save_run  # noqa: E402
from compare import compare_csv  # noqa: E402


def scenario(count: int = 1) -> dict:
    return json.loads((ROOT / "data" / "scenarios" / f"agv_{count}.json").read_text(encoding="utf-8"))


def valid_manifest() -> dict:
    return {
        "schema_version": 1, "usd_root": "usd/factory_scene.usda",
        "equipment": [
            {"equipment_id": eq, "prim_path": f"/World/Factory/{folder}/{eq}", "kind": kind}
            for eq, folder, kind in (
                ("M01", "Equipment", "machine"), ("M02", "Equipment", "machine"),
                ("QC01", "Equipment", "inspection"), ("AGV01", "AGVs", "agv"),
                ("AGV02", "AGVs", "agv"),
            )
        ],
    }


class ScenarioValidationTests(unittest.TestCase):
    def test_both_samples_valid(self):
        for count in (1, 2):
            result = run_scenario(scenario(count), 42)
            self.assertEqual(result.kpi["arrived_jobs"], 300)
            self.assertGreater(result.kpi["completed_jobs"], 0)

    def test_bad_contracts_rejected(self):
        for field, bad in (
            ("agv_count", 0), ("fixed_step_ms", 500), ("dispatch_policy", "LIFO"),
            ("arrival_interval_seconds", 0), ("duration_seconds", -1),
        ):
            case = scenario()
            case[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                run_scenario(case, 42)
        with self.assertRaises(ValueError):
            run_scenario(scenario(), -1)

    def test_invalid_fault_sequence_rejected(self):
        for faults in (
            [{"time_seconds": 200, "equipment_id": "M01", "action": "Repair"}],
            [{"time_seconds": 200, "equipment_id": "UNKNOWN", "action": "Down"}],
            [{"time_seconds": 3600, "equipment_id": "M01", "action": "Down"}],
            [{"time_seconds": 260, "equipment_id": "M01", "action": "Down"},
             {"time_seconds": 200, "equipment_id": "M01", "action": "Repair"}],
        ):
            case = scenario()
            case["scripted_faults"] = faults
            with self.subTest(faults=faults), self.assertRaises(ValueError):
                run_scenario(case)


class DeterministicModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.one = run_scenario(scenario(1), 42)
        cls.two = run_scenario(scenario(2), 42)

    def test_same_seed_same_bytes_and_kpi(self):
        again = run_scenario(scenario(1), 42)
        self.assertEqual(self.one.jsonl(), again.jsonl())
        self.assertEqual(self.one.kpi, again.kpi)
        digest = hashlib.sha256(self.one.jsonl().encode("utf-8")).hexdigest()
        self.assertEqual(self.one.kpi["event_hash"], digest)

    def test_different_seed_same_arrival_schedule(self):
        other = run_scenario(scenario(1), 43)
        self.assertNotEqual(self.one.jsonl(), other.jsonl())
        self.assertEqual(self.one.kpi["arrived_jobs"], other.kpi["arrived_jobs"])

    def test_seed_workload_identical_across_agv_counts(self):
        assignments_a = [(j["job_id"], j["arrival_ms"], j["machine_id"]) for j in self.one.jobs]
        assignments_b = [(j["job_id"], j["arrival_ms"], j["machine_id"]) for j in self.two.jobs]
        self.assertEqual(assignments_a, assignments_b)

    def test_work_conservation_and_no_duplicate_jobs(self):
        for result in (self.one, self.two):
            ids = [job["job_id"] for job in result.jobs]
            self.assertEqual(len(ids), len(set(ids)))
            stages = Counter(job["status"] for job in result.jobs)
            self.assertEqual(len(ids), result.kpi["arrived_jobs"])
            self.assertEqual(stages["completed"], result.kpi["completed_jobs"])
            self.assertEqual(len(ids) - stages["completed"], sum(v for k, v in stages.items() if k != "completed"))
            arrivals = [e["job_id"] for e in result.events if e["event_type"] == "job_arrived"]
            completions = [e["job_id"] for e in result.events if e["event_type"] == "job_completed"]
            self.assertEqual(set(arrivals), set(ids))
            self.assertEqual(set(completions), {job["job_id"] for job in result.jobs if job["status"] == "completed"})
            self.assertEqual(len(completions), len(set(completions)))

    def test_kpis_can_be_recomputed_from_exported_event_stream(self):
        for result in (self.one, self.two):
            arrivals = {}
            finished = {}
            busy = {"M01": 0, "M02": 0}
            state = {"M01": "Idle", "M02": "Idle"}
            previous = {"M01": 0, "M02": 0}
            for event in result.events:
                kind = event["event_type"]
                t = event["simulation_time_ms"]
                if kind == "job_arrived":
                    arrivals[event["job_id"]] = t
                if kind == "job_completed":
                    finished[event["job_id"]] = t
                eq = event["equipment_id"]
                if eq in state and kind == "state_changed":
                    if state[eq] == "Busy":
                        busy[eq] += t - previous[eq]
                    state[eq] = event["state"]
                    previous[eq] = t
            duration = result.kpi["duration_seconds"] * 1000
            for eq in state:
                if state[eq] == "Busy":
                    busy[eq] += duration - previous[eq]
            self.assertEqual(len(arrivals), result.kpi["arrived_jobs"])
            self.assertEqual(len(finished), result.kpi["completed_jobs"])
            mean = sum((t - arrivals[job_id]) / 1000 for job_id, t in finished.items()) / len(finished)
            self.assertAlmostEqual(mean, result.kpi["mean_lead_time_seconds"])
            self.assertAlmostEqual(busy["M01"] / duration, result.kpi["m01_busy_fraction"])
            self.assertAlmostEqual(busy["M02"] / duration, result.kpi["m02_busy_fraction"])

    def test_fault_pauses_busy_machine_until_repair(self):
        transitions = [e for e in self.two.events if e["equipment_id"] == "M01" and e["event_type"] == "state_changed"]
        self.assertIn((200000, "Down"), [(e["simulation_time_ms"], e["state"]) for e in transitions])
        self.assertEqual([e for e in transitions if 200000 < e["simulation_time_ms"] < 260000], [])
        at_repair = [e["state"] for e in transitions if e["simulation_time_ms"] == 260000]
        self.assertTrue(at_repair and at_repair[0] in ("Busy", "Idle"))
        self.assertTrue(all(0 <= self.two.kpi[key] <= 1 for key in ("m01_busy_fraction", "m02_busy_fraction")))

    def test_event_schema_and_active_agv_only(self):
        for result, count in ((self.one, 1), (self.two, 2)):
            validate_event_stream(result.events, agv_count=count)
            self.assertEqual([e["event_id"] for e in result.events], list(range(1, len(result.events) + 1)))
            self.assertEqual([e["simulation_time_ms"] for e in result.events], sorted(e["simulation_time_ms"] for e in result.events))
        self.assertFalse(any(event["equipment_id"] == "AGV02" for event in self.one.events))

    def test_zero_completion_kpi_is_null(self):
        config = scenario()
        config["duration_seconds"] = 5
        config["scripted_faults"] = []
        result = run_scenario(config, 42)
        self.assertEqual(result.kpi["completed_jobs"], 0)
        self.assertIsNone(result.kpi["mean_lead_time_seconds"])


class ConsumerValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = run_scenario(scenario(1), 42).events

    def assert_bad(self, modify):
        events = copy.deepcopy(self.sample)
        modify(events)
        with self.assertRaises(ValueError):
            validate_event_stream(events, agv_count=1)

    def test_unknown_id_rejected(self):
        self.assert_bad(lambda events: events[0].update(equipment_id="FAKE"))

    def test_duplicate_event_id_rejected(self):
        self.assert_bad(lambda events: events[1].update(event_id=1))

    def test_unsorted_timestamp_rejected(self):
        self.assert_bad(lambda events: events[7].update(simulation_time_ms=0))

    def test_invalid_state_rejected(self):
        self.assert_bad(lambda events: events[0].update(state="Down"))

    def test_missing_event_field_rejected(self):
        self.assert_bad(lambda events: events[0].pop("state"))

    def test_duplicate_job_completion_rejected(self):
        events = copy.deepcopy(self.sample)
        completed = next(e for e in events if e["event_type"] == "job_completed")
        duplicate = copy.deepcopy(completed)
        duplicate["event_id"] = len(events) + 1
        duplicate["simulation_time_ms"] = events[-1]["simulation_time_ms"]
        events.append(duplicate)
        with self.assertRaises(ValueError):
            validate_event_stream(events, agv_count=1)

    def test_bad_waypoint_and_boolean_event_id_rejected(self):
        self.assert_bad(lambda events: events[0].update(waypoint=["INBOUND"]))
        self.assert_bad(lambda events: events[0].update(event_id=True))

    def test_malformed_jsonl_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            path.write_text('{"event_id":\n', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                read_events(path)

    def test_manifest_duplicate_id_or_prim_and_missing_id_rejected(self):
        self.assertEqual(len(validate_manifest(valid_manifest())), 5)
        for change in ("duplicate_id", "duplicate_prim", "missing"):
            manifest = valid_manifest()
            if change == "duplicate_id":
                manifest["equipment"][1]["equipment_id"] = "M01"
            elif change == "duplicate_prim":
                manifest["equipment"][1]["prim_path"] = manifest["equipment"][0]["prim_path"]
            else:
                manifest["equipment"].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_manifest(manifest)


class OutputAndExperimentTests(unittest.TestCase):
    def test_jsonl_roundtrip_csv_upsert_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            one = run_scenario(scenario(1), 42)
            two = run_scenario(scenario(2), 42)
            save_run(one, out=folder / "one.jsonl", kpi_out=folder / "kpi.csv")
            save_run(two, out=folder / "two.jsonl", kpi_out=folder / "kpi.csv")
            save_run(one, out=folder / "one.jsonl", kpi_out=folder / "kpi.csv")
            self.assertEqual(read_events(folder / "one.jsonl", agv_count=1), one.events)
            with (folder / "kpi.csv").open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["event_hash"], one.kpi["event_hash"])
            self.assertEqual(rows[1]["event_hash"], two.kpi["event_hash"])

    def test_three_seed_paired_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for count in (1, 2):
                for seed in (42, 43, 44):
                    result = run_scenario(scenario(count), seed)
                    save_run(result, out=folder / f"run_{count}_{seed}.jsonl", kpi_out=folder / "kpi.csv")
            report = compare_csv(folder / "kpi.csv")
            self.assertIn("Paired seeds: 42, 43, 44", report)
            self.assertIn("throughput_per_hour", report)
            with (folder / "kpi.csv").open(encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                rows = list(reader)
            self.assertEqual(len(rows), 6)
            self.assertGreater(sum(float(row["completed_jobs"]) for row in rows if row["scenario_id"] == "agv_2"), 0)

    def test_unmatched_seeds_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            save_run(run_scenario(scenario(1), 42), out=folder / "only_one.jsonl", kpi_out=folder / "kpi.csv")
            with self.assertRaises(ValueError):
                compare_csv(folder / "kpi.csv")


if __name__ == "__main__":
    unittest.main()
