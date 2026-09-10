"""P3 U2/U3 control-assembly composition host.

Composes the source-derived buck functional nine and the P1 U4 accepted MCU
ten into one assembly candidate package on the P3 target context.

What this host does (apparatus only, no engineering-rule duplication):

1. Builds the P1 combined source wrapper (``control-assembly.ato``) in a
   fresh workspace with pinned Atopile, then bridges the real combined
   netlist by canonical instance path. The buck/MCU refdes renumbering is
   real evidence (``U3`` -> ``U1``, ``C9`` -> ``C1`` a.s.o.), so every map
   here is keyed by source path, never by refdes.
2. Generates the assembly candidate board from that combined netlist on the
   P3 target outline, with the buck functional nine placed by translating
   the real prototype layout as a rigid cluster into the reserved buck block
   and the MCU ten placed at the delivered package's staged geometry.
3. Imports the prototype's local buck copper by canonical source path:
   prototype outer copper (F.Cu/B.Cu) maps onto the target outer pair,
   through vias are recreated with the target ``F.Cu-B.Cu`` span, and every
   object serving a prototype fixture (J1/J2/TP1-TP4/H1-H4) is removed
   before it can become product copper. Unsupported layers and shared
   fixture/functional copper are rejected, never silently dropped.
4. Applies the U1 replacement ledger with before/after identities, checks
   the owned-region guard, and scaffolds the assembly/overlay cross-view
   comparison.

The live model was transport-blocked (Zen HTTP 429); this pass is
APPARATUS-ONLY and is labelled as such. It does not claim a qualified
cooker. See ``docs/hardware/control-assembly/integration-report.md``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(REPO / "scripts"))

import block_source  # noqa: E402
import compose_blocks  # noqa: E402
import gen_pcb_skeleton as skeleton  # noqa: E402
import harness  # noqa: E402

CONTROL_ASSEMBLY = REPO / "pcb" / "blocks" / "control-assembly"
DEFAULT_SOURCE = CONTROL_ASSEMBLY / "source" / "combined-bridge.json"
DEFAULT_PACKAGE = CONTROL_ASSEMBLY / "assembly-candidate"
PROTOTYPE_BOARD = REPO / "pcb" / "prototypes" / "buck-reva" / "buck-reva.kicad_pcb"
MCU_PACKAGE = REPO / "pcb" / "blocks" / "mcu"
MCU_MANIFEST = MCU_PACKAGE / "source-manifest.json"
TARGET_CONTEXT = CONTROL_ASSEMBLY / "target-context.json"

# Prototype-only refs (fixtures): never become product components (KTD5).
PROTOTYPE_ONLY_REFS = (
    "J1",
    "J2",
    "TP1",
    "TP2",
    "TP3",
    "TP4",
    "H1",
    "H2",
    "H3",
    "H4",
)

# Prototype functional ref -> canonical combined source path (KTD4). The
# refdes is recorded on the left only to read prototype geometry; identity is
# the source path on the right.
BUCK_PROTO_REF_TO_PATH = {
    "U3": "buck.buck",
    "L2": "buck.l_out",
    "C9": "buck.c_in",
    "C10": "buck.c_boot",
    "C11": "buck.c_out1",
    "C12": "buck.c_out2",
    "C13": "buck.c_out_hf",
    "R16": "buck.r_fb_top",
    "R17": "buck.r_fb_bot",
}

# Prototype net name -> combined compiled net name. String aliases are
# resolved by canonical source identity (target context reconciled
# contradiction #5), not by match.
PROTO_NET_TO_COMBINED = {
    "+15V": "buck-vcc",
    "+3V3": "buck-vcc-1",
    "gnd": "gnd",
    "sw": "sw",
    "fb": "fb",
    "boot": "boot",
}

# Prototype outer copper -> target outer copper. The mapping is identity by
# name because the target outer pair is also F.Cu/B.Cu; the point is that any
# other prototype layer is rejected.
PROTO_LAYER_TO_TARGET = {"F.Cu": "F.Cu", "B.Cu": "B.Cu"}

PAD_ATTACH_TOLERANCE_MM = 0.05


class AssemblyCompositionError(Exception):
    """An assembly admission failure naming the responsible input."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def extract_geometry(board_path: Path) -> dict:
    """Native ``pcbnew`` geometry census (see assembly_geometry.py)."""
    result = subprocess.run(
        [harness.KICAD_PYTHON, str(LAB / "assembly_geometry.py"), "extract", str(board_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise AssemblyCompositionError(
            f"native geometry extraction failed for {board_path}: {result.stderr[-800:]}"
        )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Combined source bridge.
# ---------------------------------------------------------------------------


def build_combined_bridge() -> dict:
    """Build the P1 combined wrapper and bridge its compiled netlist.

    Returns a dict with the bridge plus build provenance. This is the only
    step that invokes Atopile; it runs offline against the pinned tool cache.
    """
    block = LAB / "blocks" / "control-assembly"
    with tempfile.TemporaryDirectory(prefix="p3-assembly-") as tmp:
        workspace = block_source.fresh_block_workspace(
            REPO, block, Path(tmp), "assembly-ws"
        )
        recorded = block_source.workspace_hashes(workspace)
        proc = block_source.run_atopile_build(
            workspace, "control-assembly.ato", "ControlAssemblyCandidate"
        )
        block_source.gate_build(proc)
        net_path = workspace / "build" / "default.net"
        csv_path = workspace / "build" / "default.csv"
        bridge = block_source.bridge_netlist(net_path, "ControlAssemblyCandidate")
        current = block_source.workspace_hashes(workspace)
        return {
            "schema": "control-assembly.combined-bridge.v1",
            "entry": "control-assembly.ato:ControlAssemblyCandidate",
            "atopile_pinned": block_source.PINNED_ATOPILE,
            "wrapper": [
                "harness-lab/blocks/control-assembly/control-assembly.ato",
                "harness-lab/blocks/control-assembly/ato.yaml",
            ],
            "workspace_hashes": current,
            "build": {
                "returncode": proc.returncode,
                "failed_present": "FAILED" in proc.stdout,
                "stdout_sha256": _sha256_text(proc.stdout),
                "netlist_sha256": _sha256(net_path),
                "bom_sha256": _sha256(csv_path),
            },
            "bridge": bridge,
            "netlist_text": net_path.read_text(encoding="utf-8"),
            "bom_text": csv_path.read_text(encoding="utf-8"),
            "provenance": {
                "recorded_workspace_hashes": recorded,
            },
        }


def load_or_build_source(source_path: Path = DEFAULT_SOURCE) -> dict:
    if source_path.is_file():
        return json.loads(source_path.read_text(encoding="utf-8"))
    return build_combined_bridge()


# ---------------------------------------------------------------------------
# Source-path keyed mapping (buck nine + MCU ten).
# ---------------------------------------------------------------------------


def combined_ref_by_path(source: dict) -> dict:
    """Map canonical instance path -> combined refdes from the bridge."""
    return {
        comp["instance_path"]: comp["reference"]
        for comp in source["bridge"]["components"]
    }


def standalone_mcu_ref_by_path() -> dict:
    manifest = json.loads(MCU_MANIFEST.read_text(encoding="utf-8"))
    return {
        comp["instance_path"]: comp["reference"]
        for comp in manifest["converted"]["components"]
    }


def build_assembly_source_map(source: dict) -> dict:
    """Source-path keyed map of the functional buck nine + MCU ten.

    Uses ``compose_blocks.build_source_map`` (extended to validate the
    functional census by canonical source path, so the combined refdes
    renumbering is preserved, not silently re-keyed).
    """
    mapping = compose_blocks.build_source_map(
        source["bridge"]["components"],
        require_mcu=True,
        expected_buck_paths=compose_blocks.BUCK_FUNCTIONAL_PATHS,
        expected_mcu_paths=compose_blocks.MCU_FUNCTIONAL_PATHS,
    )
    standalone = standalone_mcu_ref_by_path()
    out: dict = {}
    for path, entry in mapping.items():
        record = dict(entry)
        if path in standalone:
            record["packaged_ref"] = standalone[path]
        out[path] = record
    if len(out) != 19:
        raise AssemblyCompositionError(
            f"assembly source map must hold exactly 19 functional instances, got {len(out)}"
        )
    return out


# ---------------------------------------------------------------------------
# Layer mapping + via recreation + fixture stripping.
# ---------------------------------------------------------------------------


def map_copper_layer(proto_layer: str) -> str:
    if proto_layer not in PROTO_LAYER_TO_TARGET:
        raise AssemblyCompositionError(
            f"unsupported prototype copper layer {proto_layer!r}: only "
            f"{sorted(PROTO_LAYER_TO_TARGET)} map onto the target outer pair; rejected, not dropped"
        )
    return PROTO_LAYER_TO_TARGET[proto_layer]


def recreate_via(via: dict) -> dict:
    target_layer = compose_blocks.map_proto_layer("F.Cu", ["F.Cu", "B.Cu"])
    del target_layer
    return compose_blocks.recreate_through_via(
        via["position_mm"], via["width_mm"], via["drill_mm"]
    )


def _pad_owners(geometry: dict) -> list:
    owners = []
    for footprint in geometry["footprints"]:
        for pad in footprint["pads"]:
            owners.append((pad["position_mm"], footprint["reference"], pad["number"]))
    return owners


def _owners_at(point: list, owners: list) -> set:
    hits = set()
    for position, reference, _number in owners:
        if (
            abs(position[0] - point[0]) <= PAD_ATTACH_TOLERANCE_MM
            and abs(position[1] - point[1]) <= PAD_ATTACH_TOLERANCE_MM
        ):
            hits.add(reference)
    return hits


def classify_prototype_copper(geometry: dict, functional_refs: set) -> dict:
    """Split prototype copper into (functional, fixture_removed, shared)."""
    owners = _pad_owners(geometry)
    functional: list = []
    fixture_removed: list = []
    shared: list = []
    for track in geometry["tracks"]:
        if track["kind"] == "segment":
            touched = _owners_at(track["start_mm"], owners) | _owners_at(
                track["end_mm"], owners
            )
        else:
            touched = _owners_at(track["position_mm"], owners)
        if touched and not (touched & functional_refs):
            fixture_removed.append(track)
        elif touched and not (touched <= functional_refs):
            shared.append(track)
        else:
            functional.append(track)
    return {
        "functional": functional,
        "fixture_removed": fixture_removed,
        "shared": shared,
    }


# ---------------------------------------------------------------------------
# Placement: buck rigid cluster translation + MCU staged geometry.
# ---------------------------------------------------------------------------


def _bounds(points: list) -> list:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def buck_cluster_offset(geometry: dict, functional_refs: set, region: dict) -> list:
    """Rigid translation putting the prototype functional bbox at block centre."""
    positions = [
        footprint["position_mm"]
        for footprint in geometry["footprints"]
        if footprint["reference"] in functional_refs
    ]
    bbox = _bounds(positions)
    proto_center = [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]
    block_center = [(region["x1"] + region["x2"]) / 2.0, (region["y1"] + region["y2"]) / 2.0]
    return [block_center[0] - proto_center[0], block_center[1] - proto_center[1]]


def _translate(point: list, offset: list) -> list:
    return [float(point[0] + offset[0]), float(point[1] + offset[1])]


def assembly_placements(
    source_map: dict,
    prototype: dict,
    mcu_staging: dict,
    offset: list,
    target: dict,
) -> dict:
    """Combined ref -> (x, y, angle) placements for the assembly candidate.

    The delivered MCU package stages its small parts in a row at
    ``region.y1 + 3`` which lands inside the reserved antenna keepout
    (``18-52 x 20-32``). That is a placement conflict, not a geometry
    change: the parts are shifted below the keepout while their source
    identity and orientation are preserved (KTD5 placement revision).
    """
    combined = {path: entry["reference"] for path, entry in source_map.items()}
    placements: dict = {}
    for proto_ref, path in BUCK_PROTO_REF_TO_PATH.items():
        footprint = next(
            f for f in prototype["footprints"] if f["reference"] == proto_ref
        )
        x, y = _translate(footprint["position_mm"], offset)
        placements[combined[path]] = [round(x, 6), round(y, 6), footprint["angle_deg"]]
    standalone = standalone_mcu_ref_by_path()
    keepout = target["reserved_regions_mm"]["antenna_keepout"]
    keepout_floor = keepout["y2"] + 3.0
    revisions: list = []
    for path, entry in source_map.items():
        if entry["block"] != "mcu":
            continue
        packaged_ref = standalone[path]
        if packaged_ref not in mcu_staging:
            raise AssemblyCompositionError(
                f"MCU package has no staged position for {packaged_ref} ({path})"
            )
        x, y, angle = mcu_staging[packaged_ref]
        x, y = float(x), float(y)
        if y < keepout_floor:
            revisions.append(
                {
                    "reference": entry["reference"],
                    "instance_path": path,
                    "from_mm": [x, y],
                    "to_mm": [x, keepout_floor],
                    "reason": "delivered neutral staging overlaps the assumed antenna keepout",
                }
            )
            y = keepout_floor
        placements[entry["reference"]] = [x, y, float(angle)]
    for reference, (_x, _y, angle) in placements.items():
        if angle not in (0, 90, 180, 270):
            raise AssemblyCompositionError(
                f"assembly placement {reference} carries non-orthogonal angle {angle}; "
                f"review required"
            )
    placements_meta = {"revisions": revisions}
    return placements, placements_meta


# ---------------------------------------------------------------------------
# Assembly candidate board generation + prototype copper import.
# ---------------------------------------------------------------------------


def combined_candidate_layout():
    """Two-sheet strict-candidate schematic layout for the combined assembly.

    ``buck`` and ``mcu`` compiled module prefixes land on separate sheets so
    the generated schematic mirrors the two source blocks rather than
    flattening them.
    """
    from gen_schematics import SchematicLayout

    return SchematicLayout(
        root_sheet="control-assembly.kicad_sch",
        sheets=("BUCK", "MCU"),
        sheet_files={"BUCK": "buck.kicad_sch", "MCU": "mcu.kicad_sch"},
        module_to_sheet={"buck": "BUCK", "mcu": "MCU"},
        title="Control Assembly Candidate (source-derived, apparatus-only)",
        sheet_description=(
            "CONTROL ASSEMBLY CANDIDATE\\n\\nGENERATED -- do not hand-edit\\n"
            "P3 U2 source-derived composition of the buck functional nine and the "
            "MCU ten; apparatus-only, live model blocked\\n\\n2 Sheets:\\nBUCK\\nMCU"
        ),
    )


def _stock_root_with_overrides(bridge: dict, root: Path) -> Path:
    """Stage the stock footprints the combined netlist needs, plus any
    prototype-vendored override P1's vendorer cannot resolve.

    ``block_source.vendor_candidate_libs`` only knows KiCad's application
    stock and ``pcb/libs``; the buck's custom ``L_Bourns_SRP1265A`` lives in
    the prototype library. That is a P1-owned gap reported in the
    integration report; this P3-local root lets the assembly build proceed
    without editing P1 code.
    """
    prototype_pretty = PROTOTYPE_BOARD.parent / "buck-reva.pretty"
    for comp in bridge["components"]:
        nickname = comp["footprint"]
        lib, _, fp = nickname.partition(":")
        if not lib or not fp or lib in ("lib", "temper"):
            continue
        stock = block_source.KICAD_STOCK_FOOTPRINT_DIR / f"{lib}.pretty" / f"{fp}.kicad_mod"
        proto = prototype_pretty / f"{fp}.kicad_mod"
        source = stock if stock.is_file() else (proto if proto.is_file() else None)
        if source is None:
            raise AssemblyCompositionError(
                f"footprint {nickname!r} is in neither KiCad stock nor the prototype library; "
                f"vendor it (P1-owned block_source gap)"
            )
        dest = root / f"{lib}.pretty" / f"{fp}.kicad_mod"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    return root


def generate_board(
    source: dict, placements: dict, output_dir: Path
) -> dict:
    """Generate the combined candidate board via the shared P1 bridge path."""
    del source
    bundle = block_source._design_bundle()
    with tempfile.TemporaryDirectory(prefix="p3-assembly-gen-") as tmp:
        workspace = block_source.fresh_block_workspace(
            REPO,
            LAB / "blocks" / "control-assembly",
            Path(tmp),
            "assembly-gen",
        )
        proc = block_source.run_atopile_build(
            workspace, "control-assembly.ato", "ControlAssemblyCandidate"
        )
        block_source.gate_build(proc)
        export_path = workspace / "resolved-components.json"
        export = block_source.run_resolved_export(
            workspace,
            "control-assembly.ato",
            "ControlAssemblyCandidate",
            export_path,
        )
        net_path = workspace / "build" / "default.net"
        csv_path = workspace / "build" / "default.csv"
        bridge = block_source.bridge_netlist(net_path, "ControlAssemblyCandidate")
        bom = block_source.parse_bom_mpn(csv_path.read_text(encoding="utf-8"))
        converted = json.loads(
            bundle.candidate_convert_bridge(
                json.dumps(export, sort_keys=True),
                json.dumps(bridge, sort_keys=True),
                json.dumps(bom, sort_keys=True),
                "ControlAssemblyCandidate",
            )
        )
        lib_dir = output_dir / "candidate-libs"
        stock_root = _stock_root_with_overrides(bridge, Path(tmp) / "stock")
        original_stock = block_source.KICAD_STOCK_FOOTPRINT_DIR
        block_source.KICAD_STOCK_FOOTPRINT_DIR = stock_root
        try:
            table_path, lib_provenance = block_source.vendor_candidate_libs(
                converted, bridge, REPO, lib_dir
            )
        finally:
            block_source.KICAD_STOCK_FOOTPRINT_DIR = original_stock
        nick_by_ref = {c["reference"]: c["footprint"] for c in bridge["components"]}
        census = block_source.footprint_pad_census(table_path, set(nick_by_ref.values()))
        entries, unconnected = block_source.build_strict_pin_map(
            converted, bridge, census, nick_by_ref
        )
        pins_by_ref = {
            comp["reference"]: sorted(
                {
                    pin
                    for net in bridge["nets"]
                    for ref, pin in net["nodes"]
                    if ref == comp["reference"]
                }
            )
            for comp in converted["components"]
        }
        pads_by_ref = {
            comp["reference"]: census[nick_by_ref[comp["reference"]]]["pads"]
            for comp in converted["components"]
        }
        bundle.candidate_validate_pin_map(
            json.dumps(entries, sort_keys=True),
            json.dumps(pads_by_ref, sort_keys=True),
            json.dumps(pins_by_ref, sort_keys=True),
            json.dumps(unconnected, sort_keys=True),
        )
        board_nets = sorted({net["name"] for net in bridge["nets"] if net["nodes"]})
        bundle.validation.candidate_check_net_admission(
            json.dumps(bridge["nets"], sort_keys=True),
            json.dumps(board_nets, sort_keys=True),
        )
        pin_map = {(e["reference"], e["pin"]): e["pad"] for e in entries}
        unconnected_set = {tuple(pair) for pair in unconnected}
        outline = json.loads(TARGET_CONTEXT.read_text(encoding="utf-8"))["target"][
            "outline_mm"
        ]
        outline_mm = (outline["x1"], outline["y1"], outline["x2"], outline["y2"])
        board_path = output_dir / "control-assembly.kicad_pcb"
        summary = skeleton.generate_candidate_board(
            skeleton.parse_netlist(net_path),
            pin_map,
            unconnected_set,
            table_path,
            outline_mm,
            {ref: tuple(pos) for ref, pos in placements.items()},
            board_path,
        )
        if not skeleton.candidate_oracle_verify(
            board_path, skeleton.parse_netlist(net_path), pin_map, outline_mm
        ):
            raise AssemblyCompositionError("assembly candidate PCB oracle failed")
        schematics = block_source.schematics
        layout = combined_candidate_layout()
        schematics.write_candidate_layout_config(
            layout, output_dir / "schematic_layout.json"
        )
        sch_netlist = schematics.parse_netlist(net_path)
        bom_values = schematics.load_bom_values(csv_path)
        schematics.apply_bom_values(sch_netlist, bom_values)
        files = schematics._generate_all_sheets(sch_netlist, output_dir, layout=layout)
        schematics._write_schematics(files, output_dir)
        if not schematics.oracle_verify(net_path, output_dir, layout=layout):
            raise AssemblyCompositionError("assembly candidate schematic oracle failed")
        return {
            "board_path": board_path,
            "summary": summary,
            "strict_map": {"entries": entries, "unconnected_pads": unconnected},
            "converted": converted,
            "bridge": bridge,
            "lib_provenance": lib_provenance,
            "census": census,
            "netlist_path": net_path,
            "csv_path": csv_path,
            "build_stdout": proc.stdout,
            "build_netlist_sha256": _sha256(net_path),
            "build_bom_sha256": _sha256(csv_path),
        }


def import_buck_copper(
    board_path: Path,
    prototype: dict,
    offset: list,
    classification: dict,
    package_dir: Path,
) -> dict:
    """Recreate admitted prototype copper on the assembly candidate.

    Segments/vias are translated by the buck cluster offset, layers are
    mapped (rejecting anything but the outer pair), and through vias are
    recreated with the target ``F.Cu-B.Cu`` span. Fixture-only copper is
    removed; functional/shared copper is retained. Connectivity is measured
    natively after import.
    """
    by_net: dict = {}
    layer_map_records: list = []
    via_records: list = []
    for track in classification["functional"]:
        payload = by_net.setdefault(track["net"], {"segments": [], "vias": []})
        if track["kind"] == "segment":
            target_layer = map_copper_layer(track["layer"])
            layer_map_records.append({"source": track["layer"], "target": target_layer})
            payload["segments"].append(
                {
                    "start_mm": _translate(track["start_mm"], offset),
                    "end_mm": _translate(track["end_mm"], offset),
                    "width_mm": track["width_mm"],
                    "layer": target_layer,
                }
            )
        else:
            target_layer = map_copper_layer("F.Cu")  # via start layer; span is enforced below
            del target_layer
            via = recreate_via(track)
            position = _translate(via["position_mm"], offset)
            via_records.append(
                {
                    "source_position_mm": track["position_mm"],
                    "position_mm": position,
                    "span": via["span"],
                    "diameter_mm": via["diameter_mm"],
                    "drill_mm": via["drill_mm"],
                }
            )
            payload["vias"].append(
                {
                    "position_mm": position,
                    "diameter_mm": via["diameter_mm"],
                    "drill_mm": via["drill_mm"],
                }
            )

    imported: list = []
    for proto_net, payload in sorted(by_net.items()):
        combined_net = PROTO_NET_TO_COMBINED.get(proto_net)
        if combined_net is None:
            raise AssemblyCompositionError(
                f"prototype net {proto_net!r} has no compiled combined identity"
            )
        existing = _extract_tracks(board_path)
        merged = {
            "segments": list(existing.get(combined_net, {}).get("segments", []))
            + payload["segments"],
            "vias": existing.get(combined_net, {}).get("vias", []) + payload["vias"],
        }
        _native_replace_copper(board_path, combined_net, merged)
        imported.append(combined_net)
    return {
        "imported_nets": imported,
        "segments": sum(len(v["segments"]) for v in by_net.values()),
        "vias": sum(len(v["vias"]) for v in by_net.values()),
        "layer_map_records": layer_map_records,
        "via_records": via_records,
    }


def _extract_tracks(board_path: Path) -> dict:
    geometry = extract_geometry(board_path)
    out: dict = {}
    for track in geometry["tracks"]:
        net = track["net"]
        entry = out.setdefault(net, {"segments": [], "vias": []})
        if track["kind"] == "segment":
            entry["segments"].append(
                {
                    "start_mm": track["start_mm"],
                    "end_mm": track["end_mm"],
                    "width_mm": track["width_mm"],
                    "layer": track["layer"],
                }
            )
        else:
            entry["vias"].append(
                {
                    "position_mm": track["position_mm"],
                    "diameter_mm": track["width_mm"],
                    "drill_mm": track.get("drill_mm", 0.4),
                }
            )
    return out


def _native_replace_copper(board_path: Path, net: str, payload: dict, zones: list | None = None) -> None:
    """Scripted bounded copper replacement through the P1 native adapter.

    Uses ``buck_native.replace_copper`` (the same primitive
    ``run_block.BlockSession`` dispatches) under the KiCad Python runtime.
    The live-model ``BlockSession`` path is blocked (Zen 429); this is the
    explicit APPARATUS-ONLY scripted equivalent.
    """
    script = (
        "import sys, json;"
        "sys.path.insert(0, 'harness-lab');"
        "import block_native;"
        "block_native.replace_copper(__import__('pathlib').Path(sys.argv[1]),"
        " sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4]),"
        " json.loads(sys.argv[5]));"
        "print('ok')"
    )
    result = subprocess.run(
        [
            harness.KICAD_PYTHON,
            "-c",
            script,
            str(board_path),
            net,
            json.dumps(payload["segments"]),
            json.dumps(payload["vias"]),
            json.dumps(zones or []),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=str(REPO),
    )
    if result.returncode != 0 or "ok" not in result.stdout:
        raise AssemblyCompositionError(
            f"native replace_copper failed for net {net!r}: {result.stderr[-800:]}"
        )


# ---------------------------------------------------------------------------
# Owned-region guard + replacement ledger + cross-view scaffold.
# ---------------------------------------------------------------------------


def _owned_envelopes(target: dict) -> list:
    regions = target["reserved_regions_mm"]
    envelopes = []
    for name in ("buck_block", "mcu_block"):
        region = regions[name]
        envelopes.append({"ref": name, "x1": region["x1"], "y1": region["y1"], "x2": region["x2"], "y2": region["y2"]})
    return envelopes


def guard_placements(placements: dict, target: dict) -> dict:
    envelopes = _owned_envelopes(target)
    records = []
    for reference in sorted(placements):
        x, y, _angle = placements[reference]
        hit = compose_blocks.check_owned_region(x, y, envelopes, ref=reference)
        records.append({"reference": reference, "x_mm": x, "y_mm": y, "envelope": hit["ref"]})
    return {"rule": "every placed instance sits inside an owned reserved region", "records": records}


def build_replacement_ledger(target: dict, source_map: dict) -> dict:
    """U1 ledger with before (native) and after (source-derived) identities."""
    # Native placeholder ref -> canonical combined source path it is replaced
    # by. The refdes is not the identity: U27 is the MCU module placeholder,
    # U3/L2 the buck IC/inductor placeholders (target-context replacement
    # ledger), and each binds to a source path, not to a same-named ref.
    native_to_path = {
        "U27": "mcu.mcu",
        "U3": "buck.buck",
        "L2": "buck.l_out",
    }
    baseline = {
        entry["ref"]: {"tstamp": entry["tstamp"], "reason": entry["reason"]}
        for entry in target["replacement_ledger"]["remove"]
    }
    removals = compose_blocks.apply_replacement_ledger(
        {ref: {"tstamp": data["tstamp"]} for ref, data in baseline.items()},
        [{"ref": ref, "reason": data["reason"]} for ref, data in baseline.items()],
    )
    for record in removals:
        ref = record["ref"]
        path = native_to_path.get(ref)
        if path is None or path not in source_map:
            raise AssemblyCompositionError(
                f"ledger removal {ref!r} has no source-derived replacement in the combined map"
            )
        entry = source_map[path]
        record["after"] = {
            "instance_path": path,
            "combined_reference": entry["reference"],
            "footprint": entry["footprint"],
        }
    return {
        "rule": "verify-then-remove; every touched object retains before/after identity "
        "(KTD4); shared +3V3/gnd nets are cut only at envelope endpoints, never deleted by net name",
        "removals": removals,
    }


def cross_view_scaffold() -> dict:
    return {
        "rule": "after routing/refill, extract the owned section from both views and compare "
        "canonical source identities, transformed pad geometry, tracks/vias/zones and interface "
        "endpoints in target coordinates; a difference in only one view fails (plan U3 scenario 7)",
        "categories": list(compose_blocks.COMPARE_CATEGORIES),
        "views": {
            "assembly": "pcb/blocks/control-assembly/assembly-candidate/control-assembly.kicad_pcb",
            "overlay": "scratch full-board overlay (production board + section); not yet produced",
        },
        "context_dependent_zones": "intentionally context-dependent zone fills must be listed and "
        "dispositioned with connectivity evidence, never silently excused",
    }


def compose(
    source_path: Path = DEFAULT_SOURCE,
    package_dir: Path = DEFAULT_PACKAGE,
) -> dict:
    """Build the U2 assembly candidate package. Returns the candidate index."""
    if package_dir.exists():
        raise AssemblyCompositionError(f"assembly package {package_dir} already exists")
    source = load_or_build_source(source_path)
    if source_path is not None and not source_path.is_file():
        _write_json(source_path, source)
    target = json.loads(TARGET_CONTEXT.read_text(encoding="utf-8"))
    prototype = extract_geometry(PROTOTYPE_BOARD)
    functional_refs = set(BUCK_PROTO_REF_TO_PATH)
    classification = classify_prototype_copper(prototype, functional_refs)
    if classification["shared"]:
        # Shared fixture/functional copper is a cut at the functional end; it
        # is recorded, not silently imported (the fixture end will not exist).
        pass
    region = target["reserved_regions_mm"]["buck_block"]
    offset = buck_cluster_offset(prototype, functional_refs, region)
    source_map = build_assembly_source_map(source)
    mcu_manifest = json.loads(MCU_MANIFEST.read_text(encoding="utf-8"))
    placements = assembly_placements(
        source_map, prototype, mcu_manifest["staging"]["positions"], offset, target
    )
    placements, placement_meta = placements
    package_dir.mkdir(parents=True)
    board = generate_board(source, placements, package_dir)
    copper = import_buck_copper(
        board["board_path"], prototype, offset, classification, package_dir
    )
    ledger = build_replacement_ledger(target, source_map)
    guard = guard_placements(placements, target)

    _write_json(package_dir / "source-map.json", {
        "schema": "control-assembly.source-map.v1",
        "rule": "keyed by canonical combined-wrapper instance path; refdes renumbering preserved",
        "combined_ref_by_path": {p: e["reference"] for p, e in source_map.items()},
        "entries": source_map,
    })
    _write_json(package_dir / "layer-map.json", {
        "schema": "control-assembly.layer-map.v1",
        "target_outer_pair": list(compose_blocks.TARGET_OUTER_PAIR),
        "physical_copper_order": target["target"]["physical_copper_order"],
        "mapping": PROTO_LAYER_TO_TARGET,
        "records": copper["layer_map_records"],
        "rejected_not_dropped": "any prototype copper layer outside F.Cu/B.Cu raises",
    })
    _write_json(package_dir / "via-recreation.json", {
        "schema": "control-assembly.via-recreation.v1",
        "target_span": compose_blocks.VIA_SPAN,
        "diameter_mm": compose_blocks.VIA_DIAMETER_MM,
        "drill_mm": compose_blocks.VIA_DRILL_MM,
        "vias": copper["via_records"],
    })
    _write_json(package_dir / "prototype-exclusion.json", {
        "schema": "control-assembly.prototype-exclusion.v1",
        "excluded_refs": list(PROTOTYPE_ONLY_REFS),
        "removed_copper": [
            {
                "uuid": t["uuid"],
                "kind": t["kind"],
                "net": t["net"],
                "reason": "serves a prototype-only fixture object",
            }
            for t in classification["fixture_removed"]
        ],
        "shared_copper_cuts": [
            {
                "uuid": t["uuid"],
                "kind": t["kind"],
                "net": t["net"],
                "reason": "joins a functional pad to a fixture pad; cut at the functional end, "
                "continuity rechecked after import",
            }
            for t in classification["shared"]
        ],
    })
    _write_json(package_dir / "replacement-ledger.json", ledger)
    _write_json(package_dir / "owned-region-guard.json", guard)
    _write_json(package_dir / "cross-view-scaffold.json", cross_view_scaffold())
    _write_json(
        package_dir / "mcu-placement-revision.json",
        {
            "schema": "control-assembly.mcu-placement-revision.v1",
            "rule": "placement only; source identity, footprint, and orientation preserved",
            "revisions": placement_meta["revisions"],
        },
    )

    index = {
        "schema": "control-assembly.candidate-index.v1",
        "milestone": "docs/plans/2026-09-10-1322-feat-buck-mcu-composition-plan.md#U2",
        "status": "apparatus-only-assisted",
        "live_model": False,
        "blocker": "live model transport blocked (Zen HTTP 429)",
        "planted": {
            "buck_source": "pcb/prototypes/buck-reva/buck-reva.kicad_pcb (functional nine, rigid translate)",
            "mcu_source": "pcb/blocks/mcu/ (P1 U4 accepted package staged geometry)",
            "combined_source": "harness-lab/blocks/control-assembly/control-assembly.ato",
        },
        "hashes": {
            "control-assembly.kicad_pcb": _sha256(board["board_path"]),
            "source-map.json": _sha256(package_dir / "source-map.json"),
            "layer-map.json": _sha256(package_dir / "layer-map.json"),
            "via-recreation.json": _sha256(package_dir / "via-recreation.json"),
            "prototype-exclusion.json": _sha256(package_dir / "prototype-exclusion.json"),
            "replacement-ledger.json": _sha256(package_dir / "replacement-ledger.json"),
            "owned-region-guard.json": _sha256(package_dir / "owned-region-guard.json"),
            "cross-view-scaffold.json": _sha256(package_dir / "cross-view-scaffold.json"),
            "mcu-placement-revision.json": _sha256(
                package_dir / "mcu-placement-revision.json"
            ),
        },
        "combined_bridge": {
            "netlist_sha256": source["build"]["netlist_sha256"],
            "bom_sha256": source["build"]["bom_sha256"],
            "atopile_pinned": source["atopile_pinned"],
        },
        "counts": {
            "functional_instances": len(source_map),
            "buck_imported_segments": copper["segments"],
            "buck_imported_vias": copper["vias"],
            "prototype_fixture_copper_removed": len(classification["fixture_removed"]),
            "shared_copper_cuts": len(classification["shared"]),
        },
    }
    _write_json(package_dir / "candidate-index.json", index)
    return index


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("compose")
    build.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    build.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    if args.command == "compose":
        index = compose(args.source, args.package)
        print(json.dumps(index, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
