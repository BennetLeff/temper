"""kicad-cli DRC JSON: every top-level key is accounted for, and the
`unconnected_items` blindness can never come back.

THE DEFECT
----------
``_drc_api._parse_drc_json`` read exactly one of kicad-cli's top-level
arrays -- ``violations`` -- and silently dropped the rest.  On the committed
board (``pcb/temper.kicad_pcb`` sha256 ``26981fea...``) the dropped
``unconnected_items`` array holds **339 entries**, every one of them
``severity: "error"``.  That is 339 of 718 real errors -- 47% -- invisible to
``power_pcb_dataset/drc_ceiling.json``, to ``scripts/ci_check_drc.py``, and to
every DRC comparison in every evidence document this project has produced.
The board's entire purpose is to be connected; the gate that exists to catch
regressions had never once seen a connectivity failure.

Nothing crashed.  The number was simply smaller than the truth, which is
indistinguishable from a good result.  That is why the demonstration below
runs the OLD parser as well as the new one: a fix to a silent under-report is
worthless unless you can show the instrument reading wrong first.

WHY THESE TESTS CANNOT BE VACUOUS
---------------------------------
``test_pre_fix_parser_is_blind_to_all_339_unconnected_items`` runs a verbatim
pin of the pre-fix parser body over a real, unedited kicad-cli report and
asserts it sees ZERO of the 339.  ``test_current_parser_sees_all_339...``
asserts the shipped parser sees all 339 over the SAME bytes.  If someone
reverts the fix, the second test fails.  If someone "fixes" it by editing the
fixture, the first test fails (the pin would stop reading 0) and so does the
key-registry audit.  If the kernel started dropping something else, the
per-category equality test fails.  The pre-fix pin is deliberately a copy of
the old body rather than a mock: a mock would prove only that mocks work.

The fixtures are three consecutive REAL kicad-cli runs, not synthesized JSON.
Conditions are recorded in ``fixtures/kicad_drc_reports/README.md`` and
restated in the constants below -- board sha256, kicad-cli version, flags,
thread pin, regenerated ``.kicad_dru``, ``fp-lib-table`` sibling.  Numbers
without those conditions are not measurements.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import pytest

from temper_placer.validation._drc_api import (
    _KNOWN_TOP_LEVEL_KEYS,
    _METADATA_KEYS,
    _VIOLATION_ARRAY_KEYS,
    DrcReportSchemaError,
    _parse_drc_json,
    drc_violation_key,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kicad_drc_reports"
RUN_PATHS = [FIXTURE_DIR / f"temper_26981fea_run{i}.json" for i in range(3)]

# --- Conditions under which every number in this file was measured ---------
BOARD_SHA256 = "26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b"
KICAD_CLI_VERSION = "10.0.5"

# --- The measurement -------------------------------------------------------
UNCONNECTED_ITEMS_COUNT = 339
VIOLATIONS_COUNT = 776
PRE_FIX_ERROR_COUNT = 379  # what every ratchet number this project recorded saw
POST_FIX_ERROR_COUNT = 718  # 379 + 339
WARNING_COUNT = 397  # unchanged by the fix: unconnected_items are all errors

# Of the 339: 290 name at least one owning footprint; the remaining 49 are
# Via/Track-to-Via misses -- bare copper with no owning component (82 Via and
# 16 Track item descriptions between them). Identical in all three runs.
UNCONNECTED_WITH_COMPONENT_REF = 290
UNCONNECTED_NET_OWNED_ONLY = 49

# Per-category error counts BEFORE the fix. The fix must leave every one of
# these untouched and add exactly one new key.
PRE_FIX_ERRORS_BY_TYPE = {
    "clearance": 179,
    "copper_edge_clearance": 11,
    "courtyards_overlap": 1,
    "creepage": 106,
    "drill_out_of_range": 6,
    "hole_clearance": 33,
    "shorting_items": 39,
    "solder_mask_bridge": 4,
}
WARNINGS_BY_TYPE = {
    "lib_footprint_issues": 13,
    "lib_footprint_mismatch": 26,
    "missing_courtyard": 5,
    "silk_edge_clearance": 1,
    "silk_over_copper": 42,
    "silk_overlap": 199,  # SATURATED at ERROR_LIMIT -- a floor, not a count
    "via_dangling": 111,
}

# kicad-cli 10.0.5 emits exactly these top-level keys on this board.
OBSERVED_TOP_LEVEL_KEYS = {
    "$schema",
    "coordinate_units",
    "date",
    "ignored_checks",
    "included_severities",
    "kicad_version",
    "schematic_parity",
    "source",
    "unconnected_items",
    "violations",
}

IGNORED_CHECKS = [
    "track_not_centered_on_via",
    "tuning_profile_track_geometries",
    "footprint_filters_mismatch",
    "footprint_type_mismatch",
]


# ---------------------------------------------------------------------------
# The pre-fix parser, pinned verbatim.
# ---------------------------------------------------------------------------
def _pre_fix_parse_drc_json(json_path: Path):
    """VERBATIM pin of ``_parse_drc_json``'s body as it stood at
    origin/main e63028ccd, immediately before the 2026-08-19 fix.

    Do NOT "update" this to match the current parser -- it is the arm of the
    comparison that shows the instrument reading wrong.  Editing it to agree
    with the fixed parser turns this whole file into a tautology.

    The only line that matters is the one that reads ``data.get("violations",
    [])`` and nothing else.
    """
    import temper_drc_rs as _tdrc

    from temper_placer.validation._drc_api import DrcError, DrcResult, DrcWarning

    with open(json_path) as f:
        data = json.load(f)

    error_records, warning_records = _tdrc.drc_parse_violations(data.get("violations", []))

    errors = [
        DrcError(
            rule=r["rule"],
            severity=r["severity"],
            location=r["location"],
            message=r["message"],
            components=r["components"],
            nets=r["nets"],
            items=r["items"],
        )
        for r in error_records
    ]
    warnings = [
        DrcWarning(
            rule=r["rule"],
            severity=r["severity"],
            location=r["location"],
            message=r["message"],
            components=r["components"],
            nets=r["nets"],
        )
        for r in warning_records
    ]
    return DrcResult(
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
    )


def _by_type(items) -> dict[str, int]:
    return dict(collections.Counter(i.rule for i in items))


@pytest.fixture(params=[0, 1, 2], ids=["run0", "run1", "run2"])
def report_path(request) -> Path:
    return RUN_PATHS[request.param]


# ---------------------------------------------------------------------------
# 1. The fixtures really are what this file says they are.
# ---------------------------------------------------------------------------
def test_fixtures_are_real_kicad_cli_reports_for_the_committed_board(report_path):
    """Anti-vacuity floor: if the fixtures were hand-written or stale, every
    number below would be fiction. Pin the instrument's own self-report."""
    data = json.loads(report_path.read_text())
    assert data["$schema"] == "https://schemas.kicad.org/drc.v1.json"
    assert data["kicad_version"] == KICAD_CLI_VERSION
    assert data["source"] == "temper.kicad_pcb"
    assert data["coordinate_units"] == "mm"


