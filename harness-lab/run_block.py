"""MCU development-profile runner (P1 U3).

Thin profile adapter over the shared runner/workspace/dispatch path:
:class:`BlockSession` reuses :class:`buck_host.Session`'s bounded native
operations, atomic staging, and protected-context handling with an MCU task
contract; :class:`BlockPreflight` is the inspection-only gate. Fixed buck
assumptions that do not transfer (movable census, admitted nets,
obligations, keepouts) live in the task contract built here from the U2
source manifest and the P3 target context — never in a forked runner.

Memory (P2) loads through the existing artifact/workspace API only:
:func:`load_memory` catalogs, validates, selects, and materializes through
:mod:`memory` / :mod:`artifacts`; :func:`deliver_to_workspace` applies the
recorded revision to a live worker. The host never edits P2 records.

Board generation stays operator-controlled: :func:`generate_candidate`
refuses without an explicit confirmation plus ``TEMPER_BLOCK_GENERATE=1``.
The construction agent may only file a bounded :func:`request_generation`
record; it cannot edit source or acceptance rules to pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import buck_host
import harness
import memory as cross_memory
import workspace
from artifacts import Store

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ADAPTER = ROOT / "block_native.py"
BASE_SKILLS = ROOT / "skills" / "base" / "skills.py"
TASK_SCHEMA = "temper.mcu-task-contract.v1"
GENERATE_ENV = "TEMPER_BLOCK_GENERATE"
GENERATION_REQUEST_MAX_BYTES = 8 * 1024

# One concrete MCU configuration for U3 qualification (KTD5). Power delivery
# (vcc/gnd) is the required internal connectivity; boundary interfaces are
# P3-owned and recorded, not coppered, in this profile.
REQUIRED_INTERNAL_NETS = ("vcc", "gnd")
MIN_POWER_WIDTH_MM = 0.6
MIN_SIGNAL_WIDTH_MM = 0.3
POWER_NETS_DEFAULT = ("vcc",)
ZONE_NETS = ("gnd",)
PROFILE = "block-operation"


def _judge_schema() -> dict[str, Any]:
    result = subprocess.run(
        [str(harness.JUDGE)],
        input=json.dumps({"profile": PROFILE, "operation": "schema", "arguments": {}}),
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Rust block schema unavailable")
    schema = json.loads(result.stdout)
    if not isinstance(schema, dict) or not isinstance(schema.get("tools"), list):
        raise RuntimeError("Rust block operation schema is malformed")
    return schema


_SCHEMA = _judge_schema()
TOOLS = _SCHEMA["tools"]
if int(_SCHEMA["max_actions"]) != buck_host.MAX_ACTIONS or float(
    _SCHEMA["max_seconds"]
) != float(buck_host.MAX_SECONDS):
    raise RuntimeError("block budget diverged from the shared host budget")
if int(_SCHEMA["max_execute_bytes"]) != buck_host.MAX_EXECUTE_BYTES:
    raise RuntimeError("block execute cap diverged from the shared host cap")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _netlist_nets(netlist_path: Path) -> dict[str, list[list[str]]]:
    """Compiled net names present in the netlist.

    Matches ``(name "..")`` declarations (compiled-netlist s-expr shape);
    component nodes carry no ``name`` field, so every hit is a net. Raises
    on an empty declaration set.
    """
    text = netlist_path.read_text(encoding="utf-8")
    names = re.findall(r'\(name\s+"([^"]+)"\)', text)
    if not names:
        raise ValueError(f"no declared nets in {netlist_path}")
    return {name: [] for name in sorted(set(names))}


def _netlist_connections(netlist_path: Path) -> dict[str, list[list[str]]]:
    """Compiled net name -> connected [ref, pin] pairs via skeleton parsing.

    Uses the same parser as the U2 bridge so connectivity identity matches
    the admitted board exactly.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    import gen_pcb_skeleton as skeleton

    parsed = skeleton.parse_netlist(netlist_path)
    connections: dict[str, list[list[str]]] = {}
    for net in parsed.nets.values():
        connections[net.name] = sorted([list(node) for node in net.nodes])
    return connections


