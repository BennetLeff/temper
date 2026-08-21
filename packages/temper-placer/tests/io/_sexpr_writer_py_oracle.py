# VERBATIM pre-migration oracle: the kiutils Board writer (Wave 4 Phase 3,
# formats/IO -- the S-expression writer, inverse of the parse engine).
#
# Pre-migration, every board the pipeline wrote went through kiutils'
# `Board.to_sexpr()` (via `Board.to_file`, which is exactly
# `write(to_sexpr())`). That is the Python behavior the Rust writer
# (`sexpr_writer.rs`, exposed as
# `temper_design_bundle_python.parse_engine.write_board_sexpr_py`) replaces,
# so it is pinned here verbatim as the oracle arm of the writer differential
# (`tests/io/test_sexpr_writer_oracle_differential.py`). The Rust writer
# must never be reconciled *to* this oracle's bytes -- kiutils' to_sexpr
# re-emits from a lossy object model (measured on the corpus: on the temper
# board it drops 1388 leaves -- 99 fp_text (at/effects/font/layer/size/
# thickness) groups -- and adds 67, including 33 phantom (tedit ...) tokens;
# it only reproduces the input token tree on the rp2040 board). The D7
# acceptance criterion is the Rust writer's re-parse parity with the INPUT
# text; this oracle pins the pre-migration reference and the differential
# asserts Rust == kiutils on the boards where kiutils is faithful, and Rust
# == input tree (strictly stronger) where kiutils is not.

from __future__ import annotations

from kiutils.board import Board
from kiutils.utils.sexpr import parse_sexp


def board_to_sexpr(text: str) -> str:
    """Pre-migration writer: kiutils load + kiutils serialize.

    The verbatim pre-migration pipeline behavior for "turn board text into
    written board text": parse with kiutils and re-emit with
    ``Board.to_sexpr()``.
    """
    return Board.from_sexpr(parse_sexp(text)).to_sexpr()


# Captured `board_to_sexpr()` output for the minimal corpus board
# (power_pcb_dataset/corpus/minimal/minimal_board.kicad_pcb, kiutils 1.4.8).
# Pinned so the oracle stays deterministic and reviewable even if kiutils is
# ever removed from the repo. The differential asserts the oracle function
# still reproduces this capture (drift detection on the oracle arm itself).
KIUTILS_MINIMAL_BOARD_SEXPR = """(kicad_pcb (version 20221018) (generator pcbnew)

  (general
    (thickness 1.6)
  )

  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (44 "Edge.Cuts" user)
  )

  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros false)
      (usegerberextensions false)
      (usegerberattributes false)
      (usegerberadvancedattributes false)
      (creategerberjobfile false)
      (svgprecision 0.0)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (hpglpennumber 0)
      (hpglpenspeed 0)
      (hpglpendiameter 0.000000)
      (dxfpolygonmode false)
      (dxfimperialunits false)
      (dxfusepcbnewfont false)
      (psnegative false)
      (psa4output false)
      (plotreference false)
      (plotvalue false)
      (plotinvisibletext false)
      (sketchpadsonfab false)
      (subtractmaskfromsilk false)
      (outputformat 0)
      (mirror false)
      (drillshape 0)
      (scaleselection 1)
      (outputdirectory "")
    )
  )

  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
  (net 3 "SIG1")
  (net 4 "SIG2")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tedit 6a8736d0) (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "R1")
    (property "Value" "10k")
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric")
    (path "/00000000-0000-0000-0000-000000000001")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 3 "SIG1"))
    (pad "2" smd roundrect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 4 "SIG2"))
  )

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tedit 6a8736d0) (tstamp 00000000-0000-0000-0000-000000000002)
    (at 110 80 90)
    (property "Reference" "R2")
    (property "Value" "4.7k")
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric")
    (path "/00000000-0000-0000-0000-000000000002")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 1 "GND"))
    (pad "2" smd roundrect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 4 "SIG2"))
  )

  (footprint "Capacitor_SMD:C_0603_1608Metric" (layer "F.Cu")
    (tedit 6a8736d0) (tstamp 00000000-0000-0000-0000-000000000003)
    (at 105 90)
    (property "Reference" "C1")
    (property "Value" "100nF")
    (property "Footprint" "Capacitor_SMD:C_0603_1608Metric")
    (path "/00000000-0000-0000-0000-000000000003")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 2 "VCC"))
    (pad "2" smd roundrect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 1 "GND"))
  )

  (footprint "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm" (layer "F.Cu")
    (tedit 6a8736d0) (tstamp 00000000-0000-0000-0000-000000000004)
    (at 120 85 180)
    (property "Reference" "U1")
    (property "Value" "LM358")
    (property "Footprint" "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    (path "/00000000-0000-0000-0000-000000000004")
    (pad "1" smd roundrect (at -2.475 -1.905) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 3 "SIG1"))
    (pad "2" smd roundrect (at -2.475 -0.635) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 4 "SIG2"))
    (pad "3" smd roundrect (at -2.475 0.635) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 4 "SIG2"))
    (pad "4" smd roundrect (at -2.475 1.905) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 1 "GND"))
    (pad "5" smd roundrect (at 2.475 1.905) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 3 "SIG1"))
    (pad "6" smd roundrect (at 2.475 0.635) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 4 "SIG2"))
    (pad "7" smd roundrect (at 2.475 -0.635) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 2 "VCC"))
    (pad "8" smd roundrect (at 2.475 -1.905) (size 1.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25)
      (net 2 "VCC"))
  )

  (gr_rect (start 90 70) (end 140 100) (layer "Edge.Cuts") (width 0.1))

)
"""
