"""Tests for check_derived_doc_drift.py.

Two groups matter most here (see docs/evidence/2026-07-26-derived-document-drift-gate.md
for the full write-up):

1. `TestHistoricalDefectReconstruction` -- rebuilds each of the four
   real 2026-07-26 incidents against small, isolated fixtures (not the
   live repo docs, which are edited concurrently by other agents today)
   and asserts the gate fails, naming the specific missing field.
2. `TestAntiVacuity` -- asserts the gate fails CLOSED (state ==
   "tool_error", never "clean") on every degenerate input: missing
   config, missing source doc, empty documents, zero tables parsed,
   zero gates configured, and ambiguous or absent row matches.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_derived_doc_drift import (
    extract_tables,
    measure_board,
    normalize,
    parse_claimed_int,
    run,
)

SOURCE_MD = """\
# Functional Test Criteria (fixture)

## 2. Protection Circuit Validation

### 2.1 Over-Current Protection (OCP)

| Parameter | Setting | Trip Threshold | Response Time |
|-----------|---------|----------------|----------------|
| **Primary OCP** | 50A Peak | **45 - 55 A** | **< 1 µs** |

### 2.2 Over-Voltage Protection (OVP)

| Parameter | Setting | Trip Threshold | Hysteresis |
|-----------|---------|----------------|------------|
| **DC Bus OVP** | 400V | **390 - 410 V** | **10 - 20 V** |

### 2.4 Under-Voltage Lockout (UVLO)

| Rail | Trip Threshold (Falling) | Recovery (Rising) |
|------|---------------------------|--------------------|
| **Logic (3.3V)** | **< 2.9 V** | **> 3.0 V** |
"""

BASE_CONFIG = {
    "source_document": "source.md",
    "derived_documents": [{"path": "derived.md", "gates": "all"}],
    "gates": {
        "OCP-01": {
            "source_row_locator": ["Primary OCP"],
            "required_fields": [
                {"name": "basis", "any_of": ["peak"]},
                {"name": "trip_threshold", "any_of": ["45-55"]},
            ],
        },
        "OVP-01": {
            "source_row_locator": ["DC Bus OVP"],
            "required_fields": [
                {"name": "trip_threshold", "any_of": ["390-410"]},
                {"name": "hysteresis_label", "any_of": ["hysteresis"]},
                {"name": "hysteresis_value", "any_of": ["10-20"]},
            ],
        },
        "UVL-02": {
            "source_row_locator": ["Logic (3.3V)"],
            "required_fields": [
                {"name": "falling_label", "any_of": ["falling"]},
                {"name": "falling_value", "any_of": ["2.9"]},
                {"name": "rising_label", "any_of": ["rising"]},
                {"name": "rising_value", "any_of": ["3.0"]},
            ],
        },
    },
}


# A miniature but structurally real .kicad_pcb. Counts are deliberately
# small and all different so an off-by-one or a swapped metric is visible:
#   footprints=3  nets=2  segments=4  vias=1  zones=2  copper_layers=2
# Note there are 12 `(net ` substrings in this text (2 declarations + 3 pad
# refs + 4 segment refs + 1 via ref + 2 zone refs). The gate must report 2.
PCB_MD = """\
(kicad_pcb
  (version 20221018)
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user)
  )
  (net 1 "GND")
  (net 2 "VCC")
  (footprint "R_0603" (layer "F.Cu")
    (pad "1" smd rect (net 1 "GND"))
  )
  (footprint "C_0603" (layer "F.Cu")
    (pad "1" smd rect (net 1 "GND"))
  )
  (footprint "U_SOIC8" (layer "F.Cu")
    (pad "1" smd rect (net 2 "VCC"))
  )
  (segment (start 0 0) (end 1 0) (net 1))
  (segment (start 1 0) (end 2 0) (net 1))
  (segment (start 2 0) (end 3 0) (net 2))
  (segment (start 3 0) (end 4 0) (net 2))
  (via (at 1 1) (net 1))
  (zone (net 1) (net_name "GND") (layer "F.Cu"))
  (zone (net 1) (net_name "GND") (layer "B.Cu"))
)
"""

BOARD_DOC_MD = """\
# Board fixture

