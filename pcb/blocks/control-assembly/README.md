# Control-assembly target context (P3 U1)

Authoritative working context for buck/MCU composition. The production board
(`pcb/temper.kicad_pcb`) is read-only; this directory is the only P3-owned
target description.

## Files

- `target-context.json` — outline, six-layer stackup, domains, reserved
  regions, replacement ledger, provenance digests. R1.
- `interfaces.json` — internal required connections vs future RTD/safety/
  programming obligations. Future endpoints are obligations, not connectors.

## Key facts (measured, not inherited)

- Outline 164x234 mm: rect (8,20)-(172,254), Edge.Cuts gr_poly.
- Six copper layers, physical order F.Cu / In3.Cu / In1.Cu / In2.Cu / In4.Cu /
  B.Cu (outer 0.07 mm, inner 0.035 mm; 1.6 mm total; ENIG). Ordinal IDs
  (0/3/1/2/4/31) are not physical order.
- Buck prototype is two-layer 50x40 mm with J1/J2/TP1-TP4/H1-H4 fixtures.
  Only the functional nine transfer:
  U3 (LMR51430), L2 (5.6 uH SRP1265A), C9 (10 uF in), C10 (100 nF boot),
  C11/C12 (2x22 uF out), C13 (100 nF HF), R16 (100 k), R17 (22.1 k).
- MCU source is ten components: module + c_vcc1/c_vcc2 + r_en/c_en +
  r_boot + btn_reset/btn_boot + 2x I2C pullups.
- Existing placeholders: U27 (ESP32-S3-WROOM-1 at 33.1,47.96 rot 90),
  U3 (117.93,149.08), L2 (135.29,147.93). Reserved envelopes:
  MCU 18-52 x 28-68, antenna keepout 18-52 x 20-32, buck 100-146 x 132-162.

## For P1

Definite outline, stackup, allowed regions, and interface obligations are in
the two JSON files. Every input carries a source path and sha256 in
`target-context.json/provenance`. Pending P1 inputs (combined source
wrapper/export, accepted `pcb/blocks/mcu/` geometry) are listed under
`pending_inputs`; U1 does not block on them.

## Verification

Artifact extraction is native KiCad file parse; no new rotation or
net-identity policy was added. Do not add tests that mirror this table —
checks must extract from KiCad and compare against these JSONs.