def build_task_contract(
    candidate_dir: Path,
    *,
    required_nets: tuple[str, ...] = REQUIRED_INTERNAL_NETS,
    kicad_version: str = "10.0.4",
) -> dict[str, Any]:
    """Assemble the judge task contract from U2 + P3 artifacts.

    Inputs (all read-only): the U2 candidate ``source-manifest.json`` with
    ``build-evidence/default.net``, plus the P3 target context, interfaces,
    and MCU identity inventory resolved relative to the repo. Unknown,
    missing, or extra fields fail here — never as silent defaults.
    """
    candidate_dir = candidate_dir.resolve()
    manifest = json.loads((candidate_dir / "source-manifest.json").read_text())
    target_context_path = REPO / manifest["target_context"]["path"]
    target_context = json.loads(target_context_path.read_text())
    if _sha256(target_context_path) != manifest["target_context"]["sha256"]:
        raise ValueError("P3 target context changed under the candidate manifest")
    target = target_context["target"]
    outline = target["outline_mm"]
    outline_mm = [outline["x1"], outline["y1"], outline["x2"], outline["y2"]]
    copper_order = target["physical_copper_order"]

    netlist_path = candidate_dir / "build-evidence" / "default.net"
    connections = _netlist_connections(netlist_path)
    _netlist_nets(netlist_path)  # declaration presence check
    for required in required_nets:
        if required not in connections:
            raise ValueError(f"required net {required!r} absent from compiled netlist")

    # Pad census and net mapping from the strict U2 pin map: every connected
    # pad maps exactly; explicitly unconnected pads are recorded, not copper.
    strict_map = manifest["strict_map"]
    net_mapping: dict[str, str] = {}
    for entry in strict_map["entries"]:
        net_mapping[f"{entry['reference']}.{entry['pin']}"] = next(
            net
            for net, nodes in connections.items()
            if [entry["reference"], entry["pin"]] in nodes
        )
    unconnected = [f"{ref}.{pad}" for ref, pad in strict_map["unconnected_pads"]]
    pad_census: dict[str, int] = {}
    for pad in list(net_mapping) + unconnected:
        ref = pad.split(".")[0]
        pad_census[ref] = pad_census.get(ref, 0) + 1
    movable_refs = sorted(manifest["staging"]["positions"])
    if sorted(pad_census) != movable_refs:
        raise ValueError("staging census differs from strict-map census")

    by_net: dict[str, list[str]] = {}
    for pad, net in net_mapping.items():
        by_net.setdefault(net, []).append(pad)
    obligations = {net: sorted(by_net.get(net, [])) for net in required_nets}
    for net, pads in obligations.items():
        if not pads:
            raise ValueError(f"required net {net!r} connects no pads")

    signal_nets = sorted(n for n in connections if n not in POWER_NETS_DEFAULT)
    antenna = target_context["reserved_regions_mm"]["antenna_keepout"]
    return {
        "schema": TASK_SCHEMA,
        "profile": "block",
        "kicad_version": kicad_version,
        "protected_sha256": manifest.get("protected_sha256", "pending-prepare"),
        "outline_mm": outline_mm,
        "physical_copper_order": copper_order,
        "supported_layers": list(copper_order),
        "allowed_copper_kinds": ["segment", "via", "zone"],
        "min_power_width_mm": MIN_POWER_WIDTH_MM,
        "min_signal_width_mm": MIN_SIGNAL_WIDTH_MM,
        "power_nets": list(POWER_NETS_DEFAULT),
        "signal_nets": signal_nets,
        "movable_refs": movable_refs,
        "protected_ports": {},
        "pad_census": pad_census,
        "net_mapping": net_mapping,
        "obligations": obligations,
        "boundary": {},
        "keepouts": [
            {
                "id": "antenna_keepout",
                "x1": antenna["x1"],
                "y1": antenna["y1"],
                "x2": antenna["x2"],
                "y2": antenna["y2"],
            }
        ],
        "zone_nets": list(ZONE_NETS),
        "via_diameter_mm": 0.8,
        "via_drill_mm": 0.4,
        "provenance": {
            "candidate_manifest_sha256": _sha256(
                candidate_dir / "source-manifest.json"
            ),
            "netlist_sha256": _sha256(netlist_path),
            "target_context_sha256": manifest["target_context"]["sha256"],
            "unconnected_pads_explicit": sorted(unconnected),
        },
    }