<!-- BOARD-FACTS-TABLE -->

| Board fact | As committed |
|---|---|
| Footprints | **3** |
| Net declarations | **2** |
| Segments | **4** |

As of 2026-07-01 the board carried no routing. Superseded: it was routed later.
"""

FAITHFUL_DERIVED_MD = """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V falling / >3.0V rising | SS2.4 |
"""

BOARD_FACTS_CFG = {
    "pcb": "board.kicad_pcb",
    "doc": "board.md",
    "anchor": "BOARD-FACTS-TABLE",
    "rows": {
        "footprints": {"label": "Footprints"},
        "nets": {"label": "Net declarations"},
        "segments": {"label": "Segments"},
    },
}

STALE_BOARD_CFG = [
    {
        "id": "board-unrouted-prose",
        "doc": "board.md",
        "patterns": ["no routing"],
        "required_mitigating_tokens": ["superseded", "as of 2026-07"],
        "message": "unrouted claim must be dated",
    }
]

BASE_CONFIG["board_facts"] = BOARD_FACTS_CFG
BASE_CONFIG["stale_board_claims"] = STALE_BOARD_CFG


def _write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text)


def _write_config(root: Path, cfg: dict) -> Path:
    p = root / "config.yaml"
    p.write_text(yaml.dump(cfg))
    return p


def _write_board_fixtures(root: Path) -> None:
    """Default board arm fixtures.

    `run()` requires a `board_facts:` section, so every test that exercises
    the `gates:` arm needs a satisfiable board arm to isolate against.
    Written only when absent, so board-arm tests can install their own
    mutated versions first.
    """
    if not (root / "board.kicad_pcb").exists():
        _write(root, "board.kicad_pcb", PCB_MD)
    if not (root / "board.md").exists():
        _write(root, "board.md", BOARD_DOC_MD)


def _run(tmp_path: Path, cfg: dict):
    _write_board_fixtures(tmp_path)
    config_path = _write_config(tmp_path, cfg)
    return run(config_path, tmp_path)


def _find(report, gate: str, field_name: str):
    return [v for v in report.violations if v.gate == gate and v.field == field_name]


class TestHistoricalDefectReconstruction:
    """Each test reproduces one of the four real 2026-07-26 incidents."""

    def test_faithful_restatement_passes(self, tmp_path):
        """Control: a derived table that keeps every qualifier passes clean."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V falling / >3.0V rising | SS2.4 |
