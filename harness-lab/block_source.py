"""P1 U2 strict source-to-board bridge for the MCU candidate.

Builds ``harness-lab/blocks/mcu/mcu.ato:McuCandidate`` (or the combined
``ControlAssemblyCandidate``) in a fresh workspace with pinned Atopile
0.2.69, assembles the explicit bridge inputs (compiled netlist, resolved
attributes, CSV BOM, resolved library bytes, hashed P3 target context), runs
the strict Rust gates in ``temper-design-bundle``, and generates a fresh
candidate directory (local libs, project, rules, source manifest, schematic,
PCB) with P3 outline/layers and neutral staging.

Fails closed: a failed compiler assertion, stale export, conflicting join,
unmatched instance, unreviewed alias, positional guess, omitted component,
unintended open, or extra connectivity prevents admission. This module never
reads the production PCB: placement/geometry come from the P3 target context
and neutral staging only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

LAB = Path(__file__).resolve().parent
REPO = LAB.parent
sys.path.insert(0, str(REPO / "scripts"))

import gen_pcb_skeleton as skeleton  # noqa: E402
import gen_schematics as schematics  # noqa: E402

PINNED_ATOPILE = "0.2.69"
CANDIDATE_SCHEMA = "temper.mcu-candidate.v1"

MCU_BLOCK = LAB / "blocks" / "mcu"
MCU_ENTRY_FILE = "mcu.ato"
MCU_ENTRY_MODULE = "McuCandidate"
COMBO_BLOCK = LAB / "blocks" / "control-assembly"
COMBO_ENTRY_FILE = "control-assembly.ato"
COMBO_ENTRY_MODULE = "ControlAssemblyCandidate"

# KiCad stock footprints are vendored from the application bundle when no
# hermetic checkout is configured. The bundle path and kicad-cli version are
# recorded in the source manifest; bytes are hashed like every other input.
KICAD_STOCK_FOOTPRINT_DIR = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

_PAD_RE = re.compile(r'\(pad\s+"([^"]+)"\s+(\S+)')


class BlockSourceError(Exception):
    """A strict-bridge admission failure naming the responsible input."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _design_bundle() -> Any:
    import temper_design_bundle_python as bundle

    return bundle


def fresh_block_workspace(repo: Path, block_dir: Path, parent: Path, tag: str) -> Path:
    """Copy production elec/src plus the block wrapper into a fresh dir."""
    workspace = parent / tag
    if workspace.exists():
        raise BlockSourceError(f"workspace {workspace} already exists")
    (workspace / "elec").mkdir(parents=True)
    shutil.copytree(
        repo / "elec" / "src",
        workspace / "elec" / "src",
        ignore=shutil.ignore_patterns("*.log", "__pycache__"),
    )
    for wrapper in sorted(block_dir.iterdir()):
        if wrapper.suffix == ".ato" or wrapper.name == "ato.yaml":
            shutil.copyfile(wrapper, workspace / wrapper.name)
    return workspace


