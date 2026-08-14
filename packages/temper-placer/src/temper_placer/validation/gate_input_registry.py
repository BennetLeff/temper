"""Gate-input registry — the single source of truth for the dead-parameter sweep.

Plan 2026-08-02-019 (R37 + R33), unit U1.

This module enumerates, in one machine-readable registry:

1.  **Live gate inputs** — the ``cp_sat/gate.py`` acceptance gate's inner
    (placement-audit) surface, whose declared inputs are the ``Placement``
    container fields the auditor actually reads.  Every declared input is
    validated to be a real dataclass field on its container (a gate declaring
    a metric its container does not carry is itself a registry failure).

2.  **CI gate scripts** — the invoked gate scripts in
    ``.github/workflows/python-tests.yml`` (the pre-flight survey, U1/U4).
    Each is registered with its primary declared input file and a
    non-covered reason (probe disabled in this landing); "not covered" is a
    recorded decision, never an oversight.

3.  **Deprecated / callerless surface** — ``validation/validation_gates.py``
    and its ``RunMetrics`` stub.  Registered only as a *tracked finding*
    (the four phantom ``required_metrics`` declarations), remediated by U5,
    never silently dropped.

The physics parameter surface is a second declarative input surface in
``power_pcb_dataset/physics_parameter_map.yaml``, loaded by
:func:`load_physics_parameter_map` and validated by
:func:`validate_physics_parameter_map`.

The probe (``dead_parameter_probe.py``) drives this registry: adding a gate,
input, or parameter is a change to this module or the YAML map — never a
hidden code edit.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- Containers the live acceptance gate reads ---------------------------------

# The acceptance-gate inner (placement-audit) surface.  The auditor reads
# exactly these Placement fields (verified against
# temper_placer/placer/cp_sat/audit.py).  Each declared input is a real
# dataclass field on the container; validation is mechanical.
ACCEPTANCE_INNER_CONTAINER = "temper_placer.placer.cp_sat.audit:Placement"
ACCEPTANCE_INNER_DECLARED_INPUTS: tuple[str, ...] = (
    "positions_mm",
    "sizes_mm",
    "board_w_mm",
    "board_h_mm",
    "zones",
    "zone_components",
)

# The acceptance-gate truth (DRC) surface.  Its declared input is the PCB
# path.  The probe for a file-kind input requires a DRC-passing baseline
# board, which the synthetic probe cannot provide — registered as a
# documented non-covered case (UNMEASURED) below.
ACCEPTANCE_TRUTH_CONTAINER = "pathlib:Path"
ACCEPTANCE_TRUTH_DECLARED_INPUTS: tuple[str, ...] = ("pcb_path",)

# --- Registry data structures --------------------------------------------------


@dataclass(frozen=True)
class InputSpec:
    """A declared input of a gate.

    Attributes:
        name: Input name (container field name or declared input id).
        container: ``"module:ClassName"`` of the container that carries the
            input, or ``"file"`` for file-kind inputs.
        field: Attribute on the container.  Empty for file-kind inputs.
        kind: ``"field"`` | ``"file"``.
        fail_forcing: Human description of how the probe fail-forces this
            input (KTD2 — a value that must flip the verdict).
        covered: True when the probe can run for this input; False means
            the input is a documented non-covered case (``reason`` required).
        reason: Why the input is not covered (required when covered=False).
    """

    name: str
    container: str
    field: str
    kind: str = "field"
    fail_forcing: str = ""
    covered: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.covered and not self.reason:
            raise ValueError(f"InputSpec '{self.name}' is not covered but has no reason")


@dataclass(frozen=True)
class CiScriptSpec:
    """A CI gate script surveyed by U1/U4.

    Attributes:
        script: ``scripts/<name>.py`` path.
        declared_input: Primary input file the gate reads (may be empty when
            the gate scans the source tree).
        reason: Why this script's probe is not enabled in this landing
            (U4: non-covered cases carry a reason).
    """

    script: str
    declared_input: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TrackedFinding:
    """A tracked pre-existing finding on the deprecated surface (U1/U5).

    A finding leaves the tracked list only when remediated — never silently
    dropped with the deprecated surface it lives on.
    """

    id: str
    title: str
    status: str  # "open" | "closed"
    remediation_unit: str
    attribution: str = ""


@dataclass(frozen=True)
class PhysicsParameterSpec:
    """A physics parameter from ``physics_parameter_map.yaml``.

    Attributes:
        name: Parameter id.
        source: ``"module:attr"`` declaration site.
        default: Production default value.
        perturbation: ``{mode: relative|absolute, delta: number}``.
        scenario: Probe scenario id.
        consumers: Production-path consumer entry points.
    """

    name: str
    source: str
    default: float
    perturbation: dict[str, Any]
    scenario: str
    consumers: tuple[str, ...]


@dataclass(frozen=True)
class GateInputRegistry:
    """The full dead-parameter registry (gate inputs + survey + findings)."""

    gates: tuple[Any, ...] = ()
    ci_scripts: tuple[CiScriptSpec, ...] = ()
    tracked_findings: tuple[TrackedFinding, ...] = ()
    non_covered: tuple[InputSpec, ...] = ()
    physics_parameters: tuple[PhysicsParameterSpec, ...] = ()


# --- Resolution helpers --------------------------------------------------------


def resolve_container(container_path: str) -> type:
    """Resolve ``"module:ClassName"`` to the class object.

    Raises:
        ImportError: if the module cannot be imported.
        AttributeError: if the class is not found on the module.
    """
    module_name, _, class_name = container_path.partition(":")
    if not class_name:
        raise ValueError(f"container path '{container_path}' has no ':' separator")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def resolve_dotted(module: Any, dotted: str) -> Any:
    """Walk a dotted attribute path on *module* (``"Class.method"`` etc.)."""
    obj: Any = module
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def _repo_root() -> Path:
    """Find the repo root by walking up to the ``power_pcb_dataset`` dir."""
    current = Path(__file__).resolve()
    for _ in range(12):
        if (current / "power_pcb_dataset").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        "Could not locate repo root (power_pcb_dataset/) above "
        f"{Path(__file__).resolve()}"
    )


def physics_map_path() -> Path:
    """Path to ``power_pcb_dataset/physics_parameter_map.yaml``."""
    return _repo_root() / "power_pcb_dataset" / "physics_parameter_map.yaml"


# --- Validation ----------------------------------------------------------------


def validate_declared_inputs(registry: GateInputRegistry) -> list[str]:
    """Validate every declared container input is a real field on its container.

    Returns a list of human-readable errors (empty when the registry is
    consistent).  A gate declaring a metric its container does not carry is
    a registry failure, named with the gate and the metric.
    """
    errors: list[str] = []
    for gate in registry.gates:
        for spec in gate.declared_inputs:
            if spec.kind == "file":
                continue  # file inputs validated by the check script
            try:
                container = resolve_container(spec.container)
            except (ImportError, AttributeError, ValueError) as exc:
                errors.append(
                    f"gate '{gate.name}': container '{spec.container}' "
                    f"unresolvable: {exc}"
                )
                continue
            if dataclasses.is_dataclass(container):
                fields = {f.name for f in dataclasses.fields(container)}
                if spec.field not in fields:
                    errors.append(
                        f"gate '{gate.name}': declared input '{spec.field}' "
                        f"is not a field of container '{spec.container}' "
                        f"(fields: {sorted(fields)})"
                    )
            elif spec.field and not hasattr(container, spec.field):
                errors.append(
                    f"gate '{gate.name}': declared input '{spec.field}' "
                    f"is not an attribute of container '{spec.container}'"
                )
    return errors


def validate_physics_parameter_map(
    params: tuple[PhysicsParameterSpec, ...],
) -> list[str]:
    """Validate the physics parameter register.

    Each parameter must:
    - resolve at its source declaration site,
    - carry a deterministic perturbation (relative or absolute),
    - name at least one consumer, and every consumer must resolve.
    A parameter with an empty consumer list is a dead parameter and fails.
    """
    errors: list[str] = []
    for param in params:
        # Source resolution (function-arg sources stop at the function and
        # are validated against the signature below).
        module_name, _, rest = param.source.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            errors.append(f"param '{param.name}': module '{module_name}' unimportable: {exc}")
            continue
        parts = rest.split(".")
        arg_name: str | None = None
        try:
            obj: Any = module
            for i, part in enumerate(parts):
                obj = getattr(obj, part)
                if inspect.isfunction(obj) and i < len(parts) - 1:
                    arg_name = parts[i + 1]
                    break
        except AttributeError as exc:
            errors.append(f"param '{param.name}': source '{param.source}' unresolved: {exc}")
            continue

        # Function-argument sources: the trailing name must be a parameter of
        # the function (a phantom arg declaration is a registry failure).
        if arg_name is not None and inspect.isfunction(obj):
            sig = inspect.signature(obj)
            if arg_name not in sig.parameters:
                errors.append(
                    f"param '{param.name}': source '{param.source}' names "
                    f"argument '{arg_name}' which is not in the signature of "
                    f"{obj.__module__}.{obj.__name__} "
                    f"(params: {list(sig.parameters)})"
                )

        # Perturbation shape.
        if not isinstance(param.perturbation, dict):
            errors.append(f"param '{param.name}': perturbation must be a mapping")
        else:
            mode = param.perturbation.get("mode")
            delta = param.perturbation.get("delta")
            if mode not in ("relative", "absolute"):
                errors.append(
                    f"param '{param.name}': perturbation mode must be "
                    f"'relative' or 'absolute', got {mode!r}"
                )
            if not isinstance(delta, (int, float)):
                errors.append(f"param '{param.name}': perturbation delta must be numeric")

        # Consumers (dead parameter check).
        if not param.consumers:
            errors.append(f"param '{param.name}': consumer list is empty (dead parameter)")
            continue
        for consumer in param.consumers:
            consumer_module, _, func_path = consumer.partition(":")
            try:
                cmod = importlib.import_module(consumer_module)
            except ImportError as exc:
                errors.append(
                    f"param '{param.name}': consumer module '{consumer_module}' "
                    f"unimportable: {exc}"
                )
                continue
            if not func_path:
                errors.append(f"param '{param.name}': consumer '{consumer}' has no callable path")
                continue
            try:
                resolve_dotted(cmod, func_path)
            except AttributeError as exc:
                errors.append(
                    f"param '{param.name}': consumer '{consumer}' unresolved: {exc}"
                )
    return errors


# --- Physics map loading -------------------------------------------------------


def load_physics_parameter_map(path: Path | None = None) -> tuple[PhysicsParameterSpec, ...]:
    """Load and parse ``physics_parameter_map.yaml`` into specs.

    Args:
        path: Explicit path to the map.  Defaults to
            ``power_pcb_dataset/physics_parameter_map.yaml``.

    Raises:
        FileNotFoundError: if the map does not exist.
        ValueError: if the map is malformed.
    """
    import yaml

    map_path = path or physics_map_path()
    if not map_path.exists():
        raise FileNotFoundError(f"physics parameter map not found: {map_path}")
    with map_path.open() as fh:
        data = yaml.safe_load(fh) or {}

    if data.get("version") != 1:
        raise ValueError(
            f"physics parameter map {map_path} has unsupported version "
            f"{data.get('version')!r} (expected 1)"
        )
    raw_params = data.get("parameters", [])
    if not isinstance(raw_params, list):
        raise ValueError(f"physics parameter map {map_path}: 'parameters' must be a list")

    params: list[PhysicsParameterSpec] = []
    for raw in raw_params:
        params.append(
            PhysicsParameterSpec(
                name=str(raw["name"]),
                source=str(raw["source"]),
                default=float(raw["default"]),
                perturbation=dict(raw["perturbation"]),
                scenario=str(raw["scenario"]),
                consumers=tuple(
                    str(c["consumer"]) for c in raw.get("consumers", [])
                ),
            )
        )
    return tuple(params)


# --- The default registry (single source of truth) -----------------------------


def _acceptance_inner_gate_spec() -> Any:
    """Declarative spec for the acceptance-gate inner (placement-audit) surface.

    The probe machinery (baseline scenario + per-input fail-forcing
    transforms + verdict consumer) lives here because it is part of the
    registry: adding an input is a change to this spec, and the probe module
    stays generic.
    """
    from temper_placer.pcl.constraints import (
        BoardSide,
        ConstraintTier,
        EdgeType,
        EnclosingConstraint,
        OnSideConstraint,
        SeparatedConstraint,
    )
    from temper_placer.placer.cp_sat.audit import Placement, PlacementAuditor

    _KW = {"tier": ConstraintTier.HARD, "because": "synthetic dead-parameter probe scenario"}

    def build_baseline() -> tuple[Placement, list]:
        """A placement+constraint set that passes the audit at baseline and
        where each registered input's fail-forcing transform flips the verdict."""
        placement = Placement(
            positions_mm={
                "A": (20.0, 20.0),
                "B": (10.0, 10.0),
                "C": (35.0, 35.0),
                "D": (11.0, 11.0),
            },
            sizes_mm={"A": (2.0, 2.0), "B": (2.0, 2.0), "C": (2.0, 2.0), "D": (2.0, 2.0)},
            rotations=dict.fromkeys(["A", "B", "C", "D"], 0),
            board_w_mm=40.0,
            board_h_mm=40.0,
            zones={"Z1": (15.0, 15.0, 25.0, 25.0), "Z2": (5.0, 5.0, 15.0, 15.0)},
            zone_components={"Z1": ["A"], "Z2": ["B"]},
        )
        constraints = [
            # Zone-to-zone separation resolved through zone_components.
            SeparatedConstraint("Z1", "Z2", min_distance_mm=5.0, **_KW),
            # Enclosing: A must sit inside zone Z1 with a 2mm margin.
            EnclosingConstraint("Z1", ["A"], margin_mm=2.0, **_KW),
            # Edge proximity: C must sit near the right and top edges; these
            # are the only checks that read board_w_mm / board_h_mm.
            OnSideConstraint(["C"], BoardSide.RIGHT, EdgeType.NEAR, max_distance_mm=5.0, **_KW),
            OnSideConstraint(["C"], BoardSide.TOP, EdgeType.NEAR, max_distance_mm=5.0, **_KW),
        ]
        return placement, constraints

    def consume(placement: Placement, constraints: list) -> bool:
        """The production verdict: AuditReport.all_pass."""
        return PlacementAuditor(placement).audit(constraints).all_pass

    import copy as _copy

    def _clone(placement: Placement) -> Placement:
        return _copy.deepcopy(placement)

    def perturb_positions(placement: Placement, _constraints: list) -> tuple[Placement, list]:
        p = _clone(placement)
        p.positions_mm = dict.fromkeys(p.positions_mm, (0.0, 0.0))
        return p, _constraints

    def perturb_sizes(placement: Placement, _constraints: list) -> tuple[Placement, list]:
        p = _clone(placement)
        p.sizes_mm = dict.fromkeys(p.sizes_mm, (100.0, 100.0))
        return p, _constraints

    def perturb_board_w(placement: Placement, _constraints: list) -> tuple[Placement, list]:
        p = _clone(placement)
        p.board_w_mm = 100.0
        return p, _constraints

    def perturb_board_h(placement: Placement, _constraints: list) -> tuple[Placement, list]:
        p = _clone(placement)
        p.board_h_mm = 100.0
        return p, _constraints

    def perturb_zones(placement: Placement, _constraints: list) -> tuple[Placement, list]:
        p = _clone(placement)
        p.zones = {"Z1": (0.0, 0.0, 2.0, 2.0), "Z2": (5.0, 5.0, 15.0, 15.0)}
        return p, _constraints

    def perturb_zone_components(placement: Placement, _constraints: list) -> tuple[Placement, list]:
        # Pull D into zone Z1's membership: SEPARATED(Z1, Z2) then resolves
        # the (D, B) pair, which overlaps.
        p = _clone(placement)
        p.zone_components = {"Z1": ["A", "D"], "Z2": ["B"]}
        return p, _constraints

    declared = tuple(
        InputSpec(
            name=name,
            container=ACCEPTANCE_INNER_CONTAINER,
            field=name,
            kind="field",
            fail_forcing=_FAIL_FORCING[name],
        )
        for name in ACCEPTANCE_INNER_DECLARED_INPUTS
    )

    @dataclass(frozen=True)
    class AcceptanceInnerGateSpec:
        name: str
        kind: str
        module: str
        declared_inputs: tuple[InputSpec, ...]
        build_baseline: Callable[[], tuple[Placement, list]] = field(compare=False)
        consume: Callable[..., bool] = field(compare=False)
        perturb: dict[str, Callable[[Placement, list], tuple[Placement, list]]] = field(
            default_factory=dict, compare=False
        )

    return AcceptanceInnerGateSpec(
        name="acceptance_gate.inner",
        kind="container",
        module="temper_placer.placer.cp_sat.gate",
        declared_inputs=declared,
        build_baseline=build_baseline,
        consume=consume,
        perturb={
            "positions_mm": perturb_positions,
            "sizes_mm": perturb_sizes,
            "board_w_mm": perturb_board_w,
            "board_h_mm": perturb_board_h,
            "zones": perturb_zones,
            "zone_components": perturb_zone_components,
        },
    )


