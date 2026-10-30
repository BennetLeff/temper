"""JLCPCB: fabrication rules, EasyEDA/LCSC part records, CPL rotation fits, placement preview, order fees,
exact-part 3D models.

  jlc.RULES        legend, mask and edge limits from the JLC capabilities page; the excerpt that states each
                   is jlc/data/jlc-capabilities-excerpts.txt (CAPABILITIES), fetched 2026-10-29 with its sha256
  jlc.easyeda      record fetch and cache (lceda.cn mirror), PAD parsing, pad-number rotation fits
  jlc.placement    JLC placement-preview simulation: vendor pads placed from the CPL against the Gerber pads
  jlc.order        the assembly fee model and part-quantity rule
  jlc.models_3d    exact-part STEP models placed in the KiCad footprint frame (OCP; CAD-env Python)
Python 3.9 compatible (KiCad's bundled Python imports easyeda and order).
"""
from pathlib import Path

CAPABILITIES = Path(__file__).resolve().parent / 'data' / 'jlc-capabilities-excerpts.txt'
SOURCE = 'https://jlcpcb.com/capabilities/pcb-capabilities (fetched 2026-10-29; excerpts in ' \
         'temper_boardkit/jlc/data/jlc-capabilities-excerpts.txt)'

# Each value is quoted in CAPABILITIES:
RULES = {
    'silk_line': 0.15,          # Legend: Minimum Line Width >= 0.15 mm
    'silk_text_h': 1.0,         # Legend: Minimum text height 40 mil (1.0 mm)
    'silk_ratio': 1 / 6,        # Legend: preferred width to height ratio 1:6 (a warning, not a fail)
    'pad_to_silk': 0.15,        # Legend: minimum distance between pad and silkscreen 0.15 mm
    'mask_bridge': 0.10,        # Soldermask bridge: 1 oz, min pad spacing 0.10 mm (green, red, yellow, blue, purple)
    'mask_to_copper': 0.09,     # Soldermask: at least 0.09 mm between openings and neighbouring traces
    'edge_copper': 0.20,        # Outline, routed: copper clearance from routed board edges >= 0.2 mm
    'edge_copper_vcut': 0.40,   # Outline, V-cut: copper clearance from V-cut board edges >= 0.4 mm
}


def capabilities_text():
    return CAPABILITIES.read_text(encoding='utf-8')
