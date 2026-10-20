"""Run with .venv/Scripts/python.exe python/tools/test_model_swap.py.

Real pxr composition/box bounds test; never writes canonical USD/manifest/catalog.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_usd as b
import set_visual_asset as swap
from pxr import Usd, UsdGeom


class ModelSwapTests(unittest.TestCase):
    def setUp(self) -> None:
        # Temp is inside owned usd/ so project and preview reside on same Windows volume.
        self._tmp = tempfile.TemporaryDirectory(prefix="_test_visual_", dir=b.PROJECT / "usd")
        self.addCleanup(self._tmp.cleanup)
        self.temp = Path(self._tmp.name)
        self.output = self.temp / "factory_scene.usda"
        self.manifest = self.temp / "equipment_manifest_preview.json"
        self.catalog = self.temp / "visual_assets_preview.json"
        self.initial = json.loads(b.CATALOG.read_text(encoding="utf-8"))
        self.catalog.write_text(json.dumps(self.initial, indent=2), encoding="utf-8")

    def _stage(self):
        stage = Usd.Stage.Open(str(self.output))
        self.assertTrue(stage)
        return stage

    def test_swap_preserves_identity_transform_and_changes_visual_shape(self):
        b.generate(self.output, self.manifest, self.catalog)
        original = self._stage()
        eq_path = "/World/Factory/Equipment/M01"
        old_id = original.GetPrimAtPath(eq_path).GetAttribute("twin:equipmentId").Get()
        old_position = UsdGeom.Xformable(original.GetPrimAtPath(eq_path)).GetLocalTransformation()
        old_anchor = original.GetPrimAtPath(eq_path + "/Geometry")
        self.assertTrue(old_anchor.HasAuthoredReferences())
        self.assertEqual(original.GetPrimAtPath(eq_path + "/Geometry/Visual").GetTypeName(), "Cube")
        bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        old_box = bounds.ComputeWorldBound(old_anchor).ComputeAlignedRange().GetSize()

        modified = copy.deepcopy(self.initial)
        modified["models"]["M01"]["model_path"] = "usd/prefabs/alternate_sphere.usda"
        modified["models"]["M01"]["scale"] = [3.0, 2.0, 2.0]
        modified["models"]["M01"]["rotation_deg"] = [0.0, 0.0, 45.0]
        self.catalog.write_text(json.dumps(modified, indent=2), encoding="utf-8")
        b.generate(self.output, self.manifest, self.catalog)
        swapped = self._stage()
        new_root = swapped.GetPrimAtPath(eq_path)
        self.assertEqual(new_root.GetAttribute("twin:equipmentId").Get(), old_id)
        self.assertEqual(UsdGeom.Xformable(new_root).GetLocalTransformation(), old_position)
        visual = swapped.GetPrimAtPath(eq_path + "/Geometry/Visual")
        self.assertEqual(visual.GetTypeName(), "Sphere")
        self.assertTrue(visual.IsA(UsdGeom.Gprim))
        new_box = bounds.ComputeWorldBound(swapped.GetPrimAtPath(eq_path + "/Geometry")).ComputeAlignedRange().GetSize()
        self.assertNotEqual(tuple(old_box), tuple(new_box))
        self.assertEqual(set(b.read_ids_with_pxr(self.output)), {
            "/World/Factory/Equipment/M01", "/World/Factory/Equipment/M02",
            "/World/Factory/Equipment/QC01", "/World/Factory/AGVs/AGV01",
            "/World/Factory/AGVs/AGV02",
        })
        # Authoring must overwrite old arcs rather than accumulate references.
        b.generate(self.output, self.manifest, self.catalog)
        b.validate_assets(self.output, self.manifest, self.catalog)
        self.assertEqual(b.read_ids_with_pxr(self.output)[eq_path], "M01")

    def test_model_path_and_transform_validation_without_writes(self):
        invalid = (
            ("path traversal", "model_path", "../secret.usda"),
            ("absolute path", "model_path", "C:/Windows/secret.usda"),
            ("missing USD", "model_path", "usd/prefabs/not_found.usda"),
            ("invalid scale", "scale", [1, 0, 1]),
            ("invalid rotation", "rotation_deg", [0, "invalid", 0]),
        )
        for label, field, value in invalid:
            with self.subTest(label=label):
                data = copy.deepcopy(self.initial)
                data["models"]["M01"][field] = value
                self.catalog.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    b.generate(self.output, self.manifest, self.catalog)
                self.assertFalse(self.output.exists(), f"{label} unexpectedly wrote root USD")
                self.assertFalse(self.manifest.exists(), f"{label} unexpectedly wrote manifest")

    def test_cli_override_only_in_preview(self):
        command = [sys.executable, str(b.PROJECT / "python" / "tools" / "build_usd.py"),
                   "--model-override", "M01=usd/prefabs/alternate_sphere.usda"]
        unsafe = subprocess.run(command, cwd=b.PROJECT, text=True, capture_output=True)
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertIn("isolated --out AND --manifest", unsafe.stderr)
        safe = subprocess.run(command + ["--out", str(self.output), "--manifest", str(self.manifest)],
                              cwd=b.PROJECT, text=True, capture_output=True)
        self.assertEqual(safe.returncode, 0, safe.stderr)
        stage = self._stage()
        self.assertEqual(stage.GetPrimAtPath("/World/Factory/Equipment/M01/Geometry/Visual").GetTypeName(), "Sphere")
        self.assertEqual(stage.GetPrimAtPath("/World/Factory/Equipment/M02/Geometry/Visual").GetTypeName(), "Cube")

    def test_one_command_helper_dry_run_and_invalid_model_leave_canonical_unchanged(self):
        tracked = [b.CATALOG, b.ROOT, b.ROOT.with_name("layout.usda"), b.MANIFEST]
        before = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in tracked}
        helper = [sys.executable, str(b.PROJECT / "python" / "tools" / "set_visual_asset.py"),
                  "--id", "M01", "--scale", "2,2,2", "--rotation", "0,0,0", "--dry-run"]
        ok = subprocess.run(helper + ["--asset", "usd/prefabs/alternate_sphere.usda"],
                            cwd=b.PROJECT, text=True, capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("DRY RUN PASS", ok.stdout)
        bad = subprocess.run(helper + ["--asset", "usd/prefabs/missing_file.usda"],
                             cwd=b.PROJECT, text=True, capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("MODEL SWAP REJECTED", bad.stderr)
        after = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in tracked}
        self.assertEqual(before, after)

    def test_one_command_helper_commit_restore_only_on_isolated_preview(self):
        """Exercise real commit+restore branches, leaving production files unopened."""
        b.generate(self.output, self.manifest, self.catalog)
        with (patch.object(b, "ROOT", self.output),
              patch.object(b, "MANIFEST", self.manifest),
              patch.object(b, "CATALOG", self.catalog)):
            committed = swap.change_visual("M01", "usd/prefabs/alternate_sphere.usda",
                                           scale=[2, 2, 2], rotation=[0, 0, 0])
            self.assertIn("COMMITTED", committed)
            first_stage = self._stage()
            self.assertEqual(first_stage.GetPrimAtPath(
                "/World/Factory/Equipment/M01/Geometry/Visual").GetTypeName(), "Sphere")
            tracked = [self.output, self.output.with_name("layout.usda"), self.manifest, self.catalog]
            snapshot = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in tracked}
            with self.assertRaises(ValueError):
                swap.change_visual("M01", "usd/prefabs/does_not_exist.usda")
            self.assertEqual(snapshot, {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in tracked})
            restored = swap.change_visual("M01", "usd/prefabs/machine.usda")
            self.assertIn("COMMITTED", restored)
            restored_stage = self._stage()
            self.assertEqual(restored_stage.GetPrimAtPath(
                "/World/Factory/Equipment/M01/Geometry/Visual").GetTypeName(), "Cube")


if __name__ == "__main__":
    unittest.main(verbosity=2)