# Fail-forcing strategy per acceptance-inner input (KTD2: derived from the
# auditor's own threshold logic — each transform must flip all_pass).
_FAIL_FORCING: dict[str, str] = {
    "positions_mm": "collapse every component to the origin — SEPARATED gap -> 0 < min_distance",
    "sizes_mm": "inflate every component to 100x100mm — SEPARATED edge-to-edge gap -> negative",
    "board_w_mm": "grow board to 100mm — ON_SIDE(right) threshold bw-max_d outruns component bbox",
    "board_h_mm": "grow board to 100mm — ON_SIDE(top) threshold bh-max_d outruns component bbox",
    "zones": "shrink zone Z1 to (0,0,2,2) — ENCLOSING bbox no longer inside the zone",
    "zone_components": "pull D into Z1 membership — SEPARATED(Z1,Z2) now checks the overlapping (D,B) pair",
}


def _acceptance_truth_non_covered() -> InputSpec:
    """The truth (DRC) gate's declared input, registered as a non-covered case.

    The probe for a file-kind input needs a DRC-passing baseline board, which
    the synthetic probe cannot produce (KiCad DRC runs in the board-gates CI
    job against the real pcb/temper.kicad_pcb).  Registered — never silently
    dropped — per U4's documented-NOTE convention.
    """
    return InputSpec(
        name="pcb_path",
        container="file",
        field="",
        kind="file",
        fail_forcing="point the truth gate at a nonexistent PCB path — gate must fail",
        covered=False,
        reason=(
            "probe requires a DRC-passing baseline board; KiCad DRC is "
            "exercised by the board-gates CI job against the real board. "
            "UNMEASURED until a synthetic DRC oracle is available."
        ),
    )