""",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "clean", [(e.where, e.reason) for e in report.tool_errors] + [
            (v.gate, v.field) for v in report.violations
        ]
        assert report.fields_checked > 0
        assert report.tool_errors == []
        assert report.violations == []

    def test_case_1_ocp01_peak_qualifier_dropped(self, tmp_path):
        """Historical case: "50A Peak" -> "45-55A" drops the peak/RMS basis.

        This was resolved as a full-blown "spec ambiguity" investigation
        (peak-vs-RMS) in STRATEGY.md before anyone noticed the qualifier
        was in the source the whole time.
        """
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V falling / >3.0V rising | SS2.4 |
""",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        hits = _find(report, "OCP-01", "basis")
        assert len(hits) == 1, "expected exactly one violation naming OCP-01's 'basis' field"
        assert "peak" in [a.lower() for a in hits[0].expected_any_of]
        # The other two gates must NOT be implicated -- field-level, not
        # document-level.
        assert _find(report, "OVP-01", "hysteresis_label") == []
        assert _find(report, "UVL-02", "falling_label") == []

    def test_case_2_ovp01_hysteresis_column_dropped(self, tmp_path):
        """Historical case: the entire Hysteresis column vanished from the
        derived row. OVP-01 was "fixed" with no hysteresis resistor at all
        because the requirement was invisible when the value was chosen."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V falling / >3.0V rising | SS2.4 |
""",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        label_hits = _find(report, "OVP-01", "hysteresis_label")
        value_hits = _find(report, "OVP-01", "hysteresis_value")
        assert len(label_hits) == 1, "must name the missing 'hysteresis_label' field"
        assert len(value_hits) == 1, "must name the missing 'hysteresis_value' field"
        assert _find(report, "OCP-01", "basis") == []

    def test_case_3_uvl02_direction_altered_and_dropped(self, tmp_path):
        """Historical case: UVL-02's rising/falling threshold direction and
        the entire Recovery column collapsed into a single undirected
        "<2.9V", reversing a reviewer's verdict on a marginal part."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V | SS2.4 |
""",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        assert len(_find(report, "UVL-02", "falling_label")) == 1
        assert len(_find(report, "UVL-02", "rising_label")) == 1
        assert len(_find(report, "UVL-02", "rising_value")) == 1

    def test_case_4_stale_fixed_verdict_not_reconciled(self, tmp_path):
        """Historical case: docs/STRATEGY.md's audit table marked OVP-01
        "FIXED" at 399.88V in a row that a later section of the SAME
        document showed lacked the required hysteresis network. The
        "FIXED" row was never corrected to say so."""
        cfg = dict(BASE_CONFIG)
        # This fixture's derived.md carries a second ("audit") table with
        # its own OVP-01 row, so the field-level check must be scoped to
        # the summary table by header -- same reason the real config
        # scopes docs/STRATEGY.md this way.
        cfg["derived_documents"] = [
            {
                "path": "derived.md",
                "gates": "all",
                "header_contains": ["Description", "Reference"],
            }
        ]
        cfg["consistency_checks"] = [
            {
                "id": "ovp01-stale-verdict",
                "gate": "OVP-01",
                "doc": "derived.md",
                "row_locator": ["OVP-01", "399.88"],
                "stale_tokens": ["FIXED"],
                "required_mitigating_tokens": ["no hysteresis", "hysteresis absent"],
                "message": "OVP-01 marked FIXED without acknowledging missing hysteresis",
            }
        ]
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V falling / >3.0V rising | SS2.4 |

| Gate | Requirement | Measured | Verdict |
|---|---|---|---|
| OVP-01 | 390-410 V | 399.88 V | FIXED |
""",
        )
        state, report = _run(tmp_path, cfg)
        assert state == "drift"
        stale_hits = [v for v in report.violations if v.kind == "stale_verdict"]
        assert len(stale_hits) == 1
        assert stale_hits[0].gate == "OVP-01"

    def test_case_4_control_mitigated_verdict_passes(self, tmp_path):
        """Same stale claim, but the row now acknowledges the missing
        hysteresis -- must NOT be flagged (this is what "corrected" looks
        like, and the check must not fire once it's true)."""
        cfg = dict(BASE_CONFIG)
        cfg["derived_documents"] = [
            {
                "path": "derived.md",
                "gates": "all",
                "header_contains": ["Description", "Reference"],
            }
        ]
        cfg["consistency_checks"] = [
            {
                "id": "ovp01-stale-verdict",
                "gate": "OVP-01",
                "doc": "derived.md",
                "row_locator": ["OVP-01", "399.88"],
                "stale_tokens": ["FIXED"],
                "required_mitigating_tokens": ["no hysteresis", "hysteresis absent"],
                "message": "OVP-01 marked FIXED without acknowledging missing hysteresis",
            }
        ]
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            """\
| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | SS2.2 |
| UVL-02 | Logic UVLO <2.9V falling / >3.0V rising | SS2.4 |

| Gate | Requirement | Measured | Verdict |
|---|---|---|---|
| OVP-01 | 390-410 V | 399.88 V | FIXED (hysteresis absent, needs r_hyst) |
""",
        )
        state, report = _run(tmp_path, cfg)
        assert state == "clean"
        assert [v for v in report.violations if v.kind == "stale_verdict"] == []


