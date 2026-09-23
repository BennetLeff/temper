# Review of four Zapote unit brainstorms

Date: 2026-09-23. Base source: `06d9070c3` on `codex/power-entry-pkgs-1-4`. This is a requirements and feasibility review, not an electrical acceptance verdict.

| Unit | Finding | Disposition in plan |
| --- | --- | --- |
| Auxiliary | Rev38's HOT AUX and logic5 producer is missing, while historical `AuxSupply` outputs an isolated SELV rail. Treating both as one physical source would silently decide an insulation and startup architecture. | U1 must inventory both domains; circuit work branches after rail ownership is confirmed. No source part is selected by the brainstorm. |
| Discharge | Historical `BusDischarge` addresses two ~170 V half-buses. Rev38 has VD, F2 and VB, with a 22 µF plus bypass VD reservoir outside F2. Copying old contact/resistor values or the old <60 s arithmetic would leave an energy island unproved. | U1 maps every island and adopts a requirement; U2 evaluates topology and fault cases on those frozen inputs. |
| Inverter | The full-board frequency story depends on loaded inductance, and the existing gate-drive unit has digital construction acceptance only. Nominal 390 V is not a worst-case input envelope. | U1 reconciles bus, coil and gate-drive contracts; no operating-frequency or switch selection is accepted without bounded inputs. |
| Cooling | The GBU/GBJ bridge studies, 395-1AB and 392-120AB sink candidates, and fan ratings have different model boundaries. None establishes installed airflow or enclosure fit. | U1 preserves candidate identity and a loss/space ledger; U2 compares concepts using matching source and boundary conditions. |

## Cross-unit checks

- Auxiliary rail interruption must invoke the applicable Rev38 stop/restart path and discharge default. The units need an interface table rather than duplicate permission logic.
- Inverter local capacitance changes the discharge island map; inverter heat changes cooling load and fan power changes auxiliary load. Each plan includes a change-triggered recheck.
- Every standalone result is limited to digital construction until hardware is assembled and measured. Integration of all units and whole-board release retain their separate roadmap gates.
- The working Rev38 branch may advance. Each new unit records the exact source commit or artifact hash it used and reconciles any later Rev38 interface change before acceptance.

No premise was found that justifies selecting a circuit topology, time threshold, power part or final fan assembly immediately. The plans therefore put source-bound contracts and adverse-case models first.
