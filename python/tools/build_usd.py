#!/usr/bin/env python3
"""Generate the shared factory USD layout and validate equipment identity.

`py -3.14 python/tools/build_usd.py` works even without `pxr`, by emitting
spec-compliant ASCII USDA. When Pixar USD is installed, its stage API authors
the layout and reopens the composed scene for stronger validation.

No simulation state belongs to this module; it only defines static geometry.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import math
import sys
import tempfile
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "usd" / "factory_scene.usda"
MANIFEST = PROJECT / "data" / "equipment_manifest.json"
CATALOG = PROJECT / "data" / "visual_assets.json"
ENVIRONMENT = PROJECT / "usd" / "factory_environment.usda"
WORLD = "/World/Factory"

# Width/depth/height and translation are in metres; world Z is up.
LOCATIONS = (
    ("INBOUND", (-6.0, 0.0, 0.5), (2.0, 2.0, 1.0), (0.70, 0.65, 0.45)),
    ("OUTBOUND", (6.0, 0.0, 0.5), (2.0, 2.0, 1.0), (0.45, 0.65, 0.70)),
)
EQUIPMENT = (
    ("M01", "machine", "Equipment", (-2.0, 2.0, 1.0), (2.0, 2.0, 2.0), (0.55, 0.60, 0.70)),
    ("M02", "machine", "Equipment", (2.0, 2.0, 1.0), (2.0, 2.0, 2.0), (0.55, 0.60, 0.70)),
    ("QC01", "inspection", "Equipment", (4.0, -2.0, 0.75), (1.5, 1.5, 1.5), (0.65, 0.70, 0.40)),
    ("AGV01", "agv", "AGVs", (-2.0, -2.0, 0.30), (1.0, 0.7, 0.6), (0.35, 0.60, 0.90)),
    ("AGV02", "agv", "AGVs", (0.0, -2.0, 0.30), (1.0, 0.7, 0.6), (0.35, 0.60, 0.90)),
)

REQUIRED_IDS = frozenset(item[0] for item in EQUIPMENT)


def _reject_duplicate_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_visual_catalog(path: Path = CATALOG, overrides: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Resolve only in-project USD assets, reject traversal, symlinks and bad transforms.

    Paths in the catalog are relative to the project root, not to the JSON file.
    This makes temporary copies of the catalog safe to use in preview tests.
    """
    obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json)
    if (not isinstance(obj, dict) or obj.get("schema_version") != 1 or
            obj.get("coordinate_system") != "Z-up" or obj.get("meters_per_unit") != 1.0):
        raise ValueError("visual catalog requires schema_version=1, Z-up, meters_per_unit=1.0")
    models = obj.get("models")
    if not isinstance(models, dict) or set(models) != REQUIRED_IDS:
        raise ValueError(f"visual models must contain exactly {sorted(REQUIRED_IDS)}")
    result: dict[str, dict[str, Any]] = {}
    for identity, row in models.items():
        if not isinstance(row, dict) or set(row) != {"model_path", "scale", "rotation_deg"}:
            raise ValueError(f"invalid visual catalog keys for {identity}")
        asset = (overrides or {}).get(identity, row["model_path"])
        if not isinstance(asset, str) or not asset or "\\" in asset or ":" in asset or asset.startswith("/"):
            raise ValueError(f"unsafe USD model_path for {identity}: {asset!r}")
        parts = asset.split("/")
        if (any(part in ("", ".", "..") for part in parts) or
                len(parts) < 3 or parts[0] != "usd" or
                Path(asset).suffix.lower() not in (".usd", ".usda", ".usdc")):
            raise ValueError(f"model_path must be under usd/ and point to a USD file: {asset!r}")
        resolved = (PROJECT / asset).resolve()
        if not resolved.is_relative_to((PROJECT / "usd").resolve()) or not resolved.is_file():
            raise ValueError(f"USD model missing or outside project: {asset!r}")
        row = dict(row)
        for field in ("scale", "rotation_deg"):
            values = row[field]
            if (not isinstance(values, list) or len(values) != 3 or
                    any(isinstance(v, bool) or not isinstance(v, (float, int)) or
                        not math.isfinite(v) for v in values)):
                raise ValueError(f"{identity}: {field} must be three finite numbers")
            if field == "scale" and any(v <= 0 or v > 1000 for v in values):
                raise ValueError(f"{identity}: scale components must be >0 and <=1000")
            if field == "rotation_deg" and any(abs(v) > 360 for v in values):
                raise ValueError(f"{identity}: rotation_deg must be within +/-360")
        row["model_path"] = asset
        row["absolute_path"] = resolved
        result[identity] = row
    if overrides and set(overrides) - REQUIRED_IDS:
        raise ValueError(f"unknown model-override IDs: {sorted(set(overrides) - REQUIRED_IDS)}")
    return result