class TestAntiVacuity:
    """Degenerate input must fail closed (tool_error), never report clean."""

    def test_missing_config_file(self, tmp_path):
        state, report = run(tmp_path / "does_not_exist.yaml", tmp_path)
        assert state == "tool_error"
        assert report.fields_checked == 0

    def test_empty_config_file(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("")
        state, report = run(config_path, tmp_path)
        assert state == "tool_error"

    def test_config_with_zero_gates(self, tmp_path):
        cfg = {
            "source_document": "source.md",
            "derived_documents": [{"path": "derived.md", "gates": "all"}],
            "gates": {},
        }
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", "| Gate |\n|---|\n| OCP-01 |\n")
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("zero gates" in e.reason for e in report.tool_errors)

    def test_config_with_zero_derived_documents(self, tmp_path):
        cfg = {
            "source_document": "source.md",
            "derived_documents": [],
            "gates": BASE_CONFIG["gates"],
        }
        _write(tmp_path, "source.md", SOURCE_MD)
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("zero derived_documents" in e.reason for e in report.tool_errors)

    def test_missing_source_document(self, tmp_path):
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n| OCP-01 | x | y |\n",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any(e.where == "source.md" and "not found" in e.reason for e in report.tool_errors)

    def test_empty_source_document(self, tmp_path):
        _write(tmp_path, "source.md", "")
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n| OCP-01 | x | y |\n",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("empty" in e.reason for e in report.tool_errors)

    def test_source_document_with_zero_tables(self, tmp_path):
        """Unrecognised/absent table format -- prose with no pipe tables at all."""
        _write(tmp_path, "source.md", "This document has no tables, only prose.\n")
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n| OCP-01 | x | y |\n",
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("zero pipe-tables" in e.reason for e in report.tool_errors)

    def test_derived_document_missing(self, tmp_path):
        _write(tmp_path, "source.md", SOURCE_MD)
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("not found" in e.reason for e in report.tool_errors)

    def test_derived_document_empty(self, tmp_path):
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", "")
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"

    def test_derived_document_zero_rows_for_gate(self, tmp_path):
        """Table exists and parses, but the gate's row was deleted entirely
        (not just a field) -- must be a tool_error (0 matches), not a
        silently-skipped/clean pass."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n"
            "| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |\n",
            # OVP-01 and UVL-02 rows are simply absent.
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("OVP-01" in e.where for e in report.tool_errors)
        assert any("UVL-02" in e.where for e in report.tool_errors)

    def test_ambiguous_source_row_locator(self, tmp_path):
        """Locator matches more than one row -- must fail closed rather
        than silently pick one (a config bug, not a document defect)."""
        ambiguous_source = SOURCE_MD + (
            "\n### 2.1b Duplicate for test\n\n"
            "| Parameter | Setting | Trip Threshold | Response Time |\n"
            "|---|---|---|---|\n"
            "| **Primary OCP** | 50A Peak | **45 - 55 A** | **< 1 µs** |\n"
        )
        _write(tmp_path, "source.md", ambiguous_source)
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n"
            "| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |\n",
        )
        cfg = {
            "source_document": "source.md",
            "derived_documents": [{"path": "derived.md", "gates": ["OCP-01"]}],
            "gates": {"OCP-01": BASE_CONFIG["gates"]["OCP-01"]},
        }
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("matched 2 rows" in e.reason for e in report.tool_errors)

    def test_stale_config_field_not_in_source_fails_closed(self, tmp_path):
        """If a required_fields any_of no longer matches anything in the
        SOURCE row (source changed, config didn't), that is a maintenance
        failure of the mapping itself and must not be silently ignored."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n"
            "| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |\n",
        )
        cfg = {
            "source_document": "source.md",
            "derived_documents": [{"path": "derived.md", "gates": ["OCP-01"]}],
            "gates": {
                "OCP-01": {
                    "source_row_locator": ["Primary OCP"],
                    "required_fields": [
                        {"name": "nonexistent", "any_of": ["this text is nowhere"]},
                    ],
                }
            },
        }
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("stale relative to the source" in e.reason for e in report.tool_errors)

    def test_empty_source_row_locator_fails_closed(self, tmp_path):
        """An empty source_row_locator must not vacuously "match" a row.

        Before the check_vacuous_gates.py-driven fix, find_rows_by_locator's
        `all(loc in ctx for loc in norm_locator)` was vacuously True for an
        empty norm_locator, so an empty source_row_locator would match
        every row of the source table -- including, in a source with
        exactly one row, silently reporting a clean match instead of the
        config error it actually is. This test fails on the pre-fix code
        (state == "clean" or a mismatched match count, not the expected
        "tool_error" naming the empty locator) and passes once
        find_rows_by_locator raises on an empty locator.
        """
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            "| Gate | Description | Reference |\n|---|---|---|\n"
            "| OCP-01 | Primary OCP 45-55A peak, <1us | SS2.1 |\n",
        )
        cfg = {
            "source_document": "source.md",
            "derived_documents": [{"path": "derived.md", "gates": ["OCP-01"]}],
            "gates": {
                "OCP-01": {
                    "source_row_locator": [],
                    "required_fields": [{"name": "basis", "any_of": ["peak"]}],
                }
            },
        }
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("locator must be non-empty" in e.reason for e in report.tool_errors)

    def test_empty_stale_tokens_fails_closed(self, tmp_path):
        """An empty stale_tokens list must not vacuously mark every row stale.

        Before the check_vacuous_gates.py-driven fix,
        `all(normalize(t) in ctx for t in check["stale_tokens"])` was
        vacuously True for an empty stale_tokens list, so every
        consistency-check row would be reported "stale" regardless of
        content (inverting the check's purpose) rather than the config
        error it actually is. This test fails on the pre-fix code (no
        tool_error is raised for the empty list) and passes once
        check_consistency raises on an empty stale_tokens list.
        """
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(
            tmp_path,
            "derived.md",
            "| Verdict | Component |\n|---|---|\n| FIXED | OVP-01 |\n",
        )
        cfg = {
            "source_document": "source.md",
            "derived_documents": [{"path": "derived.md", "gates": "all"}],
            "gates": BASE_CONFIG["gates"],
            "consistency_checks": [
                {
                    "id": "ovp01-stale-check",
                    "doc": "derived.md",
                    "row_locator": ["OVP-01"],
                    "gate": "OVP-01",
                    "stale_tokens": [],
                    "required_mitigating_tokens": ["mitigated"],
                    "message": "test consistency check with empty stale_tokens",
                }
            ],
        }
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("stale_tokens must be non-empty" in e.reason for e in report.tool_errors)