# The pre-flight survey of invoked CI gate scripts (U1 step 1 / U4).  Extracted
# from .github/workflows/python-tests.yml `run:` steps; the U4 completeness
# test re-derives this list from the workflow and fails on drift.
_CI_SCRIPT_SURVEY: list[tuple[str, str, str]] = [
    # (script, primary declared input file, reason probe is non-covered)
    ("check_board_containment.py", "pcb/temper.kicad_pcb", "board-containment invariant (R26); needs the real board; probe harness deferred"),
    ("check_board_defect_corpus.py", "pcb/temper.kicad_pcb", "board-defect mutation corpus (plan 2026-08-02-024 R38); needs the real board; probe harness deferred"),
    ("check_bom_source_reconciliation.py", "docs/hardware/BOM.md", "BOM<->source reconciliation (goal-set R14); needs the real BOM and elec/src; probe harness deferred"),
    ("check_dead_parameter_inputs.py", "power_pcb_dataset/physics_parameter_map.yaml", "dead-parameter standing check (plan 2026-08-02-019 U3); probe is the check itself"),
    ("check_firmware_board_contract.py", "firmware/tools/board_derivations.yaml", "firmware-board contract oracle (plan 2026-08-02-027); probe harness deferred"),
    ("check_required_checks.py", ".github/required-checks.json", "aggregator drift validation; probe harness deferred"),
    ("classify_changed_paths.py", "", "change-driven CI path classifier (main, 2026-08-03); probe harness deferred"),
    ("constraint_mutation_gate.py", "power_pcb_dataset/constraint_kill_sets.yaml", "mutation-suite gate (plan 2026-08-02-006); probe harness deferred"),
    ("capacity_budget_gate.py", "scripts/capacity_budget_packages.yaml", "reads fault-tree fan-in data; probe harness deferred"),
    ("check_copper_net_consistency.py", "pcb/temper.kicad_pcb", "needs compiled netlist (elec/build/, not committed); baseline red today"),
    ("check_creepage_clearance_drift.py", "elec/src/constraints.ato", "cross-source creepage/clearance SSOT drift gate -- PREPARED, NOT ENABLED: the python-tests.yml step invoking it is deliberately commented out pending human approval of the 4 mismatched value families it reports (docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md Task 3); would go CI-red on main by design. Registered as a documented non-covered case; its own unit tests pass against synthetic fixtures."),
    ("check_gate_mutations.py", "scripts/gate_mutate.py", "R42 gate-mutation sweep gate (d1220e577); probe is the check itself; registered as documented non-covered"),
    ("check_coverage_gate.py", "coverage.json", "consumes pytest-cov output; probe harness deferred"),
    ("check_derived_doc_drift.py", "docs/STRATEGY.md", "doc-drift comparison; probe harness deferred"),
    ("check_domain_partition.py", "elec/build/default.net", "needs compiled netlist (elec/build/, not committed)"),
    ("check_drc_ceiling_approval.py", "power_pcb_dataset/drc_ceiling.json", "git merge-base dependent; probe harness deferred"),
    ("check_erc_off_grid_consequence.py", "pcb/temper.kicad_sch", "ERC endpoint_off_grid consequence classification (docs/evidence/2026-08-07-erc-off-grid-endpoint-analysis.md); needs kicad-cli-regenerated ERC JSON + schematic netlist XML; probe harness deferred"),
    ("check_evidence_provenance.py", "docs/evidence/", "provenance scan; probe harness deferred"),
    ("check_footprint_drift.py", "pcb/temper.kicad_pcb", "needs compiled netlist; probe harness deferred"),
    ("check_hash_order_determinism.py", ".hash-order-inventory", "salted-hash order gate (PYTHONHASHSEED determinism); probe harness deferred"),
    ("check_hv_netclass_coverage.py", "elec/domain_manifest.yaml", "HV netclass coverage gate (N4); probe harness deferred"),
    ("check_isolation_keepout.py", "pcb/temper.kicad_pcb", "baseline red on main (no keepout zones); probe inconclusive today"),
    ("check_manifest_gate.py", "scripts/manifest.yaml", "manifest scan; probe harness deferred"),
    ("check_measurement_provenance.py", "power_pcb_dataset/drc_ceiling.json", "baseline red on main (stale ceiling); probe inconclusive today"),
    ("check_net_classification.py", "elec/domain_manifest.yaml", "source-tree scan; probe harness deferred"),
    ("check_net_pin_identity_pad_correspondence.py", "pcb/temper.kicad_pcb", "net accounting gate (router silent-net-loss investigation, 2026-08-13): flags a net whose (component_ref, pad_number) pin-identity view collapses to <=1 distinct pin while its real physical pad count is >1 -- the invariant behind discharge.k_dis1-no/discharge.k_dis2-no falsely certifying as a trivial no-copper-needed net; self-contained regex parse of the real board, needs no compiled extension; probe harness deferred"),
    ("check_netlist_board_reconciliation.py", "elec/build/default.net", "netlist<->board reconciliation (plan 2026-08-02-021 R16); needs compiled netlist (elec/build/, not committed)"),
    ("check_netlist_mutation_corpus.py", "elec/build/default.net", "netlist-mutation corpus (plan 2026-08-02-021 R39/U7); needs compiled netlist (elec/build/, not committed)"),
    ("check_netlist_stage_checks.py", "elec/build/default.net", "netlist-stage checks (single-pin nets, unconnected power pins, voltage-domain compatibility; docs/STRATEGY.md 'Checks by stage'); needs compiled netlist (elec/build/, not committed); 27 open findings on a dated backlog allowlist"),
    ("check_no_raw_rotation_trig.py", "", "source-tree scan; probe harness deferred"),
    ("check_oracle_hashes.py", "scripts/oracle_hashes.json", "oracle content-hash gate (decision 2026-08-06); probe is the check itself"),
    ("check_pad_orientation.py", "pcb/temper.kicad_pcb", "needs the real board; probe harness deferred"),
    ("check_physics_provenance.py", "packages/temper-placer/src/temper_placer/physics/", "source-tree scan; probe harness deferred"),
    ("check_plane_condemnation_quantifier.py", "pcb/temper.kicad_pcb", "plane-condemnation quantifier gate (docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md); needs the real board; probe harness deferred"),
    ("check_pll_range_consistency.py", "firmware/components/control/pll_control.h", "firmware-header scan; probe harness deferred"),
    ("check_rust_drc_presence.py", "packages/temper-drc-rs/src", "extension-symbol scan; probe harness deferred"),
    ("check_script_sunset.py", "scripts/manifest.yaml", "manifest scan (warn-only in CI); probe harness deferred"),
    ("check_stale_extensions.py", "packages/", "extension freshness scan; probe harness deferred"),
    ("check_test_baseline_writes.py", "power_pcb_dataset/baselines/", "protected-artifact write detector; probe harness deferred"),
    ("check_typecheck_gate.py", "", "type-check artifact scan; probe harness deferred"),
    ("check_undeclared_imports.py", "", "source-tree import scan; probe harness deferred"),
    ("check_unwired_kernels.py", "packages/", "Rust-kernel production-caller gate (#826); source-tree scan; probe harness deferred"),
    ("check_vacuous_gates.py", "", "source-tree scan; probe harness deferred"),
    ("check_verdict_coverage.py", "", "Wave-4 residual-verdict coverage gate (R7); source-tree scan; probe harness deferred"),
    ("ci_check_drc.py", "pcb/temper.kicad_pcb", "DRC ratchet; needs real board + kicad-cli"),
    ("ci_closure_test.py", "", "source-tree scan; probe harness deferred"),
    ("ci_identity_check.py", "pcb/temper.kicad_pcb", "board identity; needs real board"),
    ("gen_config_reference.py", "firmware/config.yaml", "codegen drift; probe harness deferred"),
    ("gen_domain_models.py", "scripts/templates/netclass_rules.py.j2", "codegen drift; probe harness deferred"),
    ("generate_kicad_dru.py", "packages/temper-placer/src/temper_placer/core/design_rules.py", "codegen drift (pcb/temper.kicad_dru from TEMPER_NET_CLASSES); probe harness deferred"),
    ("gen_repo_state.py", "", "repo-state snapshot; probe harness deferred"),
    ("gen_schematics.py", "elec/src/", "codegen drift; probe harness deferred"),
    ("gen_wasm_test_registry.py", "tools/wasm/wasm_test_registry.json", "wasm test-family census generator (wired into CI by #949; registry regenerated via make regen); probe harness deferred"),
    ("gate_mutate.py", "scripts/", "R42 gate-mutation generator (d1220e577); mutates gates in-place during the sweep; probe harness deferred"),
    ("import_linter_gate.py", ".importlinter", "boundary scan; probe harness deferred"),
    ("known_failure_pins.py", "known-failure-pins.yaml", "data scan; probe harness deferred"),
    ("mpn_fabrication_gate.py", "elec/src/", "MPN/value scan; probe harness deferred"),
    ("part_stress_gate.py", "scripts/part_stress_limits.yaml", "part stress vs. abs-max rating gate (docs/hardware/PART_STRESS_AUDIT.md); needs the real BOM (elec/build/default.csv, not committed); 3 open over-rating findings on a dated backlog"),
    ("physics_soundness_register_gate.py", "power_pcb_dataset/physics_soundness_register.yaml", "physics soundness-proof register gate (R20, plan 2026-08-02-004); probe harness deferred"),
    ("regen_derived.py", "make regen", "derived-artifact regenerator (README counts, oracle registry, wasm registry; make regen/ regen-check; probe harness deferred)"),
    ("pytest_guard.py", "", "test-suite guard; probe harness deferred"),
    ("test_root_hygiene.py", "", "repo-root scan; probe harness deferred"),
    ("test_physics_soundness_register_gate.py", "", "test file referenced in the workflow path filters (packages/temper-placer/tests/scripts/); probe harness deferred"),
    ("trace_invocations.py", "scripts/manifest.yaml", "invocation-graph generator; probe harness deferred"),
    ("update_oracle_hashes.py", "scripts/oracle_hashes.json", "oracle registry generator; not wired into CI (referenced in the workflow comment); probe harness deferred"),
    ("update_production_routing_baseline.py", "power_pcb_dataset/baselines/", "production-routing baseline generator; referenced in the workflow path filters; probe harness deferred"),
    ("vulture_gate.py", "scripts/deadcode-baseline.py", "dead-code scan; probe harness deferred"),
    ("write_extension_stamps.py", "packages/", "stamp writer; probe harness deferred"),
    # 2026-08-12 hygiene/type-debt paydown: 7 correspondence/integrity gates
    # invoked in python-tests.yml but never added to this survey (the U4
    # completeness test only started catching this once run -- see the PR
    # for the gate's own before/after). Reasons/declared-inputs summarized
    # from each script's scripts/manifest.yaml entry, which was kept current.
    ("check_corpus_fixture_realboard_divergence.py", "power_pcb_dataset/corpus/manifest.yaml", "corpus-fixture <-> real-board divergence gate (2026-08-11 golden-fixture decision); probe harness deferred"),
    ("check_layer_plane_emission_coverage.py", "pcb/temper.kicad_pcb", "declared <-> emitted layer-plane coverage gate; advisory (continue-on-error) pending the underlying In1.Cu/In2.Cu fix; probe harness deferred"),
    ("check_netclass_class_param_correspondence.py", "pcb/temper.kicad_pro", "netclass scalar-parameter correspondence gate; advisory (continue-on-error); currently VIOLATION on origin/main (HighVoltage.clearance mismatch); probe harness deferred"),
    ("check_netclass_map_board_correspondence.py", "pcb/temper.kicad_pcb", "hand-maintained net_classes: YAML <-> board net-name correspondence gate; probe harness deferred"),
    ("check_pcl_config_board_correspondence.py", "packages/temper-placer/configs/constraints/temper_induction_cooker.yaml", "PCL placement-constraint config <-> board correspondence gate; advisory (continue-on-error) pending the config fix; probe harness deferred"),
    ("check_pd2_compartment_evidence.py", "docs/specs/pd2_compartment_evidence.yaml", "PD2/8.0mm creepage compartment-evidence gate; advisory (continue-on-error) pending the compartment being built; probe harness deferred"),
    ("check_venv_integrity.py", "", "venv editable-install identity gate (2026-08-11 shared-venv-hijack incident); source/site-packages scan; probe harness deferred"),
]