def run_atopile_build(
    workspace: Path, entry_file: str, entry_module: str, timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "tool",
            "run",
            "--offline",
            "--from",
            f"atopile=={PINNED_ATOPILE}",
            "ato",
            "--non-interactive",
            "build",
            f"{entry_file}:{entry_module}",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def gate_build(proc: subprocess.CompletedProcess[str]) -> None:
    """Atopile writes artifacts even on FAILED assertions: gate on the return
    code AND the report text, never on artifact presence."""
    if proc.returncode != 0:
        raise BlockSourceError(
            f"compiler exited {proc.returncode}; artifacts unqualified (tail: {proc.stdout[-800:]})"
        )
    if "FAILED" in proc.stdout:
        raise BlockSourceError("build report contains a FAILED assertion; artifacts unqualified")


def run_resolved_export(
    workspace: Path, entry_file: str, entry_module: str, output: Path
) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "uv",
            "tool",
            "run",
            "--offline",
            "--from",
            f"atopile=={PINNED_ATOPILE}",
            "python",
            str(LAB / "circuit_export.py"),
            str(workspace),
            str(output),
            "--entry-file",
            entry_file,
            "--entry",
            entry_module,
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0 or not output.is_file():
        raise BlockSourceError(f"resolved export failed rc={proc.returncode}: {proc.stderr[-800:]}")
    return json.loads(output.read_text(encoding="utf-8"))


def workspace_hashes(workspace: Path) -> dict[str, str]:
    return {
        str(path.relative_to(workspace)): sha256_file(path)
        for path in sorted(workspace.rglob("*.ato"))
    }


def parse_bom_mpn(csv_text: str) -> dict[str, str]:
    """Designator -> MPN, expanding grouped cells ("R1,R2"); fail on gaps."""
    bom: dict[str, str] = {}
    reader = csv.DictReader(csv_text.splitlines())
    if reader.fieldnames is None or "Comment" not in reader.fieldnames:
        raise BlockSourceError("BOM has no Comment column")
    if "Designator" not in reader.fieldnames:
        raise BlockSourceError("BOM has no Designator column")
    for row in reader:
        mpn = (row["Comment"] or "").strip()
        for ref in (row["Designator"] or "").split(","):
            ref = ref.strip().strip('"')
            if not ref:
                continue
            if ref in bom:
                raise BlockSourceError(f"BOM names {ref} more than once")
            if not mpn:
                raise BlockSourceError(f"BOM entry {ref} has an empty MPN")
            bom[ref] = mpn
    if not bom:
        raise BlockSourceError("BOM yielded no designators")
    return bom


def bridge_netlist(net_path: Path, entry_module: str) -> dict[str, Any]:
    """Compiled netlist as bridge JSON, keyed by stable instance paths."""
    parsed = skeleton.parse_netlist(net_path)
    components = []
    for comp in parsed.components.values():
        # skeleton._full_sheetpath keeps the segments after the entry tail
        # ("<abs>:<Entry>::" prefix is consumed by the parser), so the stored
        # sheetpath IS the stable instance path (e.g. "mcu.mcu").
        if "::" in comp.sheetpath or "/" in comp.sheetpath:
            raise BlockSourceError(
                f"component {comp.ref} sheetpath {comp.sheetpath!r} is not a "
                f"normalized instance path for entry {entry_module}"
            )
        if not comp.sheetpath or comp.sheetpath == "unknown":
            raise BlockSourceError(
                f"component {comp.ref} has no usable sheetpath; cannot "
                f"establish a renumbering-safe identity"
            )
        components.append(
            {
                "reference": comp.ref,
                "instance_path": comp.sheetpath,
                "footprint": comp.footprint,
                "tstamp": comp.tstamp,
            }
        )
    nets = [
        {"name": net.name, "nodes": [list(node) for node in net.nodes]}
        for net in parsed.nets.values()
    ]
    return {"components": components, "nets": nets}


def _stock_footprint_source(nickname: str) -> Path:
    lib, _, fp = nickname.partition(":")
    candidate = KICAD_STOCK_FOOTPRINT_DIR / f"{lib}.pretty" / f"{fp}.kicad_mod"
    if not candidate.is_file():
        raise BlockSourceError(
            f"stock footprint {nickname!r} not found at {candidate}; "
            f"vendor it under pcb/libs or set a hermetic checkout"
        )
    return candidate


def vendor_candidate_libs(
    converted: dict[str, Any],
    bridge: dict[str, Any],
    repo: Path,
    lib_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Copy every used footprint into the candidate; return the fp-lib-table
    plus per-footprint provenance (source path + bytes hash).

    Resolution uses the NETLIST nickname (e.g. ``lib:ESP32-S3-WROOM-1``);
    the resolved-attribute footprint must agree on the stem, otherwise the
    two sources are out of sync and vendoring fails.
    """
    lib_dir.mkdir(parents=True, exist_ok=True)
    net_nick = {c["reference"]: c["footprint"] for c in bridge["components"]}
    table_lines = ["(fp_lib_table", "  (version 7)"]
    provenance: dict[str, Any] = {}
    for comp in sorted(converted["components"], key=lambda c: c["reference"]):
        nickname = net_nick[comp["reference"]]
        if nickname.split(":")[-1] != comp["footprint"].split(":")[-1]:
            raise BlockSourceError(
                f"component {comp['reference']}: netlist footprint "
                f"{nickname!r} disagrees with resolved "
                f"{comp['footprint']!r}"
            )
        lib, _, fp = nickname.partition(":")
        if not lib or not fp:
            nickname = f"lib:{comp['footprint']}"
            lib, _, fp = nickname.partition(":")
        dest_dir = lib_dir / f"{lib}.pretty"
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / f"{fp}.kicad_mod"
        if lib in ("lib", "temper"):
            source = repo / "pcb" / "libs" / f"{lib}.pretty" / f"{fp}.kicad_mod"
            origin = f"pcb/libs/{lib}.pretty/{fp}.kicad_mod"
        else:
            source = _stock_footprint_source(nickname)
            origin = f"kicad-stock:{source}"
        if not source.is_file():
            raise BlockSourceError(f"footprint source missing: {source}")
        if dest.is_file() and sha256_file(dest) != sha256_file(source):
            raise BlockSourceError(
                f"footprint {nickname!r} resolves to conflicting bytes "
                f"({source} vs already-vendored copy)"
            )
        shutil.copyfile(source, dest)
        provenance[nickname] = {"source": origin, "sha256": sha256_file(dest)}
        table_lines.append(
            f'  (lib (name "{lib}")(type "KiCad")'
            f'(uri "${{KIPRJMOD}}/{lib_dir.name}/{lib}.pretty")'
            f'(options "")(descr "U2 candidate-local vendored copy"))'
        )
    # Deduplicate lib rows while keeping order.
    seen: set[str] = set()
    rows = [table_lines[0], table_lines[1]]
    for line in table_lines[2:]:
        if line not in seen:
            seen.add(line)
            rows.append(line)
    rows.append(")")
    table_path = lib_dir.parent / "fp-lib-table"
    table_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return table_path, provenance


def footprint_pad_census(table_path: Path, nicknames: set[str]) -> dict[str, dict[str, Any]]:
    """Actual numbered pads per footprint nickname, in library-byte order,
    with the source bytes hash. Only smd/thru_hole pads are connectable."""
    census: dict[str, dict[str, Any]] = {}
    for nickname in sorted(nicknames):
        fp_path = skeleton.resolve_footprint(nickname, table_path)
        text = fp_path.read_text(encoding="utf-8")
        pads = [match.group(1) for match in _PAD_RE.finditer(text)]
        if not pads:
            raise BlockSourceError(f"footprint {nickname!r} exposes no pads")
        census[nickname] = {"pads": pads, "sha256": sha256_file(fp_path)}
    return census


def build_strict_pin_map(
    converted: dict[str, Any],
    bridge: dict[str, Any],
    census: dict[str, dict[str, Any]],
    nick_by_ref: dict[str, str],
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """Exact pin==pad map plus explicit unconnected pads.

    Names differ nowhere on this block (compiled pin numbers equal footprint
    pad numbers 1:1), so every entry is exact with no alias note; any
    footprint pad without a compiled pin is explicitly listed unconnected.
    A name difference without a reviewed note fails downstream in Rust.

    The map is keyed by ``(reference, pin)``, not by footprint pad instance.
    A footprint may expose the same pad number on more than one physical pad
    (e.g. a switch whose two terminals per contact share number ``1`` or
    ``2``); those repeats are one electrical identity and must be emitted
    once. Emitting one entry per footprint pad instance would instead fail
    the Rust gate as ``duplicate_map`` -- which is correct, because two
    entries for the same ``(ref, pin)`` are indistinguishable from a real
    duplicate. Repeated same-number pads are covered by the single entry;
    a pad number claimed by two *different* compiled pins is still rejected
    downstream as ``split_pad``.
    """
    pins_by_ref: dict[str, set[str]] = {}
    for net in bridge["nets"]:
        for ref, pin in net["nodes"]:
            pins_by_ref.setdefault(ref, set()).add(pin)
    by_ref = {comp["reference"]: comp for comp in converted["components"]}
    entries: list[dict[str, Any]] = []
    unconnected: list[list[str]] = []
    for comp in converted["components"]:
        ref = comp["reference"]
        pads = census[nick_by_ref[ref]]["pads"]
        pins = pins_by_ref.get(ref, set())
        instance = next(
            c["instance_path"] for c in bridge["components"] if c["reference"] == ref
        )
        seen_pads: set[str] = set()
        for pad in pads:
            if pad in seen_pads:
                # Same-number repeat on another physical pad: one identity.
                continue
            seen_pads.add(pad)
            if pad in pins:
                entries.append(
                    {
                        "instance_path": instance,
                        "reference": ref,
                        "pin": pad,
                        "pad": pad,
                        "alias_note": "",
                        "positional": False,
                    }
                )
            else:
                unconnected.append([ref, pad])
    # Every compiled pin must land on a pad of the same number.
    for ref, pins in pins_by_ref.items():
        pads = set(census[nick_by_ref[ref]]["pads"])
        for pin in sorted(pins):
            if pin not in pads:
                raise BlockSourceError(
                    f"compiled pin {ref}.{pin} has no same-numbered pad on "
                    f"{by_ref[ref]['footprint']!r} (positional fallback is "
                    f"forbidden; a reviewed alias map entry is required)"
                )
    entries.sort(key=lambda e: (e["reference"], e["pin"]))
    unconnected.sort()
    return entries, unconnected


def neutral_staging(converted: dict[str, Any], region: dict[str, float]) -> dict[str, list[float]]:
    """Deterministic grid inside the P3 MCU region: module near center, small
    parts in one row along the top edge. Staging only, never a solution."""
    refs = sorted(comp["reference"] for comp in converted["components"])
    module_refs = [r for r in refs if r.startswith("U")]
    small_refs = [r for r in refs if not r.startswith("U")]
    if len(module_refs) != 1:
        raise BlockSourceError(f"neutral staging expects exactly one module, found {module_refs}")
    x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
    staging: dict[str, list[float]] = {
        module_refs[0]: [(x1 + x2) / 2.0, (y1 + y2) / 2.0 + 2.0, 0.0]
    }
    row_y = y1 + 3.0
    span = (x2 - x1) - 6.0
    step = span / max(len(small_refs) - 1, 1) if small_refs else 0.0
    for i, ref in enumerate(small_refs):
        staging[ref] = [x1 + 3.0 + i * step, row_y, 0.0]
    return staging


def kicad_cli_version() -> str:
    try:
        proc = subprocess.run(["kicad-cli", "version"], capture_output=True, text=True, timeout=30)
        return proc.stdout.strip() or proc.stderr.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "missing"


def assemble_mcu_candidate(
    repo: Path,
    target_context_path: Path,
    output_dir: Path,
    work_parent: Path | None = None,
) -> dict[str, Any]:
    """Full U2 build: strict gates, then candidate generation. Returns the
    source manifest (also written to the candidate directory)."""
    bundle = _design_bundle()
    repo = repo.resolve()
    if output_dir.exists():
        raise BlockSourceError(f"candidate dir {output_dir} already exists")
    target_context = json.loads(target_context_path.read_text(encoding="utf-8"))
    target = target_context["target"]
    region = target_context["reserved_regions_mm"]["mcu_block"]
    outline = target["outline_mm"]
    outline_mm = (outline["x1"], outline["y1"], outline["x2"], outline["y2"])
    # Pinned physical stackup contract: the generator's six-layer defs must
    # match the live P3 context exactly; a drift fails here for review.
    if [name for _, name in skeleton.CANDIDATE_COPPER_ORDER] != target["physical_copper_order"]:
        raise BlockSourceError("generator copper order diverged from the live P3 target context")

    with tempfile.TemporaryDirectory(prefix="mcu-u2-") as tmp:
        workspace = fresh_block_workspace(repo, MCU_BLOCK, Path(tmp), "mcu-ws")
        recorded = workspace_hashes(workspace)
        proc = run_atopile_build(workspace, MCU_ENTRY_FILE, MCU_ENTRY_MODULE)
        gate_build(proc)
        export_path = workspace / "resolved-components.json"
        export = run_resolved_export(workspace, MCU_ENTRY_FILE, MCU_ENTRY_MODULE, export_path)
        current = workspace_hashes(workspace)
        bundle.validation.candidate_check_freshness(
            json.dumps(recorded, sort_keys=True),
            json.dumps(current, sort_keys=True),
            proc.returncode,
            proc.stdout,
        )

        net_path = workspace / "build" / "default.net"
        csv_path = workspace / "build" / "default.csv"
        bridge = bridge_netlist(net_path, MCU_ENTRY_MODULE)
        bom = parse_bom_mpn(csv_path.read_text(encoding="utf-8"))
        converted = json.loads(
            bundle.candidate_convert_bridge(
                json.dumps(export, sort_keys=True),
                json.dumps(bridge, sort_keys=True),
                json.dumps(bom, sort_keys=True),
                MCU_ENTRY_MODULE,
            )
        )

        lib_dir = output_dir / "candidate-libs"
        output_dir.mkdir(parents=True)
        table_path, lib_provenance = vendor_candidate_libs(converted, bridge, repo, lib_dir)
        nick_by_ref = {c["reference"]: c["footprint"] for c in bridge["components"]}
        census = footprint_pad_census(table_path, set(nick_by_ref.values()))
        entries, unconnected = build_strict_pin_map(converted, bridge, census, nick_by_ref)
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

        staging = neutral_staging(converted, region)
        pin_map = {(e["reference"], e["pin"]): e["pad"] for e in entries}
        unconnected_set = {tuple(pair) for pair in unconnected}

        (output_dir / "fp-lib-table").write_text(
            table_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        layout = schematics.mcu_candidate_layout()
        schematics.write_candidate_layout_config(layout, output_dir / "schematic_layout.json")
        sch_netlist = schematics.parse_netlist(net_path)
        bom_values = schematics.load_bom_values(csv_path)
        schematics.apply_bom_values(sch_netlist, bom_values)
        files = schematics._generate_all_sheets(sch_netlist, output_dir, layout=layout)
        schematics._write_schematics(files, output_dir)

        skel_netlist = skeleton.parse_netlist(net_path)
        summary = skeleton.generate_candidate_board(
            skel_netlist,
            pin_map,
            unconnected_set,
            output_dir / "fp-lib-table",
            outline_mm,
            {ref: tuple(pos) for ref, pos in staging.items()},
            output_dir / "mcu_candidate.kicad_pcb",
            values=bom_values,
        )
        if not skeleton.candidate_oracle_verify(
            output_dir / "mcu_candidate.kicad_pcb",
            skel_netlist,
            pin_map,
            outline_mm,
        ):
            raise BlockSourceError("candidate PCB oracle failed")
        if not schematics.oracle_verify(net_path, output_dir, layout=layout):
            raise BlockSourceError("candidate schematic oracle failed")

        manifest: dict[str, Any] = {
            "schema": CANDIDATE_SCHEMA,
            "block": "mcu",
            "entry": f"{MCU_ENTRY_FILE}:{MCU_ENTRY_MODULE}",
            "atopile_pinned": PINNED_ATOPILE,
            "kicad_cli": kicad_cli_version(),
            "target_context": {
                "path": str(
                    target_context_path.resolve().relative_to(repo)
                    if target_context_path.resolve().is_relative_to(repo)
                    else target_context_path.resolve()
                ),
                "sha256": sha256_file(target_context_path),
                "outline_mm": outline,
                "mcu_region_mm": region,
                "antenna_keepout_mm": target_context["reserved_regions_mm"]["antenna_keepout"],
            },
            "inputs": {
                "workspace_hashes": current,
                "build_gate": {
                    "returncode": proc.returncode,
                    "failed_present": "FAILED" in proc.stdout,
                },
                "stdout_sha256": None,  # filled after build-evidence copy
                "stderr_sha256": None,
                "netlist_sha256": sha256_file(net_path),
                "bom_sha256": sha256_file(csv_path),
                "export_sha256": sha256_file(export_path),
                "libraries": lib_provenance,
                "footprint_census": census,
                "build_evidence": "build-evidence/default.net, default.csv, resolved-components.json, stdout.txt, stderr.txt (byte copies of the qualified build)",
            },
            "converted": {
                "components": converted["components"],
                "net_count": len(converted["nets"]),
                "empty_reference_nets_excluded": converted["empty_reference_nets"],
            },
            "strict_map": {"entries": entries, "unconnected_pads": unconnected},
            "staging": {"positions": staging, "staging_only": True},
            "schematic": {
                "layout": json.loads(
                    (output_dir / "schematic_layout.json").read_text(encoding="utf-8")
                ),
                "files": sorted(files),
            },
            "board": summary,
            "production_pcb_geometry_used": False,
        }
        (output_dir / "rules.json").write_text(
            json.dumps(
                {
                    "schema": "temper.mcu-candidate-rules.v1",
                    "edge_clearance_rule_mm": target_context["mechanical"][
                        "edge_clearance_rule_mm"
                    ],
                    "antenna_keepout_mm": target_context["reserved_regions_mm"]["antenna_keepout"],
                    "mcu_region_mm": region,
                    "voltage_domains": target_context["voltage_domains"],
                    "functional_copper": "none: starting board carries no tracks, vias, zones, or pours",
                    "manufacturer_layout_rules": "see harness-lab/blocks/mcu/identity-inventory.json manufacturer_layout_rules; numeric enforcement ships in U3",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (output_dir / "mcu_candidate.kicad_pro").write_text(
            json.dumps(
                {
                    "meta": {
                        "filename": "mcu_candidate.kicad_pro",
                        "version": 1,
                    },
                    "boards": [],
                    "sheets": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        evidence_dir = output_dir / "build-evidence"
        evidence_dir.mkdir(exist_ok=True)
        for artifact in ("default.net", "default.csv"):
            shutil.copyfile(workspace / "build" / artifact, evidence_dir / artifact)
        shutil.copyfile(export_path, evidence_dir / "resolved-components.json")
        (evidence_dir / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (evidence_dir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
        manifest["inputs"]["stdout_sha256"] = sha256_file(evidence_dir / "stdout.txt")
        manifest["inputs"]["stderr_sha256"] = sha256_file(evidence_dir / "stderr.txt")
        (output_dir / "source-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument(
        "--target-context",
        type=Path,
        default=REPO / "pcb" / "blocks" / "control-assembly" / "target-context.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = assemble_mcu_candidate(args.repo, args.target_context, args.output_dir)
    print(
        json.dumps(
            {
                "components": len(manifest["converted"]["components"]),
                "nets": manifest["board"]["nets"],
                "output": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
