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

import json

from temper_placer.validation._drc_api import (
    _extract_ref_from_item_description,
    _parse_drc_json,
)


def _write_drc_json(tmp_path, violations):
    path = tmp_path / "drc.json"
    path.write_text(json.dumps({"violations": violations}))
    return path


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