class TestNormalizeAndTableParsing:
    """Unit-level checks on the primitives the integration tests rely on."""

    def test_normalize_collapses_spacing_around_dash(self):
        assert normalize("45 - 55 A") == normalize("45-55A")

    def test_normalize_collapses_spacing_around_comparator(self):
        assert normalize("< 1 µs") == normalize("<1µs")

    def test_normalize_strips_bold_markers(self):
        assert normalize("**45 - 55 A**") == normalize("45-55A")

    def test_normalize_does_not_erase_qualifier_words(self):
        """The exact defect this gate exists to catch: "50A Peak" and
        "50A" must remain distinguishable after normalization."""
        assert "peak" in normalize("50A Peak")
        assert "peak" not in normalize("50A")

    def test_extract_tables_returns_empty_for_prose(self):
        assert extract_tables("Just some prose.\nNo pipes here.\n") == []

    def test_extract_tables_ignores_a_bare_pipe_line_with_no_separator(self):
        # A single "|"-prefixed line with no following dash-separator row
        # is not a table -- e.g. an accidental leading pipe in prose.
        assert extract_tables("| not a table, just one line\nmore prose\n") == []


class TestBoardFactMeasurement:
    """Unit-level checks on the .kicad_pcb parser.

    The whole reason for parsing structurally rather than by text match is
    the `nets` metric, so it gets an explicit assertion here.
    """

    def test_counts_top_level_forms(self):
        m = measure_board(PCB_MD)
        assert m["footprints"] == 3
        assert m["segments"] == 4
        assert m["vias"] == 1
        assert m["zones"] == 2
        assert m["copper_layers"] == 2

    def test_net_declarations_are_not_net_references(self):
        """A naive `(net ` scan finds 12 in this fixture; only 2 are
        declarations. This is the measurement error the gate exists to
        prevent, reproduced at unit level."""
        assert PCB_MD.count("(net ") == 12
        assert measure_board(PCB_MD)["nets"] == 2

    def test_parentheses_inside_quoted_strings_do_not_shift_depth(self):
        pcb = PCB_MD.replace('"R_0603"', '"R_0603 ((weird) name"')
        assert measure_board(pcb)["footprints"] == 3

    def test_parse_claimed_int_handles_bold_and_thousands_separator(self):
        assert parse_claimed_int("**2,338**") == 2338
        assert parse_claimed_int("48") == 48

    def test_parse_claimed_int_rejects_non_integer(self):
        assert parse_claimed_int("~2,338 or so") is None
        assert parse_claimed_int("") is None


