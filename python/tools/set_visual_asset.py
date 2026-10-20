#!/usr/bin/env python3
"""Swap only a FactoryTwin USD visual model; preserve equipment prims and IDs.

Example:
  python python/tools/set_visual_asset.py --id M01 --asset usd/prefabs/alternate_sphere.usda --scale 2,2,2 --rotation 0,0,0 --dry-run
Omit --dry-run to commit after a complete preview Stage.Open validation.
Close UE/Kit live USD Stage before applying a production swap; then reopen.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import build_usd as b


def _vector(value: str) -> list[float]:
    parts = value.split(",")
    if len(parts) != 3:
        raise ValueError("transform must be three comma-separated numbers")
    return [float(v) for v in parts]


def change_visual(identity: str, asset: str, scale: list[float] | None = None,
                  rotation: list[float] | None = None, *, dry_run: bool = False) -> str:
    """Preflight in isolated USD temp. A failed swap leaves canonical unchanged."""
    if identity not in b.REQUIRED_IDS:
        raise ValueError(f"unknown equipment ID: {identity}")
    if not b.CATALOG.exists():
        raise FileNotFoundError(f"visual catalog not found: {b.CATALOG}")
    data = json.loads(b.CATALOG.read_text(encoding="utf-8"), object_pairs_hook=b._reject_duplicate_json)
    candidate = data["models"][identity]
    candidate["model_path"] = asset
    if scale is not None:
        candidate["scale"] = scale
    if rotation is not None:
        candidate["rotation_deg"] = rotation
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.TemporaryDirectory(prefix="_preview_visual_", dir=b.PROJECT / "usd") as tmp_dir:
        tmp = Path(tmp_dir)
        temporary_catalog = tmp / "visual_assets.json"
        temporary_catalog.write_text(payload, encoding="utf-8")
        b.load_visual_catalog(temporary_catalog)
        b.validate_prefabs_with_pxr(b.load_visual_catalog(temporary_catalog))
        # Stronger than asset existence: actually compose all five references,
        # then verify their reference arcs, schema, identity and renderables.
        b.generate(tmp / "factory_scene.usda", tmp / "equipment_manifest_preview.json", temporary_catalog)
        result, errors = b.validate_assets(tmp / "factory_scene.usda",
                                           tmp / "equipment_manifest_preview.json", temporary_catalog)
        if result != "PASS" or errors:
            raise ValueError("model swap requires pxr Stage.Open PASS: " + "; ".join(errors))
    if dry_run:
        return f"DRY RUN PASS {identity} -> {asset}; canonical catalog/USD unchanged"

    # All candidate paths, coordinates and composed references passed. Retain
    # complete pre-commit bytes for rollback if the filesystem write fails.
    files = (b.CATALOG, b.ROOT, b.ROOT.with_name("layout.usda"), b.MANIFEST)
    snapshots = {path: path.read_bytes() if path.exists() else None for path in files}
    try:
        with tempfile.TemporaryDirectory(prefix="_commit_visual_", dir=b.PROJECT / "usd") as tmp_dir:
            temp_catalog = Path(tmp_dir) / "candidate_catalog.json"
            temp_catalog.write_text(payload, encoding="utf-8")
            b.generate(b.ROOT, b.MANIFEST, temp_catalog)
            b._atomic_write(b.CATALOG, payload)
            status, errors = b.validate_assets(b.ROOT, b.MANIFEST, b.CATALOG)
            if status != "PASS" or errors:
                raise ValueError("post-commit USD validation failed: " + "; ".join(errors))
    except Exception:
        for path, previous in snapshots.items():
            if previous is None:
                if path.exists():
                    path.unlink()
            else:
                b._atomic_write(path, previous.decode("utf-8"))
        raise
    return f"COMMITTED {identity} -> {asset}; five equipment IDs and references validated"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="M01/M02/QC01/AGV01/AGV02")
    parser.add_argument("--asset", required=True, help="Safe project-relative usd/*.usd(a|c) file")
    parser.add_argument("--scale", type=_vector, default=None, help="metres-relative XYZ, e.g. 2,2,2")
    parser.add_argument("--rotation", type=_vector, default=None, help="degrees XYZ, e.g. 0,0,90")
    parser.add_argument("--dry-run", action="store_true", help="Validate preview without touching canonical assets")
    args = parser.parse_args()
    try:
        print(change_visual(args.id, args.asset, args.scale, args.rotation, dry_run=args.dry_run))
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"MODEL SWAP REJECTED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
