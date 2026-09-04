"""Regression tests for _drc_api._parse_drc_json's ref/location extraction.

Covers the bug in docs/solutions/logic-errors/
drc-api-wrapper-components-and-location-always-empty.md: kicad-cli's DRC
JSON never emits an item-level "reference" key or a violation-level "pos"
key -- real kicad-cli output puts the component ref in each item's
free-text "description" string, and position only on a per-item basis.
The old parser's `item.get("reference")` and `violation.get("pos", {})`
matched nothing on ANY violation type (not just courtyard ones), so
`DrcError.components` was always `[]` and `.location` was always
`(0.0, 0.0)` for every single violation kicad-cli ever reports.
"""

import contextlib
import json
import subprocess
from pathlib import Path

import pytest

from temper_placer.validation import _drc_api
from temper_placer.validation._drc_api import (
    _extract_ref_from_item_description,
    _parse_drc_json,
)


def _write_drc_json(tmp_path, violations):
    path = tmp_path / "drc.json"
    path.write_text(json.dumps({"violations": violations}))
    return path


def _stage_complete_project(tmp_path: Path, *, footprints: int = 0) -> Path:
    """Create the minimum project-local context required by strict DRC."""
    pcb = tmp_path / "candidate.kicad_pcb"
    footprint_blocks = "\n".join(
        f'  (footprint "Test:R" (property "Reference" "R{index}"))'
        for index in range(footprints)
    )
    pcb.write_text(f"(kicad_pcb\n{footprint_blocks}\n)\n", encoding="utf-8")
    pcb.with_suffix(".kicad_pro").write_text("{}\n", encoding="utf-8")
    pcb.with_suffix(".kicad_dru").write_text("(version 1)\n", encoding="utf-8")
    (tmp_path / "fp-lib-table").write_text("(fp_lib_table)\n", encoding="utf-8")
    return pcb


def _install_fake_kicad(monkeypatch, report: dict, seen: dict) -> None:
    monkeypatch.setattr(_drc_api, "is_kicad_cli_available", lambda: True)

    @contextlib.contextmanager
    def pinned_environment():
        yield {"KICAD_CONFIG_HOME": "/strict-test-config"}

    monkeypatch.setattr(_drc_api, "_single_threaded_kicad_env", pinned_environment)

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        output = Path(command[command.index("--output") + 1])
        output.write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(_drc_api.subprocess, "run", fake_run)


def test_footprint_item_description_extracts_ref():
    assert _extract_ref_from_item_description("Footprint D3") == "D3"


def test_reference_field_item_description_extracts_ref():
    assert _extract_ref_from_item_description("Reference field of C1") == "C1"


def test_silkscreen_segment_item_description_extracts_ref():
    assert _extract_ref_from_item_description("Segment of C16 on F.Silkscreen") == "C16"


def test_pad_item_description_extracts_ref():
    assert _extract_ref_from_item_description("Pad 13 [power_in.ntc-no] of K1 on F.Cu") == "K1"


def test_pth_pad_item_description_extracts_ref():
    assert _extract_ref_from_item_description("PTH pad 1 [+15V] of R1") == "R1"


def test_via_item_description_has_no_ref():
    """Vias are net-owned, not owned by a single component -- must not
    guess a wrong ref."""
    assert _extract_ref_from_item_description("Via [bias] on F.Cu - B.Cu") is None


def test_edge_cuts_polygon_item_description_has_no_ref():
    """Board-level features have no owning component."""
    assert _extract_ref_from_item_description("Polygon on Edge.Cuts") is None


def test_courtyards_overlap_violation_extracts_both_components_and_real_location(tmp_path):
    path = _write_drc_json(
        tmp_path,
        [
            {
                "description": "Courtyards overlap",
                "items": [
                    {"description": "Footprint D3", "pos": {"x": 134.8, "y": 74.25}, "uuid": "u1"},
                    {"description": "Footprint C4", "pos": {"x": 139.92, "y": 64.5}, "uuid": "u2"},
                ],
                "severity": "error",
                "type": "courtyards_overlap",
            }
        ],
    )
    result = _parse_drc_json(path)
    assert result.error_count == 1
    e = result.errors[0]
    assert e.components == ["D3", "C4"]
    assert e.location == (134.8, 74.25)


def test_via_clearance_violation_has_empty_components_not_a_wrong_guess(tmp_path):
    """A via-to-via clearance violation has no owning component -- this
    must stay empty rather than silently attributing it to the wrong
    part."""
    path = _write_drc_json(
        tmp_path,
        [
            {
                "description": "Clearance violation",
                "items": [
                    {
                        "description": "Via [cs_n] on F.Cu - B.Cu",
                        "pos": {"x": 10.0, "y": 20.0},
                        "uuid": "u1",
                    },
                    {
                        "description": "Via [sclk] on F.Cu - B.Cu",
                        "pos": {"x": 12.0, "y": 20.0},
                        "uuid": "u2",
                    },
                ],
                "severity": "error",
                "type": "clearance",
            }
        ],
    )
    result = _parse_drc_json(path)
    e = result.errors[0]
    assert e.components == []
    # Falls back to the first item's position since no item has a ref.
    assert e.location == (10.0, 20.0)


