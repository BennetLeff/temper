"""U8 anti-false-zero provenance checks for via-aware routed boards.

The fail-closed measurement validator was moved here from
``temper_placer.router_v6.audit_provenance`` (retired 2026-08-11: it had no
production consumers -- the schema it validates matches no committed evidence
file). It is deliberately small and fail-closed: a missing, malformed, or
unmeasured record is never evidence that routing is clean. Connectivity is
compared against the declared pre-U1 baseline, because the production board
already carries known multi-pad-net disconnects outside the via-transition
workstream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[4]


class MeasurementRecordError(ValueError):
    """Raised when a routing measurement cannot prove what it claims."""


_BOARD_NAMES = frozenset(("corpus", "production"))
_MEASURED_GATE_STATUSES = frozenset(("CLEAN", "VIOLATIONS"))


def _load_record(record_or_path: object) -> object:
    if isinstance(record_or_path, Path):
        try:
            return json.loads(record_or_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MeasurementRecordError(f"Cannot read routing measurement record: {exc}") from exc
    return record_or_path


def _require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MeasurementRecordError(f"{name} must be an object")
    return value


def validate_via_routing_measurement(record_or_path: object) -> dict[str, Any]:
    """Validate the U8 measurement schema and fail on unmeasured gate output.

    A ``VIOLATIONS`` status is valid evidence: it reports a real measurement
    without disguising an unresolved physical problem as clean.  In contrast,
    ``UNMEASURED`` is rejected because it offers no routing truth at all.
    """
    record = _require_mapping(_load_record(record_or_path), "measurement record")
    if record.get("schema_version") != 1:
        raise MeasurementRecordError("schema_version must be 1")

    boards = _require_mapping(record.get("boards"), "boards")
    if set(boards) != _BOARD_NAMES:
        raise MeasurementRecordError(
            f"boards must be exactly {sorted(_BOARD_NAMES)}, got {sorted(boards)}"
        )

    for board_name in sorted(_BOARD_NAMES):
        board = _require_mapping(boards[board_name], f"boards.{board_name}")
        completion = board.get("completion_rate")
        if not isinstance(completion, (int, float)) or completion != 1.0:
            raise MeasurementRecordError(f"boards.{board_name}.completion_rate must be exactly 1.0")
        baseline_unconnected = board.get("baseline_unconnected_items")
        if (
            not isinstance(baseline_unconnected, int)
            or isinstance(baseline_unconnected, bool)
            or baseline_unconnected < 0
        ):
            raise MeasurementRecordError(
                f"boards.{board_name}.baseline_unconnected_items must be a non-negative integer"
            )
        unconnected = board.get("unconnected_items")
        if not isinstance(unconnected, int) or isinstance(unconnected, bool) or unconnected < 0:
            raise MeasurementRecordError(
                f"boards.{board_name}.unconnected_items must be a non-negative integer"
            )
        if unconnected > baseline_unconnected:
            raise MeasurementRecordError(
                f"boards.{board_name}.unconnected_items ({unconnected}) exceeds "
                f"the pre-U1 baseline ({baseline_unconnected})"
            )
        if board.get("contains_vias") is not True:
            raise MeasurementRecordError(f"boards.{board_name}.contains_vias must be true")
        counts = _require_mapping(board.get("drc_counts"), f"boards.{board_name}.drc_counts")
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in counts.values()
        ):
            raise MeasurementRecordError(
                f"boards.{board_name}.drc_counts must contain non-negative integers"
            )
        gates = _require_mapping(board.get("gates"), f"boards.{board_name}.gates")
        if set(gates) != {"clearance", "iec_creepage"}:
            raise MeasurementRecordError(
                f"boards.{board_name}.gates must contain clearance and iec_creepage"
            )
        for gate_name, status in gates.items():
            if status not in _MEASURED_GATE_STATUSES:
                raise MeasurementRecordError(
                    f"boards.{board_name}.gates.{gate_name} is {status!r}; "
                    "UNMEASURED or unknown statuses are not evidence"
                )
    return record


def _valid_record() -> dict:
    return {
        "schema_version": 1,
        "boards": {
            "corpus": {
                "completion_rate": 1.0,
                "baseline_unconnected_items": 0,
                "unconnected_items": 0,
                "contains_vias": True,
                "drc_counts": {"clearance": 1},
                "gates": {"clearance": "VIOLATIONS", "iec_creepage": "CLEAN"},
            },
            "production": {
                "completion_rate": 1.0,
                "baseline_unconnected_items": 149,
                "unconnected_items": 149,
                "contains_vias": True,
                "drc_counts": {"shorting_items": 2},
                "gates": {"clearance": "VIOLATIONS", "iec_creepage": "VIOLATIONS"},
            },
        },
    }


def test_measurement_requires_real_gate_results_and_nonregressing_connectivity() -> None:
    """A record cannot hide worsening DRC connectivity behind completion."""
    validate_via_routing_measurement(_valid_record())

    invalid = _valid_record()
    invalid["boards"]["corpus"]["gates"]["clearance"] = "UNMEASURED"
    with pytest.raises(MeasurementRecordError, match="UNMEASURED"):
        validate_via_routing_measurement(invalid)

    invalid = _valid_record()
    invalid["boards"]["production"]["unconnected_items"] = 150
    with pytest.raises(MeasurementRecordError, match="exceeds"):
        validate_via_routing_measurement(invalid)


@given(
    st.one_of(
        st.none(),
        st.text(),
        st.dictionaries(st.text(), st.integers()),
        st.lists(st.integers()),
    )
)
def test_measurement_record_pbt_rejects_malformed_top_level_payloads(payload: object) -> None:
    """Malformed provenance payloads never become a false clean measurement."""
    with pytest.raises(MeasurementRecordError):
        validate_via_routing_measurement(payload)


def test_committed_u8_measurement_record_is_well_formed() -> None:
    """The audit evidence is a checked artifact, not a prose-only claim.

    The U8 via-aware measurement was committed as
    ``docs/evidence/2026-07-20-via-aware-U8-kicad-drc.json`` (commit
    e5c6b29f3) with a flat schema (`pre_u7_baseline`/`post_u7_measurement`/
    `verdict`/`provenance`) rather than the ``schema_version``/``boards``
    schema ``validate_via_routing_measurement`` validates (that schema
    matches no committed evidence file; the test's in-memory ``_valid_record``
    fixture is its only conforming example). An earlier version of this test
    asserted existence of ``2026-07-19-via-aware-routing-u8.json``, a file
    that has never existed in this repo's git history at all (triaged in
    docs/evidence/2026-07-28-pad-geometry-model-fix.md); this version checks
    the artifact that actually exists, against the schema it actually uses.
    """
    record_path = REPO_ROOT / "docs" / "evidence" / "2026-07-20-via-aware-U8-kicad-drc.json"
    assert record_path.exists(), f"Missing U8 measurement record: {record_path}"

    with open(record_path) as f:
        record = json.load(f)

    # Anti-false-zero: the committed record must prove the real measurement,
    # not just exist as bytes. Every field below is load-bearing evidence
    # (docs/METHODOLOGY.md Sec 5); a prose-only or placeholder file fails.
    assert record.get("unit") == "U8"
    assert record.get("measurement_date") == "2026-07-20"
    assert record.get("board") == "pcb/temper.kicad_pcb"
    assert record.get("kicad_cli_version"), "missing kicad_cli_version"

    pre = record.get("pre_u7_baseline") or {}
    post = record.get("post_u7_measurement") or {}
    assert pre.get("unconnected_items") == 149
    assert post.get("unconnected_items") == 0
    assert "149" in record.get("verdict", "") and "0" in record.get("verdict", "")

    # The provenance block is the "checked artifact" claim: a record without
    # provenance is not a record. (Its values are UNKNOWN -- backfilled before
    # the provenance gate existed -- but the block itself must be present.)
    assert isinstance(record.get("provenance"), dict)
