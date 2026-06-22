# PEEC Tool Evaluation — Layout-Aware SPICE Stack

**Date:** 2026-06-22
**Evaluator:** AI Agent
**Decision:** G3 Fallback (Hand-Calculated Parasitics)
**Time Spent:** < 1 day

## Summary

No open-source PEEC tool that directly consumes KiCad `.kicad_pcb` S-expression
format and produces a SPICE-ready equivalent-circuit netlist is available as a
ready-to-use Python package. Three candidates were evaluated. All require
non-trivial adapter code to bridge KiCad geometry to the tool's input format.
Given the 1-day spike constraint and the project scale (1-3 person hobby build),
the **G3 escape hatch** is activated: hand-calculated parasitics from trace
geometry with conservative derating.

---

## Tools Evaluated

### 1. FastHenry

- **Repository:** https://github.com/ediloren/FastHenry (academic fork)
- **Status:** C codebase, requires compilation. Input format is a custom
  text-based segment list (not KiCad-native). No Python bindings.
- **Input format gap:** Requires manual conversion of KiCad trace segments
  to FastHenry segment definitions.
- **Output:** Produces R+L matrices in a parseable impedance table.
- **Verdict:** FAIL for 1-day spike. Writing a KiCad-to-FastHenry exporter
  exceeds the time budget. The tool itself is mature for magneto-quasistatic
  extraction but the integration cost is too high.

### 2. FasterCap

- **Repository:** https://github.com/ediloren/FasterCap
- **Status:** C codebase, same ecosystem as FastHenry. Extracts capacitance
  only (no inductance). Input format is a boundary-element mesh.
- **Verdict:** FAIL. Capacitance-only, no R/L extraction. Does not cover
  the primary need (gate-drive loop inductance).

### 3. Open PEEC / parasitics.py

- **Search:** PyPI, GitHub
- **Status:** No maintained Python PEEC package found. The term "parasitics.py"
  appears in academic papers but no release was located.
- **Verdict:** FAIL. Does not exist as an installable package.

### 4. pyparsing + Hand Calculation (Adopted)

- **Approach:** Parse KiCad `.kicad_pcb` S-expression with `pyparsing`
  (already available in the project environment). Compute per-net trace
  lengths from segment geometry. Apply conservative derated parasitic
  formulas per unit length.
- **Input format gap:** None. Direct S-expression parsing, no intermediate
  format export required.
- **Output:** Per-net R_series (mΩ), L_series (nH), C_shunt (pF).
- **Verdict:** PASS (G3 path). Meets all G2 criteria except the "not a
  hardcoded heuristic" requirement — the 0.8 nH/mm figure is a known
  engineering approximation for PCB microstrip, validated by Howard Johnson's
  *High-Speed Digital Design* and IPC-2141.

---

## G3 Fallback Definition

### Hand-Calculation Formulas

All parasitics are computed from trace geometry extracted from the KiCad PCB:

```
L_trace(nH) = length_mm * 0.8 nH/mm          (microstrip over ground plane)
R_trace(mΩ) = length_mm * 17 mΩ/mm / w_mm    (1 oz copper, 20°C)
C_trace(pF) = length_mm * w_mm * 0.04 pF/mm²  (FR-4, 1.6mm, εr=4.5)
L_via(nH)  = 1.0 nH per via                   (standard FR-4 via)
```

### Conservative Derating

| Parameter | Derating Factor | Rationale |
|-----------|----------------|-----------|
| Gate-drive L | × 2.0 | Accounts for inner-layer return path impedance, mutual coupling, and via pair inductance. The 0.8 nH/mm figure is for a trace-over-ideal-ground; the return path through In2.Cu adds impedance that simple microstrip formulas miss. |
| DC-bus L | × 1.5 | Bus traces are wider and lower impedance; mutuals less significant. |
| Resonant tank L | × 1.5 | Tank traces carry high current; proximity effect increases effective L. |
| All R values | × 1.3 | Temperature coefficient of copper (0.393%/°C) at 100°C Tj. |

### Critical Loop Groups Covered

| Loop Group | KiCad Nets | Extracted |
|-----------|-----------|-----------|
| Gate-drive HS | GATE_H, GND (driver return) | Yes |
| Gate-drive LS | GATE_L, PGND | Yes |
| DC-bus | DC_BUS+, DC_BUS- | Yes |
| Resonant tank | SW_NODE, tank-return | Yes |
| Aux supply | +3V3, +5V, +15V, VCC_BOOT | Yes |

### Mutual Coupling

The G3 path does not extract mutual coupling (k-factors) between loop pairs.
Per R3, this limitation is documented. Conservative worst-case mutual
coupling is modeled by the ×2.0 gate-drive inductance derating.

---

## Working Example

```python
from tools.spice.extract import extract_parasitics

parasitics = extract_parasitics("pcb/temper_spice_validated.kicad_pcb")
for net_name, values in parasitics.items():
    print(f"{net_name}: R={values['R_mOhm']:.0f}mOhm L={values['L_nH']:.1f}nH C={values['C_pF']:.1f}pF")
```

Expected output includes at minimum the gate-drive and DC-bus loop nets with
non-zero inductance values computed from actual trace geometry.

---

## Risk Acknowledgment

Hand-calculated parasitics are less accurate than a full PEEC mesh. The
challenger model (Unit 5) provides an independent thermal cross-check that
catches systematic errors from the simplified inductance model. If the
challenger disagrees with the primary Tj prediction by >10%, the derating
multipliers should be reviewed.

Post-fab correlation (comparing simulated vs. measured loop inductance on a
populated board) is recommended before committing to production volumes.
