#!/usr/bin/env python3
"""Board-defect mutation corpus runner (plan 2026-08-02-024, R38).

For each defect class (component off-board, pad short, creepage crossing,
plain copper clearance, courtyard overlap -- the last two added 2026-08-07;
see ``docs/evidence/2026-08-07-clearance-courtyard-corpus-coverage.md`` for
why ``clearance``/``courtyards_overlap`` were VACUOUS gates before this
change and how the new classes close that -- plus drilled hole-to-hole
spacing and missing courtyard, added later the same day for STRATEGY.md
build order step 4; see ``docs/evidence/
2026-08-07-missing-courtyard-and-hole-to-hole-classes.md``. ``missing-courtyard``
was a DELIBERATE exception there: its injector was independently
self-verified but its owning gate did not fire, reported as a genuine
coverage gap rather than weakened, per METHODOLOGY.md Sec. 5.

UPDATE (2026-08-13): this runner's own ``measure_drc()`` never gave its
clean/mutated scratch copies a sibling ``.kicad_pro`` (see
``copy_kicad_project_sidecar`` calls in ``run_corpus`` below, added this
date), so every measurement in this file was itself running context-blind
in exactly the way ``_drc_api.DrcProjectContextError`` warns callers
about -- a corpus bug, not a corpus finding. Fixing that closes
``missing-courtyard`` (its owning gate now fires -- cause (1) in the
manifest's ``uncovered_finding`` note is resolved; see
``scripts/board_defect_corpus.yaml``) but exposes a NEW, previously
hidden gap in the ``clearance`` class instead: the seeded R64/R67 pad
pair no longer registers a clearance violation once real project context
is used, even at complete pad overlap, while other pad/track clearance
pairs on the same board measure correctly in the same run. ``clearance``
is now the DELIBERATE exception (see its own
``uncovered_finding`` note in the manifest and
``scripts/tests/test_check_board_defect_corpus.py``'s
``TestCorpusEndToEnd._EXPECTED_UNCOVERED``) this runner:

  1. re-derives a mutated copy of the committed ``pcb/temper.kicad_pcb``
     from the seed manifest (``scripts/board_defect_corpus.yaml``) via
     ``scripts/board_defect_mutator.py`` -- the committed board is never
     modified (KTD1, KTD3);
  2. runs the class's OWNING gate(s) against BOTH the clean and the mutated
     board (KTD2) and asserts the class's failure signal -- the gate must
     name the seeded defect on the mutated board and must NOT name it on
     the clean board (both halves of R9);
  3. fails the run if any class has no failing gate (uncovered class), or
     if the clean board violates the anti-vacuity control.

Failure signals, and why they are identity-based rather than count-deltas
-------------------------------------------------------------------------
Until 2026-08-04 every class asserted a *count-delta*: some DRC category's
count on the mutated board had to exceed both the clean count and the
recorded ``drc_ceiling.json`` ceiling. Two of the three classes were
measured uncovered on 2026-08-04, and the count-delta formulation was the
direct cause of one of them and hid the other (see
``docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md``):

  * ``off-board`` named ``courtyards_overlap``/``copper_edge_clearance`` as
    owning gates. Neither actually checks containment. Moving a component
    off the outline REMOVES its copper from the layout, so the board's DRC
    counts go DOWN (measured -9 across three categories), and a count-delta
    can never fire. The class now has a real owning gate,
    ``scripts/check_board_containment.py`` (the R26 invariant), asserted by
    identity: the gate must report the mutated ref outside the outline, and
    must report nothing on the clean board.

  * ``pad-short`` asserted ``shorting_items`` +1 against
    ``max(clean, ceiling)``. That comparison is unsatisfiable whenever the
    recorded ceiling exceeds the clean count by more than the delta -- and
    it did (ceiling 201, clean 200, so the mutation needed 202). It is also
    below the measurement's own noise floor: ``shorting_items`` was measured
    at 199,199,199,200,199 over repeated runs of one byte-identical board.
    And the category itself is not stable for this defect: KiCad reports the
    identical seeded short as ``shorting_items`` on one board and as
    ``clearance`` (actual 0.0000 mm) + ``solder_mask_bridge`` on another.
    The class now asserts that SOME DRC error names BOTH shorted pads on
    the mutated board and none does on the clean board -- independent of
    category name, immune to the noise floor, and strictly stronger than a
    count-delta (a count can rise for an unrelated reason; an error naming
    the two pads the mutator moved cannot).

``creepage`` keeps its per-class count-delta against the clean
measurement. The REQ-SAFE-01 creepage gate is RED on main today, so it is
excluded from the clean-board anti-vacuity control and asserted against the
clean measurement as its documented known-finding baseline -- see
``scripts/board_defect_corpus.yaml`` ``classes.creepage.baseline_note``.

  * ``clearance`` and ``courtyard`` (added 2026-08-07) are identity-based
    from the start, for the same reason ``pad-short`` had to become
    identity-based: ``clearance`` is this repo's OWN documented
    nondeterministic DRC category (AGENTS.md's DRC-ceiling section requires
    >=120 samples for it precisely because it moves on a byte-identical
    board), so a raw count-delta on it would repeat the exact defect this
    module was fixed to stop having. ``clearance`` asserts that some DRC
    error names both a specific pad of the seeded ref AND a specific pad of
    a fixed anchor ref (:func:`errors_naming_two_pads` -- the two-footprint
    generalization of ``pad-short``'s same-footprint check). ``courtyard``
    asserts that some DRC error names both the seeded ref and a fixed
    anchor ref (:func:`errors_naming_both_refs` -- courtyard violations are
    footprint-level, "Footprint X", not pad-level). Measured over 120
    repeated runs of each byte-identical mutated board: the identity signal
    is exactly 2/0 (clearance) and 1/0 (courtyard) respectively (mutated
    vs clean) with ZERO variance, even though the underlying category
    totals in principle carry the same allocation-address-ordering
    nondeterminism ``_drc_api.py`` documents for ``clearance``. See
    ``docs/evidence/2026-08-07-clearance-courtyard-corpus-coverage.md`` for
    the full sample data and why ``courtyards_overlap`` -- which the
    2026-08-04 evidence measured NOT to discriminate the ``off-board`` seed
    (11 -> 11, unchanged) -- discriminates the new ``courtyard`` seed
    cleanly: that mutation computes its target position FROM the two
    footprints' own courtyard geometry, so the overlap is a deterministic
    property of the seed rather than an accident of unrelated placement
    geometry.

The clean-board anti-vacuity control covers the DRC gate categories that
are GREEN on the committed board (``courtyards_overlap`` /
``copper_edge_clearance`` / ``shorting_items`` at or below their
``drc_ceiling.json`` ceilings) plus board containment, which must be
completely clean on the committed board.

Measurement paths are the canonical ones: DRC via
``temper_placer.validation._drc_api.run_drc`` (which bakes in
``--all-track-errors`` -- see that module's comment for why bare kicad-cli
is not reproducible), and creepage via the REQ-SAFE-01 validator itself
(``tests.requirements.safety._real_board_fixture.load_real_board_placement``
+ ``verify_iec60335_compliance``), pointed at the mutated board copy.

Exit codes:
  0 - pass: all classes covered, clean board anti-vacuity control green
  1 - corpus failure: an uncovered class, or a clean-board anti-vacuity
      violation (the defect class is named in the output)
  2 - GATE ERROR: kicad-cli unavailable, board missing, netlist/manifest
      missing, or a measurement failed -- never reported as a pass

Usage:
  uv run --no-sync python scripts/check_board_defect_corpus.py
  uv run --no-sync python scripts/check_board_defect_corpus.py --update-manifest
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))
# The REQ-SAFE-01 fixture imports `tests.requirements.validators.clearance`
# as a package, so packages/temper-placer must be importable.
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer"))

EXIT_PASS = 0
EXIT_CORPUS_FAIL = 1
EXIT_GATE_ERROR = 2

MANIFEST_PATH = REPO_ROOT / "scripts" / "board_defect_corpus.yaml"
BOARD_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"
CEILING_PATH = REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json"

# The corpus's DRC owning-gate categories (part of the class-to-gate table,
# KTD2). Every one of these must be at or below its drc_ceiling.json
# ceiling on the clean board (anti-vacuity control); the creepage gate is
# handled separately (red on main -- see module docstring).
DRC_GATE_CATEGORIES = ("courtyards_overlap", "copper_edge_clearance", "shorting_items")


class GateError(RuntimeError):
    """A corpus input or measurement is unavailable -- fail closed (exit 2),
    never reported as a pass."""


@dataclass
class ClassVerdict:
    name: str
    ok: bool
    message: str
    gate_error: bool = False


@dataclass
class CorpusReport:
    ok: bool
    exit_code: int
    board_sha256: str
    manifest_board_sha256: str
    board_matches_manifest: bool
    clean_drc: dict[str, int] = field(default_factory=dict)
    clean_creepage_dc_lv: int | None = None
    clean_containment_refs: list[str] = field(default_factory=list)
    anti_vacuity_violations: list[str] = field(default_factory=list)
    class_verdicts: list[ClassVerdict] = field(default_factory=list)
    mutation_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    workdir: str | None = None


# ---------------------------------------------------------------------------
# canonical measurement paths
# ---------------------------------------------------------------------------


def regenerate_dru(repo_root: Path) -> Path:
    """Regenerate ``pcb/temper.kicad_dru`` from its SSOT generator -- same
    convention as ``ci_check_drc.py``, so the corpus measures against the one
    canonical rules file, never whatever is (or isn't) on disk."""
    import generate_kicad_dru

    content = generate_kicad_dru.generate_dru()
    generate_kicad_dru.OUTPUT_PATH.write_text(content, encoding="utf-8")
    return generate_kicad_dru.OUTPUT_PATH


def measure_drc(pcb_path: Path, dru_path: Path | None) -> list[Any]:
    """Every DRC error AND warning for *pcb_path* via run_drc (the canonical
    path).

    kicad-cli resolves ``<stem>.kicad_dru`` next to the board file (verified:
    placing the regenerated SSOT dru beside a copy makes the custom
    ``creepage`` DRU category appear), so the dru is copied next to the
    mutated copy to keep the measurement byte-for-byte the ratchet's.

    Returns ``result.errors + result.warnings`` (mixed ``DrcError``/
    ``DrcWarning`` objects), not just ``result.errors``, since 2026-08-07:
    ``hole_to_hole`` is a genuinely-computed kicad-cli rule whose severity
    is ``warning`` even under kicad-cli's compiled-in defaults (no project
    file present) -- ``_parse_drc_json`` buckets anything ``severity ==
    "warning"`` into ``result.warnings``, so a class whose owning gate is a
    warning-severity rule was previously invisible to every consumer of
    this function, discovered while building the ``hole-to-hole`` corpus
    class (docs/evidence/
    2026-08-07-missing-courtyard-and-hole-to-hole-classes.md). This is
    local to the corpus's own measurement wrapper -- ``_drc_api.run_drc()``
    itself, and every OTHER consumer of it (the DRC ceiling ratchet,
    ``ci_check_drc.py``), are unmodified. ``DrcWarning`` has no ``items``
    field (only ``components``/``nets`` -- see its docstring), so any
    identity check that needs raw per-item pad-number text
    (:func:`errors_naming_pad_pair`/:func:`errors_naming_two_pads`) still
    only matches ``DrcError`` entries; ref-level checks
    (:func:`errors_naming_both_refs`/:func:`errors_of_type_naming_ref`)
    work on both.
    """
    if dru_path is not None and dru_path.exists():
        shutil.copyfile(dru_path, pcb_path.with_suffix(".kicad_dru"))
    from temper_placer.validation._drc_api import DrcRunnerError, run_drc

    try:
        result = run_drc(pcb_path)
    except (DrcRunnerError, OSError) as exc:
        raise GateError(f"DRC measurement failed on {pcb_path.name}: {exc}") from exc
    return list(result.errors) + list(result.warnings)


def drc_counts(errors: list[Any]) -> dict[str, int]:
    """Per-violation-type counts, the shape the ceilings are recorded in."""
    return dict(Counter(e.rule for e in errors))


# KiCad item descriptions naming a pad, in both spellings the report uses:
# "Pad 1 [I_SENSE] of C28 on F.Cu" (SMD) and "PTH pad 1 [SW_NODE] of C26"
# (through-hole, lowercase, no trailing layer clause).
_PAD_ITEM_RE = re.compile(
    r"\bpad\s+(?P<pad>\S+)\s+\[[^\]]*\]\s+of\s+(?P<ref>\S+)", re.IGNORECASE
)


def item_names_pad(description: str, ref: str, pad: str) -> bool:
    """Does one kicad-cli item description name *pad* of *ref*?"""
    match = _PAD_ITEM_RE.search(description or "")
    if match is None:
        return False
    return match.group("ref") == ref and match.group("pad") == pad


def errors_naming_pad_pair(
    errors: list[Any], ref: str, pad_a: str, pad_b: str
) -> list[str]:
    """DRC errors that name BOTH *pad_a* and *pad_b* of *ref*.

    This is the pad-short class's failure signal. A violation between two
    pads of one footprint is exactly what the mutator creates and exactly
    what a category count cannot distinguish from unrelated drift.
    """
    found: list[str] = []
    for error in errors:
        items = getattr(error, "items", None) or []
        if any(item_names_pad(i, ref, pad_a) for i in items) and any(
            item_names_pad(i, ref, pad_b) for i in items
        ):
            found.append(f"{error.rule}: {error.message}")
    return found


def errors_naming_two_pads(
    errors: list[Any], ref_a: str, pad_a: str, ref_b: str, pad_b: str
) -> list[str]:
    """DRC errors that name *pad_a* of *ref_a* AND *pad_b* of *ref_b* --
    the same identity signal as :func:`errors_naming_pad_pair`, generalized
    to two DIFFERENT footprints. This is the ``clearance`` class's failure
    signal: the mutator compresses the gap between one pad of each
    footprint below the required net-class clearance, and a violation
    naming both of those exact pads cannot be produced by unrelated board
    drift, unlike a category count.
    """
    found: list[str] = []
    for error in errors:
        items = getattr(error, "items", None) or []
        if any(item_names_pad(i, ref_a, pad_a) for i in items) and any(
            item_names_pad(i, ref_b, pad_b) for i in items
        ):
            found.append(f"{error.rule}: {error.message}")
    return found


def errors_naming_both_refs(errors: list[Any], ref_a: str, ref_b: str) -> list[str]:
    """DRC errors whose (deduped) ``components`` name BOTH *ref_a* and
    *ref_b* -- the ``courtyard`` class's failure signal. Courtyard items are
    footprint-level ("Footprint R48"), not pad-level, so this checks
    ``error.components`` (already extracted by ``_drc_api._parse_drc_json``
    from each item's description) rather than the pad-number regex
    :func:`item_names_pad` uses.
    """
    found: list[str] = []
    for error in errors:
        components = getattr(error, "components", None) or []
        if ref_a in components and ref_b in components:
            found.append(f"{error.rule}: {error.message}")
    return found


def errors_of_type_naming_both_refs(
    errors: list[Any], rule: str, ref_a: str, ref_b: str
) -> list[str]:
    """DRC errors of *rule* type whose (deduped) ``components`` name BOTH
    *ref_a* and *ref_b* -- the ``hole-to-hole`` class's failure signal.

    Ref-level (like :func:`errors_naming_both_refs`), not pad-level like
    :func:`errors_naming_two_pads`: ``hole_to_hole`` is reported as a
    ``DrcWarning`` under kicad-cli's compiled-in default severity for that
    rule (verified 2026-08-07 -- see :func:`measure_drc`'s docstring), and
    ``DrcWarning`` carries no raw per-item ``items`` text, only the deduped
    ``components`` list. Since the mutation moves exactly one footprint to
    sit next to one fixed anchor footprint, naming both refs together in a
    ``hole_to_hole``-type violation is unambiguous without needing the pad
    number.
    """
    found: list[str] = []
    for error in errors:
        if getattr(error, "rule", None) != rule:
            continue
        components = getattr(error, "components", None) or []
        if ref_a in components and ref_b in components:
            found.append(f"{error.rule}: {error.message}")
    return found


def errors_of_type_naming_ref(errors: list[Any], rule: str, ref: str) -> list[str]:
    """DRC errors of *rule* type whose (deduped) ``components`` name *ref*
    -- the ``missing-courtyard`` class's failure signal. Scoped to a single
    rule (unlike :func:`errors_naming_both_refs`) because a footprint ref
    can legitimately appear in OTHER rule types' output (e.g.
    ``courtyards_overlap``) without that meaning the specific rule this
    class cares about fired.
    """
    found: list[str] = []
    for error in errors:
        if getattr(error, "rule", None) != rule:
            continue
        components = getattr(error, "components", None) or []
        if ref in components:
            found.append(f"{error.rule}: {error.message}")
    return found


def measure_containment(pcb_path: Path) -> set[str]:
    """Reference designators with copper outside the board outline, via the
    R26 containment gate (``scripts/check_board_containment.py``) -- the
    off-board class's owning gate."""
    import check_board_containment

    try:
        report = check_board_containment.analyze_board(Path(pcb_path))
    except check_board_containment.GateError as exc:
        raise GateError(
            f"board-containment measurement failed on {pcb_path.name}: {exc}"
        ) from exc
    return report.refs_outside()


def measure_creepage_dc_lv(pcb_path: Path) -> int:
    """DC_BUS<->LV_CONTROL creepage violation count via the REQ-SAFE-01
    validator, pointed at *pcb_path* (a run-time board copy)."""
    from tests.requirements.safety import _real_board_fixture as fixture

    from temper_placer.requirements.validators.clearance import (
        verify_iec60335_compliance,
    )

    fixture._PCB_PATH = Path(pcb_path)
    try:
        placement, voltage_domains, _stats = fixture.load_real_board_placement()
    except fixture.RealBoardUnavailable as exc:
        raise GateError(f"REQ-SAFE-01 inputs unavailable: {exc}") from exc
    result = verify_iec60335_compliance(placement, voltage_domains)
    return sum(
        1
        for v in result.violations
        if v.metric == "creepage" and v.boundary == "DC_BUS<->LV_CONTROL"
    )


def load_drc_ceilings(repo_root: Path) -> dict[str, int]:
    """Per-type error ceilings for the corpus's DRC gate categories, from
    the DRC ratchet's SSOT (``power_pcb_dataset/drc_ceiling.json``). A
    category absent from the file is not part of the corpus contract."""
    if not (repo_root / "power_pcb_dataset" / "drc_ceiling.json").exists():
        raise GateError(
            "power_pcb_dataset/drc_ceiling.json not found -- the corpus's "
            "anti-vacuity control reads its ceilings from the DRC ratchet SSOT"
        )
    data = json.loads((repo_root / "power_pcb_dataset" / "drc_ceiling.json").read_text())
    for entry in data.get("boards", []):
        if entry.get("board_id") == "temper":
            by_type = entry.get("violations_by_type") or {}
            return {k: int(v) for k, v in by_type.items() if k in DRC_GATE_CATEGORIES}
    raise GateError("drc_ceiling.json has no 'temper' board entry")


# ---------------------------------------------------------------------------
# pure decision logic (unit-testable without kicad-cli)
# ---------------------------------------------------------------------------


@dataclass
class ClassMeasurement:
    """Everything the owning gates saw, on the clean board and on the
    mutated board, for one defect class."""

    params: dict[str, Any] = field(default_factory=dict)
    clean_containment_refs: set[str] = field(default_factory=set)
    mutated_containment_refs: set[str] = field(default_factory=set)
    clean_pair_errors: list[str] = field(default_factory=list)
    mutated_pair_errors: list[str] = field(default_factory=list)
    clean_creepage: int | None = None
    mutated_creepage: int | None = None
    clean_cross_pair_errors: list[str] = field(default_factory=list)
    mutated_cross_pair_errors: list[str] = field(default_factory=list)
    clean_courtyard_pair_errors: list[str] = field(default_factory=list)
    mutated_courtyard_pair_errors: list[str] = field(default_factory=list)
    clean_hole_pair_errors: list[str] = field(default_factory=list)
    mutated_hole_pair_errors: list[str] = field(default_factory=list)
    clean_missing_courtyard_errors: list[str] = field(default_factory=list)
    mutated_missing_courtyard_errors: list[str] = field(default_factory=list)
    clean_courtyard_item_count: int | None = None
    mutated_courtyard_item_count: int | None = None


def evaluate_class(
    class_name: str,
    mutation: str,
    measurement: ClassMeasurement,
) -> ClassVerdict:
    """Decide whether a mutated board fails its owning gate.

    A class is COVERED (ok) iff its owning gate NAMES the seeded defect on
    the mutated board and does NOT name it on the clean board -- both
    halves of R9. A class with no firing gate is a corpus error, not a pass
    (KTD2), and the returned verdict names the class and what was measured
    so the failure is actionable.
    """
    if mutation == "off-board":
        ref = measurement.params.get("ref", "<no ref>")
        if ref in measurement.clean_containment_refs:
            return ClassVerdict(
                name=class_name,
                ok=False,
                message=(
                    f"{class_name}: control violated -- {ref} is ALREADY "
                    "outside the board outline on the CLEAN board, so the "
                    "mutated board proves nothing. Re-seed this class onto "
                    "a ref that starts inside the outline."
                ),
            )
        if ref in measurement.mutated_containment_refs:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate board_containment fired: "
                    f"{ref} has copper outside the Edge.Cuts outline on the "
                    "mutated board and none on the clean board"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- owning gate "
                f"board_containment did not name {ref} on the mutated board "
                f"(refs outside outline: {sorted(measurement.mutated_containment_refs) or 'none'})"
            ),
        )
    if mutation == "pad-short":
        ref = measurement.params.get("ref", "<no ref>")
        pad_a = measurement.params.get("pad_a")
        pad_b = measurement.params.get("pad_b")
        if measurement.clean_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=False,
                message=(
                    f"{class_name}: control violated -- {ref} pads {pad_a}/"
                    f"{pad_b} are ALREADY in violation together on the CLEAN "
                    f"board ({measurement.clean_pair_errors[0]}), so the "
                    "mutated board proves nothing. Re-seed this class onto a "
                    "pad pair that starts clean."
                ),
            )
        if measurement.mutated_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate kicad-drc fired: "
                    f"{len(measurement.mutated_pair_errors)} DRC error(s) name "
                    f"both {ref} pad {pad_a} and pad {pad_b} on the mutated "
                    f"board and none on the clean board "
                    f"[{'; '.join(measurement.mutated_pair_errors[:3])}]"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- no DRC error names both "
                f"{ref} pad {pad_a} and pad {pad_b} on the mutated board"
            ),
        )
    if mutation == "creepage":
        clean_creepage = measurement.clean_creepage
        mutated_creepage = measurement.mutated_creepage
        if clean_creepage is None or mutated_creepage is None:
            return ClassVerdict(
                name=class_name,
                ok=False,
                gate_error=True,
                message=(
                    f"{class_name}: gate error -- REQ-SAFE-01 creepage "
                    "measurement unavailable (netlist/manifest missing or "
                    "measurement failed)"
                ),
            )
        if mutated_creepage > clean_creepage:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate req-safe-01-creepage-dc-lv "
                    f"fired: DC_BUS<->LV_CONTROL creepage {clean_creepage} -> "
                    f"{mutated_creepage} (documented known-finding baseline: "
                    "gate red on main; class asserted via per-class delta)"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- DC_BUS<->LV_CONTROL "
                f"creepage did not rise ({clean_creepage} -> {mutated_creepage})"
            ),
        )
    if mutation == "clearance":
        ref_a = measurement.params.get("ref", "<no ref>")
        pad_a = measurement.params.get("pad", "<no pad>")
        ref_b = measurement.params.get("anchor_ref", "<no anchor_ref>")
        pad_b = measurement.params.get("anchor_pad", "<no anchor_pad>")
        if measurement.clean_cross_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=False,
                message=(
                    f"{class_name}: control violated -- {ref_a} pad {pad_a} "
                    f"and {ref_b} pad {pad_b} are ALREADY in violation "
                    f"together on the CLEAN board "
                    f"({measurement.clean_cross_pair_errors[0]}), so the "
                    "mutated board proves nothing. Re-seed this class onto a "
                    "pad pair that starts clean."
                ),
            )
        if measurement.mutated_cross_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate kicad-drc fired: "
                    f"{len(measurement.mutated_cross_pair_errors)} DRC "
                    f"error(s) name both {ref_a} pad {pad_a} and {ref_b} pad "
                    f"{pad_b} on the mutated board and none on the clean "
                    f"board [{'; '.join(measurement.mutated_cross_pair_errors[:3])}]"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- no DRC error names both "
                f"{ref_a} pad {pad_a} and {ref_b} pad {pad_b} on the mutated "
                "board"
            ),
        )
    if mutation == "courtyard":
        ref_a = measurement.params.get("ref", "<no ref>")
        ref_b = measurement.params.get("anchor_ref", "<no anchor_ref>")
        if measurement.clean_courtyard_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=False,
                message=(
                    f"{class_name}: control violated -- {ref_a} and {ref_b} "
                    "ALREADY have overlapping courtyards on the CLEAN board "
                    f"({measurement.clean_courtyard_pair_errors[0]}), so the "
                    "mutated board proves nothing. Re-seed this class onto a "
                    "pair whose courtyards start clear."
                ),
            )
        if measurement.mutated_courtyard_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate kicad-drc "
                    "(courtyards_overlap) fired: "
                    f"{len(measurement.mutated_courtyard_pair_errors)} DRC "
                    f"error(s) name both {ref_a} and {ref_b} on the mutated "
                    "board and none on the clean board "
                    f"[{'; '.join(measurement.mutated_courtyard_pair_errors[:3])}]"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- no DRC error names both "
                f"{ref_a} and {ref_b} on the mutated board"
            ),
        )
    if mutation == "hole-to-hole":
        ref_a = measurement.params.get("ref", "<no ref>")
        ref_b = measurement.params.get("anchor_ref", "<no anchor_ref>")
        if measurement.clean_hole_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=False,
                message=(
                    f"{class_name}: control violated -- {ref_a} and {ref_b} "
                    "ALREADY have a hole_to_hole violation together on the "
                    f"CLEAN board ({measurement.clean_hole_pair_errors[0]}), "
                    "so the mutated board proves nothing. Re-seed this "
                    "class onto a pad pair that starts clean."
                ),
            )
        if measurement.mutated_hole_pair_errors:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate kicad-drc (hole_to_hole) "
                    "fired: "
                    f"{len(measurement.mutated_hole_pair_errors)} DRC "
                    f"error(s) name both {ref_a} and {ref_b} on the mutated "
                    "board and none on the clean board "
                    f"[{'; '.join(measurement.mutated_hole_pair_errors[:3])}]"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- no hole_to_hole DRC "
                f"error names both {ref_a} and {ref_b} on the mutated board"
            ),
        )
    if mutation == "missing-courtyard":
        ref = measurement.params.get("ref", "<no ref>")
        clean_items = measurement.clean_courtyard_item_count
        mutated_items = measurement.mutated_courtyard_item_count
        if clean_items is None or mutated_items is None:
            return ClassVerdict(
                name=class_name,
                ok=False,
                gate_error=True,
                message=(
                    f"{class_name}: gate error -- independent courtyard-item "
                    "re-parse unavailable, cannot verify the injector itself"
                ),
            )
        if clean_items == 0:
            return ClassVerdict(
                name=class_name,
                ok=False,
                message=(
                    f"{class_name}: control violated -- {ref} ALREADY has 0 "
                    "F.CrtYd/B.CrtYd items on the CLEAN board, so the "
                    "mutated board proves nothing. Re-seed this class onto a "
                    "ref that starts with real courtyard graphics."
                ),
            )
        if mutated_items != 0:
            return ClassVerdict(
                name=class_name,
                ok=False,
                gate_error=True,
                message=(
                    f"{class_name}: injector no-op -- {ref} still has "
                    f"{mutated_items} F.CrtYd/B.CrtYd item(s) on the mutated "
                    "board (independent re-parse); the mutation did not take "
                    "effect"
                ),
            )
        # Injector self-verified independently of the DRC gate: ref had
        # courtyard graphics on the clean board (clean_items > 0) and has
        # none on the mutated board (mutated_items == 0), confirmed by a
        # re-parse of the written file -- not by asking kicad-cli anything.
        # The DRC gate itself is checked next, and is EXPECTED not to fire
        # -- see board_defect_corpus.yaml's uncovered_finding note and
        # board_defect_mutator.mutate_missing_courtyard's docstring for the
        # two independently verified root causes. Reported honestly as
        # uncovered rather than silently dropped or weakened.
        if measurement.mutated_missing_courtyard_errors:
            # Would only happen if run_drc()'s invocation is later fixed to
            # request warning-severity output with a project file present
            # -- kept so this class re-covers itself automatically the day
            # that gap closes, instead of needing a second edit here.
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate kicad-drc (missing_courtyard) "
                    f"fired: {len(measurement.mutated_missing_courtyard_errors)} "
                    f"DRC error(s) name {ref} on the mutated board and none "
                    "on the clean board "
                    f"[{'; '.join(measurement.mutated_missing_courtyard_errors[:3])}]"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: UNCOVERED -- injector independently verified "
                f"({ref}: 1 courtyard item on clean board, 0 on mutated "
                "board, re-parsed directly), but no DRC error names "
                f"missing_courtyard for {ref} on the mutated board. As of "
                "2026-08-13 this scratch copy DOES have a sibling .kicad_pro "
                "(run_corpus() calls copy_kicad_project_sidecar() before "
                "measuring -- the original root cause (1) below is closed), "
                "so if this branch is reached again the remaining suspect is "
                "root cause (2): run_drc() never passes --severity-warning/"
                "--severity-all and missing_courtyard is a warning-severity "
                "rule. Historical root-cause detail (both were independently "
                "verified sufficient alone, before the project-context fix): "
                "docs/evidence/2026-08-07-missing-courtyard-and-hole-to-hole-classes.md."
            ),
        )
    raise GateError(f"manifest class {class_name!r} has unknown mutation {mutation!r}")


