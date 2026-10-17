"""Pad layer flags must be read by value, not by presence.

kiutils 1.4.8 treats ``(remove_unused_layers no)`` as true. The candidate
board generator then stripped outer copper from through-hole pads.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("kiutils")
import gen_pcb_skeleton as skeleton  # noqa: E402

FOOTPRINT = """(footprint "T"
\t(layer "F.Cu")
\t(pad "1" thru_hole circle (at 0 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask")
\t\t(remove_unused_layers no))
\t(pad "2" thru_hole circle (at 5 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask")
\t\t(remove_unused_layers yes) (keep_end_layers yes))
\t(pad "3" thru_hole circle (at 10 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask")
\t\t(remove_unused_layers))
\t(pad "4" thru_hole circle (at 15 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask"))
)
"""


def test_pad_layer_flags_follow_their_values(tmp_path):
    path = tmp_path / "T.kicad_mod"
    path.write_text(FOOTPRINT)
    pads = skeleton._load_footprint(path).pads
    assert [p.removeUnusedLayers for p in pads] == [False, True, True, False]
    assert [p.keepEndLayers for p in pads] == [False, True, False, False]
    assert "remove_unused_layers" not in pads[0].to_sexpr()


def test_unknown_flag_value_is_rejected(tmp_path):
    path = tmp_path / "T.kicad_mod"
    path.write_text(FOOTPRINT.replace("(remove_unused_layers no)", "(remove_unused_layers maybe)"))
    with pytest.raises(ValueError, match="remove_unused_layers"):
        skeleton._load_footprint(path)