def build_default_registry() -> GateInputRegistry:
    """Construct the default registry (the single source of truth)."""
    ci_scripts = tuple(
        CiScriptSpec(script=s, declared_input=d, reason=r)
        for s, d, r in _CI_SCRIPT_SURVEY
    )
    tracked_findings = (
        TrackedFinding(
            id="R37-PHANTOM-REQUIRED-METRICS",
            title=(
                "Deprecated RunMetrics stub: four phantom required_metrics "
                "declarations (gate_loop_area_mm2, bootstrap_loop_area_mm2, "
                "commutation_loop_area_mm2, igbt_edge_distance_mm) on "
                "PlacementCompleteGate/ProductionReadyGate that the container "
                "does not carry and the checks never read"
            ),
            status="closed",  # remediated by U5 in this changeset
            remediation_unit="U5",
            attribution=(
                "declarations removed from validation_gates.py in commit "
                "2292e097c204c0ce02765dee35e374cf9d3572b1; RunMetrics "
                "(core/loss_types.py) never carried them; live surface uses "
                "metrics/physics.py EMIMetrics.gate_loop_area_mm2 (different "
                "container)"
            ),
        ),
    )
    return GateInputRegistry(
        gates=(_acceptance_inner_gate_spec(),),
        ci_scripts=ci_scripts,
        tracked_findings=tracked_findings,
        non_covered=(_acceptance_truth_non_covered(),),
        physics_parameters=load_physics_parameter_map(),
    )