def test_location_prefers_item_with_extractable_ref_over_degenerate_board_feature(tmp_path):
    """copper_edge_clearance's first item is routinely a board-level
    Edge.Cuts polygon with a degenerate (0, 0) pos; the real, useful
    position belongs to the second item (the actual offending pad). The
    parser must not default to the first item's position blindly."""
    path = _write_drc_json(
        tmp_path,
        [
            {
                "description": "Board edge clearance violation",
                "items": [
                    {
                        "description": "Polygon on Edge.Cuts",
                        "pos": {"x": 0.0, "y": 0.0},
                        "uuid": "u1",
                    },
                    {
                        "description": "Pad 1 [V_BUS_SENSE] of C35 on F.Cu",
                        "pos": {"x": 100.385, "y": 60.23},
                        "uuid": "u2",
                    },
                ],
                "severity": "error",
                "type": "copper_edge_clearance",
            }
        ],
    )
    result = _parse_drc_json(path)
    e = result.errors[0]
    assert e.components == ["C35"]
    assert e.location == (100.385, 60.23)


def test_strict_measurement_retains_exact_raw_bytes_and_candidate_flags(tmp_path, monkeypatch):
    pcb = _stage_complete_project(tmp_path, footprints=2)
    report = {
        "violations": [
            {
                "type": "silk_overlap",
                "severity": "warning",
                "description": "Silkscreen overlap",
                "items": [
                    {
                        "description": "Segment of R1 on F.Silkscreen",
                        "pos": {"x": 1.0, "y": 2.0},
                    }
                ],
            }
        ],
        "unconnected_items": [
            {
                "type": "unconnected_items",
                "severity": "error",
                "description": "Unconnected items",
                "items": [
                    {
                        "description": "Pad 1 [GND] of R1 on F.Cu",
                        "pos": {"x": 3.0, "y": 4.0},
                    }
                ],
            }
        ],
        "schematic_parity": [
            {
                "type": "footprint",
                "severity": "error",
                "description": "Missing footprint for symbol R2",
                "items": [
                    {
                        "description": "Footprint R2",
                        "pos": {"x": 5.0, "y": 6.0},
                    }
                ],
            }
        ],
        "ignored_checks": [
            {
                "key": "track_not_centered_on_via",
                "description": "Track endpoint not centered on via",
            },
            {
                "key": "footprint_type_mismatch",
                "description": "Footprint component type does not match footprint pads",
            },
        ],
        "included_severities": ["error", "warning", "exclusion"],
    }
    raw = json.dumps(report, separators=(",", ":")).encode() + b"\n"
    seen: dict = {}

    monkeypatch.setattr(_drc_api, "is_kicad_cli_available", lambda: True)

    @contextlib.contextmanager
    def pinned_environment():
        yield {"KICAD_CONFIG_HOME": "/strict-test-config"}

    monkeypatch.setattr(_drc_api, "_single_threaded_kicad_env", pinned_environment)

    real_read_bytes = Path.read_bytes
    report_reads: list[bytes] = []

    def read_report_once(path: Path) -> bytes:
        value = real_read_bytes(path)
        if path.suffix == ".json":
            report_reads.append(value)
            if len(report_reads) > 1:
                # A second read would represent a divergent retained form.
                return b'{"violations": []}'
        return value

    monkeypatch.setattr(Path, "read_bytes", read_report_once)

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(raw)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(_drc_api.subprocess, "run", fake_run)

    measurement = _drc_api.run_drc_measurement(pcb)

    assert measurement.raw_report_bytes == raw
    assert measurement.raw_report == report
    assert measurement.raw_findings == [
        *report["violations"],
        *report["unconnected_items"],
        *report["schematic_parity"],
    ]
    assert measurement.result.error_count == 2
    assert measurement.result.warning_count == 1
    assert measurement.result.ignored_checks == [
        "track_not_centered_on_via",
        "footprint_type_mismatch",
    ]
    assert measurement.result.included_severities == ["error", "warning", "exclusion"]
    assert len(report_reads) == 1
    assert measurement.thread_pinned is True
    assert {"--all-track-errors", "--severity-all", "--refill-zones"}.issubset(seen["command"])
    assert seen["env"] == {"KICAD_CONFIG_HOME": "/strict-test-config"}


def test_strict_measurement_rejects_all_footprints_unresolved(tmp_path, monkeypatch):
    pcb = _stage_complete_project(tmp_path, footprints=2)
    report = {
        "violations": [
            {
                "type": "lib_footprint_issues",
                "severity": "warning",
                "description": f"Footprint issue {index}",
                "items": [
                    {
                        "description": f"Footprint R{index}",
                        "pos": {"x": float(index), "y": 0.0},
                    }
                ],
            }
            for index in range(2)
        ],
    }
    seen: dict = {}
    _install_fake_kicad(monkeypatch, report, seen)

    with pytest.raises(_drc_api.DrcProjectContextError, match="footprint resolution"):
        _drc_api.run_drc_measurement(pcb, strict=True)


@pytest.mark.parametrize(
    "report",
    [
        {
            "violations": [
                {
                    "type": "lib_footprint_issues",
                    "severity": "warning",
                    "description": "only one unresolved footprint",
                    "items": [],
                }
            ]
        },
        {
            "violations": [
                {
                    "type": "lib_footprint_issues",
                    "severity": "warning",
                    "description": "two unresolved footprints",
                    "items": [],
                },
                {
                    "type": "lib_footprint_issues",
                    "severity": "warning",
                    "description": "two unresolved footprints",
                    "items": [],
                },
                {
                    "type": "lib_footprint_mismatch",
                    "severity": "warning",
                    "description": "one explicit mismatch",
                    "items": [],
                },
            ]
        },
    ],
)
def test_strict_measurement_does_not_reject_near_miss_resolution_signature(
    tmp_path, monkeypatch, report
):
    pcb = _stage_complete_project(tmp_path, footprints=2)
    _install_fake_kicad(monkeypatch, report, {})

    measurement = _drc_api.run_drc_measurement(pcb, strict=True)

    assert measurement.result.warning_count == len(report["violations"])