def test_fixture_board_is_still_the_board_these_numbers_were_measured_on():
    """The pinned counts describe board ``26981fea...``. If the committed
    board moves, this fails FIRST -- so nobody reads a stale number as a
    current one. Re-measure with conditions attached; do not edit constants."""
    import hashlib

    repo_root = Path(__file__).resolve().parents[4]
    board = repo_root / "pcb" / "temper.kicad_pcb"
    if not board.exists():  # pragma: no cover - board is committed
        pytest.skip(f"board not found at {board}")
    digest = hashlib.sha256(board.read_bytes()).hexdigest()
    assert digest == BOARD_SHA256, (
        f"pcb/temper.kicad_pcb is now {digest}, but the counts pinned in this "
        f"file were measured on {BOARD_SHA256}. Re-measure them (3 runs, "
        f"--all-track-errors, thread-pinned, regenerated pcb/temper.kicad_dru, "
        f"fp-lib-table present) and state the new conditions -- do not just "
        f"edit the numbers."
    )


# ---------------------------------------------------------------------------
# 2. THE BLINDNESS DEMONSTRATION.
# ---------------------------------------------------------------------------
def test_the_board_really_has_339_unconnected_items(report_path):
    """Establish the ground truth the pre-fix parser was blind to, straight
    from the instrument's own bytes -- no parser involved."""
    data = json.loads(report_path.read_text())
    assert len(data["unconnected_items"]) == UNCONNECTED_ITEMS_COUNT
    assert {v["type"] for v in data["unconnected_items"]} == {"unconnected_items"}
    assert {v["severity"] for v in data["unconnected_items"]} == {"error"}


