"""Build constraint-family campaign inputs from the production solve path.

This is a marshalling adapter, not a second production configuration.  The
no-loop CLI call to :func:`solve_placement` is the authoritative source for
the common options and for the families that are enabled there.  Optional
audit inputs are built with the same real-board loaders used by that caller.
Families that have no live production caller/configuration are returned in
``unavailable_families``; this module never represents them with empty kwargs.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.placer.cp_sat.constraint_family_campaign import (
    ConstraintFamilyCampaignResult,
    run_constraint_family_campaign,
)
from temper_placer.placer.cp_sat.constraint_family_probe_planner import (
    plan_constraint_family_probes,
)
from temper_placer.placer.cp_sat.constraint_family_schema import production_family_kwargs
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from temper_placer.placer.cp_sat.constraint_family_campaign import (
        ConstraintFamilyProbe,
    )
    from temper_placer.placer.cp_sat.constraint_family_frontier import (
        ConstraintFamilySearchFrontier,
    )
    from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
        RestorationLimits,
    )


_UNAVAILABLE_FAMILY_REASONS = {
    "decomposed_creepage": (
        "solve_placement's production caller does not enable decomposed_creepage"
    ),
    "isolation_barrier": (
        "isolation_barrier is only assembled by the repair command after its preflight; "
        "the production no-loop caller does not pass it"
    ),
    "heatsink_colocation": (
        "heatsink_colocation is accepted by solve_placement but no production caller "
        "supplies a common rotation"
    ),
    "protective_impedance_colocation": (
        "protective_impedance_colocation is accepted by solve_placement but no production "
        "caller supplies its manifest/chains"
    ),
    "fixed_copper": (
        "fixed_copper is assembled only by the repair command from a routed-board "
        "parse result and repair touch set"
    ),
}


@dataclass(frozen=True, slots=True)
class ProductionConstraintFamilyInputs:
    """Parsed production inputs and only the family options backed by them."""

    input_pcb: Path
    config: Path
    parse_result: object
    netlist: object
    board: object
    production_kwargs: Mapping[str, object]
    families: Mapping[str, Mapping[str, object]]
    unavailable_families: Mapping[str, str]
    diagnostics: tuple[str, ...] = ()
    stripped_instance: object | None = None

    @property
    def available_families(self) -> tuple[str, ...]:
        """Return family names in deterministic adapter order."""

        return tuple(self.families)


def _find_repo_file(relative_path: str, *, start: Path | None = None) -> Path | None:
    """Mirror the production CLI's cwd-parent artifact lookup."""

    origin = (start or Path.cwd()).resolve()
    if origin.is_file():
        origin = origin.parent
    for candidate in (origin, *origin.parents):
        path = candidate / relative_path
        if path.is_file():
            return path
    return None


def _load_aliases(config: Path, netlist: object) -> tuple[Mapping[str, str] | None, Mapping[str, str] | None]:
    """Load the exact reference manifest used by the production caller."""

    manifest_path = config.with_suffix(".references.yaml")
    if not manifest_path.is_file():
        return None, None
    from temper_io_types import load_reference_alias_manifest

    from temper_placer.placer.cp_sat.encoder import _resolve_loop_components

    loop_names = _resolve_loop_components(netlist)
    manifest = load_reference_alias_manifest(
        manifest_path,
        component_refs=[component.ref for component in netlist.components],
        loop_names=loop_names,
    )
    return manifest.component_aliases or None, manifest.loop_aliases or None


def _validator_input(input_pcb: Path) -> tuple[dict[str, object] | None, str | None]:
    """Build the CLI's validator input, or explain why it is unavailable."""

    manifest = _find_repo_file("elec/domain_manifest.yaml", start=input_pcb)
    netlist_path = _find_repo_file("elec/build/default.net", start=input_pcb)
    if manifest is None:
        return None, "elec/domain_manifest.yaml is not present"
    if netlist_path is None:
        return None, "elec/build/default.net is not present (run `make netlist` first)"

    from temper_placer.io.real_board import RealBoardUnavailable, load_real_board_placement

    try:
        placement, voltage_domains, _stats = load_real_board_placement(
            pcb_path=input_pcb,
            manifest_path=manifest,
            netlist_path=netlist_path,
        )
    except RealBoardUnavailable as exc:
        return None, f"validator artifacts unavailable: {exc}"
    if not placement.get("components"):
        return None, "validator artifact has zero domain-classified components"
    return {"placement": placement, "voltage_domains": voltage_domains}, None


