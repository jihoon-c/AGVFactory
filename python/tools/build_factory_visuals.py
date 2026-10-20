#!/usr/bin/env python3
"""Author replaceable, metre-scale industrial USD assets for FactoryTwin.

Run from FactoryTwinUE: .venv/Scripts/python.exe python/tools/build_factory_visuals.py
Creates authored geometry only: the existing layout owns all equipment IDs,
positions and Python replay. The factory shell is a separate USD layer.
"""

from __future__ import annotations

from pathlib import Path

from pxr import Gf, Usd, UsdGeom


PROJECT = Path(__file__).resolve().parents[2]
PREFABS = PROJECT / "usd" / "prefabs"
ENVIRONMENT = PROJECT / "usd" / "factory_environment.usda"

CHARCOAL = (0.075, 0.105, 0.14)
STEEL = (0.27, 0.33, 0.39)
SILVER = (0.68, 0.76, 0.79)
BLUE = (0.11, 0.32, 0.55)
TEAL = (0.08, 0.64, 0.62)
YELLOW = (0.95, 0.65, 0.12)
GLASS = (0.18, 0.43, 0.53)
WALL = (0.34, 0.39, 0.44)


def new_stage(path: Path, default: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.Xform.Define(stage, default)
    stage.SetDefaultPrim(stage.GetPrimAtPath(default))
    return stage


def solid(stage, path: str, xyz, size, color, shape="Cube", rotation=(0, 0, 0)):
    """One portable USD Gprim with authored colour and local transform."""
    if shape == "Cube":
        prim = UsdGeom.Cube.Define(stage, path)
        prim.CreateSizeAttr(1.0)
    elif shape == "Cylinder":
        prim = UsdGeom.Cylinder.Define(stage, path)
        prim.CreateRadiusAttr(0.5)
        prim.CreateHeightAttr(1.0)
    elif shape == "Sphere":
        prim = UsdGeom.Sphere.Define(stage, path)
        prim.CreateRadiusAttr(0.5)
    else:
        raise ValueError(shape)
    prim.AddTranslateOp().Set(Gf.Vec3d(*map(float, xyz)))
    if any(rotation):
        prim.AddRotateXYZOp().Set(Gf.Vec3f(*map(float, rotation)))
    prim.AddScaleOp().Set(Gf.Vec3f(*map(float, size)))
    prim.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def save(stage, path: Path):
    # ExportToString does not retain anonymous file-system-specific paths.
    path.write_text(stage.GetRootLayer().ExportToString(), encoding="utf-8")
    opened = Usd.Stage.Open(str(path))
    if not opened or not opened.GetDefaultPrim().IsValid():
        raise RuntimeError(f"USD prefab failed to reopen: {path}")
    n = sum(1 for p in opened.Traverse() if p.IsA(UsdGeom.Gprim))
    if n < 1:
        raise RuntimeError(f"USD has no geometry: {path}")
    print(f"USD authored: {path.relative_to(PROJECT)} ({n} Gprims)")


def build_machine():
    stage = new_stage(PREFABS / "factory_machine.usda", "/Model")
    s = lambda name, xyz, dims, color, shape="Cube", rotation=(0, 0, 0): solid(stage, "/Model/" + name, xyz, dims, color, shape, rotation)
    s("Visual", (0, 0.03, -0.065), (.94, .84, .83), STEEL)
    s("RoofCap", (0, .01, .367), (1.0, .93, .10), SILVER)
    s("LeftGuard", (-.43, -.402, 0), (.09, .09, .67), CHARCOAL)
    s("RightGuard", (.43, -.402, 0), (.09, .09, .67), CHARCOAL)
    s("DoorFrameTop", (0, -.422, .292), (.85, .065, .065), SILVER)
    s("DoorFrameBottom", (0, -.422, -.307), (.85, .065, .06), SILVER)
    s("DoorFrameCenter", (.13, -.434, -.005), (.028, .07, .60), SILVER)
    s("ObservationWindow", (-.10, -.46, .075), (.52, .032, .38), GLASS)
    s("SpindleHub", (-.15, -.483, .07), (.115, .06, .115), CHARCOAL, "Cylinder", (90, 0, 0))
    s("ControlPod", (.365, -.51, .08), (.23, .19, .43), CHARCOAL)
    s("ControlScreen", (.365, -.615, .14), (.175, .018, .19), TEAL)
    s("ControlButtons", (.35, -.612, -.078), (.13, .022, .075), YELLOW)
    s("DoorGrip", (.20, -.483, -.09), (.027, .047, .17), SILVER)
    s("ServicePanel", (.23, .468, -.07), (.35, .019, .37), CHARCOAL)
    s("BrandPlate", (-.22, -.478, .36), (.35, .022, .045), BLUE)
    for i, x in enumerate((-.36, .36)):
        for j, y in enumerate((-.34, .35)):
            s(f"Foot_{i}_{j}", (x, y, -.465), (.16, .15, .07), CHARCOAL)
    for i, x in enumerate((-.24, -.08, .08, .24)):
        s(f"RearVent_{i}", (x, .469, .11), (.055, .025, .22), CHARCOAL)
    s("BeaconStem", (.34, .27, .417), (.037, .037, .10), SILVER)
    s("BeaconAmber", (.34, .27, .476), (.09, .09, .04), YELLOW, "Cylinder")
    save(stage, PREFABS / "factory_machine.usda")


def build_qc():
    stage = new_stage(PREFABS / "factory_inspection.usda", "/Model")
    s = lambda name, xyz, dims, color, shape="Cube", rotation=(0, 0, 0): solid(stage, "/Model/" + name, xyz, dims, color, shape, rotation)
    s("Visual", (0, 0, -.29), (.92, .75, .22), BLUE)
    s("BeltSurface", (0, 0, -.16), (.92, .63, .035), CHARCOAL)
    s("InspectionBed", (0, 0, -.105), (.47, .46, .035), STEEL)
    s("LeftRail", (0, -.35, -.11), (.93, .045, .14), SILVER)
    s("RightRail", (0, .35, -.11), (.93, .045, .14), SILVER)
    for i, x in enumerate((-.36, .36)):
        for j, y in enumerate((-.25, .25)):
            s(f"Leg_{i}_{j}", (x, y, -.398), (.08, .085, .19), SILVER)
    for i, x in enumerate((-.30, .30)):
        s(f"GantryPost_{i}", (x, .20, .13), (.075, .08, .59), CHARCOAL)
    s("GantryBeam", (0, .20, .395), (.73, .14, .105), SILVER)
    s("CameraBody", (0, .15, .295), (.23, .19, .155), CHARCOAL)
    s("CameraLens", (0, .15, .206), (.085, .085, .04), GLASS, "Cylinder")
    s("LightBar", (0, -.25, .28), (.62, .07, .06), TEAL)
    s("OperatorTerminal", (.39, -.40, .025), (.21, .11, .37), CHARCOAL)
    s("OperatorDisplay", (.39, -.462, .10), (.17, .015, .18), GLASS)
    s("ScannerStripe", (0, -.03, -.08), (.40, .06, .016), YELLOW)
    save(stage, PREFABS / "factory_inspection.usda")


def build_agv():
    stage = new_stage(PREFABS / "factory_agv.usda", "/Model")
    s = lambda name, xyz, dims, color, shape="Cube", rotation=(0, 0, 0): solid(stage, "/Model/" + name, xyz, dims, color, shape, rotation)
    s("Visual", (0, 0, -.085), (.92, .88, .37), BLUE)
    s("FrontBumper", (0, -.472, -.16), (.96, .075, .18), CHARCOAL)
    s("RearBumper", (0, .472, -.16), (.96, .075, .18), CHARCOAL)
    s("Deck", (0, 0, .128), (.86, .77, .075), STEEL)
    s("PalletBase", (0, 0, .202), (.66, .60, .063), YELLOW)
    s("PalletPayload", (0, 0, .30), (.53, .46, .12), SILVER)
    s("FrontArrowShaft", (0, -.30, .171), (.07, .20, .015), TEAL)
    s("FrontArrowTip", (0, -.41, .175), (.20, .07, .012), TEAL)
    s("LidarStem", (.27, .25, .255), (.05, .05, .16), CHARCOAL)
    s("LidarHead", (.27, .25, .35), (.13, .13, .075), SILVER, "Cylinder")
    s("StatusLight", (-.26, -.27, .171), (.12, .12, .04), TEAL)
    s("FrontSensor", (0, -.512, -.05), (.24, .018, .07), GLASS)
    for i, x in enumerate((-.31, .31)):
        for j, y in enumerate((-.41, .41)):
            s(f"Wheel_{i}_{j}", (x, y, -.285), (.18, .18, .115), CHARCOAL, "Cylinder", (90, 0, 0))
            s(f"Hub_{i}_{j}", (x, y + (-.095 if j == 0 else .095), -.285), (.075, .075, .035), SILVER, "Cylinder", (90, 0, 0))
    for i, x in enumerate((-.42, .42)):
        s(f"SideGuard_{i}", (x, 0, -.19), (.065, .62, .15), CHARCOAL)
    save(stage, PREFABS / "factory_agv.usda")


def build_environment():
    stage = new_stage(ENVIRONMENT, "/World")
    UsdGeom.Xform.Define(stage, "/World/Factory")
    base = "/World/Factory/Environment"
    UsdGeom.Xform.Define(stage, base)
    s = lambda name, xyz, dims, color, shape="Cube", rotation=(0, 0, 0): solid(stage, base + "/" + name, xyz, dims, color, shape, rotation)
    s("Foundation", (0, 0, -.19), (18.0, 11.6, .33), (.15, .17, .20))
    # Cutaway facility: leave SW camera-facing sides completely open so equipment
    # is visible in UE's fixed southwest camera (no near walls or front truss).
    s("FactoryFloor", (0, 0, -.01), (17.80, 11.4, .07), (.36, .39, .39))
    # The USD-to-UE stage can appear with opposite side facing the built-in
    # director camera. A 4m outer wall blocks most gameplay on that side, so
    # this demonstrator uses an open-top cutaway with knee-high boundary rails.
    s("RearSafetyRail", (0, 5.68, .18), (17.6, .16, .33), WALL)
    s("RightSafetyRail", (8.82, 0, .18), (.16, 11.2, .33), WALL)
    s("RearAccentRail", (0, 5.54, .29), (17.2, .035, .10), BLUE)
    for j, x in enumerate((-8.60, -4.30, 0.0, 4.30, 8.60)):
        s(f"RearSafetyPost_{j}", (x, 5.50, .47), (.12, .16, .92), SILVER)
    # The vehicle lane is y=-2, connecting docks through both machines and QC.
    s("VehicleLane", (0, -2.0, .013), (17.0, 2.12, .012), (.20, .25, .28))
    for i, x in enumerate(range(-8, 9)):
        s(f"LaneDash_{i:02d}", (float(x), -2.0, .023), (.55, .035, .014), YELLOW)
    for j, y in enumerate((-3.08, -.92)):
        s(f"LaneEdge_{j}", (0, y, .022), (17.0, .045, .018), YELLOW)
    for j, x in enumerate((-6., 6.)):
        s(f"DockPad_{j}", (x, 0, .020), (2.45, 2.46, .025), (.26, .37, .39))
        for i in range(5):
            s(f"DockSafety_{j}_{i}", (x - .96 + .48 * i, 1.24, .03), (.30, .065, .02), YELLOW)
    # Machine bay safety framing surrounds the equipment but leaves walkways clear.
    for i, x in enumerate((-2., 2.)):
        for j, dy in enumerate((-1.22, 1.22)):
            s(f"MachineBayLine_{i}_{j}", (x, 2 + dy, .025), (2.85, .055, .013), YELLOW)
        for j, dx in enumerate((-1.42, 1.42)):
            s(f"MachineBaySide_{i}_{j}", (x + dx, 2, .025), (.055, 2.45, .013), YELLOW)
    s("InspectionBay", (4, -4.03, .022), (2.7, .06, .013), TEAL)
    for i, x in enumerate((-8.3, 8.3)):
        s(f"StationCabinet_{i}", (x, 4.0, .75), (.85, 1.5, 1.5), BLUE)
        for j in range(3):
            s(f"StationShelf_{i}_{j}", (x, 3.42 + .48*j, 1.08), (.78, .07, .045), SILVER)
    for i, x in enumerate((-6.9, 6.9)):
        for j, y in enumerate((3.0, 4.1)):
            s(f"Pallet_{i}_{j}", (x, y, .105), (1.03, .70, .17), YELLOW)
            s(f"Cargo_{i}_{j}", (x, y, .39), (.82, .58, .39), STEEL)
    save(stage, ENVIRONMENT)


def main():
    build_machine()
    build_qc()
    build_agv()
    build_environment()


if __name__ == "__main__":
    main()
