"""Static visual integration checks on the actual composed FactoryTwin stage.

Run: .venv/Scripts/python.exe python/tools/test_factory_appearance.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pxr import Usd, UsdGeom

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_usd as b


class IndustrialVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = Usd.Stage.Open(str(b.ROOT))
        if not cls.stage:
            raise RuntimeError("canonical factory_scene.usda could not be composed")

    def test_visual_swap_does_not_modify_five_equipment_identities(self):
        expected = {f"/World/Factory/{group}/{identity}": identity for identity, _, group, *_ in b.EQUIPMENT}
        self.assertEqual(b.read_ids_with_pxr(b.ROOT), expected)
        for identity, _kind, group, location, *_ in b.EQUIPMENT:
            parent_path = f"/World/Factory/{group}/{identity}"
            parent = self.stage.GetPrimAtPath(parent_path)
            transform = UsdGeom.Xformable(parent).GetLocalTransformation()
            self.assertEqual(tuple(round(transform.ExtractTranslation()[i], 4) for i in range(3)), location)
            geometry = self.stage.GetPrimAtPath(parent_path + "/Geometry")
            self.assertTrue(geometry.HasAuthoredReferences(), identity)
            descendants = [p for p in Usd.PrimRange(geometry) if p.IsA(UsdGeom.Gprim)]
            self.assertGreaterEqual(len(descendants), 10, identity)

    def test_factory_environment_is_separate_from_simulation(self):
        background = self.stage.GetPrimAtPath("/World/Factory/Environment")
        self.assertTrue(background.IsValid())
        descendants = list(Usd.PrimRange(background))
        self.assertGreaterEqual(sum(p.IsA(UsdGeom.Gprim) for p in descendants), 60)
        self.assertFalse(any(p.HasAttribute("twin:equipmentId") for p in descendants))
        self.assertEqual(len(self.stage.GetRootLayer().subLayerPaths), 2)
        self.assertEqual(b.validate_assets(b.ROOT, b.MANIFEST)[0], "PASS")

    def test_prefabs_stand_near_the_factory_floor(self):
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        for identity, _kind, group, *_ in b.EQUIPMENT:
            prim = self.stage.GetPrimAtPath(f"/World/Factory/{group}/{identity}/Geometry")
            bound = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            self.assertGreaterEqual(bound.GetMin()[2], -0.075, identity)
            self.assertLess(bound.GetMin()[2], 0.16, identity)
            self.assertGreater(bound.GetMax()[2], bound.GetMin()[2], identity)


if __name__ == "__main__":
    unittest.main(verbosity=2)
