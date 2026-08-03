"""Full-board DRC oracle differential (R11).

Every committed placement is measured by two independent engines on the
*same written board artifact*:

- the placer's internal model: ``temper_drc_rs.run_drc()`` on the
  K1-schema board dict built from the parsed ``.kicad_pcb``
  (``DRCOracle._build_board_dict_from_parsed_pcb`` — the parsed-PCB path
  ``scripts/ci_closure_test.py`` already uses), and
- real ``kicad-cli`` DRC via ``temper_placer.validation._drc_api.run_drc``
  (which always passes ``--all-track-errors``; bare ``kicad-cli`` without
  it is not reproducible, see ``_drc_api.py``'s own comment).

Violation records from both engines are normalized to a common shape
(rule class, severity, component pair, location), matched across engines,
and the per-class count delta ``kicad_count - internal_count`` is compared
against a measured tolerance band. A delta beyond its band fails the run.

Origin: R11 of docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md,
implemented per docs/plans/2026-08-02-008-feat-full-board-drc-oracle-plan.md
(U1 harness, U2 mapping + bands, U3 gate wiring).

Incident class this exists for: ``CourtyardCheckStage`` reported zero
courtyard collisions while real ``kicad-cli`` DRC found 43 on the
identical export (docs/solutions/logic-errors/
courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md) through
two stacked silent-no-op bugs. A differential that compares the model
against reality on every committed placement makes that class fail at
commit time instead of when a human reads closely.

Band provenance (per docs/evidence/2026-08-02-validation-portfolio-review.md
fix #1): tolerance bands are derived from the TWO-engine delta
distribution — both engines run N times on the committed board and the
per-class delta spread is measured — NOT from the ceiling file's
kicad-only ranges. The ceiling file contributes only (a) the
kicad-variance component (``nondeterministic_error_types``) and (b) the
unmodeled-class exclusion list (the classes that stay ceiling-governed).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rule-class mapping
# ---------------------------------------------------------------------------
# Canonical rule classes group one or more kicad-cli types onto the internal
# check(s) that model them.  ``band`` is the measured upper tolerance on
# ``delta = kicad_count - internal_count`` (see DELTA_BANDS below); 0 means
# "the internal model must never under-report reality" (observed delta max
# was negative on the committed board, so any positive delta is divergence).
# The mapping was confirmed at implementation against the committed board's
# measured types (plan U2 step 1 + assumption).

INTERNAL_CHECK_TO_CLASS: dict[str, str] = {
    "drc_courtyard": "courtyard",
    "drc_clearance": "clearance",
    "drc_component_overlap": "shorting_items",
    "drc_zone_containment": "copper_edge_clearance",
}

KICAD_TYPE_TO_CLASS: dict[str, str] = {
    "courtyards_overlap": "courtyard",
    "pth_inside_courtyard": "courtyard",
    "clearance": "clearance",
    "shorting_items": "shorting_items",
    "copper_edge_clearance": "copper_edge_clearance",
}

# Every kicad-cli type the temper board emits that the internal model does
# NOT model, with an attributed cause.  Mirrors the ceiling file's
# "debt, not budget" discipline (KTD4): exclusions are named, never silent.
# Governed by the existing ceiling ratchet (power_pcb_dataset/drc_ceiling.json).
EXCLUDED_KICAD_TYPES: dict[str, str] = {
    # track/via/zone classes the internal component-only model cannot see
    "tracks_crossing": "not modeled by the internal engine (track geometry); governed by the ceiling ratchet",
    "via_diameter": "not modeled by the internal engine (via geometry); governed by the ceiling ratchet",
    "drill_out_of_range": "not modeled by the internal engine (drill geometry); governed by the ceiling ratchet",
    "hole_clearance": "not modeled by the internal engine (hole geometry); governed by the ceiling ratchet",
    "hole_to_hole": "not modeled by the internal engine (hole geometry); governed by the ceiling ratchet",
    "annular_width": "not modeled by the internal engine (pad/via geometry); governed by the ceiling ratchet",
    "solder_mask_bridge": "not modeled by the internal engine (mask geometry); governed by the ceiling ratchet",
    # creepage: excluded at implementation, per the plan's own confirmation
    # clause ("mapping confirmed against the committed board's measured
    # types").  Bare _drc_api.run_drc — the differential's kicad path, per
    # the ceiling convention — does not emit creepage: the ceiling's own
    # 32 is measured via ci_check_drc.py's DRU-regenerating invocation (the
    # ceiling file's measured_via documents this), and the internal
    # safety_creepage check is vacuous on the parsed-PCB path (it needs
    # isolation-barrier constraints the minimal constraints dict does not
    # carry).  Neither engine sees it on this path, so it is not a
    # differential class; the ceiling ratchet remains its governor.
    "creepage": "not emitted by bare _drc_api.run_drc (ceiling's count is DRU-path-only); "
    "internal safety_creepage vacuous on the parsed-PCB path; governed by the ceiling ratchet",
    # warning classes without an internal counterpart
    "holes_co_located": "not modeled by the internal engine (hole geometry); governed by the ceiling ratchet",
    "lib_footprint_issues": "library-state class, not placement geometry; governed by the ceiling ratchet",
    "lib_footprint_mismatch": "library-state class, not placement geometry; governed by the ceiling ratchet",
    "missing_courtyard": "footprint-authoring class, not placement geometry; governed by the ceiling ratchet",
    "silk_edge_clearance": "silkscreen cosmetics, not placement geometry; governed by the ceiling ratchet",
    "silk_over_copper": "silkscreen cosmetics, not placement geometry; governed by the ceiling ratchet",
    "silk_overlap": "silkscreen cosmetics, not placement geometry; governed by the ceiling ratchet",
    "track_dangling": "routing-completeness class, not placement geometry; governed by the ceiling ratchet",
    "via_dangling": "routing-completeness class, not placement geometry; governed by the ceiling ratchet",
}

# ---------------------------------------------------------------------------
# Measured per-class tolerance bands
# ---------------------------------------------------------------------------
# Derived from the two-engine delta distribution: both engines run N samples
# on the committed board (pcb/temper.kicad_pcb at the measured commit) and
# the per-class delta (kicad_count - internal_count) spread is recorded.
# Band convention (same spirit as the ceiling file's max+1 headroom):
#     band = max(observed_max_delta + 1, 0)
# The floor at 0 exists because a delta can be negative (the internal bbox
# model over-reports some classes relative to real courtyards); a negative
# observed max would otherwise produce a negative band.  A floor of 0 means
# "model must not under-report reality at all" for such classes — which is
# exactly the incident class (model says zero, real DRC says N).
#
# Measurement record: measured 2026-08-02 via
# ``measure_delta_bands(pcb/temper.kicad_pcb, n_samples=120)`` on the
# committed board at the plan's base commit (validation/p1-execution,
# d3e99b153).  Internal counts are fully deterministic (pure computation on
# the parsed board dict); kicad-cli 10.0.4 with --all-track-errors.  The
# per-class delta spread therefore equals kicad's run-to-run spread, which
# for clearance reproduces the ceiling file's documented 499-501 range and
# is single-valued for every other class (all 120 samples).  creepage is
# deliberately NOT a mapped class: bare _drc_api.run_drc does not emit it
# (see EXCLUDED_KICAD_TYPES), so including it would make the differential's
# kicad side depend on whether pcb/temper.kicad_dru happens to exist on
# disk (ci_check_drc regenerates it; a clean checkout does not) — the
# ambient-state hazard this harness exists to be immune to.
DELTA_BANDS: dict[str, dict[str, Any]] = {
    "courtyard": {
        "internal_count": 34,
        "kicad_observed": [23],
        "observed_min": -11,
        "observed_max": -11,
        "band": 0,
        "samples": 120,
        "note": "kicad courtyard class = courtyards_overlap (14) + pth_inside_courtyard "
        "(9) = 23, all 120 samples. Internal drc_courtyard (bbox model) over-reports "
        "vs real courtyards (34 vs 23), so the delta is negative and the band is "
        "floored at 0: any under-report (kicad > internal) fails. This is the "
        "incident class band.",
    },
    "clearance": {
        "internal_count": 35,
        "kicad_observed": [499, 500, 501],
        "observed_min": 464,
        "observed_max": 466,
        "band": 467,
        "samples": 120,
        "note": "kicad clearance varies 499-501 (the ceiling file's one "
        "nondeterministic category, matching its documented range exactly); delta "
        "spread 464-466. Band = max+1 headroom per the ceiling convention. The "
        "internal component-only model cannot see track/via/zone clearance "
        "violations, so the delta is large but stable; a model that silently drops "
        "below 35 (or kicad that rises past 501) breaks the band.",
    },
    "shorting_items": {
        "internal_count": 32,
        "kicad_observed": [118],
        "observed_min": 86,
        "observed_max": 86,
        "band": 87,
        "samples": 120,
        "note": "Deterministic at 118 on all 120 samples (matches the ceiling "
        "record). Band = max+1 headroom.",
    },
    "copper_edge_clearance": {
        "internal_count": 0,
        "kicad_observed": [15],
        "observed_min": 15,
        "observed_max": 15,
        "band": 16,
        "samples": 120,
        "note": "Internal drc_zone_containment is vacuous on the parsed-PCB path "
        "(no zones in the minimal constraints dict), so the delta is the full "
        "kicad count. The band absorbs the constant and the gate catches "
        "copper_edge_clearance rising above 16.",
    },
}

# Location tolerance for record matching (mm).  kicad reports per-item pad
# positions while the internal engine reports pair midpoints, so exact
# equality is the wrong test; a generous tolerance still discriminates the
# D3/C4-style pair because component pairs are matched first.
LOCATION_TOLERANCE_MM = 5.0

# Internal constraints dict for the parsed-PCB path.  Missing keys default
# to "no constraint" semantics in temper_drc_rs's serde ConstraintSet; the
# internal clearance check falls back to the net_class_rules already carried
# by the board dict (see drc_oracle._build_board_dict_from_parsed_pcb).
def _build_constraints_dict(parsed: Any) -> dict[str, Any]:
    """Build the minimal K1-schema constraints dict for a ParsedPCB.

    Uses the parsed design rules' board dimensions; clearances come from the
    board dict's ``net_class_rules`` via the Rust engine's fallback path.
    """
    return {
        "clearances": [],
        "zones": [],
        "critical_loops": [],
        "noise_domains": [],
        "isolation_barriers": [],
        "thermal_properties": [],
        "matched_length_groups": [],
        "snubber_requirements": [],
        "bleed_resistor": None,
        "skin_effect_derating": None,
        "hv_clearance_mm": 10.0,
        "board_width": float(parsed.board.width),
        "board_height": float(parsed.board.height),
    }


@dataclass(frozen=True)
class ViolationRecord:
    """One normalized violation from either engine.

    Attributes:
        rule_class: Canonical class name (``courtyard``, ``clearance``,
            ``shorting_items``, ``copper_edge_clearance``), or ``None`` for
            an excluded/unmapped type.
        severity: ``"error"`` or ``"warning"``.
        component_pair: frozenset of the two component refs involved, or
            ``None`` when no single owning pair exists (e.g. via items).
        location: (x, y) in mm, or None.
        kicad_type: original kicad-cli ``type`` string (empty for internal).
    """

    rule_class: str | None
    severity: str
    component_pair: frozenset[str] | None
    location: tuple[float, float] | None
    kicad_type: str = ""


def _pair_from_items(items: list[Any]) -> frozenset[str] | None:
    """Build an order-insensitive component pair from an affected-items list.

    kicad-cli reports up to two owning refs per violation; the internal
    engine reports two affected_items for pairwise checks.  Records owned
    by a single ref (e.g. intra-component) or by none (vias, polygons)
    yield ``None``.
    """
    refs = [str(i) for i in items if i is not None]
    if len(refs) >= 2:
        return frozenset(refs[:2])
    return None


def _location_from_dict(location: Any) -> tuple[float, float] | None:
    if not isinstance(location, dict):
        return None
    x = location.get("x")
    y = location.get("y")
    if x is None or y is None:
        return None
    try:
        return (float(x), float(y))
    except (TypeError, ValueError):
        return None


def normalize_internal_violation(violation: dict[str, Any]) -> ViolationRecord:
    """Normalize one ``temper_drc_rs`` violation dict to a ViolationRecord."""
    check_name = violation.get("check_name", "")
    rule_class = INTERNAL_CHECK_TO_CLASS.get(check_name)
    return ViolationRecord(
        rule_class=rule_class,
        severity=str(violation.get("severity", "ERROR")).lower(),
        component_pair=_pair_from_items(violation.get("affected_items", [])),
        location=_location_from_dict(violation.get("location")),
    )


def normalize_kicad_violation(
    rule: str,
    severity: str,
    components: list[str],
    location: tuple[float, float],
) -> ViolationRecord:
    """Normalize one kicad-cli violation (from _drc_api.DrcError/DrcWarning)
    to a ViolationRecord."""
    return ViolationRecord(
        rule_class=KICAD_TYPE_TO_CLASS.get(rule),
        severity=severity,
        component_pair=_pair_from_items(components),
        location=location,
        kicad_type=rule,
    )


def run_internal_engine(pcb_path: Path) -> list[ViolationRecord]:
    """Run the placer's internal DRC model on a written board artifact.

    Parses the ``.kicad_pcb`` (the parsed-PCB path, not a synthetic
    export — KTD3), builds the K1-schema board dict via
    ``DRCOracle._build_board_dict_from_parsed_pcb``, and runs the full
    ``temper_drc_rs`` registry.

    Raises:
        ImportError: If ``temper_drc_rs`` is not installed.
    """
    import temper_drc_rs  # type: ignore[import-untyped]

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.validation.drc_oracle import DRCOracle

    parsed = parse_kicad_pcb_v6(pcb_path)
    board_dict = DRCOracle._build_board_dict_from_parsed_pcb(parsed)
    constraints_dict = _build_constraints_dict(parsed)
    violations = temper_drc_rs.run_drc(board_dict, constraints_dict)
    return [normalize_internal_violation(v) for v in violations]


def run_kicad_engine(pcb_path: Path) -> list[ViolationRecord]:
    """Run real kicad-cli DRC on the same artifact via
    ``temper_placer.validation._drc_api.run_drc`` (--all-track-errors).

    Raises:
        DrcRunnerError: If kicad-cli is unavailable or DRC fails.
        FileNotFoundError: If the PCB file does not exist.
    """
    from temper_placer.validation._drc_api import run_drc

    result = run_drc(pcb_path)
    records: list[ViolationRecord] = []
    for err in result.errors:
        records.append(normalize_kicad_violation(err.rule, err.severity, err.components, err.location))
    for warn in result.warnings:
        records.append(
            normalize_kicad_violation(warn.rule, warn.severity, warn.components, warn.location)
        )
    return records


def match_records(
    kicad_records: list[ViolationRecord],
    internal_records: list[ViolationRecord],
    location_tolerance_mm: float = LOCATION_TOLERANCE_MM,
) -> tuple[int, list[ViolationRecord], list[ViolationRecord]]:
    """Greedily match kicad records to internal records.

    A kicad record matches an internal record when both share a mapped
    rule class and component pair and their locations are within
    ``location_tolerance_mm``.  Returns (matched_count, unmatched_kicad,
    unmatched_internal).  Matching is diagnostic — the gate verdict is the
    count delta — but the matched/unmatched split is what makes the
    report useful (plan KTD1).
    """
    matched = 0
    unmatched_kicad: list[ViolationRecord] = []
    used_internal: set[int] = set()

    # Index internal records by (rule_class, pair) for O(1) candidate lookup.
    by_key: dict[tuple[str | None, frozenset[str] | None], list[tuple[int, ViolationRecord]]] = {}
    for idx, rec in enumerate(internal_records):
        by_key.setdefault((rec.rule_class, rec.component_pair), []).append((idx, rec))

    for kicad_rec in kicad_records:
        key = (kicad_rec.rule_class, kicad_rec.component_pair)
        candidates = by_key.get(key, [])
        chosen: int | None = None
        for idx, internal_rec in candidates:
            if idx in used_internal:
                continue
            if _locations_within(
                kicad_rec.location, internal_rec.location, location_tolerance_mm
            ):
                chosen = idx
                break
        if chosen is not None:
            used_internal.add(chosen)
            matched += 1
        else:
            unmatched_kicad.append(kicad_rec)

    unmatched_internal = [
        rec for idx, rec in enumerate(internal_records) if idx not in used_internal
    ]
    return matched, unmatched_kicad, unmatched_internal


def _locations_within(
    a: tuple[float, float] | None,
    b: tuple[float, float] | None,
    tolerance_mm: float,
) -> bool:
    if a is None or b is None:
        # Location-less records can still match on (class, pair).
        return True
    return abs(a[0] - b[0]) <= tolerance_mm and abs(a[1] - b[1]) <= tolerance_mm


@dataclass
class ClassDelta:
    """Per-class differential outcome.

    Attributes:
        rule_class: Canonical class name.
        internal_count: Mapped violations reported by the internal engine.
        kicad_count: Mapped violations reported by kicad-cli.
        delta: ``kicad_count - internal_count``.
        band: Measured upper tolerance on delta.
        within_band: ``delta <= band``.
        matched_records: kicad records matched to an internal record.
        unmatched_kicad: kicad records with no matching internal record.
        unmatched_internal: internal records with no matching kicad record.
    """

    rule_class: str
    internal_count: int
    kicad_count: int
    delta: int
    band: int
    within_band: bool
    matched_records: int = 0
    unmatched_kicad: int = 0
    unmatched_internal: int = 0


@dataclass
class DifferentialVerdict:
    """Verdict of a full-board differential run.

    ``skipped`` is True when an engine was unavailable; ``skip_reason``
    carries the cause.  A skipped run is never a pass (plan U1 step 4).
    """

    passed: bool
    skipped: bool = False
    skip_reason: str | None = None
    per_class: list[ClassDelta] = field(default_factory=list)
    excluded_types_seen: list[str] = field(default_factory=list)


def build_verdict(
    kicad_records: list[ViolationRecord],
    internal_records: list[ViolationRecord],
    delta_bands: dict[str, dict[str, Any]] | None = None,
    location_tolerance_mm: float = LOCATION_TOLERANCE_MM,
) -> DifferentialVerdict:
    """Compute the differential verdict from both engines' records.

    Counts mapped violations per canonical class, matches records across
    engines, and compares each class's delta (kicad - internal) against its
    band.  Excluded kicad types are ignored by the verdict and reported in
    ``excluded_types_seen`` (plan U2 test 5).
    """
    bands = delta_bands if delta_bands is not None else DELTA_BANDS

    internal_by_class = Counter(r.rule_class for r in internal_records if r.rule_class)
    kicad_by_class = Counter(r.rule_class for r in kicad_records if r.rule_class)

    excluded_seen = sorted(
        {r.kicad_type for r in kicad_records if r.kicad_type in EXCLUDED_KICAD_TYPES}
    )

    per_class: list[ClassDelta] = []
    for rule_class in sorted(bands.keys()):
        internal_count = int(internal_by_class.get(rule_class, 0))
        kicad_count = int(kicad_by_class.get(rule_class, 0))
        delta = kicad_count - internal_count
        band = int(bands[rule_class]["band"])
        matched, unmatched_kicad, unmatched_internal = match_records(
            [r for r in kicad_records if r.rule_class == rule_class],
            [r for r in internal_records if r.rule_class == rule_class],
            location_tolerance_mm=location_tolerance_mm,
        )
        per_class.append(
            ClassDelta(
                rule_class=rule_class,
                internal_count=internal_count,
                kicad_count=kicad_count,
                delta=delta,
                band=band,
                within_band=delta <= band,
                matched_records=matched,
                unmatched_kicad=len(unmatched_kicad),
                unmatched_internal=len(unmatched_internal),
            )
        )

    passed = all(cd.within_band for cd in per_class)
    return DifferentialVerdict(
        passed=passed,
        per_class=per_class,
        excluded_types_seen=excluded_seen,
    )


def run_differential(
    pcb_path: Path | str,
    delta_bands: dict[str, dict[str, Any]] | None = None,
    location_tolerance_mm: float = LOCATION_TOLERANCE_MM,
) -> DifferentialVerdict:
    """Run both DRC engines on one board artifact and compare per class.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` to measure (both engines run
            on this same written artifact — KTD3).
        delta_bands: Optional per-class band table (defaults to the
            committed ``DELTA_BANDS``).
        location_tolerance_mm: Location match tolerance for record pairing.

    Returns:
        DifferentialVerdict.  Engine unavailability yields a SKIPPED verdict
        with the cause — never a silent pass (plan U1 step 4).

    Raises:
        FileNotFoundError: If the PCB file does not exist.
    """
    pcb_path = Path(pcb_path)
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    from temper_placer.validation._drc_api import DrcRunnerError

    try:
        kicad_records = run_kicad_engine(pcb_path)
    except DrcRunnerError as exc:
        # A missing kicad-cli binary (or a crashed DRC run) is an
        # unavailable measurement, never a pass: SKIPPED-with-cause.
        return DifferentialVerdict(passed=False, skipped=True, skip_reason=str(exc))

    try:
        internal_records = run_internal_engine(pcb_path)
    except ImportError as exc:
        return DifferentialVerdict(
            passed=False,
            skipped=True,
            skip_reason=f"internal engine unavailable: {exc}",
        )

    return build_verdict(
        kicad_records,
        internal_records,
        delta_bands=delta_bands,
        location_tolerance_mm=location_tolerance_mm,
    )


def is_kicad_cli_unavailable() -> bool:
    """Return True when the kicad-cli binary cannot be found on PATH.

    Exists so the harness can produce a SKIPPED-with-cause verdict for
    oracle unavailability (plan U1 step 4) without calling into
    ``_drc_api`` twice.
    """
    from temper_placer.validation._drc_api import is_kicad_cli_available

    return not is_kicad_cli_available()


def measure_delta_bands(
    pcb_path: Path | str,
    n_samples: int = 120,
    delta_bands: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Measure the two-engine delta distribution for a board (band source).

    Runs BOTH engines ``n_samples`` times on the same artifact and records
    the per-class delta (kicad - internal) spread.  This is the measurement
    the review fix requires bands to come from (docs/evidence/
    2026-08-02-validation-portfolio-review.md fix #1): not the ceiling
    file's kicad-only ranges, but the actual two-engine delta distribution.

    Returns a ``DELTA_BANDS``-shaped table.  The internal engine is
    deterministic (pure computation on the parsed board dict), so its count
    is computed once and reused; the delta spread is kicad's run-to-run
    spread around a constant.  ``delta_bands`` may be passed in to seed
    internal counts from a prior parse (e.g. the committed table) and keep
    the band convention (``max(observed_max + 1, 0)``) stable.

    Raises:
        FileNotFoundError: If the PCB file does not exist.
        DrcRunnerError: If kicad-cli is unavailable (propagated by
            ``run_drc``).
    """
    from temper_placer.validation._drc_api import run_drc

    pcb_path = Path(pcb_path)
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    # Internal counts are deterministic: compute once, reuse across samples.
    internal_records = run_internal_engine(pcb_path)
    internal_by_class = Counter(r.rule_class for r in internal_records if r.rule_class)

    bands = delta_bands if delta_bands is not None else DELTA_BANDS
    deltas: dict[str, list[int]] = {cls: [] for cls in bands}
    kicad_observed: dict[str, list[int]] = {cls: [] for cls in bands}

    for _ in range(n_samples):
        result = run_drc(pcb_path)
        kicad_by_class = Counter()
        for err in result.errors:
            cls = KICAD_TYPE_TO_CLASS.get(err.rule)
            if cls:
                kicad_by_class[cls] += 1
        for warn in result.warnings:
            cls = KICAD_TYPE_TO_CLASS.get(warn.rule)
            if cls:
                kicad_by_class[cls] += 1
        for cls in bands:
            kicad_count = int(kicad_by_class.get(cls, 0))
            internal_count = int(internal_by_class.get(cls, 0))
            deltas[cls].append(kicad_count - internal_count)
            kicad_observed[cls].append(kicad_count)

    out: dict[str, dict[str, Any]] = {}
    for cls, band_spec in bands.items():
        delta_vals = deltas[cls]
        out[cls] = {
            "internal_count": int(internal_by_class.get(cls, 0)),
            "kicad_observed": sorted(set(kicad_observed[cls])),
            "observed_min": min(delta_vals),
            "observed_max": max(delta_vals),
            "band": max(max(delta_vals) + 1, 0),
            "samples": n_samples,
            "note": band_spec.get("note", ""),
        }
    return out