class TestBoardFactDrift:
    """The motivating bug: the doc asserts a board state the file contradicts."""

    def test_control_matching_table_passes(self, tmp_path):
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "clean"
        assert report.board_facts_checked == 3

    def test_stale_segment_count_is_drift(self, tmp_path):
        """Reconstruction of the 2026-07-27 defect: the board was routed,
        the doc still claims zero segments."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace("| Segments | **4** |", "| Segments | **0** |"),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        v = [x for x in report.violations if x.kind == "board_fact"]
        assert len(v) == 1
        assert v[0].field == "segments"
        assert "claims 0" in v[0].source_hint
        assert "measures 4" in v[0].source_hint
        assert "do not edit" in v[0].remedy.lower()

    def test_board_drift_is_reported_as_board_violation(self, tmp_path):
        """Board drift must be visible to the soft-launch bypass in main()."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace("| Footprints | **3** |", "| Footprints | **149** |"),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        assert len(report.board_violations()) == 1


class TestBoardFactFailsClosed:
    """Every way a claim can stop being locatable must be a tool_error.

    This is the fail-open class the gate was designed against: a check
    that quietly stops checking is worse than no check, because it reports
    success. `state == "clean"` must be unreachable in all of these.
    """

    def _setup(self, tmp_path):
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)

    def test_missing_anchor_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        _write(tmp_path, "board.md", BOARD_DOC_MD.replace("<!-- BOARD-FACTS-TABLE -->", ""))
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("found 0 times" in e.reason for e in report.tool_errors)

    def test_duplicated_anchor_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        _write(tmp_path, "board.md", BOARD_DOC_MD + "\n<!-- BOARD-FACTS-TABLE -->\n")
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("found 2 times" in e.reason for e in report.tool_errors)

    def test_renamed_row_label_is_tool_error_not_silent_pass(self, tmp_path):
        """The fail-open case. Rewording a row label must break loudly."""
        self._setup(tmp_path)
        _write(tmp_path, "board.md", BOARD_DOC_MD.replace("| Segments |", "| Copper segments |"))
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any(
            "found 0 times" in e.reason and "segments" in e.where for e in report.tool_errors
        )

    def test_table_detached_from_anchor_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace(
                "<!-- BOARD-FACTS-TABLE -->", "<!-- BOARD-FACTS-TABLE -->\n" + "\nfiller\n" * 8
            ),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("not followed by a pipe-table" in e.reason for e in report.tool_errors)

    def test_ungated_row_added_to_table_is_tool_error(self, tmp_path):
        """A new board claim nobody configured must not ride along unchecked."""
        self._setup(tmp_path)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace("| Segments | **4** |", "| Segments | **4** |\n| Vias | **99** |"),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("not configured under" in e.reason for e in report.tool_errors)

    def test_unparseable_claim_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace("| Segments | **4** |", "| Segments | roughly 4 |"),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("not a plain integer" in e.reason for e in report.tool_errors)

    def test_missing_pcb_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        _write(tmp_path, "board.md", BOARD_DOC_MD)
        cfg = dict(BASE_CONFIG, board_facts=dict(BOARD_FACTS_CFG, pcb="absent.kicad_pcb"))
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("source of truth not found" in e.reason for e in report.tool_errors)

    def test_unparseable_pcb_is_tool_error_not_zero_counts(self, tmp_path):
        """A PCB the parser cannot read yields zeros; comparing against
        those zeros would silently 'confirm' an unrouted board."""
        self._setup(tmp_path)
        _write(tmp_path, "board.kicad_pcb", "not an s-expression at all\n")
        _write(tmp_path, "board.md", BOARD_DOC_MD)
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("0 top-level footprints" in e.reason for e in report.tool_errors)

    def test_missing_board_facts_section_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        cfg = {k: v for k, v in BASE_CONFIG.items() if k != "board_facts"}
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("no `board_facts:` section" in e.reason for e in report.tool_errors)

    def test_unknown_metric_is_tool_error(self, tmp_path):
        self._setup(tmp_path)
        _write(tmp_path, "board.md", BOARD_DOC_MD)
        rows = dict(BOARD_FACTS_CFG["rows"], sprockets={"label": "Footprints"})
        cfg = dict(BASE_CONFIG, board_facts=dict(BOARD_FACTS_CFG, rows=rows))
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any("unknown metric" in e.reason for e in report.tool_errors)