def validate_registry(registry: GateInputRegistry) -> list[str]:
    """Run all registry validations; returns a list of errors (empty = OK)."""
    errors = list(validate_declared_inputs(registry))
    errors.extend(validate_physics_parameter_map(registry.physics_parameters))
    return errors


# --- Unregistered-parameter scan (U3 scenario 3) --------------------------------
#
# A new float field on a registered physics config that is neither registered
# in physics_parameter_map.yaml nor on the documented allowlist is an
# unregistered physics parameter and fails the standing check.  The allowlist
# records WHY each excluded field is not probed — the A3 named set is
# conductivity / convection / ampacity; grid geometry, solver budgets and
# non-material constants are documented follow-ups, never silent exclusions.

PHYSICS_CONFIG_SCAN: tuple[str, ...] = (
    "temper_placer.physics.thermal_fdm:ThermalFDMConfig",
    "temper_placer.physics.thermal_potential:ThermalPotentialConfig",
    "temper_placer.validation.thermal_scorer:ThermalScorerConfig",
)

UNREGISTERED_PHYSICS_FIELDS_ALLOWLIST: dict[tuple[str, str], str] = {
    # ThermalFDMConfig — registered: k_fr4, k_copper
    ("temper_placer.physics.thermal_fdm:ThermalFDMConfig", "cell_size_mm"): "grid geometry input — A3 named set excludes geometry; documented follow-up",
    ("temper_placer.physics.thermal_fdm:ThermalFDMConfig", "ambient_C"): "ambient boundary condition — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_fdm:ThermalFDMConfig", "board_thickness_mm"): "stackup geometry input — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_fdm:ThermalFDMConfig", "target_solve_time_s"): "solver budget — not a physics material parameter",
    # ThermalPotentialConfig — registered: convection_weight
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "edge_weight"): "potential component weight — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "copper_weight"): "potential component weight — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "coupling_weight"): "potential component weight — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "exclusion_weight"): "potential component weight — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "edge_decay_length_mm"): "potential geometry input — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "thermal_exclusion_radius_mm"): "potential geometry input — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "exclusion_barrier_height"): "potential barrier constant — not in the A3 named set; documented follow-up",
    ("temper_placer.physics.thermal_potential:ThermalPotentialConfig", "exclusion_steepness"): "potential barrier constant — not in the A3 named set; documented follow-up",
    # ThermalScorerConfig — registered: h
    ("temper_placer.validation.thermal_scorer:ThermalScorerConfig", "tolerance_C"): "backward-compat field, unused in the convective model (documented in module)",
    ("temper_placer.validation.thermal_scorer:ThermalScorerConfig", "relaxation"): "backward-compat field, unused in the convective model (documented in module)",
}