def source_facts(candidate_dir: Path) -> dict[str, Any]:
    """Model-visible source facts: what the agent may inspect, not mutate.

    Derived read-only from the U2 manifest, identity inventory, and P3
    interfaces. No board bytes, no acceptance rules.
    """
    candidate_dir = candidate_dir.resolve()
    manifest = json.loads((candidate_dir / "source-manifest.json").read_text())
    inventory = json.loads(
        (ROOT / "blocks" / "mcu" / "identity-inventory.json").read_text()
    )
    interfaces = json.loads(
        (REPO / "pcb" / "blocks" / "control-assembly" / "interfaces.json").read_text()
    )
    return {
        "entry": manifest["entry"],
        "atopile_pinned": manifest["atopile_pinned"],
        "components": manifest["converted"]["components"],
        "net_count": manifest["converted"]["net_count"],
        "boundary_nets": inventory["boundary_nets"],
        "interfaces": inventory["interfaces"],
        "internal_required": interfaces["internal_required"],
        "future_obligations": interfaces["future_obligations"],
        "manufacturer_layout_rules": inventory["manufacturer_layout_rules"],
        "open_items": inventory["open_items"],
        "staging_only": manifest["staging"]["staging_only"],
        "manifest_sha256": _sha256(candidate_dir / "source-manifest.json"),
    }