def check_anti_vacuity(
    clean_drc: dict[str, int],
    ceilings: dict[str, int],
    gate_categories: tuple[str, ...] = DRC_GATE_CATEGORIES,
    clean_containment_refs: set[str] | None = None,
) -> list[str]:
    """Clean-board anti-vacuity control: every corpus DRC gate category must
    be at or below its recorded ceiling on the unmutated board, and the
    board-containment gate must be completely clean on it. The creepage
    gate is deliberately NOT in *gate_categories* (red on main today -- see
    module docstring); its class uses a per-class delta instead."""
    violations: list[str] = []
    if clean_containment_refs:
        violations.append(
            "clean-board board_containment is not green: copper outside the "
            f"outline on {sorted(clean_containment_refs)} -- the off-board "
            "class cannot demonstrate anything against a board that already "
            "fails its owning gate"
        )
    for category in gate_categories:
        ceiling = ceilings.get(category)
        if ceiling is None:
            # Category not part of the ratchet's recorded contract -- the
            # corpus does not invent a ceiling for it.
            continue
        clean = clean_drc.get(category, 0)
        if clean > ceiling:
            violations.append(
                f"clean-board {category} {clean} > recorded ceiling {ceiling}"
            )
    return violations


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def _drc_delta(clean: dict[str, int], mutated: dict[str, int]) -> dict[str, str]:
    """Categories whose count changed, as "clean -> mutated" strings.

    Context for the report only. The off-board class deliberately does not
    assert on this: a component that leaves the board takes its copper with
    it, so these deltas are typically NEGATIVE.
    """
    return {
        category: f"{clean.get(category, 0)} -> {mutated.get(category, 0)}"
        for category in sorted(set(clean) | set(mutated))
        if clean.get(category, 0) != mutated.get(category, 0)
    }


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    import yaml

    if not manifest_path.exists():
        raise GateError(f"corpus manifest not found: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "classes" not in data:
        raise GateError(f"corpus manifest {manifest_path} has no 'classes' section")
    return data


def run_corpus(
    repo_root: Path,
    manifest_path: Path | None = None,
    workdir: Path | None = None,
    update_manifest: bool = False,
) -> CorpusReport:
    manifest_path = manifest_path or REPO_ROOT / "scripts" / "board_defect_corpus.yaml"
    manifest = load_manifest(manifest_path)
    meta = manifest.get("_meta", {})

    board_path = repo_root / "pcb" / "temper.kicad_pcb"
    if not board_path.exists():
        raise GateError(f"committed board not found: {board_path}")
    if shutil.which("kicad-cli") is None:
        raise GateError(
            "kicad-cli is not available -- the corpus measures through "
            "run_drc (--all-track-errors), the same constraint as the DRC "
            "ratchet; without it the corpus fails closed"
        )

    from board_defect_mutator import apply_mutation, board_content_hash, copy_board
    from temper_placer.validation._drc_api import copy_kicad_project_sidecar

    actual_board_hash = board_content_hash(board_path)
    recorded_board_hash = meta.get("board_sha256")
    board_matches = recorded_board_hash is None or actual_board_hash == recorded_board_hash

    ceilings = load_drc_ceilings(repo_root)
    dru_path = regenerate_dru(repo_root)

    workdir_path = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="board-defect-corpus-"))
    workdir_path.mkdir(parents=True, exist_ok=True)

    # --- clean-board control (byte-identical copy of the committed board) ---
    clean_copy = workdir_path / "clean.kicad_pcb"
    copy_board(board_path, clean_copy)
    # run_drc() (via _drc_api.ensure_resolvable_kicad_project, added
    # 2026-08-08 in 67e04601f) now refuses to DRC a board with no sibling
    # .kicad_pro -- give the scratch copy the real board's project under
    # its own stem so the measurement isn't silently blind to the
    # project's creepage/track_width DRU rules and rule_severities
    # overrides. copy_kicad_project_sidecar() is the supported mechanism
    # DrcProjectContextError itself points callers at.
    copy_kicad_project_sidecar(clean_copy, board_path)
    clean_errors = measure_drc(clean_copy, dru_path)
    clean_drc = drc_counts(clean_errors)
    clean_containment_refs = measure_containment(clean_copy)
    try:
        clean_creepage = measure_creepage_dc_lv(clean_copy)
    except GateError as exc:
        clean_creepage = None
        print(f"  [gate-error] clean-board creepage measurement: {exc}")

    anti_vacuity_violations = check_anti_vacuity(
        clean_drc, ceilings, clean_containment_refs=clean_containment_refs
    )

    # --- per-class mutations + owning-gate assertion ---
    class_verdicts: list[ClassVerdict] = []
    mutation_summaries: dict[str, dict[str, Any]] = {}
    for class_name, class_def in manifest["classes"].items():
        mutation = class_def["mutation"]
        seed = int(class_def["seed"])
        out_path = workdir_path / f"{class_name}_mutated.kicad_pcb"
        mutation_result = apply_mutation(
            board_path, mutation, class_def["params"], seed, out_path
        )
        # Same project-context propagation as the clean copy above -- every
        # scratch board this runner DRCs needs its own resolvable project.
        copy_kicad_project_sidecar(out_path, board_path)
        report_mutation = {
            "seed": seed,
            "mutated_sha256": mutation_result.mutated_sha256,
            "seed_board_sha256": mutation_result.seed_board_sha256,
            "summary": mutation_result.summary,
        }

        params = class_def["params"]
        measurement = ClassMeasurement(
            params=params,
            clean_containment_refs=clean_containment_refs,
            clean_creepage=clean_creepage,
        )

        if mutation == "creepage":
            if clean_creepage is None:
                class_verdicts.append(
                    ClassVerdict(
                        name=class_name,
                        ok=False,
                        gate_error=True,
                        message=(
                            "gate error: clean-board REQ-SAFE-01 baseline "
                            "unavailable, cannot assert the class delta"
                        ),
                    )
                )
                continue
            try:
                measurement.mutated_creepage = measure_creepage_dc_lv(out_path)
            except GateError as exc:
                class_verdicts.append(
                    ClassVerdict(
                        name=class_name,
                        ok=False,
                        gate_error=True,
                        message=f"gate error: {exc}",
                    )
                )
                continue
        elif mutation == "off-board":
            measurement.mutated_containment_refs = measure_containment(out_path)
            # Reported for context only -- the off-board class is NOT
            # asserted on DRC counts (they FALL when a component leaves the
            # board; see the module docstring).
            report_mutation["drc_delta"] = _drc_delta(
                clean_drc, drc_counts(measure_drc(out_path, dru_path))
            )
        elif mutation == "pad-short":
            ref, pad_a, pad_b = params["ref"], params["pad_a"], params["pad_b"]
            measurement.clean_pair_errors = errors_naming_pad_pair(
                clean_errors, ref, pad_a, pad_b
            )
            measurement.mutated_pair_errors = errors_naming_pad_pair(
                measure_drc(out_path, dru_path), ref, pad_a, pad_b
            )
        elif mutation == "clearance":
            ref_a, pad_a = params["ref"], params["pad"]
            ref_b, pad_b = params["anchor_ref"], params["anchor_pad"]
            measurement.clean_cross_pair_errors = errors_naming_two_pads(
                clean_errors, ref_a, pad_a, ref_b, pad_b
            )
            measurement.mutated_cross_pair_errors = errors_naming_two_pads(
                measure_drc(out_path, dru_path), ref_a, pad_a, ref_b, pad_b
            )
        elif mutation == "courtyard":
            ref_a, ref_b = params["ref"], params["anchor_ref"]
            measurement.clean_courtyard_pair_errors = errors_naming_both_refs(
                clean_errors, ref_a, ref_b
            )
            measurement.mutated_courtyard_pair_errors = errors_naming_both_refs(
                measure_drc(out_path, dru_path), ref_a, ref_b
            )
        elif mutation == "hole-to-hole":
            ref_a, ref_b = params["ref"], params["anchor_ref"]
            measurement.clean_hole_pair_errors = errors_of_type_naming_both_refs(
                clean_errors, "hole_to_hole", ref_a, ref_b
            )
            measurement.mutated_hole_pair_errors = errors_of_type_naming_both_refs(
                measure_drc(out_path, dru_path), "hole_to_hole", ref_a, ref_b
            )
        elif mutation == "missing-courtyard":
            ref = params["ref"]
            from board_defect_mutator import courtyard_item_count

            # Independent re-parse of both files -- injector self-
            # verification, decoupled from whatever the DRC gate does or
            # does not see (METHODOLOGY.md Sec. 5).
            measurement.clean_courtyard_item_count = courtyard_item_count(
                clean_copy, ref
            )
            measurement.mutated_courtyard_item_count = courtyard_item_count(
                out_path, ref
            )
            measurement.clean_missing_courtyard_errors = errors_of_type_naming_ref(
                clean_errors, "missing_courtyard", ref
            )
            measurement.mutated_missing_courtyard_errors = errors_of_type_naming_ref(
                measure_drc(out_path, dru_path), "missing_courtyard", ref
            )
        else:
            raise GateError(
                f"manifest class {class_name!r} has unknown mutation {mutation!r}"
            )

        class_verdicts.append(evaluate_class(class_name, mutation, measurement))
        mutation_summaries[class_name] = report_mutation

    # --- aggregate ---
    any_gate_error = any(v.gate_error for v in class_verdicts)
    any_uncovered = any(not v.ok and not v.gate_error for v in class_verdicts)
    anti_vacuity_ok = not anti_vacuity_violations
    ok = anti_vacuity_ok and not any_uncovered and not any_gate_error

    report = CorpusReport(
        ok=ok,
        exit_code=EXIT_GATE_ERROR if any_gate_error else (EXIT_PASS if ok else EXIT_CORPUS_FAIL),
        board_sha256=actual_board_hash,
        manifest_board_sha256=recorded_board_hash or "",
        board_matches_manifest=board_matches,
        clean_drc=clean_drc,
        clean_creepage_dc_lv=clean_creepage,
        clean_containment_refs=sorted(clean_containment_refs),
        anti_vacuity_violations=anti_vacuity_violations,
        class_verdicts=class_verdicts,
        mutation_summaries=mutation_summaries,
        workdir=str(workdir_path),
    )

    if update_manifest and ok and not board_matches and recorded_board_hash is not None:
        _stamp_manifest_hash(manifest_path, actual_board_hash)
        report.board_matches_manifest = True
        report.manifest_board_sha256 = actual_board_hash

    return report


