# Fabrication note: power-stage-120v native-17 (CANDIDATE, not released)

Board: `native-17/section.kicad_pcb`, SHA-256
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
Gerbers: `native-17-gerbers.zip`, SHA-256
`ce4ee2eb19bbaa6350696be606d2dc97296e01dbbeb7f690015d8ebb03561144`.

**This package isn't released for ordering.** The release gates in
`DECISIONS.md` and `FAB-JLCPCB.md` are still open (finished-copper, thermal
and insulation qualification; the CTI confirmation below).

| Item | Requirement |
| --- | --- |
| Size | 240 × 160 mm, 4 layers |
| Stackup | JLCPCB **JLC041622-7628**, 1.6 mm |
| Copper | **2 oz outer and 2 oz inner** |
| Laminate | CTI ≥ 175 V (material group IIIa) **required**; confirm on the order (open question to JLCPCB) |
| Surface finish | Lead-free HASL or ENIG |
| Solder mask / silk | Green / white |
| Impedance control | None |
| Vias | Tented (mask over vias) on 353 of 354 via sides; one via side has a mask opening |
| Drills | 293 plated (177 vias, 116 component holes), 8 non-plated |

Deviations and notes:
- Footprint outline silk uses stock KiCad 0.12 mm strokes (JLCPCB
  recommends ≥ 0.15 mm); designators are 1.0 mm / 0.15 mm.
- Plated through-hole pads have lands on both outer layers; unconnected inner
  rings are removed on purpose (`tools/pth_layer_policy.py`).
- Three L1/J3 silkscreen overlaps are known and accepted pending the owner.