def validate_prefabs_with_pxr(models: dict[str, dict[str, Any]]) -> None:
    try:
        from pxr import Sdf, Usd, UsdGeom, UsdUtils  # type: ignore
    except ImportError:
        return
    for identity, row in models.items():
        _layers, dependency_assets, unresolved = UsdUtils.ComputeAllDependencies(str(row["absolute_path"]))
        if unresolved:
            raise ValueError(f"{identity}: USD prefab has unresolved asset dependencies: {unresolved}")
        for dependency in dependency_assets:
            dep = str(dependency).replace("\\", "/")
            if dep.startswith("/") or ":" in dep or ".." in dep.split("/"):
                raise ValueError(f"{identity}: prefab references unsafe external asset {dep!r}")
        stage = Usd.Stage.Open(str(row["absolute_path"]))
        if not stage or not stage.GetDefaultPrim().IsValid():
            raise ValueError(f"{identity}: prefab missing valid USD defaultPrim")
        if (UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z or
                abs(UsdGeom.GetStageMetersPerUnit(stage) - 1) > 1e-9):
            raise ValueError(f"{identity}: prefab must be Z-up and metersPerUnit=1")
        default_prim = stage.GetDefaultPrim()
        if not default_prim.IsA(UsdGeom.Xform):
            raise ValueError(f"{identity}: prefab defaultPrim must be Xform for Geometry anchor")
        if any(prim.HasAttribute("twin:equipmentId") for prim in stage.Traverse()):
            raise ValueError(f"{identity}: prefab cannot provide identity metadata")
        if not any(prim.IsA(UsdGeom.Gprim) for prim in Usd.PrimRange(default_prim)):
            raise ValueError(f"{identity}: prefab defaultPrim has no renderable Gprim")
        for prim in stage.Traverse():
            for attribute in prim.GetAttributes():
                if attribute.GetTypeName() != Sdf.ValueTypeNames.Asset:
                    continue
                asset = attribute.Get()
                if not asset:
                    continue
                asset_path = asset.path
                if (not isinstance(asset_path, str) or not asset_path or
                        asset_path.startswith("/") or ":" in asset_path or
                        ".." in asset_path.replace("\\", "/").split("/") or
                        not asset.resolvedPath):
                    raise ValueError(f"{identity}: missing/unsafe texture or USD asset: {asset_path!r}")
                if not Path(asset.resolvedPath).resolve().is_relative_to(PROJECT.resolve()):
                    raise ValueError(f"{identity}: asset dependency escapes project: {asset_path!r}")


def manifest_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "usd_root": "usd/factory_scene.usda",
        "equipment": [
            {"equipment_id": identity, "prim_path": f"{WORLD}/{group}/{identity}", "kind": kind}
            for identity, kind, group, *_ in EQUIPMENT
        ],
    }