def _is_float_field(field_: dataclasses.Field) -> bool:
    """True for fields that carry a float physics value (by default value or
    annotation).  Ints, strings, tuples and None-defaults are excluded."""
    default = field_.default
    annotation = field_.type
    return (
        isinstance(default, float)
        or annotation is float
        or annotation == "float"
        or (default is dataclasses.MISSING and annotation is float)
    )


def scan_unregistered_physics_fields(registry: GateInputRegistry) -> list[str]:
    """Flag float fields on registered physics configs that are neither
    registered in the physics map nor on the documented allowlist.

    Returns a list of errors (empty = every float field is registered or
    documented).  A new physics parameter added to a registered config
    without a map entry fails the standing check (U3 scenario 3).
    """
    registered_by_config: dict[str, set[str]] = {}
    for param in registry.physics_parameters:
        module_name, _, rest = param.source.partition(":")
        parts = rest.split(".")
        if len(parts) >= 2:
            config_path = f"{module_name}:{parts[0]}"
            registered_by_config.setdefault(config_path, set()).add(parts[1])

    errors: list[str] = []
    for config_path in PHYSICS_CONFIG_SCAN:
        try:
            cls = resolve_container(config_path)
        except (ImportError, AttributeError, ValueError) as exc:
            errors.append(f"physics-config scan: '{config_path}' unresolvable: {exc}")
            continue
        registered = registered_by_config.get(config_path, set())
        for field_ in dataclasses.fields(cls):
            if not _is_float_field(field_):
                continue
            if field_.name in registered:
                continue
            allow = UNREGISTERED_PHYSICS_FIELDS_ALLOWLIST.get((config_path, field_.name))
            if allow is not None:
                continue
            errors.append(
                f"unregistered physics parameter: '{config_path}.{field_.name}' "
                f"is a float field on a registered physics config but has no "
                f"entry in physics_parameter_map.yaml and no allowlisted "
                f"exclusion — register it or document the exclusion"
            )
    return errors
