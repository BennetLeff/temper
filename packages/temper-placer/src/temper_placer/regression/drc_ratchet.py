"""DRC ratchet CI gate.

Loads drc_ceiling.json, runs DRC on target boards, and enforces
a monotonically-non-increasing ceiling on DRC violation counts.

Wave 4 Phase 4 (regression slice): the ceiling-COMPARISON compute — aggregate
deltas, per-type category failure detection (implicit-zero ceiling), the
pass/fail message composition, and ``detect_ceiling_raise`` — moved to the
Rust kernels ``temper_drc_rs.ratchet_check`` /
``temper_drc_rs.detect_ceiling_raise`` (packages/temper-drc-rs/src/
drc_ratchet.rs). The DRC backends (rust-engine board-dict building,
kicad-cli subprocess), the ceiling-file loading, and the result dataclasses
stay Python — I/O and marshalling. The ratchet CONSTANTS (drc_ceiling.json,
the #575 gate) are untouched: this migration only ports the comparison
logic, so the ratchet reads exactly what it read before. Design boundaries
are argued in ``packages/temper-drc-rs/VERIFICATION.md``.

R27 (the machine-checked monotone ceiling contract, #611) composes on top of
the migration, keeping the three-way shape R27's gate relies on:
``find_ceiling_raises`` stays the Python contract-layer enumeration of "what
raised" (the single enumeration R27's ``validate_raise_evidence`` consumes),
and ``detect_ceiling_raise`` runs the SAME raise rules in the Rust kernel
``temper_drc_rs.detect_ceiling_raise`` — a verbatim port of the
pre-migration raise detector, kept bit-identical to the Python enumeration
by the differential suite (test_drc_ratchet_rust_differential.py).
``validate_raise_evidence`` enforces the measurement-evidence contract (a NEW
non-empty ``_march`` cause entry plus a fresh measured-live provenance
record); ``scripts/check_drc_ceiling_approval.py`` runs the three-stage gate
enumerate -> detect -> validate. The pass-2 fail-loudly marshal
(``CeilingMarshalError``) guards every ceiling/count value on BOTH paths —
the kernel boundary in ``detect_ceiling_raise``/``_check_board`` AND the
enumeration reads in ``find_ceiling_raises`` that ``validate_raise_evidence``
inherits — so a non-int (e.g. float ``100.5``) never gets silently truncated
into an invisible raise (the #575 fail-open class).

Supports two backends:
  - ``rust`` (default): uses ``temper_drc_rs.run_drc()`` with the
    parsed-PCB-via-KiCad-parser path.
  - ``kicad-cli``: uses the KiCad CLI DRC via
    ``temper_placer.validation._drc_api.run_drc()``.

When the Rust backend is selected but ``temper_drc_rs`` is not
installed, the check fails with a clear error message.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_RS = None


def _tdrc():
    global _RS
    if _RS is None:
        import temper_drc_rs  # type: ignore[import-untyped]

        _RS = temper_drc_rs
    return _RS


_VERIFY_COMMITS_EXIST = None

# This file's own location fixes where scripts/check_evidence_provenance.py
# lives on disk: packages/temper-placer/src/temper_placer/regression/ is
# always four directories below packages/, which is always one directory
# below the repo root. Deliberately NOT derived from the repo_root a caller
# passes to _verify_commits_exist -- that repo_root names the repository
# whose *commits* are being checked (in tests, a throwaway synthetic repo
# that has no scripts/ directory of its own), which is a different question
# from "where is this module's own sibling tooling installed".
_REPO_ROOT_FOR_TOOLING = Path(__file__).resolve().parents[5]


def _verify_commits_exist(shas: set[str], repo_root: Path) -> dict[str, bool]:
    """Lazily load and call ``check_evidence_provenance.verify_commits_exist``.

    Reused, not reimplemented: real commit-existence resolution (a single
    ``git cat-file --batch-check`` subprocess) already exists in
    ``scripts/check_evidence_provenance.py`` for exactly this purpose.
    ``check_evidence_provenance.py`` is a ``scripts/`` sibling script, not an
    installed package, so it is loaded from its file path (relative to this
    module's own location -- see ``_REPO_ROOT_FOR_TOOLING`` -- rather than
    assuming ``scripts/`` is on ``sys.path``, since this module is a library
    module that may be imported from contexts where it is not).

    *repo_root* is passed straight through to ``verify_commits_exist`` as
    the repository the SHAs are checked against (git's ``cwd``) -- it may
    legitimately differ from where this module's own tooling lives, e.g. a
    test's throwaway synthetic repo.

    Raises ``RuntimeError`` (git unavailable, or a shallow clone where
    "does not resolve" would be true of nearly every legitimate historical
    SHA) exactly as ``verify_commits_exist`` does -- a fail-closed TOOL
    ERROR, propagated to the caller rather than swallowed.
    """
    global _VERIFY_COMMITS_EXIST
    if _VERIFY_COMMITS_EXIST is None:
        import importlib.util

        script_path = _REPO_ROOT_FOR_TOOLING / "scripts" / "check_evidence_provenance.py"
        spec = importlib.util.spec_from_file_location(
            "temper_placer_drc_ratchet._check_evidence_provenance", script_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"cannot load {script_path} to verify commit existence -- "
                "check_evidence_provenance.py is missing or not importable"
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _VERIFY_COMMITS_EXIST = module.verify_commits_exist
    return _VERIFY_COMMITS_EXIST(shas, repo_root)


class CeilingMarshalError(ValueError):
    """A ceiling/count value the #575 gate cannot compare safely.

    The ratchet data model is int-only (``DrcCeilingEntry.error_ceiling``/
    ``warning_ceiling`` are typed ``int``; ``drc_ceiling.json`` records
    integer DRC counts measured by ``run_drc``). The pre-fix marshal coerced
    every value with ``int()``, which silently truncated a float-valued
    ceiling (``100.5`` -> ``100``): a raise ``100 -> 100.5`` became invisible
    to ``temper_drc_rs.detect_ceiling_raise``, so the shim returned None and
    the #575 approval gate failed OPEN. Any value that is not a genuine int
    is a data-model violation and fails LOUDLY here instead -- a fail-closed
    deviation from the oracle's raw compare, documented in
    ``packages/temper-drc-rs/VERIFICATION.md``.
    """


def _marshal_ceiling_int(value: object, field: str, board_id: str) -> int:
    """Coerce one ceiling/count value to int, failing loudly on anything that
    is not a genuine int (bool excluded).

    Raises:
        CeilingMarshalError: if ``value`` is not an ``int`` (a float --
            integral or fractional -- a string, None, ...). Naming the field
            and value so the bad record is identifiable without digging into
            a stack trace.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise CeilingMarshalError(
            f"non-integer {field}={value!r} on board {board_id!r}: the #575 "
            "ceiling gate requires integer-valued ceilings/counts (an int() "
            "coercion could hide a raise by truncating it)"
        )
    return value


_READ_CHUNK = 1 << 20  # 1 MiB
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{40}")
_SAMPLE_COUNT_RE = re.compile(r"(\d+)\s*samples?\b", re.IGNORECASE)


def _sha256_file(path: Path) -> str:
    """Content hash (hex sha256) of *path* -- mirrors
    ``scripts/_lib/measurement_provenance.py::sha256_file``, kept local so
    the temper-placer package never depends on repo-internal ``scripts/``.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _provenance_sample_count(prov: dict[str, Any]) -> int | None:
    """Sample count a provenance record's measurement used, or None.

    Structured ``provenance.sample_count`` field first; legacy records
    carry the count in ``measured_via`` prose (e.g. "(120 samples; ...)")
    and are parsed from that. Mirrors
    ``scripts/_lib/measurement_provenance.py::get_sample_count``, kept
    local for the same package-boundary reason as ``_sha256_file``.
    """
    raw = prov.get("sample_count")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    measured_via = prov.get("measured_via")
    if isinstance(measured_via, str):
        match = _SAMPLE_COUNT_RE.search(measured_via)
        if match:
            return int(match.group(1))
    return None


@dataclass
class DrcCeilingEntry:
    """A single board entry in the DRC ceiling file.

    ``tool_versions`` and ``category_source`` are read from the file's
    ``provenance`` block and top level respectively -- pure metadata, never
    ceiling values -- and exist so the ratchet can (1) tell the reader which
    engine produced ``violations_by_type``/``warnings_by_type`` (currently
    always kicad-cli; see ``_check_board``'s kicad-cli branch, the only one
    that ever populates a per-type breakdown) and (2) detect when the
    running ``kicad-cli`` differs from the one the ceiling was measured
    with, rather than silently comparing against a different engine.

    ``nondeterministic_error_types`` is read verbatim from the file's own
    top-level ``nondeterministic_error_types`` block (e.g. ``{"clearance":
    {"observed": [377, 378], "samples": 120, "note": "..."}}``) -- the
    multi-sample characterization the file's own ``_march`` protocol
    already requires (>= 120 samples) for every category whose count moves
    on a byte-identical board. It exists so ``check_noise_headroom`` can
    compare a category's *measured run-to-run spread* against its *ceiling
    headroom* without re-deriving either number: both are already
    committed, human-reviewed data, never re-measured by this guard.
    """

    board_id: str
    path: str
    error_ceiling: int
    warning_ceiling: int
    violations_by_type: dict[str, int] = field(default_factory=dict)
    warnings_by_type: dict[str, int] = field(default_factory=dict)
    tool_versions: dict[str, str] = field(default_factory=dict)
    category_source: str | None = None
    nondeterministic_error_types: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DrcCategoryFailure:
    """One violation-type category that exceeded its ceiling.

    ``is_new`` distinguishes a category absent from ``violations_by_type``
    (or, for warnings, ``warnings_by_type``) entirely (an implicit ceiling
    of 0, by design -- see drc_ceiling.json's ``_march`` notes) from one
    that is present in the file but regressed past its recorded ceiling.
    Both are real ceiling violations, but a brand-new violation class means
    the board grew a defect *type* the ratchet has never seen before, which
    is a materially different signal from "more of a kind we already
    track" and must not be folded into the same bucket silently.

    ``kind`` distinguishes an error-category failure from a warning-category
    failure -- they come from separate exhaustive records
    (``violations_by_type`` vs. ``warnings_by_type``) and must not be
    conflated when reporting which dimension regressed.

    ``source`` names the DRC engine that produced this category's count
    (currently always ``"kicad-cli"`` at runtime -- the ``rust`` backend
    never supplies a per-type breakdown, see ``_check_board``). This exists
    because ``creepage``, for example, is a real category the Rust engine
    (``temper_drc_rs``) reports under its own ``check_name``, but it is not
    a KiCad DRC violation type at all -- bare kicad-cli never emits it. A
    category list mixing engines without saying which is which lets a
    reader mistake one engine's finding for the other's.
    """

    rule: str
    count: int
    allowed: int
    is_new: bool
    kind: str = "error"
    source: str = "unknown"

    @property
    def delta(self) -> int:
        return self.count - self.allowed


@dataclass
class DrcRatchetResult:
    """Result of a DRC ratchet check.

    A failing result may fail along more than one dimension at once
    (aggregate errors, aggregate warnings, and/or one or more per-type
    categories) -- ``message`` composes all of them into one human-readable
    report. ``category_failures`` and the two ``aggregate_*_delta`` fields
    carry the same information in structured form for callers that want it
    (e.g. a future CI step-summary table) without re-parsing ``message``.
    Existing consumers (``scripts/ci_check_drc.py``, the test suite) only
    read ``.passed``/``.message``/``.exit_code`` and are unaffected by the
    additional fields.
    """

    passed: bool
    board_id: str
    message: str
    exit_code: int = 0
    violation_deltas: dict[str, int] = field(default_factory=dict)
    category_failures: list[DrcCategoryFailure] = field(default_factory=list)
    aggregate_error_delta: int = 0
    aggregate_warning_delta: int = 0
    kicad_cli_version_running: str | None = None
    kicad_cli_version_expected: str | None = None
    kicad_cli_version_mismatch: bool = False
    # Per-type categories whose measured count saturates KiCad's reporting
    # cap (ERROR_LIMIT 199 / EXTENDED_ERROR_LIMIT 499): the ceiling
    # comparison for such a category compares a FLOOR ("true count >= N"),
    # not a count, so a pass there is inconclusive — the true count can
    # exceed the ceiling without the raw number ever crossing it. Values
    # are ``DrcCount.display()`` strings ("199 (CAPPED — true count >=
    # 199)"). Error categories in ``capped_error_categories``, warning
    # categories in ``capped_warning_categories``. Only populated by the
    # kicad-cli backend (the rust backend supplies no per-type breakdown).
    capped_error_categories: dict[str, str] = field(default_factory=dict)
    capped_warning_categories: dict[str, str] = field(default_factory=dict)


@dataclass
class NoiseHeadroomViolation:
    """A nondeterministic category whose ceiling headroom is smaller than
    its own measured run-to-run spread.

    Why this check exists: ``DrcRatchet.check()`` (``_check_board``) runs
    ``run_drc`` exactly ONCE per CI invocation and compares that single
    sample directly against the ceiling. That is only safe if a single
    fresh sample on an unchanged board is guaranteed to land at or below
    the ceiling -- which is true if and only if the ceiling's headroom
    above the historical max (``ceiling - max(observed)``) is at least as
    wide as the measured spread (``max(observed) - min(observed)``) the
    file's own 120-sample protocol already characterized. The ``max + 1``
    convention this file uses throughout gives exactly 1 unit of headroom;
    if a category's own measured spread is wider than 1 (e.g. a category
    that visits 3 distinct values, not 2), a single fresh sample can land
    outside the previously-observed range purely from noise -- a false
    ceiling-exceeded FAIL on a board that did not regress. This dataclass
    is what ``check_noise_headroom`` reports when that invariant does not
    hold; it does not itself re-measure anything.

    2026-08-11 correction -- this was not hypothetical, it was live: every
    ``creepage`` record in ``drc_ceiling.json`` from the #602 K3 swap
    onward (6 consecutive re-measurements, 2026-08-02 through 2026-08-11)
    carried exactly this failure -- a measured spread of 2 (three distinct
    values: 185-187, then 169-171, then 182-184 as the board changed)
    against a mechanically-applied ``max + 1`` ceiling, because every
    re-measurement in that window copied the ``+1`` convention forward
    without re-checking it against ITS OWN invariant above. The convention
    a human (or agent) setting a ceiling for a category newly added to
    ``nondeterministic_error_types`` should actually follow is
    ``max(observed) + spread``, i.e. exactly enough headroom to satisfy
    this dataclass's own ``headroom >= spread`` check -- ``+ 1`` is only
    correct when the measured spread happens to be 1 (true for creepage's
    very first characterization, 199-200, false ever since). Run
    ``check_noise_headroom`` (or ``scripts/ci_check_drc.py``) against the
    candidate ceiling BEFORE committing a re-measurement, rather than
    trusting the arithmetic convention blindly -- the check is cheap
    (no DRC run) and exists precisely to catch this. See
    docs/evidence/2026-08-11-creepage-noise-headroom-guard-fix.md for the
    full incident, the multi-campaign spread measurement, and why the
    fix widens headroom by exactly the measured spread rather than by an
    arbitrary safety buffer.
    """

    board_id: str
    category: str
    observed: list[int]
    samples: int | None
    ceiling: int

    @property
    def spread(self) -> int:
        return max(self.observed) - min(self.observed)

    @property
    def headroom(self) -> int:
        return self.ceiling - max(self.observed)

    @property
    def message(self) -> str:
        samples_desc = f"{self.samples} samples" if self.samples else "an unrecorded sample count"
        return (
            f"{self.board_id}: {self.category!r} has ceiling headroom "
            f"{self.headroom} (ceiling {self.ceiling} - observed max "
            f"{max(self.observed)}) smaller than its own measured "
            f"run-to-run spread {self.spread} (observed {self.observed} "
            f"over {samples_desc}). A single-sample CI run can land above "
            f"the ceiling from noise alone, with no board regression -- "
            f"widen the headroom (or move this category to a "
            f"deterministic engine) before trusting a single sample."
        )


def check_noise_headroom(board_id: str, entry: DrcCeilingEntry) -> list[NoiseHeadroomViolation]:
    """Check every category ``entry`` records as nondeterministic against
    the single-sample-safety invariant: ceiling headroom >= measured
    spread. Returns one ``NoiseHeadroomViolation`` per category that fails
    it (empty list = single-sampling is safe for every recorded category
    on this board, given its own measured noise).

    Reads only already-committed data (``nondeterministic_error_types`` and
    ``violations_by_type``, both loaded by ``DrcRatchet.load()``) -- this
    performs no DRC run of its own, so it costs nothing beyond the JSON
    parse ``check()`` already does. A category with fewer than 2 distinct
    observed values, or with no per-type ceiling recorded at all, is
    skipped: there is no spread to compare (or nothing to compare it to).
    """
    violations: list[NoiseHeadroomViolation] = []
    for category, info in sorted(entry.nondeterministic_error_types.items()):
        observed = info.get("observed")
        if not isinstance(observed, list) or len(observed) < 2:
            continue
        ceiling = entry.violations_by_type.get(category)
        if ceiling is None:
            continue
        samples = info.get("samples")
        violation = NoiseHeadroomViolation(
            board_id=board_id,
            category=category,
            observed=list(observed),
            samples=samples if isinstance(samples, int) else None,
            ceiling=ceiling,
        )
        if violation.headroom < violation.spread:
            violations.append(violation)
    return violations


class DrcRatchet:
    """Enforces DRC ceiling via committed JSON file.

    Args:
        ceiling_path: Path to ``drc_ceiling.json``.
        backend: ``"rust"`` (default) to use the Rust DRC engine via
            ``temper_drc_rs.run_drc()``, or ``"kicad-cli"`` to use
            KiCad's CLI DRC.
    """

    def __init__(self, ceiling_path: Path, backend: str = "rust"):
        self.ceiling_path = Path(ceiling_path)
        self.backend = backend
        self.entries: dict[str, DrcCeilingEntry] = {}

    def load(self) -> None:
        if not self.ceiling_path.exists():
            return

        with open(self.ceiling_path) as f:
            data = json.load(f)

        for entry in data.get("boards", []):
            board_id = entry["board_id"]
            provenance = entry.get("provenance") or {}
            self.entries[board_id] = DrcCeilingEntry(
                board_id=board_id,
                path=entry["path"],
                error_ceiling=entry.get("error_ceiling", 0),
                warning_ceiling=entry.get("warning_ceiling", 0),
                violations_by_type=entry.get("violations_by_type", {}),
                warnings_by_type=entry.get("warnings_by_type", {}),
                tool_versions=provenance.get("tool_versions") or {},
                category_source=entry.get("category_source"),
                nondeterministic_error_types=entry.get("nondeterministic_error_types") or {},
            )

    def check(self, repo_root: Path) -> list[DrcRatchetResult]:
        results: list[DrcRatchetResult] = []

        for board_id, entry in self.entries.items():
            pcb_path = repo_root / entry.path
            result = self._check_board(board_id, pcb_path, entry)
            results.append(result)

        return results

    def check_noise_headroom(self) -> list[NoiseHeadroomViolation]:
        """Run ``check_noise_headroom`` (module-level) over every loaded
        board entry. See that function and ``NoiseHeadroomViolation`` for
        what this guards against.

        Independent of ``check()``/``_check_board``: it needs no PCB file,
        no ``repo_root``, and no DRC run -- it is a pure function of the
        already-loaded ceiling data, so it is safe (and cheap) to call on
        every CI invocation regardless of backend.
        """
        violations: list[NoiseHeadroomViolation] = []
        for board_id, entry in self.entries.items():
            violations.extend(check_noise_headroom(board_id, entry))
        return violations

    def _run_rust_drc(self, pcb_path: Path) -> tuple[int, int]:
        """Run the Rust DRC engine on a PCB file.

        Returns:
            (error_count, warning_count)

        Raises:
            ImportError: If ``temper_drc_rs`` is not installed.
            Exception: On parse/DRC failure.
        """
        import temper_drc_rs

        from temper_placer.core.design_rules import TEMPER_NET_CLASSES
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

        parsed = parse_kicad_pcb_v6(pcb_path)

        # ── Build board_dict ────────────────────────────────────────────
        components = []
        for c in parsed.components:
            x, y = c.initial_position or (0.0, 0.0)
            rotation = float(c.initial_rotation_quadrant * 90) if c.initial_rotation_quadrant is not None else 0.0
            side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
            fp_lower = c.footprint.lower() if c.footprint else ""
            if any(p in fp_lower for p in ("tht", "through", "pin", "dip")):
                package_type = "tht"
            elif "to-247" in fp_lower or "to247" in fp_lower:
                package_type = "to247"
            elif "to-220" in fp_lower or "to220" in fp_lower:
                package_type = "to220"
            elif "bga" in fp_lower:
                package_type = "bga"
            elif "qfn" in fp_lower:
                package_type = "qfn"
            elif "qfp" in fp_lower or "tqfp" in fp_lower:
                package_type = "qfp"
            elif "dpak" in fp_lower or "d2pak" in fp_lower:
                package_type = "dpak"
            else:
                package_type = "smd"

            components.append(
                {
                    "ref": c.ref,
                    "x": x,
                    "y": y,
                    "rot": rotation,
                    "side": side,
                    "width": float(c.width),
                    "height": float(c.height),
                    "net_class": c.net_class,
                    "package_type": package_type,
                    "power_dissipation_w": None,
                    "is_magnetic": False,
                    "is_electrolytic": False,
                    "vent_direction": None,
                    "footprint_polygon": None,
                    "is_mechanical": c.ref.startswith("MH"),
                }
            )

        nets: dict[str, list[str]] = {}
        net_classes: dict[str, str] = {}
        for net in parsed.nets:
            comp_refs = list({ref for ref, _ in net.pins})
            nets[net.name] = comp_refs
            net_classes[net.name] = net.net_class

        # Real per-class rules, from this project's own netclass SSOT
        # (``TEMPER_NET_CLASSES``, core/design_rules.py) -- NOT
        # ``parsed.design_rules.net_classes``, which only ever holds
        # whatever ``(net_class ...)`` blocks are embedded directly in the
        # .kicad_pcb text (a "vestigial" extraction path per
        # ``_parse_nets._extract_design_rules``'s own docstring). Before
        # real net classification landed, every net resolved to "Signal"
        # and that vestigial dict's own "Signal" fallback happened to be
        # enough to keep this working; now that nets carry their real
        # classes (ACMains, HighVoltage, FinePitch, ...), those class names
        # must have real entries here or ``temper_drc_rs.run_drc`` hard-errors
        # (see #1039: an unresolvable net_class_rules entry is a loud
        # failure, not a silent thinnest-rule-set default).
        net_class_rules: dict[str, dict] = {}
        for class_name, rules in TEMPER_NET_CLASSES.items():
            net_class_rules[class_name] = {
                "trace_width_mm": rules.trace_width,
                "clearance_mm": rules.clearance,
                "creepage_mm": rules.creepage_mm,
                "voltage_v": rules.voltage_v,
                "max_current_rating": rules.max_current_rating,
                "safety_category": rules.safety_category,
                "required_layer": rules.required_layer,
                "routing_strategy": rules.routing_strategy,
            }

        board_dict = {
            "board": {
                "width_mm": float(parsed.board.width),
                "height_mm": float(parsed.board.height),
                "margin_mm": 3.0,
            },
            "components": components,
            "nets": nets,
            "net_classes": net_classes,
            "net_class_rules": net_class_rules,
        }

        # ── Build constraints_dict ──────────────────────────────────────
        constraints_dict: dict[str, Any] = {
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

        violations = temper_drc_rs.run_drc(board_dict, constraints_dict)

        errors = sum(
            1 for v in violations if v.get("severity", "").upper() in ("ERROR", "CRITICAL")
        )
        warnings = sum(1 for v in violations if v.get("severity", "").upper() == "WARNING")

        return errors, warnings

    def _check_board(
        self, board_id: str, pcb_path: Path, entry: DrcCeilingEntry
    ) -> DrcRatchetResult:
        if not pcb_path.exists():
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"PCB file not found: {pcb_path}",
                exit_code=1,
            )

        # Per-error-type and per-warning-type counts, when the backend can
        # supply them. None means "this backend cannot break this dimension
        # down", which is distinct from "no violations" (``{}``) and must
        # never be treated as an all-clear.
        current_by_type: dict[str, int] | None = None
        current_warnings_by_type: dict[str, int] | None = None
        # Saturated-at-cap categories, populated only by the kicad-cli
        # backend (which supplies a per-type breakdown): a count at exactly
        # its category's KiCad reporting cap is a FLOOR, not a count (see
        # DrcRatchetResult.capped_error_categories).
        capped_error_categories: dict[str, str] = {}
        capped_warning_categories: dict[str, str] = {}

        try:
            if self.backend == "rust":
                current_errors, current_warnings = self._run_rust_drc(pcb_path)
            elif self.backend == "kicad-cli":
                from temper_placer.validation._drc_api import classify_counts, run_drc

                drc_result = run_drc(pcb_path)
                current_errors = drc_result.error_count
                current_warnings = drc_result.warning_count
                current_by_type = {}
                for err in drc_result.errors:
                    rule = err.rule or "unknown"
                    current_by_type[rule] = current_by_type.get(rule, 0) + 1

                # ``getattr`` (not a direct attribute access) because a
                # result object that cannot supply a warnings breakdown --
                # deliberately -- looks exactly like one that lacks the
                # attribute entirely; both must resolve to None, never to a
                # crash and never to an all-clear ``{}``.
                raw_warnings = getattr(drc_result, "warnings", None)
                if raw_warnings is not None:
                    current_warnings_by_type = {}
                    for warn in raw_warnings:
                        rule = warn.rule or "unknown"
                        current_warnings_by_type[rule] = (
                            current_warnings_by_type.get(rule, 0) + 1
                        )

                # Cap-saturation detection: a per-type count at exactly its
                # category's KiCad reporting cap is a FLOOR, not a count --
                # the true count is >= N, so a ceiling comparison on the raw
                # number is inconclusive (the true count can exceed the
                # ceiling while the capped reading never crosses it).
                # Classify every per-type count through DrcCount (Rust
                # kernel) and surface the saturated ones on the result;
                # the ceiling comparison itself still runs on the raw
                # counts (the pinned kernel contract) -- see
                # DrcRatchetResult.capped_error_categories.
                capped_error_categories = {
                    rule: info.display
                    for rule, info in classify_counts(current_by_type).items()
                    if info.is_capped
                }
                capped_warning_categories = {}
                if current_warnings_by_type is not None:
                    capped_warning_categories = {
                        rule: info.display
                        for rule, info in classify_counts(current_warnings_by_type).items()
                        if info.is_capped
                    }
            else:
                return DrcRatchetResult(
                    passed=False,
                    board_id=board_id,
                    message=f"Unknown DRC backend: {self.backend}",
                    exit_code=1,
                )
        except Exception as e:
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"DRC ({self.backend}) failed: {e}",
                exit_code=1,
            )

        # kicad-cli version pin: the ceiling's provenance records the
        # kicad-cli version it was measured with, but nothing previously
        # enforced that CI (or a local run) uses that same version -- a
        # patch bump changes the DRC engine, which means a red gate could
        # be silently comparing against a different measuring instrument
        # rather than an actual regression. Reported prominently rather
        # than hard-failed: a version bump alone was already shown not to
        # explain the report count on this board (see
        # docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md section 2),
        # so failing the whole gate on any patch mismatch would be its own
        # false positive -- but it must never again pass through unnoted.
        running_kicad_cli_version: str | None = None
        expected_kicad_cli_version: str | None = None
        version_mismatch = False
        if self.backend == "kicad-cli":
            from temper_placer.validation._drc_api import get_kicad_cli_version

            running_kicad_cli_version = get_kicad_cli_version()
            expected_kicad_cli_version = entry.tool_versions.get("kicad-cli")
            version_mismatch = bool(
                running_kicad_cli_version
                and expected_kicad_cli_version
                and running_kicad_cli_version != expected_kicad_cli_version
            )

        # Evaluate every ceiling dimension -- aggregate errors, aggregate
        # warnings, and per-type -- before deciding pass/fail. A failing run
        # must show the complete picture in one shot: returning on the first
        # exceeded dimension (the previous behavior) hid the per-type
        # breakdown -- exactly the categories most worth seeing -- whenever
        # the aggregate itself was also exceeded. See
        # docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md.
        #
        # Wave 4 Phase 4: this comparison + message composition now runs in
        # ``temper_drc_rs.ratchet_check`` (the backend above still supplies
        # the measured counts; the kernel applies the ceiling comparisons and
        # builds the exact messages bit-identically to the pre-migration
        # oracle). ``None`` breakdowns stay None (the "backend cannot break
        # this dimension down" sentinel, distinct from an all-clear ``{}``).
        # The kernel call sits INSIDE a try/except so a missing
        # ``temper_drc_rs`` produces the clean "DRC (...) failed" FAIL (the
        # pre-migration graceful degradation) instead of an unhandled
        # ImportError traceback. Every ceiling/count crossing the i64
        # boundary is int-validated: a float-valued value (e.g. a ``100.5``
        # ceiling in the JSON) fails loudly with ``CeilingMarshalError``
        # rather than being silently truncated by the old ``int()`` coercion
        # (the P1-1 fail-open class).
        try:
            ratchet_dict = _tdrc().ratchet_check(
                board_id=board_id,
                current_errors=_marshal_ceiling_int(
                    current_errors, "current_errors", board_id
                ),
                current_warnings=_marshal_ceiling_int(
                    current_warnings, "current_warnings", board_id
                ),
                error_ceiling=_marshal_ceiling_int(
                    entry.error_ceiling, "error_ceiling", board_id
                ),
                warning_ceiling=_marshal_ceiling_int(
                    entry.warning_ceiling, "warning_ceiling", board_id
                ),
                current_by_type=(
                    list(current_by_type.items())
                    if current_by_type is not None
                    else None
                ),
                allowed_by_type=list(entry.violations_by_type.items()),
                current_warnings_by_type=(
                    list(current_warnings_by_type.items())
                    if current_warnings_by_type is not None
                    else None
                ),
                allowed_warnings_by_type=list(entry.warnings_by_type.items()),
                backend=self.backend,
                version_mismatch=version_mismatch,
                running_version=running_kicad_cli_version,
                expected_version=expected_kicad_cli_version,
            )
        except Exception as e:
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"DRC ({self.backend}) failed: {e}",
                exit_code=1,
            )
        return DrcRatchetResult(
            passed=ratchet_dict["passed"],
            board_id=board_id,
            message=ratchet_dict["message"],
            exit_code=ratchet_dict["exit_code"],
            violation_deltas=ratchet_dict["violation_deltas"],
            category_failures=[
                DrcCategoryFailure(
                    rule=c["rule"],
                    count=c["count"],
                    allowed=c["allowed"],
                    is_new=c["is_new"],
                    kind=c["kind"],
                    source=c["source"],
                )
                for c in ratchet_dict["category_failures"]
            ],
            aggregate_error_delta=ratchet_dict["aggregate_error_delta"],
            aggregate_warning_delta=ratchet_dict["aggregate_warning_delta"],
            kicad_cli_version_running=ratchet_dict["kicad_cli_version_running"],
            kicad_cli_version_expected=ratchet_dict["kicad_cli_version_expected"],
            kicad_cli_version_mismatch=ratchet_dict["kicad_cli_version_mismatch"],
            capped_error_categories=capped_error_categories,
            capped_warning_categories=capped_warning_categories,
        )

    def find_ceiling_raises(
        self, old_ceiling: dict, new_ceiling: dict
    ) -> list[tuple[str, list[str]]]:
        """Return ``(board_id, reasons)`` for every board whose ceiling was
        raised between *old_ceiling* and *new_ceiling*, regardless of
        approval. ``reasons`` is a list of human-readable per-dimension
        deltas ("error_ceiling 1017 -> 1020", "violations_by_type[clearance]
        502 -> 600", ...).

        A raise is any of: the aggregate ``error_ceiling`` increasing, the
        aggregate ``warning_ceiling`` increasing, or any single rule inside
        ``violations_by_type`` (errors) or ``warnings_by_type`` (warnings)
        increasing -- including a rule that didn't exist in the old record
        at all, which is a raise from its implicit ceiling of 0 (the same
        implicit-zero semantics ``_check_board`` enforces at runtime).
        Editing the ceiling *file* to grant a rule more room is exactly as
        much a raise as editing the aggregate number, and must require the
        same ``Ceiling-Approval:`` trailer -- otherwise the per-type
        ceiling could be silently inflated in the JSON itself, sidestepping
        the runtime check entirely. This applies symmetrically to
        ``violations_by_type`` and ``warnings_by_type``: an earlier version
        of this method checked only the warnings side, which meant a
        per-type *error* ceiling (e.g. ``clearance``) could be raised in
        the committed JSON with no trailer and this detector would not
        notice, even though ``_check_board`` enforces that exact ceiling at
        runtime.

        This is the single enumeration of "what raised" for R27's
        measurement-evidence validation -- ``validate_raise_evidence``
        consumes it, so a raise can never pass evidence validation while
        being invisible to this enumeration. Approval detection
        (``detect_ceiling_raise``) runs the SAME raise rules in the Rust
        kernel ``temper_drc_rs.detect_ceiling_raise`` (a verbatim port of
        the pre-migration raise detector, kept bit-identical by the
        differential suite in test_drc_ratchet_rust_differential.py), so a
        raise is visible to both checks across the Python/Rust boundary --
        the R27 "never invisible to one check" property holds.

        Pass 2 (P1-1): every ceiling value is int-VALIDATED here, the same
        fail-loudly ``CeilingMarshalError`` boundary ``detect_ceiling_raise``
        applies before the kernel. A float-valued ceiling in EITHER record
        is a data-model violation and fails loudly instead of being compared
        raw (``100.5 > 100`` detects a raise only in the oracle; the int-only
        kernels cannot represent it, and the old ``int()`` coercion silently
        truncated it -- the #575 fail-open class). R27's
        ``validate_raise_evidence`` inherits this marshal through its use of
        this enumeration.
        """
        old_boards = {b["board_id"]: b for b in old_ceiling.get("boards", [])}
        new_boards = {b["board_id"]: b for b in new_ceiling.get("boards", [])}

        raises: list[tuple[str, list[str]]] = []
        for board_id, new_entry in new_boards.items():
            old_entry = old_boards.get(board_id)
            if old_entry is None:
                continue

            old_errors = _marshal_ceiling_int(
                old_entry.get("error_ceiling", 0), "error_ceiling", board_id
            )
            new_errors = _marshal_ceiling_int(
                new_entry.get("error_ceiling", 0), "error_ceiling", board_id
            )
            old_warnings = _marshal_ceiling_int(
                old_entry.get("warning_ceiling", 0), "warning_ceiling", board_id
            )
            new_warnings = _marshal_ceiling_int(
                new_entry.get("warning_ceiling", 0), "warning_ceiling", board_id
            )

            reasons: list[str] = []
            if new_errors > old_errors:
                reasons.append(f"error_ceiling {old_errors} -> {new_errors}")
            if new_warnings > old_warnings:
                reasons.append(f"warning_ceiling {old_warnings} -> {new_warnings}")

            old_violations_by_type = old_entry.get("violations_by_type") or {}
            new_violations_by_type = new_entry.get("violations_by_type") or {}
            for rule in sorted(new_violations_by_type):
                new_count = _marshal_ceiling_int(
                    new_violations_by_type[rule], f"violations_by_type[{rule}]", board_id
                )
                old_count = _marshal_ceiling_int(
                    old_violations_by_type.get(rule, 0),
                    f"violations_by_type[{rule}]",
                    board_id,
                )
                if new_count > old_count:
                    reasons.append(f"violations_by_type[{rule}] {old_count} -> {new_count}")

            old_warnings_by_type = old_entry.get("warnings_by_type") or {}
            new_warnings_by_type = new_entry.get("warnings_by_type") or {}
            for rule in sorted(new_warnings_by_type):
                new_count = _marshal_ceiling_int(
                    new_warnings_by_type[rule], f"warnings_by_type[{rule}]", board_id
                )
                old_count = _marshal_ceiling_int(
                    old_warnings_by_type.get(rule, 0),
                    f"warnings_by_type[{rule}]",
                    board_id,
                )
                if new_count > old_count:
                    reasons.append(f"warnings_by_type[{rule}] {old_count} -> {new_count}")

            if reasons:
                raises.append((board_id, reasons))

        return raises

    def validate_raise_evidence(
        self, old_ceiling: dict, new_ceiling: dict, repo_root: Path
    ) -> list[str]:
        """Return every problem with the evidence a ceiling raise claims,
        or ``[]`` when every raise satisfies the contract.

        The R27 monotone contract (docs/plans/2026-08-02-023): a raise
        requires two checkable artifacts in the same PR --

          (a) an **attributed cause**: a NEW non-empty ``_march`` entry in
              the new ceiling file (a key absent from the old ``_march``,
              with a non-empty prose value naming the component/commit that
              drove the raise). This file's ``_march`` log is the single
              cause authority; there is deliberately no separate
              trailer-body grammar to parse.
          (b) a **measured sample**: the raised board's new ``provenance``
              block must be a measured-live record -- source
              ``"measured-live"``, a resolvable ``measured_at_commit``, a
              clean tree (``dirty`` false), a concrete recorded kicad-cli
              version, at least 120 samples whenever ANY category is
              declared nondeterministic (structured ``sample_count`` or
              ``measured_via`` prose) -- not only ``clearance``; see the
              2026-08-11 fix note inline below for why this is
              category-generic now -- and an input hash that still matches
              ``pcb/temper.kicad_pcb``'s current content.

        Each violation is reported as one problem string naming the failing
        dimension, so an unapproved raise fails with the *specific* reason
        (the anti-vacuity discipline: a raise cannot fail for a generic
        reason that hides which check actually bit).

        The ceiling values themselves are read through
        ``find_ceiling_raises``, which int-VALIDATES them with the same
        fail-loudly ``CeilingMarshalError`` marshal ``detect_ceiling_raise``
        applies -- a non-int ceiling in the raise comparison fails loudly
        here too, never silently truncated.
        """
        problems: list[str] = []

        raises = self.find_ceiling_raises(old_ceiling, new_ceiling)
        if not raises:
            return problems

        # (a) Cause authority: the _march log. One check over the whole
        # raise set -- a single new entry can attribute several per-type
        # deltas (every real remeasurement entry in this file does exactly
        # that), so the requirement is "at least one", not one per raise.
        old_march = old_ceiling.get("_march") or {}
        new_march = new_ceiling.get("_march") or {}
        new_cause_entries = [
            key
            for key, value in new_march.items()
            if key not in old_march and isinstance(value, str) and value.strip()
        ]
        if not new_cause_entries:
            problems.append(
                "raise has no attributed cause: no NEW non-empty '_march' entry "
                "(drc_ceiling.json's _march log is the single cause authority -- "
                "a raise must name the component/commit that drove it)"
            )

        # (b) Measurement evidence, per raised board.
        board_by_id = {b.get("board_id"): b for b in new_ceiling.get("boards", [])}

        # Batch-verify every shape-valid measured_at_commit resolves to a
        # real commit object -- one `git cat-file --batch-check` subprocess
        # for the whole raise set (see _verify_commits_exist above). The
        # pre-fix check below only validated SHA *shape*
        # (_SHA256_HEX_RE.fullmatch) while its own error message claimed
        # the commit "does not resolve to a commit" -- it never asked git,
        # so a syntactically-valid but dangling/orphaned SHA (e.g. one
        # orphaned by a rebase) passed silently. This is exactly how
        # drc_ceiling.json carried an unresolvable measured_at_commit for
        # weeks.
        shas_to_verify: set[str] = set()
        for board_id, _reasons in raises:
            record = board_by_id.get(board_id)
            if record is None:
                continue
            prov = record.get("provenance")
            if not isinstance(prov, dict):
                continue
            commit = prov.get("measured_at_commit")
            if isinstance(commit, str) and _SHA256_HEX_RE.fullmatch(commit):
                shas_to_verify.add(commit)
        resolved_commits = _verify_commits_exist(shas_to_verify, repo_root)

        for board_id, _reasons in raises:
            record = board_by_id.get(board_id)
            if record is None:
                problems.append(
                    f"{board_id}: raised board missing from the new ceiling record"
                )
                continue

            prov = record.get("provenance")
            if not isinstance(prov, dict):
                problems.append(
                    f"{board_id}: raise has no measured sample: the board's new "
                    "record carries no 'provenance' object"
                )
                continue

            source = prov.get("source")
            if source != "measured-live":
                problems.append(
                    f"{board_id}: provenance source={source!r} is not "
                    "'measured-live' -- a raise must cite a freshly measured "
                    "record, not a backfilled one"
                )

            commit = prov.get("measured_at_commit")
            if not (
                isinstance(commit, str)
                and _SHA256_HEX_RE.fullmatch(commit)
                and resolved_commits.get(commit, False)
            ):
                problems.append(
                    f"{board_id}: provenance measured_at_commit={commit!r} does not "
                    "resolve to a commit -- a measured-live raise must name the "
                    "commit it was measured at"
                )

            dirty = prov.get("dirty")
            if dirty is not False:
                problems.append(
                    f"{board_id}: provenance dirty={dirty!r} -- a raise must be "
                    "measured in a clean tree"
                )

            tool_versions = prov.get("tool_versions")
            kicad_cli_version = (
                tool_versions.get("kicad-cli") if isinstance(tool_versions, dict) else None
            )
            if not (
                isinstance(kicad_cli_version, str)
                and kicad_cli_version.strip()
                and kicad_cli_version != "UNKNOWN"
            ):
                problems.append(
                    f"{board_id}: provenance does not record a concrete kicad-cli "
                    "version in tool_versions -- a raise must be measured with the "
                    "contract tool (run_drc with --all-track-errors)"
                )

            # Sample count: >= 120 whenever ANY category is declared
            # nondeterministic -- every such category's ceiling is an
            # observed-max-plus-headroom number, which is only meaningful
            # when the observation actually sampled the run-to-run spread.
            #
            # This used to check only ``"clearance" in nondet`` -- literally
            # true when clearance was this file's one chronically-scattering
            # category, but it silently stopped enforcing anything the
            # moment a DIFFERENT category (``creepage``, since the #602 K3
            # swap) became the one carrying real run-to-run noise: a
            # creepage-only raise sailed through this check with zero
            # samples required, because the string "clearance" just wasn't
            # in its ``nondeterministic_error_types`` keys. Found while
            # fixing the creepage noise-headroom guard (2026-08-11) -- the
            # same discipline this file's docstring already claims
            # ("at least 120 samples for the nondeterministic clearance
            # category") was never actually category-generic in code. Now
            # checked once per declared-nondeterministic category, not once
            # for a single hardcoded name.
            nondet = record.get("nondeterministic_error_types")
            if isinstance(nondet, dict) and nondet:
                sample_count = _provenance_sample_count(prov)
                if sample_count is None or sample_count < 120:
                    categories = ", ".join(sorted(nondet))
                    problems.append(
                        f"{board_id}: {categories} declared nondeterministic but the "
                        f"provenance records {sample_count!r} sample(s) -- the "
                        "measurement contract requires at least 120 samples "
                        "(provenance.sample_count, or measured_via prose on "
                        "legacy records)"
                    )

            # Input freshness: the recorded board hash must still match the
            # board file's current content -- a raise measured against a
            # board that has since moved is a stale measurement.
            board_rel = record.get("path")
            # Bind once, then narrow: `prov.get(...)` called twice is two
            # separate expressions, so the isinstance does not narrow the
            # value that actually gets assigned.
            raw_inputs = prov.get("inputs")
            inputs = raw_inputs if isinstance(raw_inputs, list) else []
            matching_inputs = [
                inp for inp in inputs if isinstance(inp, dict) and inp.get("path") == board_rel
            ]
            if not matching_inputs:
                problems.append(
                    f"{board_id}: provenance inputs do not name the board file "
                    f"{board_rel!r} -- a raise must hash the exact input it measured"
                )
            else:
                try:
                    current_hash = _sha256_file(repo_root / board_rel)
                except OSError as exc:
                    problems.append(
                        f"{board_id}: cannot hash the board file {board_rel!r} "
                        f"({exc}) -- a raise must be backed by a board that exists"
                    )
                    continue
                for inp in matching_inputs:
                    recorded_hash = inp.get("sha256")
                    if not (
                        isinstance(recorded_hash, str)
                        and len(recorded_hash) == 64
                        and recorded_hash == current_hash
                    ):
                        problems.append(
                            f"{board_id}: provenance input hash for {board_rel} does "
                            "not match the file's current content -- the raise cites "
                            "a STALE measurement (input moved since it was measured)"
                        )

        return problems

    def detect_ceiling_raise(
        self, old_ceiling: dict, new_ceiling: dict, commit_message: str = ""
    ) -> DrcRatchetResult | None:
        """Detect if ceiling was raised without approval.

        A raise is any of: the aggregate ``error_ceiling`` increasing, the
        aggregate ``warning_ceiling`` increasing, or any single rule inside
        ``violations_by_type`` (errors) or ``warnings_by_type`` (warnings)
        increasing -- including a rule that didn't exist in the old record
        at all, which is a raise from its implicit ceiling of 0 (the same
        implicit-zero semantics ``_check_board`` enforces at runtime).
        Editing the ceiling *file* to grant a rule more room is exactly as
        much a raise as editing the aggregate number, and must require the
        same ``Ceiling-Approval:`` trailer -- otherwise the per-type
        ceiling could be silently inflated in the JSON itself, sidestepping
        the runtime check entirely. This applies symmetrically to
        ``violations_by_type`` and ``warnings_by_type``: an earlier version
        of this method checked only the warnings side, which meant a
        per-type *error* ceiling (e.g. ``clearance``) could be raised in
        the committed JSON with no trailer and this detector would not
        notice, even though ``_check_board`` enforces that exact ceiling at
        runtime.

        The ``Ceiling-Approval:`` check remains the substring marker (any
        commit in the PR containing it) -- it is the *raise detector*, not
        the cause authority. Whether an approved raise actually carries an
        attributed cause and a measured sample is the measurement-evidence
        contract, validated separately by ``validate_raise_evidence``.

        Wave 4 Phase 4: the raise-detection compute (the enumeration above
        plus the substring check) now runs in ``temper_drc_rs.detect_ceiling_raise``
        -- a verbatim port of the pre-migration raise detector, whose
        constants are unchanged -- so the #575 gate's behavior is preserved.
        R27's ``find_ceiling_raises`` implements the same raise rules as the
        Python contract layer (consumed by ``validate_raise_evidence``); the
        differential suite in test_drc_ratchet_rust_differential.py keeps the
        two bit-identical.
        """

        def _marshal(ceiling: dict) -> list[tuple]:
            # Pass 2 (P1-1): every value is int-VALIDATED at this marshal
            # boundary, not merely int()-coerced. The old coercion silently
            # truncated a float-valued ceiling (``100.5`` -> ``100``), making
            # a raise ``100 -> 100.5`` invisible to the kernel and failing
            # the #575 approval gate OPEN. ``CeilingMarshalError`` fires
            # before the kernel instead.
            boards: list[tuple] = []
            for board in ceiling.get("boards", []):
                board_id = board["board_id"]
                boards.append(
                    (
                        board_id,
                        _marshal_ceiling_int(
                            board.get("error_ceiling", 0), "error_ceiling", board_id
                        ),
                        _marshal_ceiling_int(
                            board.get("warning_ceiling", 0), "warning_ceiling", board_id
                        ),
                        [
                            (
                                rule,
                                _marshal_ceiling_int(
                                    count,
                                    f"violations_by_type[{rule}]",
                                    board_id,
                                ),
                            )
                            for rule, count in (board.get("violations_by_type") or {}).items()
                        ],
                        [
                            (
                                rule,
                                _marshal_ceiling_int(
                                    count,
                                    f"warnings_by_type[{rule}]",
                                    board_id,
                                ),
                            )
                            for rule, count in (board.get("warnings_by_type") or {}).items()
                        ],
                    )
                )
            return boards

        result = _tdrc().detect_ceiling_raise(
            _marshal(old_ceiling),
            _marshal(new_ceiling),
            commit_message,
        )
        if result is None:
            return None
        return DrcRatchetResult(
            passed=result["passed"],
            board_id=result["board_id"],
            message=result["message"],
            exit_code=result["exit_code"],
        )