def _stamp_manifest_hash(manifest_path: Path, board_sha256: str) -> None:
    """Rewrite the manifest's recorded board hash after a green run on a
    changed board -- the only manifest mutation the corpus performs.

    Deliberately a line-targeted replacement, NOT a yaml round-trip: the
    seed manifest's comments are load-bearing documentation (the
    defect-to-gate mapping notes and the creepage baseline_note), and
    ``yaml.safe_dump`` would drop every one of them.
    """
    import re

    text = manifest_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^(  board_sha256: )[0-9a-f]{64}$", re.MULTILINE)
    new_text, n = pattern.subn(rf"\g<1>{board_sha256}", text, count=1)
    if n != 1:
        raise GateError(
            f"could not stamp board_sha256 into {manifest_path.name}: the "
            "'  board_sha256: <64-hex>' line was not found"
        )
    manifest_path.write_text(new_text, encoding="utf-8")
    print(f"  [manifest] stamped board_sha256 {board_sha256} into {manifest_path.name}")


def _print_report(report: CorpusReport) -> None:
    print(f"board sha256: {report.board_sha256[:16]}...")
    if report.board_matches_manifest:
        print("  matches manifest seed hash (corpus validated against this board)")
    else:
        print(
            "  WARNING: committed board hash differs from the manifest's "
            "recorded hash -- board changed since the corpus was seeded; "
            "this run re-validates every seed. After a green run, stamp the "
            "new hash with --update-manifest."
        )
    print(f"clean-board DRC: {json.dumps(report.clean_drc)}")
    print(
        "clean-board DC_BUS<->LV_CONTROL creepage: "
        f"{report.clean_creepage_dc_lv if report.clean_creepage_dc_lv is not None else '<unavailable>'}"
    )
    print(
        "clean-board containment (refs with copper outside the outline): "
        f"{report.clean_containment_refs or 'none'}"
    )

    print("\nanti-vacuity control (clean board at/below recorded ceilings):")
    if report.anti_vacuity_violations:
        for violation in report.anti_vacuity_violations:
            print(f"  FAIL: {violation}")
    else:
        print("  PASS")

    print("\ndefect classes:")
    for verdict in report.class_verdicts:
        status = "GATE-ERROR" if verdict.gate_error else ("PASS" if verdict.ok else "FAIL")
        print(f"  [{status}] {verdict.name}: {verdict.message}")
        mut = report.mutation_summaries.get(verdict.name)
        if mut is not None:
            print(
                f"      mutation seed={mut['seed']} "
                f"mutated_sha256={mut['mutated_sha256'][:16]}... "
                f"seed+board_sha256={mut['seed_board_sha256'][:16]}... "
                f"summary={json.dumps(mut['summary'])}"
            )

    n_covered = sum(1 for v in report.class_verdicts if v.ok)
    n_total = len(report.class_verdicts)
    if report.ok:
        print(
            f"\nBoard-defect corpus: PASS -- {n_covered}/{n_total} classes "
            "covered, clean board green (mutated boards in "
            f"{report.workdir})"
        )
    else:
        print(
            f"\nBoard-defect corpus: FAIL -- {n_covered}/{n_total} classes "
            f"covered (mutated boards left in {report.workdir} for inspection)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--workdir", type=Path, default=None,
                        help="persistent directory for mutated boards (default: temp)")
    parser.add_argument("--update-manifest", action="store_true",
                        help="stamp the manifest's board_sha256 after a green "
                             "run on a changed board")
    args = parser.parse_args(argv)

    try:
        report = run_corpus(
            args.repo_root,
            manifest_path=args.manifest,
            workdir=args.workdir,
            update_manifest=args.update_manifest,
        )
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    _print_report(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
