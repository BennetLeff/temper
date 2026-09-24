#!/usr/bin/env python3
"""Generate source-bound native CurrentSenseUnit KiCad artifacts.

Engineering policy, placement search and routing are outside this adapter.
Every footprint pose and the rectangular Edge.Cuts outline must be supplied
by the caller.  The source build must already have passed Atopile and strict
export checks; this script only transports those artifacts through the
existing bridge and generators.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ENTRY_MODULE = "CurrentSenseUnit"
DEFAULT_MODULES = ("current_sense", "ocp", "unit_io")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_donors(repo: Path):
    sys.path[:0] = [str(repo / "harness-lab"), str(repo / "scripts")]
    import block_source  # type: ignore[import-not-found]
    import check_stale_extensions  # type: ignore[import-not-found]
    import gen_pcb_skeleton as skeleton  # type: ignore[import-not-found]
    import gen_schematics as schematics  # type: ignore[import-not-found]

    return block_source, check_stale_extensions, skeleton, schematics


def _require_poses(
    poses_path: Path,
    by_path: dict[str, str],
    owned_paths: set[str],
) -> dict[str, tuple[float, float, float]]:
    try:
        raw = json.loads(poses_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid poses JSON {poses_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("poses must be an object mapping instance paths to [x,y,angle]")
    unknown = sorted(set(raw) - owned_paths)
    missing = sorted(owned_paths - set(raw))
    if unknown or missing:
        raise ValueError(
            "poses must cover exactly selected source components; "
            + json.dumps({"missing": missing, "unknown": unknown})
        )
    staging: dict[str, tuple[float, float, float]] = {}
    for instance_path, pose in raw.items():
        if (
            not isinstance(pose, list)
            or len(pose) != 3
            or any(not isinstance(value, (int, float)) for value in pose)
        ):
            raise ValueError(
                f"pose for {instance_path!r} must be numeric [x_mm,y_mm,angle_deg]"
            )
        reference = by_path[instance_path]
        staging[reference] = tuple(float(value) for value in pose)
    return staging


def _outline(path: Path) -> tuple[float, float, float, float]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid outline JSON {path}: {exc}") from exc
    values = raw.get("outline_mm") if isinstance(raw, dict) else raw
    if (
        not isinstance(values, list)
        or len(values) != 4
        or any(not isinstance(value, (int, float)) for value in values)
    ):
        raise ValueError("outline must be [x1_mm,y1_mm,x2_mm,y2_mm]")
    x1, y1, x2, y2 = (float(value) for value in values)
    if not x2 > x1 or not y2 > y1:
        raise ValueError("outline must have x2>x1 and y2>y1")
    return x1, y1, x2, y2


def _filter_netlist(netlist: Any, refs: set[str]) -> Any:
    netlist.components = {
        ref: component
        for ref, component in netlist.components.items()
        if ref in refs
    }
    for net in netlist.nets.values():
        net.nodes = [node for node in net.nodes if node[0] in refs]
    return netlist


def _apply_selected_symbol_identity(
    netlist: Any,
    selected_mpn_by_ref: dict[str, str],
    bom_mpn_by_ref: dict[str, str],
    schematics: Any,
) -> None:
    """Rekey numeric-pin symbols to the selected MPN for this native projection.

    Atopile's compiled libpart is shared by footprint. Its part name and pin
    *names* can therefore belong to another component. Retain only its pin
    numbers and their order; the resolved export and BOM must agree on the
    actual part identity for every selected reference. This does not assert
    that functional pin names have been checked against device datasheets.
    """
    refs = set(netlist.components)
    if set(selected_mpn_by_ref) != refs:
        missing = sorted(refs - set(selected_mpn_by_ref))
        extra = sorted(set(selected_mpn_by_ref) - refs)
        raise ValueError(
            f"missing selected MPN or extra reference: missing={missing}, extra={extra}"
        )
    if set(bom_mpn_by_ref) != refs:
        missing = sorted(refs - set(bom_mpn_by_ref))
        extra = sorted(set(bom_mpn_by_ref) - refs)
        raise ValueError(
            f"missing BOM MPN or extra reference: missing={missing}, extra={extra}"
        )

    selected_libparts: dict[str, Any] = {}
    sanitized_names: dict[str, str] = {}
    for ref, component in netlist.components.items():
        mpn = selected_mpn_by_ref[ref]
        if not isinstance(mpn, str) or not mpn.strip():
            raise ValueError(f"{ref}: missing selected MPN")
        if mpn != bom_mpn_by_ref[ref]:
            raise ValueError(
                f"{ref}: MPN mismatch: resolved={mpn!r}, BOM={bom_mpn_by_ref[ref]!r}"
            )
        alias = component.part_name
        source_libpart = netlist.libparts.get(alias)
        if source_libpart is None or not source_libpart.pins:
            raise ValueError(f"{ref}: missing compiled pin-number libpart {alias!r}")
        numbers = [num for num, _name in source_libpart.pins]
        if any(not isinstance(num, str) or not num for num in numbers) or len(
            numbers
        ) != len(set(numbers)):
            raise ValueError(f"{ref}: invalid or duplicate compiled pin numbers")
        symbol_id = schematics._sanitize_name(mpn)
        prior = sanitized_names.setdefault(symbol_id, mpn)
        if prior != mpn:
            raise ValueError(f"selected MPN symbol ID collision: {prior!r}, {mpn!r}")
        numeric_pins = [(num, num) for num in numbers]
        existing = selected_libparts.get(mpn)
        if existing is not None and existing.pins != numeric_pins:
            raise ValueError(
                f"{ref}: selected MPN {mpn!r} has conflicting compiled pin numbers"
            )
        if existing is None:
            selected_libparts[mpn] = schematics.LibPart(
                part_name=mpn,
                description=(
                    f"{mpn}; pin-number connectivity from compiled netlist; "
                    "functional pin names unverified"
                ),
                pins=numeric_pins,
            )
        component.part_name = mpn
        component.description = selected_libparts[mpn].description

    for net in netlist.nets.values():
        for ref, pin in net.nodes:
            if ref not in refs:
                raise ValueError(f"net {net.name!r} contains unselected reference {ref!r}")
            selected_pins = {
                num for num, _name in selected_libparts[selected_mpn_by_ref[ref]].pins
            }
            if pin not in selected_pins:
                raise ValueError(f"{ref}: net {net.name!r} uses absent pin number {pin!r}")
    netlist.libparts = selected_libparts


def _require_source_hashes(repo: Path, source: Path, export: Any) -> dict[str, str]:
    """Require source provenance and keep every hashed path inside ``source``."""
    repo_root = repo.resolve()
    source_root = source.resolve()
    try:
        source_root.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(
            f"source build must be contained under repo: {source_root}"
        ) from exc
    if not isinstance(export, dict):
        raise ValueError("resolved source export must be a JSON object")
    source_hashes = export.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("resolved source export must contain a nonempty source_sha256 map")
    checked: dict[str, str] = {}
    for relative, expected in source_hashes.items():
        if not isinstance(relative, str) or not relative:
            raise ValueError("source_sha256 keys must be nonempty relative paths")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"source hash path escapes source build: {relative!r}")
        target = (source_root / relative_path).resolve()
        try:
            target.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"source hash path escapes source build: {relative!r}") from exc
        if not target.is_file():
            raise FileNotFoundError(f"hashed source file is absent: {target}")
        if (
            not isinstance(expected, str)
            or len(expected) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in expected)
        ):
            raise ValueError(f"invalid SHA-256 for source path: {relative!r}")
        actual = sha256(target)
        if actual.lower() != expected.lower():
            raise ValueError(f"stale source: {relative}")
        checked[relative] = actual
    return checked


def build(
    repo: Path,
    source: Path,
    output: Path,
    poses_path: Path,
    outline_path: Path,
    modules: tuple[str, ...],
    entry_module: str = ENTRY_MODULE,
    entry_file: str = "elec/src/current_sense_unit.ato",
    title: str = "Standalone Current-Sensing Unit",
    local_libraries: Path | None = None,
    assembly_only: tuple[dict[str, str], ...] = (),
) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite native output: {output}")
    required = (
        source / "stdout.txt",
        source / "build" / "default.net",
        source / "build" / "default.csv",
        source / "resolved-components.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "source build is incomplete; refusing native generation: "
            + ", ".join(missing)
        )
    stdout = (source / "stdout.txt").read_text(encoding="utf-8")
    if "Build complete!" not in stdout or "FAILED" in stdout:
        raise ValueError("source build did not pass compiler gate")

    block_source, stale, skeleton, schematics = load_donors(repo)
    crate = next(
        (
            crate
            for crate in stale.discover_crates(repo)
            if crate.name == "temper-design-bundle"
        ),
        None,
    )
    if crate is None:
        raise ValueError("temper-design-bundle crate is not discoverable")
    extension = stale.check_module(crate)
    if extension.state != "fresh" or extension.artifact is None:
        raise ValueError("strict source bridge is not fresh: " + extension.detail)
    extension_sha = sha256(extension.artifact)

    net_path = source / "build" / "default.net"
    csv_path = source / "build" / "default.csv"
    export_path = source / "resolved-components.json"
    export = json.loads(export_path.read_text(encoding="utf-8"))
    _require_source_hashes(repo, source, export)

    bridge = block_source.bridge_netlist(net_path, entry_module)
    bom = block_source.parse_bom_mpn(csv_path.read_text(encoding="utf-8"))
    bundle = block_source._design_bundle()
    converted = json.loads(
        bundle.candidate_convert_bridge(
            json.dumps(export, sort_keys=True),
            json.dumps(bridge, sort_keys=True),
            json.dumps(bom, sort_keys=True),
            entry_module,
        )
    )
    by_path = {component["instance_path"]: component["reference"] for component in bridge["components"]}
    # The Rust bridge compares the full resolved source against each explicit
    # assembly-only declaration before the PCB projection can omit it.
    scope = (
        json.loads(
            bundle.candidate_board_scope(
                json.dumps(converted, sort_keys=True),
                json.dumps(assembly_only, sort_keys=True),
            )
        )
        if assembly_only
        else {
            "board_references": [component["reference"] for component in converted["components"]],
            "assembly_only_components": [],
        }
    )
    owned = set(scope["board_references"])
    owned_paths = {path for path, reference in by_path.items() if reference in owned}
    if len(owned_paths) != len(owned):
        raise ValueError("board scope references are not unique compiled instances")
    if not owned_paths:
        raise ValueError("compiled CurrentSenseUnit source contains no components")
    section = {
        "components": [
            component
            for component in converted["components"]
            if component["reference"] in owned
        ]
    }
    section_bridge = {
        "components": [
            component for component in bridge["components"] if component["reference"] in owned
        ],
        "nets": [
            {
                "name": net["name"],
                "nodes": [node for node in net["nodes"] if node[0] in owned],
            }
            for net in bridge["nets"]
        ],
    }
    attrs = {
        component["address"].split("::", 1)[1]: component["attributes"]
        for component in export["components"]
    }
    selected_mpn_by_ref = {
        ref: attrs[path]["mpn"] for path, ref in by_path.items() if ref in owned
    }
    sch = _filter_netlist(schematics.parse_netlist(net_path), owned)
    _apply_selected_symbol_identity(
        sch, selected_mpn_by_ref, {ref: bom[ref] for ref in owned}, schematics
    )
    schematics.apply_bom_values(sch, {ref: bom[ref] for ref in owned})

    output.mkdir(parents=True)
    table, libraries = block_source.vendor_candidate_libs(
        section, bridge, repo, output / "candidate-libs", local_libraries=local_libraries
    )
    nicknames = {component["reference"]: component["footprint"] for component in section_bridge["components"]}
    census = block_source.footprint_pad_census(table, set(nicknames.values()))
    entries, unconnected = block_source.build_strict_pin_map(
        section, section_bridge, census, nicknames
    )
    pads = {ref: census[nickname]["pads"] for ref, nickname in nicknames.items()}
    pins = {
        ref: sorted(
            {
                pin
                for net in section_bridge["nets"]
                for node_ref, pin in net["nodes"]
                if node_ref == ref
            }
        )
        for ref in owned
    }
    bundle.candidate_validate_pin_map(
        json.dumps(entries, sort_keys=True),
        json.dumps(pads, sort_keys=True),
        json.dumps(pins, sort_keys=True),
        json.dumps(unconnected, sort_keys=True),
    )

    poses = _require_poses(poses_path, by_path, owned_paths)
    outline_mm = _outline(outline_path)
    netlist = _filter_netlist(skeleton.parse_netlist(net_path), owned)
    for component in netlist.components.values():
        component.value = attrs[component.sheetpath].get("value") or attrs[component.sheetpath]["mpn"]
    pin_map = {(entry["reference"], entry["pin"]): entry["pad"] for entry in entries}
    board_path = output / "section.kicad_pcb"
    board_summary = skeleton.generate_candidate_board(
        netlist,
        pin_map,
        {tuple(pair) for pair in unconnected},
        table,
        outline_mm,
        poses,
        board_path,
        values={ref: component.value for ref, component in netlist.components.items()},
    )

    layout = schematics.SchematicLayout(
        root_sheet="section.kicad_sch",
        sheets=("CurrentSense",),
        sheet_files={"CurrentSense": "section.kicad_sch"},
        module_to_sheet=dict.fromkeys(modules, "CurrentSense"),
        title=title,
        sheet_description=f"Generated from {entry_module} Atopile source",
        flat=True,
    )
    files = schematics._generate_all_sheets(sch, output, layout)
    schematics._write_schematics(files, output)
    schematics.write_candidate_layout_config(layout, output / "schematic_layout.json")

    if sha256(extension.artifact) != extension_sha:
        raise ValueError("strict source bridge artifact changed during generation")
    manifest = {
        "schema": "zapote.current-sense.native-source-manifest.v1",
        "entry": f"{entry_file}:{entry_module}",
        "source": str(source),
        "module_prefixes": list(modules),
        "component_scope": (
            "compiled source minus explicitly declared assembly-only parts"
            if assembly_only else "all components in the standalone entry"
        ),
        "assembly_only_components": scope["assembly_only_components"],
        "strict_bridge_extension": {
            "path": str(extension.artifact),
            "sha256": extension_sha,
            "freshness_method": extension.method,
            "detail": extension.detail,
        },
        "input_hashes": {
            "default.net": sha256(net_path),
            "default.csv": sha256(csv_path),
            "resolved-components.json": sha256(export_path),
            "poses.json": sha256(poses_path),
            "outline.json": sha256(outline_path),
        },
        "bridge": section_bridge,
        "full_bridge": bridge,
        "components": section["components"],
        "libraries": libraries,
        "strict_pin_map": entries,
        "unconnected_pads": unconnected,
        "footprint_census": census,
        "source_attributes": attrs,
        "poses": {path: list(poses[reference]) for path, reference in by_path.items() if path in owned_paths},
        "outline_mm": list(outline_mm),
        "board": board_summary,
        "board_sha256": sha256(board_path),
        "schematic_files": sorted(files),
    }
    (output / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "source-bound-native-generated", "output": str(output)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--poses", type=Path, required=True)
    parser.add_argument("--outline", type=Path, required=True)
    parser.add_argument("--module", dest="modules", action="append", default=None)
    args = parser.parse_args()
    build(
        args.repo.resolve(),
        args.source.resolve(),
        args.output.resolve(),
        args.poses.resolve(),
        args.outline.resolve(),
        tuple(args.modules or DEFAULT_MODULES),
    )


if __name__ == "__main__":
    main()