def _body_collision_input(input_pcb: Path) -> tuple[dict[str, object] | None, str | None]:
    """Build the CLI's fail-closed F.Fab audit input."""

    allowlist_path = _find_repo_file(
        "packages/temper-placer/configs/body_collision_allowlist.yaml",
        start=input_pcb,
    )
    if allowlist_path is None:
        return None, "body_collision_allowlist.yaml is not present"

    from temper_placer.io.fab_body_extraction import extract_fab_bodies
    from temper_placer.placer.cp_sat.body_collision import load_body_collision_allowlist

    allowlist = load_body_collision_allowlist(allowlist_path)
    fab_bodies = extract_fab_bodies(input_pcb)
    if not fab_bodies:
        return None, "input PCB has no parseable F.Fab body geometry"
    return {"fab_bodies": fab_bodies, "allowlist": allowlist}, None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stripped_refs(instance: object) -> tuple[str, ...]:
    components = getattr(instance, "components", None)
    if isinstance(components, (str, bytes)) or not isinstance(components, Sequence):
        raise ValueError("prepared stripped instance has no component sequence")
    refs = tuple(str(row[0]) for row in components)
    if not refs or any(not ref.strip() for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("prepared stripped instance has invalid component references")
    return refs


def _json_aliases(value: object) -> list[list[str]] | None:
    """Project aliases without leaking loader-specific mapping objects."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("reference aliases must be a mapping")
    return [[str(key), str(item)] for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))]


def production_constraint_family_cache_projections(
    inputs: ProductionConstraintFamilyInputs,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Return stable JSON-safe cache identity projections for *inputs*.

    Production kwargs contain live PCL and audit objects that are useful to
    the solver but unsuitable as cache identity.  Only scalar configuration,
    aliases, and source-artifact digests enter the frontier key.
    """

    production = {
        "config_sha256": _sha256(inputs.config),
        "seed": int(inputs.production_kwargs.get("seed", 0)),
        "experimental_omit_generated_creepage": bool(
            inputs.production_kwargs.get("experimental_omit_generated_creepage", False)
        ),
        "reference_aliases": _json_aliases(inputs.production_kwargs.get("reference_aliases")),
        "loop_aliases": _json_aliases(inputs.production_kwargs.get("loop_aliases")),
        "extra_constraints_count": len(inputs.production_kwargs.get("extra_constraints", ())),
    }
    families: dict[str, Mapping[str, object]] = {}
    for name, options in inputs.families.items():
        if name == "exact_creepage":
            families[name] = {"experimental_omit_generated_creepage": False}
        elif name == "tank_creepage":
            families[name] = {"tank_creepage": {"margin_mm": DEFAULT_TANK_CREEPAGE_MM}}
        else:
            # Audit kwargs contain geometry objects.  Their source files and
            # census are enough to identify the prepared audit input.
            projection: dict[str, object] = {"option_keys": sorted(str(key) for key in options)}
            if name == "validator_audit":
                manifest = _find_repo_file("elec/domain_manifest.yaml", start=inputs.input_pcb)
                netlist = _find_repo_file("elec/build/default.net", start=inputs.input_pcb)
                projection.update(
                    {
                        "domain_manifest_sha256": _sha256(manifest) if manifest else None,
                        "netlist_sha256": _sha256(netlist) if netlist else None,
                    }
                )
            elif name == "body_collision_audit":
                allowlist = _find_repo_file(
                    "packages/temper-placer/configs/body_collision_allowlist.yaml",
                    start=inputs.input_pcb,
                )
                projection["allowlist_sha256"] = _sha256(allowlist) if allowlist else None
            families[name] = projection
    return production, families


@dataclass(frozen=True, slots=True)
class ProductionCreepageVerification:
    """Result of the authoritative Rust exhaustive creepage check."""

    violations: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations


def make_production_constraint_family_verifier(
    inputs: ProductionConstraintFamilyInputs,
) -> Callable[[object], ProductionCreepageVerification]:
    """Create a verifier over the prepared Rust-owned requirement set.

    Campaign solver results expose component centres and absolute quarter-turn
    rotations.  The stripped Rust boundary consumes lower-left coordinates and
    rotations relative to each component's parsed orientation; this adapter
    performs that conversion exactly once at the process boundary.
    """

    from temper_placer.placer.cp_sat.production_stripped_instance import (
        ProductionStrippedInstance,
    )

    instance = inputs.stripped_instance
    if not isinstance(instance, ProductionStrippedInstance):
        raise ValueError("production inputs do not contain a prepared stripped instance")
    specs = {str(row[0]): (float(row[1]), float(row[2])) for row in instance.components}
    initial = instance.initial_placements
    expected = set(_stripped_refs(instance))

    def verify(candidate: object) -> ProductionCreepageVerification:
        positions = getattr(candidate, "positions", None)
        rotations = getattr(candidate, "rotations", None)
        if not isinstance(positions, Mapping) or not isinstance(rotations, Mapping):
            return ProductionCreepageVerification(("candidate has no position/rotation mappings",))
        if set(positions) != expected or set(rotations) != expected:
            return ProductionCreepageVerification(("candidate does not cover the exact component set",))
        placements: list[tuple[str, float, float, int]] = []
        for ref in sorted(expected):
            point = positions[ref]
            rotation = rotations[ref]
            if isinstance(point, (str, bytes)) or not isinstance(point, Sequence) or len(point) != 2:
                return ProductionCreepageVerification((f"candidate position for {ref!r} is malformed",))
            if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in range(4):
                return ProductionCreepageVerification((f"candidate rotation for {ref!r} is malformed",))
            try:
                center_x, center_y = float(point[0]), float(point[1])
            except (TypeError, ValueError):
                return ProductionCreepageVerification((f"candidate position for {ref!r} is malformed",))
            if not math.isfinite(center_x) or not math.isfinite(center_y):
                return ProductionCreepageVerification((f"candidate position for {ref!r} is non-finite",))
            initial_rotation = initial[ref][2]
            if (
                isinstance(initial_rotation, bool)
                or not isinstance(initial_rotation, int)
                or initial_rotation not in range(4)
            ):
                return ProductionCreepageVerification((f"initial rotation for {ref!r} is malformed",))
            width, height = specs[ref]
            relative_rotation = (rotation - int(initial_rotation)) % 2
            if relative_rotation:
                width, height = height, width
            placements.append(
                (ref, center_x - width / 2.0, center_y - height / 2.0, relative_rotation)
            )
        try:
            import temper_orchestration as _to

            _to.verify_stripped_creepage_py(
                list(instance.components),
                list(instance.requirements),
                instance.board_width_mm,
                instance.board_height_mm,
                placements,
                True,
            )
        except Exception as exc:
            return ProductionCreepageVerification((f"{type(exc).__name__}: {exc}",))
        return ProductionCreepageVerification()

    return verify


# Explicit builder spelling for callers that treat the verifier as an input
# adapter, while retaining the descriptive ``make_`` name for compatibility.
build_production_creepage_verifier = make_production_constraint_family_verifier


def prepare_production_constraint_family_inputs(
    input_pcb: Path | str,
    config: Path | str,
    *,
    seed: int = 0,
    include_audits: bool = True,
    stripped_instance: object | None = None,
) -> ProductionConstraintFamilyInputs:
    """Prepare a campaign input from the live production no-loop path.

    The common model retains the production PCL constraints and aliases but
    sets ``experimental_omit_generated_creepage=True`` so the exact generated
    creepage family is an explicit probe.  Tank creepage is included because
    the production no-loop caller passes the SSOT margin unconditionally.
    Validator and body-collision families are included only when their real
    board artifacts resolve completely.  Missing optional audit artifacts are
    reported, never replaced by empty dictionaries.
    """

    pcb_path = Path(input_pcb)
    config_path = Path(config)
    from temper_placer.io.config_loader import load_constraints
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    board = parse_result.board
    constraints = load_constraints(config_path)
    pcl_constraints = list(getattr(constraints, "pcl_constraints", []))
    reference_aliases, loop_aliases = _load_aliases(config_path, netlist)

    production_kwargs: dict[str, object] = {
        "extra_constraints": pcl_constraints,
        "seed": seed,
        "reference_aliases": reference_aliases,
        "loop_aliases": loop_aliases,
        # Diagnostic baseline: exact generated creepage is restored as a
        # family option below, never silently left enabled in the base.
        "experimental_omit_generated_creepage": True,
    }
    validator: dict[str, object] | None = None
    body: dict[str, object] | None = None
    unavailable = dict(_UNAVAILABLE_FAMILY_REASONS)
    diagnostics: list[str] = [
        "assembled from the production no-loop solve_placement caller",
    ]

    if include_audits:
        validator, validator_reason = _validator_input(pcb_path)
        if validator is None:
            unavailable["validator_audit"] = validator_reason or "validator input unavailable"
        body, body_reason = _body_collision_input(pcb_path)
        if body is None:
            unavailable["body_collision_audit"] = body_reason or "body-collision input unavailable"
    else:
        unavailable["validator_audit"] = "audit inputs excluded by caller"
        unavailable["body_collision_audit"] = "audit inputs excluded by caller"

    # The schema owns the top-level keyword mapping and validates that each
    # fragment is complete.  Passing None omits an unavailable family; an
    # empty mapping would incorrectly claim that the family was assembled.
    families = production_family_kwargs(
        exact_creepage=True,
        tank_creepage={"margin_mm": DEFAULT_TANK_CREEPAGE_MM},
        validator_input=validator,
        body_collision_input=body,
    )

    if stripped_instance is None:
        from temper_placer.placer.cp_sat.production_stripped_instance import (
            prepare_production_stripped_instance,
        )

        stripped_instance = prepare_production_stripped_instance(pcb_path, normalize=True)
    if set(_stripped_refs(stripped_instance)) != {
        str(component.ref) for component in netlist.components
    }:
        raise ValueError("prepared stripped instance does not match the authoritative netlist")

    return ProductionConstraintFamilyInputs(
        pcb_path,
        config_path,
        parse_result,
        netlist,
        board,
        production_kwargs,
        families,
        unavailable,
        tuple(diagnostics),
        stripped_instance,
    )


def run_production_constraint_family_campaign(
    inputs: ProductionConstraintFamilyInputs,
    *,
    planner: Callable[..., Iterable[ConstraintFamilyProbe | Sequence[str] | Mapping[str, object]]] | object = plan_constraint_family_probes,
    solver: Callable[..., object] | None = None,
    verify: Callable[[object], object] | None = None,
    limits: RestorationLimits | None = None,
    initial_hint_positions: Mapping[str, tuple[float, float, int]] | None = None,
    frontier: ConstraintFamilySearchFrontier | object | None = None,
) -> ConstraintFamilyCampaignResult:
    """Feed prepared production artifacts into the fresh-model campaign."""

    from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationLimits

    kwargs: dict[str, object] = {
        "families": inputs.families,
        "planner": planner,
        "production_kwargs": inputs.production_kwargs,
        "initial_hint_positions": initial_hint_positions,
        "verify": verify,
        "limits": limits or RestorationLimits(),
        "frontier": frontier,
    }
    if solver is not None:
        kwargs["solver"] = solver
    return run_constraint_family_campaign(inputs.netlist, inputs.board, **kwargs)  # type: ignore[arg-type]


def run_production_constraint_family_real_board_campaign(
    input_pcb: Path | str,
    config: Path | str,
    *,
    seed: int = 0,
    include_audits: bool = True,
    probes: Sequence[ConstraintFamilyProbe | Sequence[str] | Mapping[str, object]] | None = None,
    planner: Callable[..., object] | object | None = plan_constraint_family_probes,
    limits: RestorationLimits | None = None,
    warm_start_timeout_s: float | None = None,
    frontier_path: Path | str | None = None,
    solver: Callable[..., object] | None = None,
) -> ConstraintFamilyCampaignResult:
    """Run the fully-wired authoritative production-board campaign.

    This is the preferred entrypoint for real measurements: it prepares the
    production options and Rust-owned full requirement set together, derives
    stable frontier projections, and supplies the exhaustive verifier to the
    real-board orchestration layer.  Callers cannot accidentally pair a
    campaign's parsed board with a verifier built from another board.
    """

    from temper_placer.placer.cp_sat.constraint_family_real_board import (
        run_real_board_constraint_family_campaign,
    )
    from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationLimits

    inputs = prepare_production_constraint_family_inputs(
        input_pcb,
        config,
        seed=seed,
        include_audits=include_audits,
    )
    verifier = make_production_constraint_family_verifier(inputs)
    production_projection, family_projection = production_constraint_family_cache_projections(inputs)
    effective_limits = limits or RestorationLimits()

    # The prepared instance is passed through the existing real-board
    # boundary so parsing, warm-start validation, frontier persistence, and
    # fresh-model execution remain in one orchestration path.
    return run_real_board_constraint_family_campaign(
        inputs.input_pcb,
        families=inputs.families,
        probes=probes,
        planner=planner,
        production_kwargs=inputs.production_kwargs,
        limits=effective_limits,
        warm_start_timeout_s=warm_start_timeout_s,
        frontier_path=frontier_path,
        solver=solver,
        verify=verifier,
        prepare=lambda _path, **_kwargs: inputs.stripped_instance,
        cache_production_options=production_projection,
        cache_family_options=family_projection,
    )


# The longer name is the explicit production-board API; this alias keeps the
# experiment vocabulary consistent with the real-board module.
run_production_board_constraint_family_campaign = run_production_constraint_family_real_board_campaign


__all__ = [
    "ProductionCreepageVerification",
    "ProductionConstraintFamilyInputs",
    "production_constraint_family_cache_projections",
    "make_production_constraint_family_verifier",
    "build_production_creepage_verifier",
    "prepare_production_constraint_family_inputs",
    "run_production_constraint_family_campaign",
    "run_production_constraint_family_real_board_campaign",
    "run_production_board_constraint_family_campaign",
]
