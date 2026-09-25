"""Source/export glue for the growing candidate; engineering verdicts are Rust.

Consumes a successful, retained full Top build, rather than inventing a second
circuit. Uses the existing strict bridge and KiCad generators. Explicit agent
poses are inputs; this module does not choose placements or routes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "harness-lab"), str(REPO / "scripts")]
import block_source
import gen_pcb_skeleton as skeleton
import gen_schematics as schematics
import check_stale_extensions


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source: Path, output: Path, poses_path: Path, unit: bool = False) -> None:
    crate = next(c for c in check_stale_extensions.discover_crates(REPO)
                 if c.name == "temper-design-bundle")
    extension = check_stale_extensions.check_module(crate)
    if extension.state != "fresh" or extension.artifact is None:
        raise ValueError("required strict source bridge is not fresh: " + extension.detail)
    extension_sha256 = digest(extension.artifact)
    stdout = (source / "stdout.txt").read_text()
    if "Build complete!" not in stdout or "FAILED" in stdout:
        raise ValueError("source build did not pass")
    net_path = source / "build/default.net"
    export = json.loads((source / "resolved-components.json").read_text())
    for relative, expected in export["source_sha256"].items():
        if digest(source / relative) != expected:
            raise ValueError(f"stale source: {relative}")
    entry = "RTDUnit" if unit else "Top"
    bridge = block_source.bridge_netlist(net_path, entry)
    bom = block_source.parse_bom_mpn((source / "build/default.csv").read_text())
    bundle = block_source._design_bundle()
    converted = json.loads(bundle.candidate_convert_bridge(
        json.dumps(export), json.dumps(bridge), json.dumps(bom), entry))
    prefixes = ("rtd_pan.", "mcu.", "power_mgmt.buck_3v3.")
    owned = {c["reference"] for c in bridge["components"]
             if unit or c["instance_path"].startswith(prefixes)}
    section = {"components": [c for c in converted["components"] if c["reference"] in owned]}
    output.mkdir(parents=True, exist_ok=True)
    table, libraries = block_source.vendor_candidate_libs(
        section, bridge, REPO, output / "candidate-libs")
    section_bridge = {
        "components": [c for c in bridge["components"] if c["reference"] in owned],
        "nets": [{"name": n["name"], "nodes": [p for p in n["nodes"] if p[0] in owned]} for n in bridge["nets"]],
    }
    nicks = {c["reference"]: c["footprint"] for c in section_bridge["components"]}
    census = block_source.footprint_pad_census(table, set(nicks.values()))
    entries, unconnected = block_source.build_strict_pin_map(section, section_bridge, census, nicks)
    pads = {ref: census[nick]["pads"] for ref, nick in nicks.items()}
    pins = {ref: sorted({pin for n in section_bridge["nets"] for r, pin in n["nodes"] if r == ref}) for ref in owned}
    bundle.candidate_validate_pin_map(json.dumps(entries), json.dumps(pads), json.dumps(pins), json.dumps(unconnected))
    netlist = skeleton.parse_netlist(net_path)
    netlist.components = {r: c for r, c in netlist.components.items() if r in owned}
    for net in netlist.nets.values():
        net.nodes = [p for p in net.nodes if p[0] in owned]
    by_path = {c["instance_path"]: c["reference"] for c in section_bridge["components"]}
    poses = json.loads(poses_path.read_text())
    staging = {by_path[path]: tuple(pose) for path, pose in poses.items()}
    attrs = {c["address"].split("::", 1)[1]: c["attributes"] for c in export["components"]}
    for comp in netlist.components.values():
        comp.value = attrs[comp.sheetpath].get("value") or attrs[comp.sheetpath]["mpn"]
    pin_map = {(e["reference"], e["pin"]): e["pad"] for e in entries}
    skeleton.generate_candidate_board(netlist, pin_map, {tuple(p) for p in unconnected}, table,
        (0.0, 0.0, 60.0, 60.0) if unit else (8.0, 20.0, 172.0, 254.0),
        staging, output / "section.kicad_pcb")
    # Generate full Top schematic. Global labels retain Atopile's global net
    # identities across sheets, unlike the donor's local/hierarchical labels.
    sch = schematics.parse_netlist(net_path)
    schematics.apply_bom_values(sch, schematics.load_bom_values(source / "build/default.csv"))
    layout = schematics.SchematicLayout(
        root_sheet="section.kicad_sch", sheets=("RTD",),
        sheet_files={"RTD": "section.kicad_sch"},
        module_to_sheet={"rtd_pan": "RTD", "unit_io": "RTD"},
        title="Standalone RTD Unit", sheet_description="Generated from RTDUnit Atopile source",
        flat=True) if unit else None
    files = schematics._generate_all_sheets(sch, output, layout)
    for name, content in files.items():
        content = content.replace('(hierarchical_label ', '(global_label ')
        content = content.replace('(label ', '(global_label ')
        (output / name).write_text(content)
    if digest(extension.artifact) != extension_sha256:
        raise ValueError("strict source bridge artifact changed during generation")
    manifest = {"schema": "zapote.rtd.source-section.v1", "source": str(source),
        "entry": entry, "standalone_unit": unit,
        "strict_bridge_extension": {"path": str(extension.artifact),
            "sha256": extension_sha256, "freshness_method": extension.method,
            "detail": extension.detail},
        "input_hashes": {str(p.relative_to(source)): digest(p) for p in
            [net_path, source / "build/default.csv", source / "resolved-components.json"]},
        "poses_sha256": digest(poses_path), "generator_sha256": digest(Path(__file__)),
        "bridge": section_bridge, "full_bridge": bridge, "components": section["components"], "libraries": libraries,
        "strict_pin_map": entries, "unconnected_pads": unconnected,
        "footprint_census": census, "source_attributes": attrs,
        "board_sha256": digest(output / "section.kicad_pcb")}
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"owned_components": len(owned), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("poses", type=Path)
    parser.add_argument("--unit", action="store_true")
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve(), args.poses.resolve(), args.unit)
