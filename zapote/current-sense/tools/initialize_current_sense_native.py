#!/usr/bin/env python3
"""Initialize a source-generated board for a two-layer current-sense unit.

The board already contains source-derived footprints and an explicit outline.
This adapter only applies native KiCad stackup/design settings and writes the
project sidecars used by later checks. It refuses boards that already contain
functional copper; placement and routing remain operator-owned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

COPPER_THICKNESS_MM = 0.07
MIN_CLEARANCE_MM = 0.2
MIN_TRACK_WIDTH_MM = 0.25
VIA_DIAMETER_MM = 0.6
VIA_DRILL_MM = 0.3


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stackup_text() -> str:
    return """(stackup
 (layer "F.SilkS" (type "Top Silk Screen"))
 (layer "F.Paste" (type "Top Solder Paste"))
 (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
 (layer "F.Cu" (type "copper") (thickness 0.07))
 (layer "dielectric 1" (type "core") (thickness 1.44) (material "FR4"))
 (layer "B.Cu" (type "copper") (thickness 0.07))
 (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
 (layer "B.Paste" (type "Bottom Solder Paste"))
 (layer "B.SilkS" (type "Bottom Silk Screen"))
 (copper_finish "ENIG") (dielectric_constraints no))"""


def replace_stackup(board_path: Path) -> None:
    text = board_path.read_text(encoding="utf-8")
    start = text.find("(stackup")
    if start < 0:
        text = text.replace("(setup", "(setup\n" + stackup_text(), 1)
    else:
        depth = 0
        end = None
        for index in range(start, len(text)):
            depth += text[index] == "("
            depth -= text[index] == ")"
            if depth == 0:
                end = index + 1
                break
        if end is None:
            raise ValueError("board stackup is unbalanced")
        text = text[:start] + stackup_text() + text[end:]
    board_path.write_text(text, encoding="utf-8")


def initialize(repo: Path, board_path: Path, receipt_path: Path) -> None:
    sys.path.insert(0, str(repo / "harness-lab"))
    import buck_native  # type: ignore[import-not-found]
    import pcbnew  # type: ignore[import-not-found]

    before = sha256(board_path)
    board = buck_native.load(board_path)
    if list(board.GetTracks()) or list(board.Zones()):
        raise ValueError("initialization requires a source-generated board without copper")
    board.SetCopperLayerCount(2)
    # The donor text skeleton rotates pad positions but leaves each pad body's
    # angle at its library-local value. Ask KiCad to place a fresh library copy
    # at the authored pose; only repair body angles once positions and the full
    # numbered-pad census agree with that external oracle.
    pad_orientation_repairs = []
    for footprint in board.GetFootprints():
        if footprint.GetLayer() != pcbnew.F_Cu:
            raise ValueError("source initialization supports front-side footprints only")
        identity = footprint.GetFPID()
        library = board_path.parent / "candidate-libs" / (str(identity.GetLibNickname()) + ".pretty")
        oracle = pcbnew.FootprintLoad(str(library), str(identity.GetLibItemName()))
        if oracle is None:
            raise ValueError(f"native library oracle missing for {identity.GetLibNickname()}:{identity.GetLibItemName()}")
        oracle.SetOrientationDegrees(footprint.GetOrientationDegrees())
        oracle.SetPosition(footprint.GetPosition())
        def physical_key(pad):
            position = pad.GetPosition()
            return pad.GetNumber(), position.x, position.y

        observed = {physical_key(pad): pad for pad in footprint.Pads()}
        expected = {physical_key(pad): pad for pad in oracle.Pads()}
        if (len(observed) != len(list(footprint.Pads()))
                or len(expected) != len(list(oracle.Pads()))):
            raise ValueError("coincident duplicate physical pads cannot be disambiguated")
        if observed.keys() != expected.keys():
            raise ValueError(f"pad-position oracle mismatch: {footprint.GetReference()}")
        uuids = [pad.m_Uuid.AsString() for pad in footprint.Pads()]
        if len(set(uuids)) != len(uuids):
            raise ValueError("duplicate physical pad UUID")
        for key, pad in observed.items():
            number = key[0]
            target = expected[key]
            old_angle = pad.GetOrientationDegrees()
            new_angle = target.GetOrientationDegrees()
            if abs((old_angle - new_angle + 180.0) % 360.0 - 180.0) > 1e-7:
                pad.SetOrientationDegrees(new_angle)
                pad_orientation_repairs.append({
                    "reference": footprint.GetReference(), "pad": number,
                    "before_deg": old_angle, "after_deg": new_angle,
                    "library_sha256": sha256(library / (str(identity.GetLibItemName()) + ".kicad_mod")),
                })
    settings = board.GetDesignSettings()
    settings.m_MinClearance = pcbnew.FromMM(MIN_CLEARANCE_MM)
    settings.m_TrackMinWidth = pcbnew.FromMM(MIN_TRACK_WIDTH_MM)
    settings.m_CopperEdgeClearance = pcbnew.FromMM(MIN_CLEARANCE_MM)
    settings.m_ViasMinSize = pcbnew.FromMM(VIA_DIAMETER_MM)
    settings.m_ViasMinAnnularWidth = pcbnew.FromMM((VIA_DIAMETER_MM - VIA_DRILL_MM) / 2)
    dimensions = settings.m_ViasDimensionsList
    dimensions.clear()
    dimension = pcbnew.VIA_DIMENSION()
    dimension.m_Diameter = pcbnew.FromMM(VIA_DIAMETER_MM)
    dimension.m_Drill = pcbnew.FromMM(VIA_DRILL_MM)
    dimensions.append(dimension)
    buck_native.save(board, board_path)
    replace_stackup(board_path)

    check = buck_native.load(board_path)
    if check.GetCopperLayerCount() != 2:
        raise ValueError("native reload did not retain exactly two copper layers")
    stackup = board_path.read_text(encoding="utf-8")
    if '(layer "F.Cu" (type "copper") (thickness 0.07))' not in stackup:
        raise ValueError("native stackup did not retain 70 um F.Cu copper")
    if '(layer "B.Cu" (type "copper") (thickness 0.07))' not in stackup:
        raise ValueError("native stackup did not retain 70 um B.Cu copper")

    project = {
        "meta": {"filename": board_path.with_suffix(".kicad_pro").name, "version": 1},
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": MIN_CLEARANCE_MM,
                    "min_track_width": MIN_TRACK_WIDTH_MM,
                    "min_via_annular_width": (VIA_DIAMETER_MM - VIA_DRILL_MM) / 2,
                    "min_via_diameter": VIA_DIAMETER_MM,
                    "min_through_hole_diameter": VIA_DRILL_MM,
                    "min_copper_edge_clearance": MIN_CLEARANCE_MM,
                    "min_hole_clearance": 0.25,
                    "min_hole_to_hole": 0.25,
                    "min_silk_clearance": 0.1,
                    "min_text_height": 0.8,
                    "min_text_thickness": 0.08,
                }
            }
        },
        "net_settings": {
            "classes": [
                {
                    "name": "Default",
                    "clearance": MIN_CLEARANCE_MM,
                    "track_width": MIN_TRACK_WIDTH_MM,
                    "via_diameter": VIA_DIAMETER_MM,
                    "via_drill": VIA_DRILL_MM,
                    "wire_width": 6,
                    "bus_width": 12,
                    "line_style": 0,
                }
            ]
        },
    }
    board_path.with_suffix(".kicad_pro").write_text(
        json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    board_path.with_suffix(".kicad_dru").write_text(
        "(version 1)\n# CurrentSenseUnit native DRC sidecar; requirements are in the project.\n",
        encoding="utf-8",
    )
    candidate_libs = board_path.parent / "candidate-libs" / "fp-lib-table"
    if candidate_libs.is_file():
        shutil.copyfile(candidate_libs, board_path.parent / "fp-lib-table")
    receipt = {
        "schema": "zapote.current-sense.native-initialization-receipt.v1",
        "status": "initialized-unrouted",
        "input_board_sha256": before,
        "output_board_sha256": sha256(board_path),
        "kicad_version": pcbnew.Version(),
        "copper_layers": ["F.Cu", "B.Cu"],
        "copper_thickness_mm": COPPER_THICKNESS_MM,
        "minimum_clearance_mm": MIN_CLEARANCE_MM,
        "minimum_track_width_mm": MIN_TRACK_WIDTH_MM,
        "via_diameter_mm": VIA_DIAMETER_MM,
        "via_drill_mm": VIA_DRILL_MM,
        "physical_tests": "NOT RUN",
        "placement_and_routing": "operator-owned; no functional copper authored",
        "pad_body_orientation_oracle": "KiCad native placement of the vendored footprint",
        "pad_orientation_repairs": pad_orientation_repairs,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    initialize(args.repo.resolve(), args.board.resolve(), args.receipt.resolve())


if __name__ == "__main__":
    main()
