---
title: "CST3015 edge-gap dimension was mistaken for a compact land pattern"
module: "hardware_design"
date: "2026-09-11"
problem_type: logic_error
component: hardware_design
severity: high
symptoms:
  - "The inherited CST3015 footprint appeared incompatible with the primary-to-LV PCB corridor."
  - "Native clearance checks agreed with the incorrect library geometry."
root_cause: missing_validation
resolution_type: code_fix
tags: ["zapote", "current-sensing", "CST3015", "footprint", "datasheet", "isolation"]
---

# CST3015 land-pattern dimension interpretation

The standalone current-sense build inherited a transformer footprint whose pad dimensions and row spacing did not match the manufacturer drawing. A correct clearance engine cannot detect that its input footprint represents the wrong physical part. Repeated DRC checks would therefore preserve the wrong conclusion about whether the isolation corridor was geometrically possible.

The [official Coilcraft CST3015 drawing](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf), document 1608-2 revised 09/08/25, specifies 4.8 × 9.0 mm primary pads and 3.0 × 4.6 mm secondary pads. The 18.5 mm vertical dimension is between copper edges. It is not the row-center distance. The correct center separation is `18.5 + 9/2 + 4.6/2 = 25.3 mm`.

The inherited footprint instead placed the rows 13.8 mm apart and used 9 × 4.8 mm primary pads. Its vertical copper gap was 9.1 mm. That shape was internally consistent enough for native tools to load and measure; its agreement with those tools did not validate the datasheet interpretation.

The local, uncommitted fix is a distinct `pcb/libs/temper.pretty/CST3015_Datasheet2025.kicad_mod`, selected by `elec/src/current_sense_unit.ato`. The original shared footprint and full-cooker board remain unchanged. Both the coordinator and a Luna reviewer independently read the rendered manufacturer figure, then checked the corrected pad coordinates through KiCad's native loader. Evidence, original bytes, source PDF hash and corrected footprint hash are retained in `zapote/current-sense/evidence/footprint-review/` and `zapote/current-sense/evidence/cst3015-footprint-review.md`.

The resulting current-sense PCB accommodates the declared 12.6 mm copper corridor. This is a PCB geometry result only. It does not qualify transformer body creepage, insulation system, pollution degree, primary termination, or the assembled cooker. Those remain separate engineering obligations.

Before rejecting a part because its library footprint cannot satisfy a corridor, trace each controlling dimension back to the official drawing: identify its endpoints, view, units, pad numbering and whether it describes body, lead, center or copper edge. Validate one native pad census against that interpretation. A library hash pins the chosen geometry; it does not establish that the geometry is right.

Vocabulary scan: no new project-specific term qualified. The existing distinctions between an isolation barrier and a measured spacing, and between model evidence and device qualification, already describe this incident.