def test_pre_fix_parser_is_blind_to_all_339_unconnected_items(report_path):
    """THE DEFECT, reproduced. The parser every DRC number in this project
    was produced by returns ZERO unconnected_items for a board that has 339
    of them, and an error_count 339 too low."""
    result = _pre_fix_parse_drc_json(report_path)

    seen = [e for e in result.errors if e.rule == "unconnected_items"]
    assert seen == [], "pre-fix pin is no longer blind -- it has been edited"
    assert "unconnected_items" not in _by_type(result.errors)
    assert result.error_count == PRE_FIX_ERROR_COUNT


def test_current_parser_sees_all_339_unconnected_items(report_path):
    """THE FIX. Same bytes, same kernel, 339 errors that were invisible."""
    result = _parse_drc_json(report_path)

    seen = [e for e in result.errors if e.rule == "unconnected_items"]
    assert len(seen) == UNCONNECTED_ITEMS_COUNT
    assert result.error_count == POST_FIX_ERROR_COUNT
    assert result.error_count - PRE_FIX_ERROR_COUNT == UNCONNECTED_ITEMS_COUNT


def test_unconnected_items_are_parsed_as_real_violations_not_placeholders(report_path):
    """Counting them is not enough -- a category that arrives as 339 empty
    shells is its own kind of lie. Every one must carry the component refs,
    net and item descriptions the rest of the pipeline consumes."""
    result = _parse_drc_json(report_path)
    seen = [e for e in result.errors if e.rule == "unconnected_items"]

    assert all(e.severity == "error" for e in seen)
    assert all(e.message == "Missing connection between items" for e in seen)
    assert all(len(e.items) >= 2 for e in seen), "a missing connection has >= 2 endpoints"
    assert all(e.location != (0.0, 0.0) for e in seen)

    # Every one resolves a net name -- an unconnected item is by definition a
    # net that did not close.
    assert all(e.nets for e in seen)

    # 290 of the 339 resolve at least one owning component ref; the other 49
    # are Via/Track-to-Via misses, which are net-owned rather than owned by a
    # single footprint. That is correct extraction behaviour (see
    # _extract_ref_from_item_description), not a parse failure -- so assert
    # the measured split rather than a blanket "every one has a component",
    # which would be false and would invite someone to weaken the check.
    with_components = [e for e in seen if e.components]
    without_components = [e for e in seen if not e.components]
    assert len(with_components) == UNCONNECTED_WITH_COMPONENT_REF
    assert len(without_components) == UNCONNECTED_NET_OWNED_ONLY
    assert all(
        item.startswith(("Via ", "Track ")) for e in without_components for item in e.items
    ), "a component-less unconnected item must be bare copper, never a dropped ref"


# ---------------------------------------------------------------------------
# 3. THE CORRECTNESS BAR: no existing category may move.
# ---------------------------------------------------------------------------
def test_fix_adds_unconnected_items_and_changes_nothing_else(report_path):
    """Diff the violation SETS, not the totals (AGENTS.md). Every pre-existing
    error and warning must survive the change byte-for-byte; the ONLY
    difference is the arrival of the unconnected_items category."""
    before = _pre_fix_parse_drc_json(report_path)
    after = _parse_drc_json(report_path)

    def as_multiset(items):
        return collections.Counter(
            (i.rule, i.severity, i.message, i.location, tuple(i.components), tuple(i.nets))
            for i in items
        )

    added = as_multiset(after.errors) - as_multiset(before.errors)
    removed = as_multiset(before.errors) - as_multiset(after.errors)
    assert removed == collections.Counter(), "the fix must not drop any existing violation"
    assert {rule for (rule, *_rest) in added} == {"unconnected_items"}
    assert sum(added.values()) == UNCONNECTED_ITEMS_COUNT

    # Warnings are untouched entirely -- all 339 are errors.
    assert as_multiset(after.warnings) == as_multiset(before.warnings)
    assert after.warning_count == before.warning_count == WARNING_COUNT


def test_per_category_counts_are_exactly_the_pinned_measurement(report_path):
    """Named numbers, so a silent shift in ANY category is a test failure
    rather than a footnote in someone's next investigation."""
    result = _parse_drc_json(report_path)
    expected_errors = dict(PRE_FIX_ERRORS_BY_TYPE)
    expected_errors["unconnected_items"] = UNCONNECTED_ITEMS_COUNT

    assert _by_type(result.errors) == expected_errors
    assert _by_type(result.warnings) == WARNINGS_BY_TYPE


