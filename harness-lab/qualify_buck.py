"""Qualify the nine-component buck fixture with native positive/negative controls."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

import harness
from build_buck import FUNCTIONAL_REFS, NETS

ROOT = harness.ROOT
CONTRACT = ROOT / "fixtures" / "buck-contract.json"
ADAPTER = ROOT / "buck_native.py"
FIXTURES = ROOT / "fixtures" / "buck"
OUTLINE_DEFAULT = [0.0, 0.0, 50.0, 40.0]
MAX_EDITS = 30
MAX_SECONDS = 600
COPPER_LAYERS = ("F.Cu", "B.Cu")

TOOLS = [
    {
        "name": "inspect",
        "description": "Read native pad geometry, copper, physical connectivity, constraints and findings. Coordinates are mm; x right, y down.",
        "inputSchema": harness.EMPTY_SCHEMA,
    },
    {
        "name": "place",
        "description": "Move one functional footprint (U3, L2, C9-C13, R16, R17) to x_mm/y_mm with orientation 0, 90, 180 or 270. Terminals never move. Copper stays in place. Thirty total edits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "enum": list(FUNCTIONAL_REFS)},
                "x_mm": {"type": "number"},
                "y_mm": {"type": "number"},
                "angle_deg": {"type": "integer", "enum": [0, 90, 180, 270]},
            },
            "required": ["reference", "x_mm", "y_mm", "angle_deg"],
            "additionalProperties": False,
        },
    },
    {
        "name": "route",
        "description": "Replace one net's tracks and vias with exactly this polyline of 2-12 explicit vertices on the named copper layer. No snapping or routing search. Thirty total edits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "net": {"type": "string", "enum": list(NETS)},
                "layer": {"type": "string", "enum": list(COPPER_LAYERS)},
                "width_mm": {"type": "number"},
                "points_mm": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 12,
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
            },
            "required": ["net", "layer", "width_mm", "points_mm"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_route",
        "description": "Remove all tracks and vias for the selected net. Counts as one edit.",
        "inputSchema": {
            "type": "object",
            "properties": {"net": {"type": "string", "enum": list(NETS)}},
            "required": ["net"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_via",
        "description": "Add one 0.8/0.4 mm via on the selected net at explicit coordinates. Counts as one edit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "net": {"type": "string", "enum": list(NETS)},
                "x_mm": {"type": "number"},
                "y_mm": {"type": "number"},
            },
            "required": ["net", "x_mm", "y_mm"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_zone",
        "description": "Add one copper pour polygon on the selected net and layer; KiCad fills it. Supply every vertex. Counts as one edit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "net": {"type": "string", "enum": list(NETS)},
                "layer": {"type": "string", "enum": list(COPPER_LAYERS)},
                "polygon_mm": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 64,
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
            },
            "required": ["net", "layer", "polygon_mm"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check",
        "description": "Reload and check physical connectivity, full applicable KiCad DRC, placement, protected state and buck layout rules. Finish only after this returns pass.",
        "inputSchema": harness.EMPTY_SCHEMA,
    },
]
INSTRUCTIONS = """Place and route Temper's nine-component 3.3 V buck using only the seven PCB tools.
Inspect first. Only the nine functional footprints may move; VIN/GND/VOUT terminals, outline and rules are frozen.
Connect every mapped pad pair with actual copper so each of the six nets is one physical island with zero opens.
Keep footprints inside the 50 x 40 mm outline. Honor input/bootstrap/output locality, feedback locality and
switching separation, minimum power/signal widths, and connected local ground returns from native feedback.
Choose all poses and copper yourself from native geometry. There is ONE budget of thirty edits and ten minutes.
Stop on indeterminate measurements. Finish with check returning pass.
A pass covers this benchmark fixture only, not electrical or manufacturing approval.
"""
PROMPT = "Place and route the nine-component buck in this fixture using the admitted PCB tools. Start with inspect and finish with a passing check."


def variant_ids(contract: dict) -> list:
    return [v["id"] for v in contract["variants"]]


def variant_spec(contract: dict, vid: str) -> dict:
    for variant in contract["variants"]:
        if variant["id"] == vid:
            return variant
    raise ValueError(f"Unqualified buck variant {vid}")


def variant_contract(contract: dict, vid: str) -> dict:
    """Per-variant judge view: frozen terminals/poses/hashes for one variant."""
    spec = variant_spec(contract, vid)
    return {
        "profile": "buck",
        "kicad_version": contract["kicad_version"],
        "protected_sha256": spec["protected_sha256"],
        "outline_mm": contract["outline_mm"],
        "supported_layers": contract["supported_layers"],
        "allowed_copper_kinds": contract["allowed_copper_kinds"],
        "min_power_width_mm": contract["min_power_width_mm"],
        "min_signal_width_mm": contract["min_signal_width_mm"],
        "power_nets": contract["power_nets"],
        "signal_nets": contract["signal_nets"],
        "pad_census": contract["pad_census"],
        "net_mapping": contract["net_mapping"],
        "terminals": spec["terminals"],
        "obligations": contract["obligations"],
        "checks": contract["checks"],
    }


def prepare(directory: Path, vid: str) -> None:
    contract = json.loads(CONTRACT.read_text())
    spec = variant_spec(contract, vid)
    source = FIXTURES / vid
    if (
        harness.file_hash(source / "candidate.kicad_pcb")
        != spec["initial_board_sha256"]
    ):
        raise ValueError("Frozen buck start board changed")
    directory.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, directory)
    shutil.copyfile(directory / "candidate.kicad_pcb", directory / "initial.kicad_pcb")


def evaluate(directory: Path, contract: dict, vid: str, evidence: Path) -> dict:
    spec = variant_spec(contract, vid)
    if harness.context_hash(directory) != spec["context_sha256"]:
        return {"status": "fail", "findings": [{"id": "protected_context_changed"}]}
    evidence.mkdir(parents=True, exist_ok=False)
    board = directory / "candidate.kicad_pcb"
    measurement = harness.native("measure", board, adapter=ADAPTER)
    (evidence / "measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")
    config = evidence / "kicad-config"
    config.mkdir()
    (config / "kicad_common.json").write_text('{"environment":{"vars":{}}}\n')
    (config / "kicad_advanced").write_text("MaximumThreads=1\n")
    report_path = evidence / "drc.json"
    command = [
        "kicad-cli",
        "pcb",
        "drc",
        "--format",
        "json",
        "--all-track-errors",
        "--severity-all",
        "--output",
        str(report_path),
        str(board),
    ]
    completed = subprocess.run(
        command,
        env={**os.environ, "KICAD_CONFIG_HOME": str(config)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    (evidence / "drc-command.json").write_text(
        json.dumps(
            {
                "argv": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
            indent=2,
        )
        + "\n"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"KiCad DRC exited {completed.returncode}; see retained evidence"
        )
    drc = json.loads(report_path.read_text())
    if harness.file_hash(board) != measurement["board_sha256"]:
        raise RuntimeError("Board changed during evaluation")
    completed = subprocess.run(
        [str(harness.JUDGE)],
        input=json.dumps(
            {
                "measurement": measurement,
                "contract": variant_contract(contract, vid),
                "drc": drc,
            }
        ),
        capture_output=True,
        text=True,
        timeout=5,
    )
    result = json.loads(completed.stdout)
    if completed.returncode not in (0, 2):
        raise RuntimeError(f"Evaluator exited {completed.returncode}")
    (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return {**result, "measurement": measurement}


def mutate(board: Path, expression: str) -> None:
    subprocess.run(
        [
            harness.KICAD_PYTHON,
            "-c",
            "import pcbnew,sys; b=pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(sys.argv[1],None); f={x.GetReference():x for x in b.GetFootprints()}\n"
            + expression
            + "\npcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(sys.argv[1],b)",
            str(board),
        ],
        check=True,
        capture_output=True,
    )


class Session(harness.Session):
    tools = TOOLS
    adapter = ADAPTER

    def __init__(
        self, directory: Path, contract: dict, vid: str, deadline: float | None = None
    ):
        self.variant = vid
        self.variant_contract = variant_contract(contract, vid)
        super().__init__(
            directory,
            contract,
            deadline if deadline is not None else time.time() + MAX_SECONDS,
        )

    def apply(self, name: str, arguments: dict) -> None:
        outline = self.contract["outline_mm"]
        x0, y0, x1, y1 = outline

        def finite(value: object) -> bool:
            return type(value) in (int, float) and math.isfinite(value)

        if name == "place":
            if set(arguments) != {"reference", "x_mm", "y_mm", "angle_deg"}:
                raise ValueError(
                    "place requires exactly reference, x_mm, y_mm, angle_deg"
                )
            reference, x, y, angle = (
                arguments[k] for k in ("reference", "x_mm", "y_mm", "angle_deg")
            )
            if reference not in FUNCTIONAL_REFS:
                raise ValueError(
                    "Only functional footprints may move; terminals are protected"
                )
            if not finite(x) or not finite(y):
                raise ValueError("Coordinates must be finite numbers")
            if type(angle) is not int or angle not in (0, 90, 180, 270):
                raise ValueError("Orientation must be 0, 90, 180, or 270")
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                raise ValueError("Footprint origin must be inside the task outline")
        elif name == "route":
            if set(arguments) != {"net", "layer", "width_mm", "points_mm"}:
                raise ValueError(
                    "route requires exactly net, layer, width_mm, points_mm"
                )
            net, layer, width, points = (
                arguments[k] for k in ("net", "layer", "width_mm", "points_mm")
            )
            if net not in NETS or layer not in COPPER_LAYERS:
                raise ValueError("Only admitted nets and copper layers may be routed")
            if not finite(width) or not 0.2 <= width <= 2.0:
                raise ValueError("Width must be a finite number in [0.2, 2.0] mm")
            if not isinstance(points, list) or not 2 <= len(points) <= 12:
                raise ValueError("A route needs 2-12 vertices")
            for point in points:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(not finite(v) or abs(v) > 100 for v in point)
                ):
                    raise ValueError(
                        "Vertices must contain two finite coordinates within native range"
                    )
        elif name == "remove_route":
            if set(arguments) != {"net"} or arguments["net"] not in NETS:
                raise ValueError("remove_route requires exactly one admitted net")
        elif name == "add_via":
            if set(arguments) != {"net", "x_mm", "y_mm"}:
                raise ValueError("add_via requires exactly net, x_mm, y_mm")
            if arguments["net"] not in NETS:
                raise ValueError("Only admitted nets may use vias")
            if not finite(arguments["x_mm"]) or not finite(arguments["y_mm"]):
                raise ValueError("Coordinates must be finite numbers")
            if not (x0 <= arguments["x_mm"] <= x1 and y0 <= arguments["y_mm"] <= y1):
                raise ValueError("Via must be inside the task outline")
        elif name == "add_zone":
            if set(arguments) != {"net", "layer", "polygon_mm"}:
                raise ValueError("add_zone requires exactly net, layer, polygon_mm")
            if arguments["net"] not in NETS or arguments["layer"] not in COPPER_LAYERS:
                raise ValueError("Only admitted nets and copper layers may use zones")
            polygon = arguments["polygon_mm"]
            if not isinstance(polygon, list) or not 3 <= len(polygon) <= 64:
                raise ValueError("A zone needs 3-64 vertices")
            for point in polygon:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(not finite(v) or abs(v) > 100 for v in point)
                ):
                    raise ValueError(
                        "Vertices must contain two finite coordinates within native range"
                    )
        elif name in ("inspect", "check") and not arguments:
            return
        else:
            raise ValueError("Unknown buck operation or unexpected arguments")
        if self.edits >= MAX_EDITS:
            raise ValueError("Thirty-edit budget exhausted")
        self.edits += 1
        staging = self.directory / "next.kicad_pcb"
        shutil.copyfile(self.board, staging)
        if name == "place":
            harness.native(
                "place",
                staging,
                arguments["reference"],
                arguments["x_mm"],
                arguments["y_mm"],
                arguments["angle_deg"],
                adapter=self.adapter,
            )
        elif name == "route":
            harness.native(
                "route",
                staging,
                arguments["net"],
                arguments["layer"],
                arguments["width_mm"],
                json.dumps(arguments["points_mm"]),
                adapter=self.adapter,
            )
        elif name == "remove_route":
            harness.native(
                "remove_route", staging, arguments["net"], adapter=self.adapter
            )
        elif name == "add_via":
            harness.native(
                "add_via",
                staging,
                arguments["net"],
                arguments["x_mm"],
                arguments["y_mm"],
                adapter=self.adapter,
            )
        elif name == "add_zone":
            harness.native(
                "add_zone",
                staging,
                arguments["net"],
                arguments["layer"],
                json.dumps(arguments["polygon_mm"]),
                adapter=self.adapter,
            )
        os.replace(staging, self.board)
        self.last_hash = harness.file_hash(self.board)

    def requirements(self) -> dict:
        return {
            "variant": self.variant,
            "fixed_terminals": ["J1 (VIN/+15V)", "J2 (GND/gnd)", "J3 (VOUT/+3V3)"],
            "editable": "functional footprint poses and admitted copper",
            "outline_mm": self.contract["outline_mm"],
            "required_connections": [
                "+15V: C9.1, U3.3, U3.5, VIN",
                "gnd: C9.2, C11.2, C12.2, C13.2, R17.2, U3.1, GND",
                "sw: U3.2, C10.2, L2.1",
                "boot: U3.6, C10.1",
                "fb: U3.4, R16.2, R17.1",
                "+3V3: L2.2, C11.1, C12.1, C13.1, R16.1, VOUT",
            ],
            "remaining_total_edits": MAX_EDITS - self.edits,
        }

    def call(self, name: str, arguments: dict) -> dict:
        self.sequence += 1
        before = harness.file_hash(self.board)
        self.append(
            {
                "kind": "request",
                "sequence": self.sequence,
                "operation": name,
                "arguments": arguments,
                "before_sha256": before,
                "elapsed_s": time.monotonic() - self.started,
            }
        )
        try:
            if time.time() >= self.deadline:
                raise ValueError("Ten-minute trial budget expired")
            if before != self.last_hash:
                raise ValueError("Candidate changed outside the operation interface")
            if (
                harness.context_hash(self.directory)
                != variant_spec(self.contract, self.variant)["context_sha256"]
            ):
                raise ValueError("Protected context changed")
            self.apply(name, arguments)
            result = evaluate(
                self.directory,
                self.contract,
                self.variant,
                self.directory / "evidence" / f"{self.sequence:03}",
            )
            current = {f["id"] for f in result.get("findings", [])}
            result["introduced"] = sorted(current - self.previous_findings)
            result["resolved"] = sorted(self.previous_findings - current)
            self.previous_findings = current
            result["requirements"] = self.requirements()
            if time.time() >= self.deadline:
                result["status"] = "fail"
                result["budget_expired"] = True
        except Exception as error:
            result = {
                "status": "indeterminate",
                "error": f"{type(error).__name__}: {error}",
            }
        result["sequence"] = self.sequence
        result["after_sha256"] = harness.file_hash(self.board)
        result["elapsed_s"] = time.monotonic() - self.started
        shutil.copyfile(
            self.board, self.directory / f"state-{self.sequence:03}.kicad_pcb"
        )
        self.append({"kind": "response", "sequence": self.sequence, "result": result})
        return result


class InspectionSession(Session):
    def apply(self, name: str, arguments: dict) -> None:
        if name != "inspect" or arguments:
            raise ValueError("Only inspect is enabled during preflight")


def pad_map(measurement: dict) -> dict:
    return {
        f["reference"] + "." + p["number"]: p["position_mm"]
        for f in measurement["footprints"]
        for p in f["pads"]
    }


def qualify(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Qualification requires assertions; do not use Python -O")
    output.mkdir(parents=True, exist_ok=False)
    contract = json.loads(CONTRACT.read_text())
    assert [v["id"] for v in contract["variants"]] == [
        "buck-dev-a",
        "buck-dev-b",
        "buck-res-a",
        "buck-res-b",
    ], "four frozen buck variants"
    assert [v["split"] for v in contract["variants"]] == [
        "development",
        "development",
        "reserved",
        "reserved",
    ], "predeclared dev/reserved split"
    cases: list[dict] = []
    witness_passes: dict[str, int] = {}

    def witness_case(vid: str, rep: int) -> None:
        directory = output / vid / f"witness-{rep}"
        prepare(directory, vid)
        shutil.copyfile(
            FIXTURES / vid / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
        )
        result = evaluate(directory, contract, vid, directory / "evaluation")
        assert result["status"] == "pass", (vid, rep, result.get("findings"))
        witness_passes[vid] = witness_passes.get(vid, 0) + 1
        cases.append(
            {"case": f"{vid}-witness-{rep}", "expected": "pass", "actual": "pass"}
        )
        print(f"{vid} witness-{rep} pass", flush=True)

    for variant in contract["variants"]:
        for rep in (1, 2, 3):
            witness_case(variant["id"], rep)

    def control(vid: str, name: str, required_id: str, change) -> None:
        directory = output / vid / f"control-{name}"
        prepare(directory, vid)
        shutil.copyfile(
            FIXTURES / vid / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
        )
        change(directory)
        result = evaluate(directory, contract, vid, directory / "evaluation")
        assert result["status"] == "fail", (vid, name, result)
        assert any(f["id"].startswith(required_id) for f in result["findings"]), (
            vid,
            name,
            result,
        )
        cases.append(
            {
                "case": f"{vid}-{name}",
                "expected": "fail",
                "required_id": required_id,
                "actual": "fail",
            }
        )
        print(f"{vid} {name} fail-as-intended ({required_id})", flush=True)

    for variant in contract["variants"]:
        vid = variant["id"]
        control(
            vid,
            "missing-terminal-connection",
            "unrouted:",
            lambda d: harness.native(
                "remove_route", d / "candidate.kicad_pcb", "gnd", adapter=ADAPTER
            ),
        )
        control(
            vid,
            "wrong-raw-copper-net",
            "wrong_net:",
            lambda d: mutate(
                d / "candidate.kicad_pcb",
                "next(t for t in b.GetTracks() if t.GetNetname()=='gnd').SetNet(b.FindNet('sw'))",
            ),
        )
        control(
            vid,
            "moved-protected-terminal",
            "terminal_moved:J1",
            lambda d: mutate(
                d / "candidate.kicad_pcb",
                "pos=f['J1'].GetPosition(); f['J1'].SetPosition(pcbnew.VECTOR2I(pos.x+pcbnew.FromMM(1),pos.y))",
            ),
        )
        control(
            vid,
            "changed-rules",
            "protected_context_changed",
            lambda d: (d / "candidate.kicad_dru").write_text("(version 1)\n"),
        )

    dev = "buck-dev-a"

    def dev_measure() -> dict:
        directory = output / dev / "control-short"
        prepare(directory, dev)
        shutil.copyfile(
            FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
        )
        return directory

    directory = dev_measure()
    centers = pad_map(
        harness.native("measure", directory / "candidate.kicad_pcb", adapter=ADAPTER)
    )
    harness.native(
        "route",
        directory / "candidate.kicad_pcb",
        "fb",
        "F.Cu",
        0.3,
        json.dumps([centers["U3.2"], centers["R16.2"]]),
        adapter=ADAPTER,
    )
    result = evaluate(directory, contract, dev, directory / "evaluation")
    assert result["status"] == "fail" and any(
        f["id"].startswith("kicad:shorting_items:") for f in result["findings"]
    ), (dev, "short", result)
    cases.append(
        {
            "case": f"{dev}-short",
            "expected": "fail",
            "required_id": "kicad:shorting_items:",
            "actual": "fail",
        }
    )
    print(f"{dev} short fail-as-intended", flush=True)

    directory = output / dev / "control-clearance"
    prepare(directory, dev)
    shutil.copyfile(
        FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
    )
    harness.native(
        "route",
        directory / "candidate.kicad_pcb",
        "fb",
        "F.Cu",
        0.3,
        json.dumps([[19.5, 18.5], [26.775, 18.5]]),
        adapter=ADAPTER,
    )
    result = evaluate(directory, contract, dev, directory / "evaluation")
    assert result["status"] == "fail" and any(
        f["id"].startswith("kicad:clearance:") for f in result["findings"]
    ), (dev, "clearance", result)
    cases.append(
        {
            "case": f"{dev}-clearance",
            "expected": "fail",
            "required_id": "kicad:clearance:",
            "actual": "fail",
        }
    )
    print(f"{dev} clearance fail-as-intended", flush=True)

    directory = output / dev / "control-outside"
    prepare(directory, dev)
    shutil.copyfile(
        FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
    )
    harness.native(
        "place", directory / "candidate.kicad_pcb", "C9", 60, 60, 0, adapter=ADAPTER
    )
    result = evaluate(directory, contract, dev, directory / "evaluation")
    assert result["status"] == "fail" and any(
        f["id"].startswith("outside_outline:C9") for f in result["findings"]
    ), (dev, "outside", result)
    cases.append(
        {
            "case": f"{dev}-outside-footprint",
            "expected": "fail",
            "required_id": "outside_outline:C9",
            "actual": "fail",
        }
    )
    print(f"{dev} outside-footprint fail-as-intended", flush=True)

    directory = output / dev / "control-locality"
    prepare(directory, dev)
    shutil.copyfile(
        FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
    )
    # C9 moves to a far but legal pose; its island is rebuilt through clean
    # corridors so native DRC stays silent while input locality fails.
    harness.native(
        "place", directory / "candidate.kicad_pcb", "C9", 8, 32, 0, adapter=ADAPTER
    )
    centers = pad_map(
        harness.native("measure", directory / "candidate.kicad_pcb", adapter=ADAPTER)
    )
    _reroute_locality_mutant(directory, centers)
    result = evaluate(directory, contract, dev, directory / "evaluation")
    assert result["status"] == "fail" and any(
        f["id"].startswith("input_locality:") for f in result["findings"]
    ), (dev, "locality", result)
    assert not any(f["id"].startswith("kicad:") for f in result["findings"]), (
        dev,
        "locality-drc-clean",
        result,
    )
    assert not any(f["id"] == "open_connections" for f in result["findings"]), (
        dev,
        "locality-connected",
        result,
    )
    cases.append(
        {
            "case": f"{dev}-drc-clean-locality",
            "expected": "fail",
            "required_id": "input_locality:",
            "actual": "fail",
        }
    )
    print(f"{dev} drc-clean-locality fail-as-intended", flush=True)

    valid = output / dev / "witness-1"
    packet = {
        "measurement": json.loads(
            (valid / "evaluation" / "measurement.json").read_text()
        ),
        "contract": variant_contract(contract, dev),
        "drc": json.loads((valid / "evaluation" / "drc.json").read_text()),
    }
    for name, change in [
        ("missing-buck-evidence", lambda m: m.pop("buck")),
        ("truncated-connectivity", lambda m: m["buck"]["connectivity"].pop()),
    ]:
        broken = copy.deepcopy(packet)
        change(broken["measurement"])
        process = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(broken),
            text=True,
            capture_output=True,
            check=False,
        )
        assert (
            process.returncode == 2
            and json.loads(process.stdout)["status"] == "indeterminate"
        ), name
        (output / f"{name}.json").write_text(
            json.dumps(
                {"input_variant": dev, "result": json.loads(process.stdout)}, indent=2
            )
        )
        cases.append({"case": name, "actual": "indeterminate"})
        print(f"{name} indeterminate", flush=True)

    directory = output / dev / "operation-recovery"
    prepare(directory, dev)
    shutil.copyfile(
        FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
    )
    session = Session(directory, contract, dev)
    assert session.call("inspect", {})["status"] == "pass"
    assert session.call("remove_route", {"net": "gnd"})["status"] == "fail"
    witness_measurement = harness.native(
        "measure", FIXTURES / dev / "witness.kicad_pcb", adapter=ADAPTER
    )
    gnd_pads = pad_map(witness_measurement)
    ordered = [
        gnd_pads[pad]
        for pad in ["J2.1", "J2.2", "C9.2", "R17.2", "C11.2", "C12.2", "C13.2"]
    ] + [[30.0, 16.0], gnd_pads["U3.1"]]
    # route() replaces the net's copper, so the spine goes down first and the
    # vias that stitch it to each pad are re-added afterwards.
    assert (
        session.call(
            "route",
            {"net": "gnd", "layer": "B.Cu", "width_mm": 0.6, "points_mm": ordered},
        )["status"]
        == "fail"
    )
    for pad in ["J2.1", "J2.2", "C9.2", "U3.1", "R17.2", "C13.2", "C12.2", "C11.2"]:
        point = gnd_pads[pad]
        assert session.call(
            "add_via", {"net": "gnd", "x_mm": point[0], "y_mm": point[1]}
        )["status"] in (
            "fail",
            "pass",
        )
    assert session.call("check", {})["status"] == "pass"
    assert session.edits == 10
    session.log.close()
    cases.append({"case": "native-remove-replace-gnd-spine", "actual": "pass"})

    directory = output / dev / "operation-boundaries"
    prepare(directory, dev)
    shutil.copyfile(
        FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
    )
    session = Session(directory, contract, dev)
    before = harness.file_hash(session.board)
    for name, args in [
        ("place", {"reference": "J1", "x_mm": 4, "y_mm": 18, "angle_deg": 0}),
        (
            "route",
            {
                "net": "nope",
                "layer": "F.Cu",
                "width_mm": 0.6,
                "points_mm": [[1, 1], [2, 2]],
            },
        ),
        ("add_zone", {"net": "gnd", "layer": "B.Cu", "polygon_mm": [[1, 1]]}),
    ]:
        assert session.call(name, args)["status"] == "indeterminate"
        assert harness.file_hash(session.board) == before
    # Non-finite coordinates are rejected before any edit, as in the older
    # profiles; here the recorder itself raises ValueError on nan payloads.
    try:
        session.call(
            "route",
            {
                "net": "sw",
                "layer": "F.Cu",
                "width_mm": 0.6,
                "points_mm": [[float("nan"), 1], [2, 2]],
            },
        )
        nan_rejected = harness.file_hash(session.board) == before
    except ValueError:
        nan_rejected = harness.file_hash(session.board) == before
    assert nan_rejected
    session.edits = MAX_EDITS
    assert session.call("remove_route", {"net": "gnd"})["status"] == "indeterminate"
    session.deadline = 0
    assert session.call("check", {})["status"] == "indeterminate"
    session.log.close()
    directory = output / dev / "inspection-boundary"
    prepare(directory, dev)
    shutil.copyfile(
        FIXTURES / dev / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
    )
    session = InspectionSession(directory, contract, dev)
    assert (
        session.call(
            "route",
            {
                "net": "gnd",
                "layer": "B.Cu",
                "width_mm": 0.6,
                "points_mm": [[1, 1], [2, 2]],
            },
        )["status"]
        == "indeterminate"
    )
    assert session.edits == 0
    session.log.close()
    cases.append({"case": "buck-budgets-invalid-inputs-preflight", "actual": "pass"})

    assert all(witness_passes.get(v["id"], 0) == 3 for v in contract["variants"]), (
        "three witness passes per variant"
    )
    assert (
        sum(1 for c in cases if c["actual"] == "pass" and "witness" in c["case"]) == 12
    )
    assert sum(1 for c in cases if c.get("expected") == "fail") == 4 * 4 + 4, (
        "intended failing controls"
    )
    assert sum(1 for c in cases if c["actual"] == "indeterminate") == 2
    receipt = {
        "status": "qualified",
        "scope": "buck_3v3",
        "rerun": "python3 harness-lab/qualify_buck.py harness-lab/runs/<fresh-output>",
        "kicad_version": contract["kicad_version"],
        "variants": {v["id"]: v for v in contract["variants"]},
        "witness_passes": witness_passes,
        "cases": cases,
        "contract_sha256": harness.file_hash(CONTRACT),
        "production_board_sha256": harness.file_hash(
            harness.ROOT.parent / "pcb" / "temper.kicad_pcb"
        ),
        "source_sha256": {
            str(p.relative_to(harness.ROOT)): harness.file_hash(p)
            for p in sorted(
                [
                    *harness.ROOT.glob("*.py"),
                    *harness.ROOT.glob("src/*.rs"),
                    harness.ROOT / "Cargo.lock",
                ]
            )
        },
        "evaluator_sha256": harness.file_hash(harness.JUDGE),
    }
    assert receipt["production_board_sha256"] == contract["production_board_sha256"], (
        "production board moved"
    )
    (output / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Qualified {len(cases)} buck controls", flush=True)


def _reroute_locality_mutant(directory: Path, centers: dict) -> None:
    board = directory / "candidate.kicad_pcb"
    c91 = centers["C9.1"]
    c92 = centers["C9.2"]
    u33 = centers["U3.3"]
    r172 = centers["R17.2"]
    j11 = centers["J1.1"]
    j12 = centers["J1.2"]
    mutate(
        board,
        "nets={str(n.GetNetname()):n for n in [b.FindNet(x) for x in ['+15V','gnd','sw','boot','fb','+3V3']]}\n"
        f"pos=[{c91[0]:.6f},{c91[1]:.6f}]\nc92=[{c92[0]:.6f},{c92[1]:.6f}]\n"
        f"u33=[{u33[0]:.6f},{u33[1]:.6f}]\nr172=[{r172[0]:.6f},{r172[1]:.6f}]\n"
        f"j11=[{j11[0]:.6f},{j11[1]:.6f}]\nj12=[{j12[0]:.6f},{j12[1]:.6f}]\n"
        "[b.Delete(t) for t in list(b.GetTracks()) if t.GetNetname()=='+15V' and t.Type()==pcbnew.PCB_TRACE_T and t.GetLayer()==pcbnew.F_Cu]\n"
        "[b.Delete(t) for t in list(b.GetTracks()) if t.GetNetname()=='gnd' and t.Type()==pcbnew.PCB_VIA_T and abs(pcbnew.ToMM(t.GetPosition().x)-16.475)<0.01]\n"
        "def seg(net,a,cpt,w,layer):\n"
        " t=pcbnew.PCB_TRACK(b)\n"
        " t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]),pcbnew.FromMM(a[1])))\n"
        " t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(cpt[0]),pcbnew.FromMM(cpt[1])))\n"
        " t.SetWidth(pcbnew.FromMM(w))\n"
        " t.SetLayer(layer)\n"
        " t.SetNet(nets[net])\n"
        " b.Add(t)\n"
        "def via(net,pt):\n"
        " v=pcbnew.PCB_VIA(b)\n"
        " v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(pt[0]),pcbnew.FromMM(pt[1])))\n"
        " v.SetWidth(pcbnew.FromMM(0.8))\n"
        " v.SetDrill(pcbnew.FromMM(0.4))\n"
        " v.SetNet(nets[net])\n"
        " b.Add(v)\n"
        "seg('+15V',j12,j11,0.6,pcbnew.F_Cu)\n"
        "seg('+15V',j11,[0.8,j11[1]],0.6,pcbnew.F_Cu)\n"
        "seg('+15V',[0.8,j11[1]],[0.8,pos[1]],0.6,pcbnew.F_Cu)\n"
        "seg('+15V',[0.8,pos[1]],pos,0.6,pcbnew.F_Cu)\n"
        "seg('+15V',pos,[pos[0],24.0],0.6,pcbnew.F_Cu)\n"
        "seg('+15V',[pos[0],24.0],[19.5,24.0],0.6,pcbnew.F_Cu)\n"
        "seg('+15V',[19.5,24.0],[19.5,22.5],0.6,pcbnew.F_Cu)\n"
        "seg('+15V',[19.5,22.5],[19.5,u33[1]],0.6,pcbnew.F_Cu)\n"
        "seg('+15V',[19.5,u33[1]],u33,0.6,pcbnew.F_Cu)\n"
        "via('gnd',c92)\nseg('gnd',c92,r172,0.6,pcbnew.B_Cu)\n",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    qualify(parser.parse_args().output.resolve())