def validate_manifest_data(data: Any, stage_ids: dict[str, str] | None = None) -> list[str]:
    """Reject bad mapping; stage_ids must be independently read from USD."""
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return ["manifest schema_version must be 1"]
    if data.get("usd_root") != "usd/factory_scene.usda":
        errors.append("usd_root does not match shared root contract")
    items = data.get("equipment")
    if not isinstance(items, list) or len(items) != 5:
        return errors + ["equipment must contain exactly five objects"]
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"equipment[{i}] must be an object")
            continue
        identity, path, kind = (item.get(k) for k in ("equipment_id", "prim_path", "kind"))
        if not isinstance(identity, str) or not identity.strip():
            errors.append(f"equipment[{i}] empty equipment_id")
        elif identity in seen_ids:
            errors.append(f"duplicate equipment_id: {identity}")
        else:
            seen_ids.add(identity)
        if not isinstance(path, str) or not path.strip():
            errors.append(f"equipment[{i}] empty prim_path")
        elif path in seen_paths:
            errors.append(f"duplicate prim_path: {path}")
        else:
            seen_paths.add(path)
        if not isinstance(kind, str) or not kind:
            errors.append(f"equipment[{i}] missing kind")
        if stage_ids is not None and isinstance(path, str):
            if path not in stage_ids:
                errors.append(f"missing USD prim or equipmentId: {path}")
            elif stage_ids[path] != identity:
                errors.append(f"USD metadata mismatch at {path}: {stage_ids[path]!r} != {identity!r}")
    expected = {row["equipment_id"]: row["prim_path"] for row in manifest_data()["equipment"]}
    if seen_ids != set(expected):
        errors.append(f"required equipment IDs differ: {sorted(seen_ids)}")
    for item in items:
        if isinstance(item, dict) and item.get("equipment_id") in expected:
            if item.get("prim_path") != expected[item["equipment_id"]]:
                errors.append(f"unexpected prim path for {item['equipment_id']}")
    if stage_ids is not None and set(stage_ids) != set(expected.values()):
        errors.append("USD equipment prim path set differs from contract")
    return errors


def _render_item(identity: str, translation: tuple, dimensions: tuple, color: tuple,
                 metadata: bool) -> str:
    x, y, z = translation
    sx, sy, sz = dimensions
    r, g, b = color
    attrs = f'        custom string twin:equipmentId = "{identity}"\n' if metadata else ""
    return (
        f'    def Xform "{identity}"\n'
        '    {\n'
        f'{attrs}'
        f'        double3 xformOp:translate = ({x}, {y}, {z})\n'
        '        uniform token[] xformOpOrder = ["xformOp:translate"]\n'
        '        def Cube "Geometry"\n'
        '        {\n'
        '            double size = 1\n'
        f'            float3 xformOp:scale = ({sx}, {sy}, {sz})\n'
        '            uniform token[] xformOpOrder = ["xformOp:scale"]\n'
        f'            color3f[] primvars:displayColor = [({r}, {g}, {b})]\n'
        '        }\n'
        '    }\n'
    )


def _reference_path(asset_path: Path, layout_path: Path) -> str:
    """Write a portable USD file-relative reference, independent of cwd."""
    return os.path.relpath(asset_path, start=layout_path.parent).replace("\\", "/")


def _render_referenced_item(identity: str, translation: tuple, model: dict, layout_path: Path) -> str:
    x, y, z = translation
    sx, sy, sz = model["scale"]
    rx, ry, rz = model["rotation_deg"]
    ref = _reference_path(model["absolute_path"], layout_path)
    return (
        f'        def Xform "{identity}"\n'
        '        {\n'
        f'            custom string twin:equipmentId = "{identity}"\n'
        f'            double3 xformOp:translate = ({x}, {y}, {z})\n'
        '            uniform token[] xformOpOrder = ["xformOp:translate"]\n'
        '            def Xform "Geometry" (\n'
        f'                prepend references = @{ref}@\n'
        '            )\n'
        '            {\n'
        f'                float3 xformOp:rotateXYZ = ({rx}, {ry}, {rz})\n'
        f'                float3 xformOp:scale = ({sx}, {sy}, {sz})\n'
        '                uniform token[] xformOpOrder = ["xformOp:rotateXYZ", "xformOp:scale"]\n'
        '            }\n'
        '        }\n'
    )