def test_silk_overlap_199_is_a_saturation_floor_not_a_count():
    """Guard against the pinned 199 above being read as a measurement.
    ERROR_LIMIT is 199; a category at exactly its cap is a floor."""
    from temper_placer.validation._drc_api import drc_count_from_kicad

    info = drc_count_from_kicad(WARNINGS_BY_TYPE["silk_overlap"], "silk_overlap")
    assert info.is_capped

    # The new category is NOT saturated: its cap is EXTENDED_ERROR_LIMIT (499)
    # and it reads 339, so 339 is a true count.
    unconnected = drc_count_from_kicad(UNCONNECTED_ITEMS_COUNT, "unconnected_items")
    assert unconnected.is_honest


# ---------------------------------------------------------------------------
# 4. THE GENERALIZABLE DEFECT: no section may be silently dropped again.
# ---------------------------------------------------------------------------
def test_key_registry_covers_every_key_kicad_cli_actually_emits(report_path):
    """The registry is the whole point: `unconnected_items` was dropped for
    the life of the project because nothing enumerated what kicad-cli sends.
    If a future kicad-cli adds a key, this fails and somebody classifies it."""
    emitted = set(json.loads(report_path.read_text()))
    assert emitted == OBSERVED_TOP_LEVEL_KEYS
    assert emitted <= _KNOWN_TOP_LEVEL_KEYS
    unclassified = emitted - _KNOWN_TOP_LEVEL_KEYS
    assert unclassified == set(), f"top-level keys nothing consumes: {sorted(unclassified)}"


def test_registry_is_partitioned_not_overlapping():
    assert set(_VIOLATION_ARRAY_KEYS).isdisjoint(_METADATA_KEYS)
    assert set(_VIOLATION_ARRAY_KEYS) | _METADATA_KEYS == _KNOWN_TOP_LEVEL_KEYS


def test_unknown_top_level_key_fails_closed(tmp_path):
    """A section this parser does not understand must be LOUD, not dropped."""
    path = tmp_path / "drc.json"
    path.write_text(json.dumps({"violations": [], "some_future_array": [{"type": "x"}]}))
    with pytest.raises(DrcReportSchemaError) as excinfo:
        _parse_drc_json(path)
    assert "some_future_array" in str(excinfo.value)


def test_violation_array_key_order_matches_the_rest_of_the_repo():
    """`violations` then `unconnected_items` is the order every other reader
    in this repo already used (deterministic/feedback/drc_parser.py,
    placer/cp_sat/gates.py, temper-drc-rs violation_contracts.rs::DrcReport).
    _parse_drc_json was the one reader that never got the merge."""
    assert _VIOLATION_ARRAY_KEYS[0] == "violations"
    assert _VIOLATION_ARRAY_KEYS[1] == "unconnected_items"


def test_schematic_parity_array_is_consumed_when_non_empty(tmp_path):
    """`schematic_parity` reads 0 on every report this repo produces -- NOT
    because the board is clean but because `run_drc` never passes kicad-cli's
    `--schematic-parity` flag. That makes a real-board assertion vacuous, so
    prove consumption on a synthesized entry instead: the array must not be
    another silently-dropped section waiting for someone to enable the flag."""
    path = tmp_path / "drc.json"
    path.write_text(
        json.dumps(
            {
                "violations": [],
                "unconnected_items": [],
                "schematic_parity": [
                    {
                        "description": "Missing footprint for symbol R99",
                        "items": [{"description": "Footprint R99", "pos": {"x": 1.0, "y": 2.0}}],
                        "severity": "error",
                        "type": "footprint",
                    }
                ],
            }
        )
    )
    result = _parse_drc_json(path)
    assert result.error_count == 1
    assert result.errors[0].rule == "footprint"
    assert result.errors[0].components == ["R99"]


def test_ignored_checks_are_surfaced_so_not_measured_cannot_read_as_clean(report_path):
    """kicad-cli disables four checks on this board. An empty category from a
    disabled check is indistinguishable from a clean one unless the consumer
    can see the check never ran."""
    result = _parse_drc_json(report_path)
    assert result.ignored_checks == IGNORED_CHECKS
    assert result.included_severities == ["error", "warning"]


def test_a_report_missing_optional_arrays_still_parses(tmp_path):
    """Backwards compatibility: the many hand-written {"violations": [...]}
    fixtures across this repo must keep working."""
    path = tmp_path / "drc.json"
    path.write_text(json.dumps({"violations": []}))
    result = _parse_drc_json(path)
    assert result.error_count == 0
    assert result.warning_count == 0
    assert result.ignored_checks == []


