#!/usr/bin/env python3
r"""Build FactoryTwin's replaceable, Blender-authored visual asset library.

RUN WITH BLENDER'S PYTHON, NOT THE SYSTEM PYTHON (bpy is required):

  blender --background --factory-startup --python \
      FactoryTwinUE/python/tools/generate_blender_assets.py -- \
      --output FactoryTwinUE/art/blender \
      --usd-export-dir FactoryTwinUE/usd/prefabs/blender --format both --render

Windows PowerShell example from the /openusd_omniverse-kit workspace:

  & 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' `
      --background --factory-startup --python `
      FactoryTwinUE/python/tools/generate_blender_assets.py -- `
      --output FactoryTwinUE/art/blender `
      --usd-export-dir FactoryTwinUE/usd/prefabs/blender --format both --render

Requires Blender 4.1+ with glTF and USD exporters, and a project .venv Python
with pxr installed. art/blender contains FactoryTwin_ArtDirection.blend, optional
FactoryTwin_hero.png and exports/*.glb. After mandatory pxr postprocessing and
validation, USD assets are published as usd/prefabs/blender/<ID>.usdc, for
M01, M02, QC01, AGV01, AGV02; the environment has its own separate export.
All per-device exports have a local pivot at (0,0,0), identity placement and
Z-up metres. These exports do not overwrite the canonical USD prefabs.

ONLY scene assembly uses the immutable project ID positions and visual catalog
scales. Runtime states, manifest identities, replay, and KPI are untouched.
Export files are generated outputs; no claim they exist until Blender is run.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The project's .venv Python can postprocess and validate USD without Blender/bpy.
# This file deliberately supports an internal --finalize-usd mode in that Python.
if "--finalize-usd" not in sys.argv:
    try:
        import bpy
    except ImportError as exc:
        raise SystemExit(
            "bpy not found: run with Blender --background --python. "
            "USD verification uses FactoryTwinUE/.venv Python separately."
        ) from exc


ROOT = Path(__file__).resolve().parents[2]
ASSET_PLACEMENTS = {
    "M01_CNC": ((-2.0, 2.0, 1.0), (2.0, 2.0, 2.0)),
    "M02_CNC": ((2.0, 2.0, 1.0), (2.0, 2.0, 2.0)),
    "QC01_Inspection": ((4.0, -2.0, 0.75), (1.5, 1.5, 1.5)),
    "AGV01": ((-2.0, -2.0, 0.3), (1.0, 0.7, 0.6)),
    "AGV02": ((0.0, -2.0, 0.3), (1.0, 0.7, 0.6)),
}
USD_FILENAMES = {
    "M01_CNC": "M01.usdc",
    "M02_CNC": "M02.usdc",
    "QC01_Inspection": "QC01.usdc",
    "AGV01": "AGV01.usdc",
    "AGV02": "AGV02.usdc",
    "Factory_Environment": "Factory_Environment.usdc",
}


def material(name, rgb, metallic=0.0, roughness=0.45, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        if bsdf.inputs.get("Emission Color"):
            bsdf.inputs["Emission Color"].default_value = (*rgb, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emission
        elif bsdf.inputs.get("Emission"):
            bsdf.inputs["Emission"].default_value = (*rgb, 1.0)
    return mat


def make_collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(obj, collection):
    if collection is not None:
        collection.objects.link(obj)
        for owner in list(obj.users_collection):
            if owner != collection:
                owner.objects.unlink(obj)


def create_root(name, collection, position=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    root = bpy.data.objects.new(name, None)
    collection.objects.link(root)
    root.empty_display_type = "CUBE"
    root.empty_display_size = 0.22
    root.location = position
    root.scale = scale
    return root


def finalize_mesh(obj, name, location, mat, parent, collection, bevel=0.0):
    obj.name = name
    move_to_collection(obj, collection)
    obj.parent = parent
    obj.location = location
    if mat is not None:
        obj.data.materials.append(mat)
    if bevel > 0:
        modifier = obj.modifiers.new("Edge highlights", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        if hasattr(modifier, "affect"):
            modifier.affect = "EDGES"
        modifier.loop_slide = True
        modifier.limit_method = "ANGLE"
    return obj


def cube(name, xyz, size, mat, root, collection, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finalize_mesh(obj, name, xyz, mat, root, collection, bevel)


def cylinder(name, xyz, radius, depth, mat, root, collection, axis="Z", vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    obj = bpy.context.object
    if axis == "X":
        obj.rotation_euler = (0.0, math.pi / 2, 0.0)
    elif axis == "Y":
        obj.rotation_euler = (math.pi / 2, 0.0, 0.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return finalize_mesh(obj, name, xyz, mat, root, collection, 0.0)


def lettering(name, text, xyz, height, mat, root, collection, facing="FRONT"):
    curve = bpy.data.curves.new(name + "_Font", "FONT")
    curve.body = text
    curve.size = height
    curve.extrude = 0.001
    curve.bevel_depth = 0.0004
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    obj.parent = root
    obj.location = xyz
    if facing == "FRONT":
        obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    return bpy.context.view_layer.objects.active


def create_palette():
    return {
        "shell": material("01 Pearl powdercoat", (0.76, 0.79, 0.80), 0.3, 0.34),
        "warm": material("02 Warm off-white", (0.92, 0.92, 0.87), 0.05, 0.63),
        "dark": material("03 Deep graphite", (0.07, 0.105, 0.135), 0.48, 0.34),
        "steel": material("04 Brushed aluminum", (0.37, 0.43, 0.47), 0.72, 0.24),
        "black": material("05 Rubber", (0.021, 0.027, 0.033), 0.0, 0.83),
        "glass": material("06 Dark blue window", (0.13, 0.23, 0.27), 0.18, 0.12),
        "teal": material("07 Safety teal", (0.015, 0.68, 0.64), 0.22, 0.28),
        "blue": material("08 Cool blue", (0.13, 0.43, 0.84), 0.24, 0.30),
        "orange": material("09 Safety amber", (1.0, 0.44, 0.07), 0.1, 0.4),
        "yellow": material("10 Marking yellow", (0.98, 0.71, 0.16), 0.0, 0.58),
        "red": material("11 Alarm red", (0.85, 0.07, 0.07), 0.1, 0.4),
        "floor": material("12 Concrete slate", (0.20, 0.25, 0.28), 0.02, 0.87),
        "seam": material("13 Grout", (0.15, 0.19, 0.22), 0.05, 0.80),
        "light": material("14 LED white", (0.75, 0.95, 1.0), 0.0, 0.28, emission=3.5),
    }


def build_cnc(name, collection, palette, accent, side="L"):
    root = create_root(name, collection, *ASSET_PLACEMENTS[name])
    c = lambda n, p, d, m, bevel=0.01: cube(n, p, d, palette[m], root, collection, bevel)
    c("Footing", (0, 0, -0.445), (0.94, 0.90, 0.095), "dark")
    c("Main steel cabinet", (0, 0.025, -0.04), (0.91, 0.88, 0.75), "shell", 0.027)
    c("Top service housing", (0, 0, 0.38), (0.95, 0.92, 0.14), "warm")
    c("Work area gasket", (-0.12, -0.438, 0.005), (0.63, 0.04, 0.56), "dark")
    c("Safety window", (-0.12, -0.467, 0.005), (0.53, 0.014, 0.44), "glass", 0.006)
    c("Window top crossbar", (-0.12, -0.481, 0.12), (0.53, 0.012, 0.025), "steel", 0)
    c("Control column", (0.36, -0.448, -0.02), (0.18, 0.067, 0.63), "dark")
    c("HMI display", (0.36, -0.484, 0.155), (0.136, 0.012, 0.205), "blue", 0.008)
    c("HMI lower controls", (0.36, -0.487, -0.105), (0.11, 0.015, 0.075), "steel")
    for i, m in enumerate(["teal", "orange", "red"]):
        cylinder("Pushbutton %s" % m, (0.325 + i * 0.034, -0.501, -0.235), 0.011, 0.01,
                 palette[m], root, collection, "Y", 16)
    c("Band across top", (0.0, -0.470, 0.355), (0.89, 0.025, 0.035), accent)
    c("Service hatch side", ((-0.464 if side == "L" else 0.464), 0.08, 0.07),
      (0.018, 0.60, 0.34), "steel")
    for x in [-0.32, -0.15, 0.15, 0.31]:
        c("Vent rib", (x, 0.47, 0.17), (0.038, 0.011, 0.18), "dark", 0)
    c("Status tower riser", (0.32, 0.34, 0.470), (0.022, 0.022, 0.11), "steel", 0)
    cylinder("Status tower LED", (0.32, 0.34, 0.52), 0.036, 0.08,
             palette[accent], root, collection)
    lettering("Machine tag", name.replace("_CNC", "") + "  |  CNC CELL", (-0.41, -0.486, 0.303),
              0.055, palette["warm"], root, collection)
    return root


def build_qc(name, collection, palette):
    root = create_root(name, collection, *ASSET_PLACEMENTS[name])
    c = lambda n, p, d, m, bevel=0.01: cube(n, p, d, palette[m], root, collection, bevel)
    c("Inspection workstation base", (0, 0, -0.40), (0.89, 0.89, 0.2), "dark")
    c("Inspection control enclosure", (0.0, 0.28, -0.12), (0.84, 0.32, 0.42), "shell")
    c("Conveyor bed", (0, -0.14, -0.24), (0.85, 0.61, 0.09), "steel")
    for i in range(7):
        cylinder("Roller %02d" % i, (0, -0.4 + i * 0.082, -0.173), 0.025, 0.81,
                 palette["dark"], root, collection, "X", 20)
    for x in [-0.38, 0.38]:
        c("Gantry pillar", (x, -0.06, 0.05), (0.055, 0.075, 0.54), "steel")
    c("Camera gantry", (0, -0.06, 0.35), (0.84, 0.085, 0.085), "shell")
    c("Vision camera", (0, -0.07, 0.248), (0.16, 0.16, 0.15), "dark")
    cylinder("Inspection lens", (0, -0.07, 0.155), 0.05, 0.04,
             palette["blue"], root, collection)
    c("Vision strip LED", (0, -0.12, 0.388), (0.60, 0.02, 0.018), "light", 0)
    c("Touchscreen", (0, -0.485, 0.008), (0.35, 0.025, 0.25), "glass")
    c("Result LED", (0.19, -0.5, 0.025), (0.035, 0.012, 0.045), "teal", 0)
    lettering("QC tag", "QC01 / OPTICAL INSPECTION", (-0.40, -0.51, 0.20),
              0.045, palette["warm"], root, collection)
    return root


def build_agv(name, collection, palette, accent):
    root = create_root(name, collection, *ASSET_PLACEMENTS[name])
    c = lambda n, p, d, m, bevel=0.01: cube(n, p, d, palette[m], root, collection, bevel)
    c("Low profile safety chassis", (0, 0, -0.16), (0.91, 0.88, 0.30), "dark", 0.075)
    c("Body upper colored cover", (0, 0, 0.035), (0.84, 0.76, 0.20), accent, 0.06)
    c("Brushed maintenance hatch", (0, 0.08, 0.146), (0.48, 0.42, 0.012), "steel")
    c("Pallet anti-slip platform", (0, 0.06, 0.171), (0.65, 0.52, 0.035), "black")
    for x in (-0.25, 0.25):
        for y in (-0.24, 0.26):
            c("Cargo stop", (x, y, 0.21), (0.06, 0.06, 0.065), "steel")
    for x in (-0.38, 0.38):
        for y in (-0.28, 0.28):
            cylinder("Drive wheel", (x, y, -0.28), 0.16, 0.08,
                     palette["black"], root, collection, "X", 32)
            cylinder("Wheel axle", (x + (0.048 if x > 0 else -0.048), y, -0.28), 0.052,
                     0.01, palette["steel"], root, collection, "X", 20)
    c("Forward LiDAR bridge", (0, -0.43, 0.02), (0.25, 0.032, 0.065), "glass")
    c("Safety luminous nose", (0, -0.458, -0.16), (0.59, 0.02, 0.042), "light", 0)
    c("Rear amber reflector", (0, 0.45, -0.15), (0.59, 0.016, 0.032), "orange", 0)
    cylinder("Lidar mast base", (0.29, 0.23, 0.192), 0.075, 0.045,
             palette["steel"], root, collection)
    cylinder("LiDAR puck", (0.29, 0.23, 0.247), 0.075, 0.07,
             palette["glass"], root, collection)
    lettering("Fleet ID label", name, (-0.34, -0.443, 0.068), 0.067,
              palette["warm"], root, collection)
    return root


def build_environment(name, collection, palette):
    root = create_root(name, collection)
    c = lambda n, p, d, m, bevel=0.0: cube(n, p, d, palette[m], root, collection, bevel)
    c("Continuous polished concrete floor", (0, 0, -0.095), (19.4, 13.6, 0.17), "floor")
    # Fine geometric joints and safety aisle markings; no external textures.
    for x in range(-9, 10, 2):
        c("Floor seam X", (x, 0, -0.007), (0.012, 13.2, 0.004), "seam")
    for y in range(-6, 7, 2):
        c("Floor seam Y", (0, y, -0.007), (18.8, 0.012, 0.004), "seam")
    for x in [-4.5, 4.5]:
        c("AGV route shoulder", (x, -3.24, 0.0), (0.065, 4.2, 0.006), "yellow")
    for y in [-4.9, -1.5]:
        c("AGV route lane", (0, y, 0.001), (13.0, 0.05, 0.006), "teal")
    for x in (-2.0, 2.0):
        for y in (0.82, 3.18):
            c("Machine bay safety border", (x, y, 0.006), (2.50, 0.055, 0.009), "yellow")
    for x in (-3.23, -0.77, 0.77, 3.23):
        c("Machine bay edge", (x, 2.0, 0.006), (0.045, 2.36, 0.009), "yellow")
    for i in range(8):
        c("Pedestrian crossing", (-4.3 + i * 0.22, -0.7, 0.006),
          (0.11, 1.1, 0.008), "warm")
    for x, color, label in ((-6.0, "yellow", "INBOUND"), (6.0, "teal", "OUTBOUND")):
        c(label + " dock pad", (x, 0, 0.014), (2.2, 2.2, 0.025), "dark")
        for i in range(5):
            c(label + " roller", (x - 0.75 + i * 0.38, 0, 0.053),
              (0.14, 1.73, 0.05), "steel")
        c(label + " dock safety panel", (x, 1.12, 0.04), (2.20, 0.055, 0.055), color)
        lettering(label + " title", label, (x - 0.66, 1.07, 0.075), 0.18,
                  palette["warm"], root, collection, facing="TOP")
    # Architectural shell with open camera side: intentionally not a collision mesh.
    c("Rear wall", (0, 6.54, 2.70), (19.4, 0.22, 5.40), "warm")
    c("Left end wall", (-9.58, 2.25, 2.70), (0.24, 8.70, 5.4), "shell")
    c("Right end wall", (9.58, 2.25, 2.70), (0.24, 8.70, 5.4), "shell")
    c("Rear facade graphite base", (0, 6.36, 0.48), (18.95, 0.06, 0.96), "dark")
    c("Brand fascia", (0, 6.37, 4.61), (18.9, 0.075, 0.7), "dark")
    lettering("Factory sign", "FACTORYTWIN  /  SMART LOGISTICS CELL", (-6.1, 6.30, 4.43),
              0.34, palette["warm"], root, collection)
    for x in (-7.2, -4.8, -2.4, 0, 2.4, 4.8, 7.2):
        c("Window bay", (x, 6.38, 2.72), (1.68, 0.08, 2.52), "glass")
        c("Window frame high", (x, 6.29, 4.02), (1.78, 0.10, 0.055), "steel")
        c("Window mullion", (x, 6.28, 2.70), (0.045, 0.10, 2.65), "steel")
    for x in (-8, -4, 0, 4, 8):
        c("Suspended light rail", (x, 0, 5.60), (0.115, 12.7, 0.12), "steel")
        for y in (-3.0, 1.0, 4.0):
            c("Linear LED fixture", (x, y, 5.48), (0.19, 1.8, 0.05), "light")
    for x in (-8.4, 8.4):
        for y in (-5.2, 5.2):
            c("Protective yellow bollard", (x, y, 0.47), (0.17, 0.17, 0.94), "orange", 0.06)
    return root


def look_at(obj, point):
    from mathutils import Vector
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_lighting_and_camera(scene):
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    camera_data = bpy.data.cameras.new("Isometric architectural camera")
    camera = bpy.data.objects.new("Camera_Hero", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (13.5, -17, 13.8)
    look_at(camera, (0, 0.0, 0.6))
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 23.6
    scene.camera = camera
    for name, xyz, power, shape, size in [
        ("Softbox key", (2, -5, 11), 3200, "DISK", 12.0),
        ("Softbox rim", (-6, 3, 10), 2400, "DISK", 9.0),
        ("Factory fill", (6, 4, 9), 1800, "DISK", 8.0),
    ]:
        source = bpy.data.lights.new(name, "AREA")
        source.energy = power
        source.shape = shape
        source.size = size
        light = bpy.data.objects.new(name, source)
        scene.collection.objects.link(light)
        light.location = xyz
        look_at(light, (0, 0, 0))
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1050
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.18, 0.22, 0.26)
    if "BLENDER_EEVEE_NEXT" in {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    else:
        scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.view_settings.view_transform = "AgX"
    except (TypeError, ValueError):
        pass


def usd_fix_metadata(path):
    """Finalize and actually verify a self-contained prefab with project pxr."""
    try:
        from pxr import Sdf, Usd, UsdGeom, UsdUtils
    except ImportError as exc:
        raise RuntimeError(
            "USD validation requires pxr in FactoryTwinUE/.venv Python "
            "(install usd-core there before running --format usd/both)."
        ) from exc
    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise RuntimeError("USD exporter produced unreadable file: " + str(path))
    prims = [p for p in stage.GetPseudoRoot().GetChildren() if p.IsDefined()]
    if len(prims) != 1 or not prims[0].IsA(UsdGeom.Xform):
        raise RuntimeError("USD prefab requires exactly one Xform root in %s; found %s" %
                           (path, [str(p.GetPath()) for p in prims]))
    stage.SetDefaultPrim(prims[0])
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    if not stage.GetRootLayer().Save():
        raise RuntimeError("Could not save defaultPrim/Z-up/metres to USD: " + str(path))
    # pxr caches opened Sdf layers in this process. Force disk reload before
    # checking persisted metadata; otherwise Stage.Open can reuse stale state.
    if not stage.GetRootLayer().Reload(force=True):
        raise RuntimeError("Could not reload saved USD layer: " + str(path))
    stage = Usd.Stage.Open(str(path))
    if stage is None or not stage.GetDefaultPrim().IsValid():
        raise RuntimeError("USD reread failed or missing defaultPrim: " + str(path))
    root_prim = stage.GetDefaultPrim()
    if (root_prim.GetPath() != prims[0].GetPath() or
            not root_prim.IsA(UsdGeom.Xform) or
            UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z or
            abs(UsdGeom.GetStageMetersPerUnit(stage) - 1.0) > 1e-9):
        raise RuntimeError("USD prefab defaultPrim/Xform/Z-up/metres verification FAIL: " + str(path))
    if not any(prim.IsA(UsdGeom.Gprim) for prim in Usd.PrimRange(root_prim)):
        raise RuntimeError("USD prefab has no renderable meshes: " + str(path))
    transform = UsdGeom.Xformable(root_prim).GetLocalTransformation()
    if any(abs(transform[row][col] - (1.0 if row == col else 0.0)) > 1e-6
           for row in range(4) for col in range(4)):
        raise RuntimeError("USD prefab root must have an identity local transform: " + str(path))
    if any(prim.HasAttribute("twin:equipmentId") for prim in stage.Traverse()):
        raise RuntimeError("USD prefab may not provide runtime equipment ID metadata: " + str(path))
    layers, dependencies, unresolved = UsdUtils.ComputeAllDependencies(str(path))
    if unresolved or dependencies:
        raise RuntimeError(
            "USD prefab must be self-contained (no missing/external textures or assets): "
            + str(path) + "; dependencies=" + str(dependencies)
            + "; unresolved=" + str(unresolved)
        )
    for prim in stage.Traverse():
        for attribute in prim.GetAttributes():
            if attribute.GetTypeName() == Sdf.ValueTypeNames.Asset and attribute.Get():
                raise RuntimeError("USD prefab may not depend on external asset paths: " + str(path))
    print("USD_FINALIZED_AND_VERIFIED", path, str(root_prim.GetPath()), "Z-up", "metres=1")


def finalize_usd_cli(argv):
    """Run with FactoryTwinUE/.venv Python, which has pxr but need not have bpy."""
    parser = argparse.ArgumentParser(description="Internal USD finalization through project pxr")
    parser.add_argument("--finalize-usd", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.finalize_usd.is_file():
            raise FileNotFoundError("Missing Blender-produced USD: " + str(args.finalize_usd))
        usd_fix_metadata(args.finalize_usd.resolve())
        return 0
    except (OSError, RuntimeError) as err:
        print("USD_VALIDATION_FAILED:", err, file=sys.stderr)
        return 1


def project_pxr_python():
    """Abort before export if project .venv / pxr is unavailable."""
    interpreter = (ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if not interpreter.is_file():
        raise RuntimeError("USD output requires FactoryTwinUE/.venv Python with pxr: missing " + str(interpreter))
    result = subprocess.run([str(interpreter), "-c", "from pxr import Usd, UsdGeom, UsdUtils"],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("FactoryTwinUE/.venv Python cannot import pxr; USD publishing blocked: "
                           + (result.stderr.strip() or result.stdout.strip()))
    return interpreter


def finalize_through_project_venv(interpreter, staged_path):
    result = subprocess.run([str(interpreter), str(Path(__file__).resolve()),
                             "--finalize-usd", str(staged_path)],
                            capture_output=True, text=True, check=False)
    if result.returncode or "USD_FINALIZED_AND_VERIFIED" not in result.stdout:
        raise RuntimeError("USD publish blocked, pxr finalization/verification failed for "
                           + str(staged_path) + ": "
                           + (result.stderr.strip() or result.stdout.strip()))
    print(result.stdout.strip())


def publish_verified_usd(staged_path, usd_export_dir):
    """Publish only validated USD via atomic rename into generated project tree."""
    usd_export_dir.mkdir(parents=True, exist_ok=True)
    target = usd_export_dir / staged_path.name
    fd, temp_name = tempfile.mkstemp(prefix="." + staged_path.stem + "-",
                                    suffix=".tmp", dir=str(usd_export_dir))
    os.close(fd)
    temp = Path(temp_name)
    try:
        shutil.copyfile(staged_path, temp)
        source_hash = hashlib.sha256(staged_path.read_bytes()).hexdigest()
        if hashlib.sha256(temp.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError("USD copy hash mismatch; refusing publish: " + str(target))
        os.replace(temp, target)
        print("USD_PUBLISHED_VERIFIED", target, target.stat().st_size, source_hash)
    finally:
        if temp.exists():
            temp.unlink()


def export_one(root, glb_destination, usd_staging_dir, fmt):
    """Save only this prefab with identity root transform, then restore placement."""
    position, scale, rotation = root.location.copy(), root.scale.copy(), root.rotation_euler.copy()
    root.location = (0, 0, 0)
    root.scale = (1, 1, 1)
    root.rotation_euler = (0, 0, 0)
    try:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in [root, *root.children_recursive]:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = root
        bpy.context.view_layer.update()
        if fmt in ("both", "glb"):
            target = glb_destination / (root.name + ".glb")
            bpy.ops.export_scene.gltf(
                filepath=str(target), export_format="GLB", use_selection=True,
                export_yup=False, export_animations=False, export_cameras=False,
                export_lights=False,
            )
            if not target.is_file() or target.stat().st_size == 0:
                raise RuntimeError("GLB export missing: " + str(target))
            print("EXPORTED_GLTF", target, target.stat().st_size)
        if fmt in ("both", "usd"):
            target = usd_staging_dir / USD_FILENAMES[root.name]
            props = bpy.ops.wm.usd_export.get_rna_type().properties.keys()
            selection_key = ("selected_objects_only" if "selected_objects_only" in props
                             else "selection_only" if "selection_only" in props else None)
            if selection_key is None:
                raise RuntimeError("Blender USD exporter lacks selected-only export support")
            settings = {"filepath": str(target), selection_key: True}
            if "export_materials" in props:
                settings["export_materials"] = True
            if "convert_orientation" in props:
                settings["convert_orientation"] = False
            bpy.ops.wm.usd_export(**settings)
            if not target.is_file() or target.stat().st_size == 0:
                raise RuntimeError("USD export missing: " + str(target))
            print("EXPORTED_USD_STAGED_UNVERIFIED", target, target.stat().st_size)
            return target
    finally:
        root.location = position
        root.scale = scale
        root.rotation_euler = rotation
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.update()
    return None


def parse_args(argv):
    arguments = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser(description="Build FactoryTwin professional 3D visual assets")
    parser.add_argument("--output", type=Path, default=ROOT / "art" / "blender")
    parser.add_argument("--usd-export-dir", type=Path,
                        default=ROOT / "usd" / "prefabs" / "blender",
                        help="Verified USD destination, only under project usd/prefabs/blender")
    parser.add_argument("--format", choices=["both", "glb", "usd"], default="both")
    parser.add_argument("--render", action="store_true", help="Render a 1600x1050 hero image")
    parser.add_argument("--source-blend", type=Path, default=None,
                        help="Export manually edited .blend without regenerating its objects")
    return parser.parse_args(arguments)


def main():
    args = parse_args(sys.argv)
    output = args.output.resolve()
    destination = output / "exports"
    allowed_usd_root = (ROOT / "usd" / "prefabs" / "blender").resolve()
    usd_export_dir = args.usd_export_dir.resolve()
    if args.format in ("usd", "both") and not usd_export_dir.is_relative_to(allowed_usd_root):
        raise RuntimeError("USD export directory must remain under " + str(allowed_usd_root)
                           + " so canonical USD assets cannot be overwritten: " + str(usd_export_dir))
    interpreter = project_pxr_python() if args.format in ("usd", "both") else None
    destination.mkdir(parents=True, exist_ok=True)
    if args.source_blend is not None:
        source = args.source_blend.resolve()
        if not source.is_file():
            raise FileNotFoundError("Edited .blend source was not found: " + str(source))
        bpy.ops.wm.open_mainfile(filepath=str(source))
        roots = {name: bpy.data.objects.get(name) for name in
                 [*ASSET_PLACEMENTS, "Factory_Environment"]}
        missing = [name for name, obj in roots.items() if obj is None]
        if missing:
            raise RuntimeError("Edited .blend is missing these export root objects: " + str(missing))
        print("LOADED_EDITED_BLEND", source)
    else:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        palette = create_palette()
        roots = {}
        for key, builder, kwargs in [
            ("M01_CNC", build_cnc, {"accent": "teal", "side": "L"}),
            ("M02_CNC", build_cnc, {"accent": "blue", "side": "R"}),
            ("QC01_Inspection", build_qc, {}),
            ("AGV01", build_agv, {"accent": "teal"}),
            ("AGV02", build_agv, {"accent": "orange"}),
            ("Factory_Environment", build_environment, {}),
        ]:
            collection = make_collection(key)
            roots[key] = builder(key, collection, palette, **kwargs)

        add_lighting_and_camera(bpy.context.scene)
        bpy.context.view_layer.update()
        blend_path = output / "FactoryTwin_ArtDirection.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        print("SAVED_BLEND", blend_path, blend_path.stat().st_size)
    with tempfile.TemporaryDirectory(prefix=".usd-blender-validation-", dir=str(output)) as scratch:
        staging_dir = Path(scratch)
        staged_usd = []
        for key, asset_root in roots.items():
            usd_path = export_one(asset_root, destination, staging_dir, args.format)
            if usd_path is not None:
                staged_usd.append(usd_path)
        # No USD is visible to the catalog until every candidate passes pxr.
        for candidate in staged_usd:
            finalize_through_project_venv(interpreter, candidate)
        for candidate in staged_usd:
            publish_verified_usd(candidate, usd_export_dir)
    if args.render:
        render_path = output / "FactoryTwin_hero.png"
        bpy.context.scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
        if not render_path.is_file() or render_path.stat().st_size == 0:
            raise RuntimeError("Hero render missing: " + str(render_path))
        print("RENDERED", render_path, render_path.stat().st_size)
    print("FACTORYTWIN_BLENDER_DONE", len(roots), "roots", args.format,
          "verified_usd", len(roots) if interpreter is not None else 0)


if __name__ == "__main__":
    if "--finalize-usd" in sys.argv:
        sys.exit(finalize_usd_cli(sys.argv[1:]))
    main()