def prepare(directory: Path, candidate_dir: Path, *, timeout: float = 60.0) -> Path:
    """Operator-side trial setup from a U2 candidate package.

    Copies the candidate board, vendored libraries (renamed to the shared
    ``fixture.pretty`` layout so the existing protected-context hash covers
    them), and minimal project/rules sidecars; seals staging plus the sealed
    task contract. Returns the trial directory. The sealed contract's
    ``protected_sha256`` comes from one native measure, never by hand.
    """
    candidate_dir = candidate_dir.resolve()
    directory = directory.resolve()
    if directory.exists():
        raise ValueError(f"trial directory {directory} already exists")
    manifest = json.loads((candidate_dir / "source-manifest.json").read_text())
    directory.mkdir(parents=True)

    board_src = next(candidate_dir.glob("*.kicad_pcb"))
    shutil.copyfile(board_src, directory / "candidate.kicad_pcb")
    # Shared protected-context layout: vendored libs live under
    # fixture.pretty so harness.context_hash and the host stage-copy cover
    # them without a forked path. The URI rewrite is mechanical and hashed.
    fixture_lib = directory / "fixture.pretty"
    fixture_lib.mkdir()
    table_text = (candidate_dir / "fp-lib-table").read_text(encoding="utf-8")
    if "candidate-libs" not in table_text:
        raise ValueError("candidate fp-lib-table does not reference candidate-libs")
    (directory / "fp-lib-table").write_text(
        table_text.replace("candidate-libs", "fixture.pretty"), encoding="utf-8"
    )
    for pretty in sorted((candidate_dir / "candidate-libs").glob("*.pretty")):
        shutil.copytree(pretty, fixture_lib / pretty.name)
    (directory / "candidate.kicad_pro").write_text(
        (candidate_dir / "mcu_candidate.kicad_pro").read_text()
        if (candidate_dir / "mcu_candidate.kicad_pro").is_file()
        else json.dumps({"meta": {"filename": "candidate.kicad_pro", "version": 1}})
        + "\n",
        encoding="utf-8",
    )
    (directory / "candidate.kicad_dru").write_text("(version 1)\n", encoding="utf-8")

    staging = {ref: list(pos) for ref, pos in manifest["staging"]["positions"].items()}
    contract = build_task_contract(candidate_dir)
    (directory / "task-contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source = {
        "schema": "temper.mcu-trial-source.v1",
        "candidate_board": board_src.name,
        "staging": staging,
        "task_contract_sha256": _sha256(directory / "task-contract.json"),
        "candidate_manifest_sha256": _sha256(candidate_dir / "source-manifest.json"),
    }
    (directory / "source.json").write_text(
        json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Seal: the admitted protected state comes from native measurement over
    # the staged board, exactly like the buck fixture's frozen hash. The
    # source seal is recomputed after sealing so it covers the final bytes.
    measurement = harness.native(
        "measure", directory / "candidate.kicad_pcb", adapter=ADAPTER
    )
    contract["protected_sha256"] = measurement["protected_sha256"]
    (directory / "task-contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source["task_contract_sha256"] = _sha256(directory / "task-contract.json")
    source["context_sha256"] = harness.context_hash(directory)
    (directory / "source.json").write_text(
        json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copyfile(directory / "candidate.kicad_pcb", directory / "initial.kicad_pcb")
    return directory


class BlockSession(buck_host.Session):
    """One bounded MCU construction attempt on a prepared trial directory.

    Reuses the shared host lifecycle (budget, deadlines, atomic staging,
    protected-context checks, native DRC + Rust check). Only the task
    contract source, the native adapter, and the Rust policy context differ
    from the buck profile.
    """

    tools = TOOLS

    def __init__(
        self,
        directory: Path,
        task_contract: dict[str, Any] | None = None,
        *,
        deadline: float | None = None,
    ) -> None:
        self.directory = directory.resolve()
        if task_contract is None:
            task_contract = json.loads(
                (self.directory / "task-contract.json").read_text()
            )
        if task_contract.get("profile") != "block":
            raise ValueError("BlockSession requires a block-profile task contract")
        self.contract = task_contract
        source = json.loads((self.directory / "source.json").read_text())
        if (
            _sha256(self.directory / "task-contract.json")
            != source["task_contract_sha256"]
        ):
            raise ValueError("task contract changed outside operator setup")
        self.context_sha256 = source["context_sha256"]
        self.board = self.directory / "candidate.kicad_pcb"
        self._require_fixture_context()
        now = time.monotonic()
        self.deadline = (
            min(deadline, now + buck_host.MAX_SECONDS)
            if deadline is not None
            else now + buck_host.MAX_SECONDS
        )
        self.actions = 0
        self.sequence = 0
        self.terminal_error: str | None = None
        self.revision = harness.file_hash(self.board)
        self.started = time.monotonic()
        self.log = (self.directory / "operations.jsonl").open("x")
        self._record(
            {
                "kind": "session",
                "profile": "block",
                "task_contract_sha256": source["task_contract_sha256"],
                "revision": self.revision,
                "deadline": self.deadline,
                "tools": TOOLS,
            }
        )

    def _require_fixture_context(self) -> None:
        required = (
            "source.json",
            "task-contract.json",
            "candidate.kicad_pro",
            "candidate.kicad_dru",
            "fp-lib-table",
        )
        missing = [name for name in required if not (self.directory / name).is_file()]
        if not self.board.is_file() or missing:
            raise ValueError(
                f"incomplete block trial context: missing {missing or ['candidate.kicad_pcb']}"
            )
        if harness.context_hash(self.directory) != self.context_sha256:
            raise ValueError("protected fixture context changed")

    def _copy_context(self, destination: Path, board: bytes) -> None:
        super()._copy_context(destination, board)
        # The native adapter enforces the same sealed census the Rust policy
        # sees; stage the frozen contract alongside the board it governs.
        shutil.copyfile(
            self.directory / "task-contract.json",
            destination / "task-contract.json",
        )

    def _rust_policy(self, operation: str, args: Any) -> dict[str, Any]:
        admitted = sorted(
            set(self.contract["power_nets"]) | set(self.contract["signal_nets"])
        )
        payload = {
            "profile": PROFILE,
            "operation": operation,
            "arguments": args,
            "context": {
                "outline_mm": self.contract["outline_mm"],
                "movable_refs": self.contract["movable_refs"],
                "admitted_nets": admitted,
                "supported_layers": self.contract["supported_layers"],
                "zone_nets": self.contract["zone_nets"],
            },
        }
        try:
            result = subprocess.run(
                [str(harness.JUDGE)],
                input=json.dumps(payload, allow_nan=False),
                text=True,
                capture_output=True,
                timeout=self._remaining_timeout(5.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"Rust policy apparatus failed: {error}") from error
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Rust policy returned malformed JSON") from error
        if result.returncode != 0 or response.get("status") != "pass":
            raise ValueError(response.get("error", "Rust policy rejected request"))
        return response

    def _native(self, command: str, path: Path, *args: object) -> dict[str, Any] | None:
        argv = [
            harness.KICAD_PYTHON,
            str(ADAPTER),
            command,
            str(path),
            *map(str, args),
        ]
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._remaining_timeout(15.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"native {command} apparatus failed: {error}") from error
        if result.returncode != 0:
            raise RuntimeError(
                f"native {command} exited {result.returncode}: {result.stderr.strip()}"
            )
        if not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"native {command} returned malformed JSON") from error


class BlockPreflight(BlockSession):
    """Inspection-only runtime gate: native load + policy qualification.

    Any mutating request is rejected before budget, board, or deadline are
    touched. Run this on the actual MCU profile before handing a trial to
    model code.
    """

    def _rust_policy(self, operation: str, args: Any) -> dict[str, Any]:
        if operation != "inspect":
            raise ValueError("Only inspect is enabled during preflight")
        return super()._rust_policy(operation, args)


class GenerationNotPermitted(RuntimeError):
    """Board generation was requested without operator confirmation."""


def generate_candidate(
    repo: Path,
    target_context: Path,
    output_dir: Path,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    """Operator-only U2 candidate generation (P1 owns the bridge call).

    Requires both an explicit ``confirm=True`` and
    ``TEMPER_BLOCK_GENERATE=1`` in the environment. Anything less raises
    without touching the filesystem.
    """
    if not confirm or os.environ.get(GENERATE_ENV) != "1":
        raise GenerationNotPermitted(
            f"generation needs confirm=True and {GENERATE_ENV}=1"
        )
    import block_source

    return block_source.assemble_mcu_candidate(repo, target_context, output_dir)


def request_generation(directory: Path, reason: str, *, attempt_id: str = "") -> Path:
    """File a bounded agent-visible generation request. Never executes.

    The agent cannot generate boards; it can only ask, within a byte cap, and
    the operator fulfills the request out of band via :func:`generate_candidate`.
    """
    directory = directory.resolve()
    payload = {
        "schema": "temper.mcu-generation-request.v1",
        "attempt_id": attempt_id,
        "reason": reason,
        "requested_unix": time.time(),
    }
    encoded = json.dumps(payload, sort_keys=True).encode()
    if len(encoded) > GENERATION_REQUEST_MAX_BYTES:
        raise ValueError("generation request exceeds the byte cap")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "generation-request.json"
    if path.exists():
        raise ValueError("a generation request is already pending")
    path.write_bytes(encoded + b"\n")
    return path


MCU_CAPABILITIES = [
    "validator-findings-inspection",
    "targeted-connection-edit",
    "independent-board-check",
    "placement-reading",
    "routing-reading",
    "run-audit-reading",
    "transport-vs-board-diagnosis",
    "simulation-evidence-scoping",
    "assumption-ledger-reading",
    "source-import",
    "pin-identity-verification-against-current-bridge",
]


def load_memory(
    store_root: Path,
    *,
    source_identities: dict[str, str],
    required_ids: list[str] | None = None,
    allow_empty_baseline: bool = False,
) -> dict[str, Any]:
    """Load P2 memory through the artifact API: catalog, validate, select,
    materialize. Returns selection, record, and receipt without touching the
    worker; use :func:`deliver_to_workspace` for delivery."""
    loaded = cross_memory.load_catalog()
    cross_memory.validate_loaded(loaded)
    selection = cross_memory.request_selection(
        loaded,
        task_capabilities=MCU_CAPABILITIES,
        source_identities=source_identities,
        required_ids=required_ids or [],
        allow_empty_baseline=allow_empty_baseline,
        base_skills_bytes=len(BASE_SKILLS.read_bytes()),
    )
    store = Store(Path(store_root))
    record = cross_memory.materialize_selection(
        store,
        loaded,
        selection,
        base_skills_source=BASE_SKILLS.read_text(encoding="utf-8"),
    )
    receipt = cross_memory.build_receipt(
        selection=selection,
        loaded=loaded,
        revision_sha256=record["revision_sha256"],
        notes_sha256=record["receipt"]["notes_sha256"],
        skills_sha256=record["receipt"]["skills_sha256"],
    )
    return {
        "loaded": loaded,
        "selection": selection,
        "record": record,
        "receipt": receipt,
    }


def deliver_to_workspace(
    worker: workspace.Workspace, delivery: dict[str, Any], directory: Path
) -> dict[str, Any]:
    """Apply the materialized memory revision to a live worker and publish
    the delivery receipt. Returns the receipt with acknowledgement set."""
    record = delivery["record"]
    applied = worker.apply_revision(
        record["revision_sha256"], record["skills_utf8"], record["notes_utf8"]
    )
    if not applied:
        raise RuntimeError("worker refused the memory revision")
    receipt = dict(delivery["receipt"])
    receipt["delivery"] = {
        **receipt["delivery"],
        "acknowledged": True,
        "worker_revision": worker.current_revision,
    }
    cross_memory.publish_receipt(Path(directory), receipt)
    return receipt


def build_model_brief(
    session: BlockSession,
    candidate_dir: Path,
    delivery: dict[str, Any] | None,
    last_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the next model observation: source facts, stage findings,
    memory content, and remaining budget. Read-only; never mutates."""
    brief: dict[str, Any] = {
        "source_facts": source_facts(candidate_dir),
        "budget": {
            "remaining_actions": buck_host.MAX_ACTIONS - session.actions,
            "deadline_unix_offset_s": session.deadline - time.monotonic(),
            "revision": session.revision,
            "sequence": session.sequence,
        },
        "protected_inputs": [
            "source.json",
            "task-contract.json",
            "candidate.kicad_pro",
        ],
    }
    if last_result is not None:
        brief["stage_findings"] = last_result.get("findings", last_result)
    if delivery is not None:
        brief["memory"] = {
            "selection_sha256": delivery["selection"]["selection_sha256"],
            "selected_ids": delivery["selection"]["selected_ids"],
            "revision_sha256": delivery["record"]["revision_sha256"],
            "notes": delivery["record"]["notes_utf8"],
        }
    return brief


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--candidate", type=Path, required=True)
    prep.add_argument("--trial", type=Path, required=True)
    gen = sub.add_parser("request-generation")
    gen.add_argument("--trial", type=Path, required=True)
    gen.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.trial, args.candidate))
    elif args.command == "request-generation":
        print(request_generation(args.trial, args.reason))
