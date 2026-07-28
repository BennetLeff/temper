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
from check_derived_doc_drift import extract_tables, normalize, run

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


def _write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text)


def _write_config(root: Path, cfg: dict) -> Path:
    p = root / "config.yaml"
    p.write_text(yaml.dump(cfg))
    return p


def _run(tmp_path: Path, cfg: dict):
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
        assert state == "clean", [
            (e.where, e.reason) for e in report.tool_errors
        ] + [(v.gate, v.field) for v in report.violations]
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