class TestStaleBoardClaimProse:
    """Retained history must stay marked as history."""

    _HISTORICAL = "As of 2026-07-01 the board carried no routing. Superseded: it was routed later."

    def test_undated_unrouted_claim_is_violation(self, tmp_path):
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace(self._HISTORICAL, "The committed board carries no routing."),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        v = [x for x in report.violations if x.kind == "stale_board_claim"]
        assert len(v) == 1
        assert v[0].field == "board-unrouted-prose"

    def test_sibling_bullet_does_not_mask_a_stale_bullet(self, tmp_path):
        """Regression: granularity must be the list ITEM, not the block.

        Found by falsifying the gate against the real docs/STRATEGY.md. The
        original defect --
        "The committed board carries no routing: 0 segments, 0 vias, 0 zones"
        -- is a bullet in a list with no blank lines between items. At
        paragraph granularity the whole list was one unit, so the *sibling*
        bullet's "as of 2026-07-25" satisfied the mitigating-token check and
        the stale bullet passed. It must be assessed on its own.
        """
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace(
                self._HISTORICAL,
                "- As of 2026-07-01 the outline was a placeholder. Superseded.\n"
                "- The committed board carries no routing: 0 segments.\n",
            ),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        v = [x for x in report.violations if x.kind == "stale_board_claim"]
        assert len(v) == 1, "the stale bullet must not be masked by its sibling"

    def test_sibling_table_row_does_not_mask_a_stale_row(self, tmp_path):
        """Same granularity rule, applied to table rows."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace(
                self._HISTORICAL,
                "| Item | State |\n|---|---|\n"
                "| Outline | placeholder, superseded 2026-07-02 |\n"
                "| Copper | the board carries no routing |\n",
            ),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "drift"
        v = [x for x in report.violations if x.kind == "stale_board_claim"]
        assert len(v) == 1

    def test_guarded_prose_removed_is_tool_error(self, tmp_path):
        """Fail-closed: if the guarded passage is reworded away, the check
        stops verifying anything and must say so rather than pass."""
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(
            tmp_path,
            "board.md",
            BOARD_DOC_MD.replace(self._HISTORICAL, "The board is in some state."),
        )
        state, report = _run(tmp_path, BASE_CONFIG)
        assert state == "tool_error"
        assert any("no longer verifying anything" in e.reason for e in report.tool_errors)

    def test_empty_mitigating_tokens_is_tool_error(self, tmp_path):
        _write(tmp_path, "source.md", SOURCE_MD)
        _write(tmp_path, "derived.md", FAITHFUL_DERIVED_MD)
        _write(tmp_path, "board.md", BOARD_DOC_MD)
        cfg = dict(
            BASE_CONFIG,
            stale_board_claims=[dict(STALE_BOARD_CFG[0], required_mitigating_tokens=[])],
        )
        state, report = _run(tmp_path, cfg)
        assert state == "tool_error"
        assert any(
            "required_mitigating_tokens must be non-empty" in e.reason for e in report.tool_errors
        )
