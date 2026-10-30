"""temper-boardkit: KiCad-free PCB craft and checks shared by Temper's hand-routed boards.

Modules (import the one you need; nothing is imported here, so KiCad's Python 3.9 without shapely can
import the pure ones):
  model      plain-dict board model, pad-addressed hand-routing helpers (P, B, T, T45, V, ...)
  craft      deterministic craft passes over hand routes and their checks
  predrc     shapely pre-DRC (clearance, edge, holes, keepouts, via-on-land, width, angle, connectivity)
  gerber     Gerber / Excellon reader and Gerber-only DFM checks
  jlc        JLC rules, EasyEDA records and fits, placement preview, order fees, 3D models
  kicad      lazily imported pcbnew helpers
  cli        boardkit-predrc, boardkit-gerber-check, boardkit-edge-clearance
"""

__version__ = "0.1.0"