def _fallback_layout(models: dict[str, dict[str, Any]], layout_path: Path) -> str:
    locations = "".join(_render_item(name, pos, dim, color, False) for name, pos, dim, color in LOCATIONS)
    equipment = "".join(_render_referenced_item(identity, pos, models[identity], layout_path)
                        for identity, _kind, group, pos, dim, color in EQUIPMENT if group == "Equipment")
    agvs = "".join(_render_referenced_item(identity, pos, models[identity], layout_path)
                   for identity, _kind, group, pos, dim, color in EQUIPMENT if group == "AGVs")
    def group_block(name: str, items: str) -> str:
        # USDA nesting is represented with braces; indentation is decorative.
        return f'        def Xform "{name}"\n        {{\n{items}        }}\n'
    return (
        '#usda 1.0\n(\n    metersPerUnit = 1\n    upAxis = "Z"\n)\n\n'
        'def Xform "World"\n{\n    def Xform "Factory"\n    {\n'
        + group_block("Locations", locations)
        + group_block("Equipment", equipment)
        + group_block("AGVs", agvs)
        + '    }\n}\n'
    )


def _author_layout_pxr(models: dict[str, dict[str, Any]], layout_path: Path) -> str | None:
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom  # type: ignore
    except ImportError:
        return None
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    for path in ("/World", WORLD, f"{WORLD}/Locations", f"{WORLD}/Equipment", f"{WORLD}/AGVs"):
        UsdGeom.Xform.Define(stage, path)
    def add_location(identity: str, pos: tuple, dim: tuple, color: tuple) -> None:
        path = f"{WORLD}/Locations/{identity}"
        parent = UsdGeom.Xform.Define(stage, path)
        parent.AddTranslateOp().Set(Gf.Vec3d(*pos))
        cube = UsdGeom.Cube.Define(stage, path + "/Geometry")
        cube.CreateSizeAttr(1.0)
        cube.AddScaleOp().Set(Gf.Vec3f(*dim))
        cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])

    for identity, pos, dim, color in LOCATIONS:
        add_location(identity, pos, dim, color)
    for identity, _kind, group, pos, _dim, _color in EQUIPMENT:
        path = f"{WORLD}/{group}/{identity}"
        parent = UsdGeom.Xform.Define(stage, path)
        parent.AddTranslateOp().Set(Gf.Vec3d(*pos))
        parent.GetPrim().CreateAttribute("twin:equipmentId", Sdf.ValueTypeNames.String, custom=True).Set(identity)
        anchor = UsdGeom.Xform.Define(stage, path + "/Geometry")
        asset = models[identity]
        # Anonymous pxr stages have no filesystem anchor. Authoring a relative
        # reference here emits false unresolved-asset warnings during composition.
        # Compose with a real absolute file, then localize the exported USDA
        # reference against layout.usda so delivered USD remains portable.
        anchor.GetPrim().GetReferences().AddReference(asset["absolute_path"].as_posix())
        anchor.AddRotateXYZOp().Set(Gf.Vec3f(*asset["rotation_deg"]))
        anchor.AddScaleOp().Set(Gf.Vec3f(*asset["scale"]))
    text = stage.GetRootLayer().ExportToString()
    for model in models.values():
        absolute = model["absolute_path"].as_posix()
        relative = _reference_path(model["absolute_path"], layout_path)
        text = text.replace("@" + absolute + "@", "@" + relative + "@")
    return text


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".factorytwin-", suffix=path.suffix, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_ids_with_pxr(root: Path, models: dict[str, dict[str, Any]] | None = None) -> dict[str, str] | None:
    try:
        from pxr import Sdf, Usd, UsdGeom  # type: ignore
    except ImportError:
        return None
    # The USD LayerRegistry retains a previously opened layout.usda in long
    # running Python/Kit sessions. Re-reading files via Stage.Open alone can
    # otherwise incorrectly validate stale reference arcs after a model swap.
    for layer_path in (root, root.with_name("layout.usda")):
        if layer_path.is_file():
            layer = Sdf.Layer.FindOrOpen(str(layer_path))
            if layer:
                layer.Reload(force=True)
    stage = Usd.Stage.Open(str(root))
    if not stage:
        raise ValueError(f"Usd.Stage.Open returned None: {root}")
    if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        raise ValueError("USD stage must be Z-up")
    if abs(UsdGeom.GetStageMetersPerUnit(stage) - 1.0) > 1e-9:
        raise ValueError("USD stage must use metersPerUnit=1.0")
    if stage.GetDefaultPrim().GetPath().pathString != "/World":
        raise ValueError("defaultPrim must be /World")
    for loc in ("INBOUND", "OUTBOUND"):
        if not stage.GetPrimAtPath(f"{WORLD}/Locations/{loc}").IsValid():
            raise ValueError(f"missing USD location: {loc}")
    result: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for prim in stage.Traverse():
        attr = prim.GetAttribute("twin:equipmentId")
        if not attr.IsValid():
            continue
        path = prim.GetPath().pathString
        if not attr.IsCustom():
            raise ValueError(f"equipmentId attribute must be custom: {path}")
        value = attr.Get()
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"empty USD equipmentId: {path}")
        if value in by_id:
            raise ValueError(f"duplicate USD equipmentId {value}: {by_id[value]} and {path}")
        by_id[value] = path
        result[path] = value
    for identity, _kind, group, *_ in EQUIPMENT:
        path = f"{WORLD}/{group}/{identity}"
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid():
            raise ValueError(f"missing USD prim: {path}")
        attr = prim.GetAttribute("twin:equipmentId")
        if not attr.IsValid() or not attr.IsCustom():
            raise ValueError(f"missing custom USD equipmentId: {path}")
        geometry = stage.GetPrimAtPath(path + "/Geometry")
        if not geometry.IsValid() or not geometry.IsA(UsdGeom.Xform):
            raise ValueError(f"missing USD Geometry Xform reference anchor: {path}")
        if not geometry.HasAuthoredReferences():
            raise ValueError(f"missing authored USD reference: {path}/Geometry")
        rendered = [p for p in Usd.PrimRange(geometry) if p.IsA(UsdGeom.Gprim)]
        if not rendered:
            raise ValueError(f"USD asset reference unresolved or has no Gprim: {path}/Geometry")
        if models is not None:
            expected = _reference_path(models[identity]["absolute_path"], root.with_name("layout.usda"))
            authored = geometry.GetPrimStack()
            refs = [ref.assetPath for primspec in authored for ref in primspec.referenceList.prependedItems]
            if refs != [expected]:
                raise ValueError(f"unexpected USD references for {identity}: {refs!r} != {[expected]!r}")
            if not all(math.isfinite(v) for v in models[identity]["scale"] + models[identity]["rotation_deg"]):
                raise ValueError(f"invalid model transform for {identity}")
    return result