# ---------------------------------------------------------------------------
# 5. THE SIBLING DEFECT: kicad-cli synthesizes item uuids.
# ---------------------------------------------------------------------------
def test_kicad_cli_synthesizes_uuids_the_board_file_does_not_carry():
    """The board declares 10 uuids. One report references 825 distinct item
    uuids, and only 291 of them recur across all three runs. Anything keyed on
    uuid is keyed on a number kicad-cli invented this run."""
    repo_root = Path(__file__).resolve().parents[4]
    board = repo_root / "pcb" / "temper.kicad_pcb"
    if not board.exists():  # pragma: no cover
        pytest.skip("board not found")

    board_uuids = set(re.findall(r'\(uuid "([0-9a-f-]+)"\)', board.read_text()))
    assert len(board_uuids) == 10

    per_run = []
    for path in RUN_PATHS:
        data = json.loads(path.read_text())
        per_run.append(
            {
                item["uuid"]
                for key in ("violations", "unconnected_items")
                for v in data[key]
                for item in v["items"]
                if "uuid" in item
            }
        )

    assert all(len(s) == 825 for s in per_run)
    assert len(per_run[0] & per_run[1] & per_run[2]) == 291
    # The overwhelming majority are invented per run.
    assert len(per_run[0] - board_uuids) > 800


@pytest.mark.parametrize("array_name", ["violations", "unconnected_items"])
def test_uuid_keying_manufactures_nondeterminism_on_a_deterministic_board(array_name):
    """Same three reports, two keys, opposite verdicts.

    Keyed on uuid the board looks broken; keyed on ``drc_violation_key`` it is
    perfectly stable. Whichever future comparison gets written, this test says
    which of the two answers is the artefact."""
    runs = [json.loads(p.read_text()) for p in RUN_PATHS]

    def stability(keyfunc):
        counters = [collections.Counter(keyfunc(v) for v in d[array_name]) for d in runs]
        intersection = counters[0] & counters[1] & counters[2]
        union = counters[0] | counters[1] | counters[2]
        return sum(intersection.values()), sum(union.values()) - sum(intersection.values())

    def uuid_key(v):
        return (v["type"], v["description"], tuple(sorted(i["uuid"] for i in v["items"])))

    uuid_stable, uuid_unstable = stability(uuid_key)
    safe_stable, safe_unstable = stability(drc_violation_key)

    expected_total = {"violations": VIOLATIONS_COUNT, "unconnected_items": UNCONNECTED_ITEMS_COUNT}[
        array_name
    ]

    # The safe key: fully deterministic, every entry present in all 3 runs.
    assert (safe_stable, safe_unstable) == (expected_total, 0)
    # The uuid key: manufactured instability on the very same bytes.
    assert uuid_unstable > 0
    assert uuid_stable < safe_stable


def test_drc_violation_key_ignores_uuid_entirely():
    """Directly: two reports of the same violation with different synthesized
    uuids are the same violation."""
    a = {
        "type": "clearance",
        "description": "Clearance violation",
        "items": [{"description": "Pad 1 of R1", "pos": {"x": 1.0, "y": 2.0}, "uuid": "aaa"}],
    }
    b = json.loads(json.dumps(a))
    b["items"][0]["uuid"] = "zzz-completely-different"
    assert drc_violation_key(a) == drc_violation_key(b)


def test_drc_violation_key_normalizes_the_shorting_items_net_swap():
    """AGENTS.md's documented trap: kicad-cli renders the net pair in either
    order. 39 of this board's violations carry such a pair and 4 actually swap
    across three runs -- without this normalization the board reads 774/4
    instead of 776/0."""
    a = {
        "type": "shorting_items",
        "description": "Items shorting two nets (nets gnd and rtd_sense_p)",
        "items": [],
    }
    b = {
        "type": "shorting_items",
        "description": "Items shorting two nets (nets rtd_sense_p and gnd)",
        "items": [],
    }
    assert drc_violation_key(a) == drc_violation_key(b)

    # ...and does not collapse genuinely different shorts.
    c = {
        "type": "shorting_items",
        "description": "Items shorting two nets (nets gnd and vcc)",
        "items": [],
    }
    assert drc_violation_key(a) != drc_violation_key(c)


def test_drc_violation_key_distinguishes_different_positions():
    """Anti-vacuity for the key itself: it must not be so lossy that two
    different violations collide (which would make any set diff read clean)."""
    a = {
        "type": "clearance",
        "description": "Clearance violation",
        "items": [{"description": "Via [gnd] on F.Cu", "pos": {"x": 1.0, "y": 2.0}}],
    }
    b = json.loads(json.dumps(a))
    b["items"][0]["pos"]["x"] = 99.0
    assert drc_violation_key(a) != drc_violation_key(b)