def validate_assets(root: Path, manifest: Path, catalog: Path = CATALOG,
                    overrides: dict[str, str] | None = None) -> tuple[str, list[str]]:
    models = load_visual_catalog(catalog, overrides)
    validate_prefabs_with_pxr(models)
    if not ENVIRONMENT.is_file():
        raise ValueError("missing factory background USD: usd/factory_environment.usda; run build_factory_visuals.py")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    stage_ids = read_ids_with_pxr(root, models)
    if stage_ids is not None:
        from pxr import Usd, UsdGeom  # type: ignore
        composed = Usd.Stage.Open(str(root))
        background = composed.GetPrimAtPath(f"{WORLD}/Environment")
        if not background or not any(p.IsA(UsdGeom.Gprim) for p in Usd.PrimRange(background)):
            raise ValueError("factory background reference missing or has no renderable geometry")
    errors = validate_manifest_data(data, stage_ids)
    return ("PASS" if stage_ids is not None else "NOT RUN (pxr absent)"), errors


def generate(root: Path = ROOT, manifest: Path = MANIFEST, catalog: Path = CATALOG,
             overrides: dict[str, str] | None = None) -> str:
    if root.name != "factory_scene.usda":
        raise ValueError("root USD must be named factory_scene.usda; its sublayer is layout.usda")
    layout_path = root.with_name("layout.usda")
    if not ENVIRONMENT.is_file():
        raise ValueError("missing factory background USD: run python/tools/build_factory_visuals.py first")
    models = load_visual_catalog(catalog, overrides)
    validate_prefabs_with_pxr(models)
    layout_text = _author_layout_pxr(models, layout_path)
    author = "pxr.Usd/UsdGeom" if layout_text is not None else "deterministic ASCII USDA fallback (pxr absent)"
    if layout_text is None:
        layout_text = _fallback_layout(models, layout_path)
    background_reference = _reference_path(ENVIRONMENT, root)
    root_text = ('#usda 1.0\n(\n    defaultPrim = "World"\n'
                 '    metersPerUnit = 1\n    upAxis = "Z"\n'
                 f'    subLayers = [\n        @layout.usda@,\n        @{background_reference}@\n    ]\n)\n')
    _atomic_write(layout_path, layout_text)
    _atomic_write(root, root_text)
    data = manifest_data()
    _atomic_write(manifest, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    stage_status, errors = validate_assets(root, manifest, catalog, overrides)
    if errors:
        raise ValueError("; ".join(errors))
    print(f"USD root: {root}")
    print(f"USD sublayer: {layout_path}")
    print(f"Manifest: {manifest} ({len(data['equipment'])} equipment IDs)")
    print(f"Writer: {author}")
    print("Manifest structural validation: PASS")
    print("Usd.Stage.Open / 7 locations and equipment prims / metadata / references: " + stage_status)
    return author


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT, help="Root USD file; sibling layout.usda is generated")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--visual-catalog", type=Path, default=CATALOG,
                        help="JSON model_path / scale / rotation_deg catalog")
    parser.add_argument("--model-override", action="append", default=[], metavar="ID=usd/path/to/model.usda",
                        help="Temporary per-ID USD model override; requires --out and --manifest preview paths")
    parser.add_argument("--validate-only", action="store_true", help="Validate existing stage/manifest; do not regenerate")
    args = parser.parse_args()
    try:
        overrides: dict[str, str] = {}
        for pair in args.model_override:
            if "=" not in pair:
                raise ValueError("--model-override must use ID=usd/path.usda")
            identity, asset = pair.split("=", 1)
            if identity in overrides:
                raise ValueError(f"duplicate --model-override: {identity}")
            overrides[identity] = asset
        if overrides and not args.validate_only:
            if args.out.resolve() == ROOT.resolve() or args.manifest.resolve() == MANIFEST.resolve():
                raise ValueError("model override requires isolated --out AND --manifest, preserving canonical assets")
        if args.validate_only:
            stage_status, errors = validate_assets(args.out.resolve(), args.manifest.resolve(),
                                                   args.visual_catalog.resolve(), overrides)
            if errors:
                raise ValueError("; ".join(errors))
            print(f"Manifest structural validation: PASS; USD Stage validation: {stage_status}")
        else:
            generate(args.out.resolve(), args.manifest.resolve(), args.visual_catalog.resolve(), overrides)
        return 0
    except (OSError, ValueError, RuntimeError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
