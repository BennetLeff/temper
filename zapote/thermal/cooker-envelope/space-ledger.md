# Cooker mechanical and airflow envelope — U1 in progress

The retained bridge cooling candidate comparison uses a 230 × 210 mm **power-entry section** board and reports enclosure fit as indeterminate. Those dimensions do not define a complete cooker PCB or enclosure.

| Candidate/region | Source-bound envelope | Current limitation |
| --- | --- | --- |
| Retained 395-1AB / two-Sunon bridge assembly | `zapote/thermal/bridge-cooling.md` reserves about 170 × 160 × 95 mm including fan frames, duct and support. | Selected for one saved board model; no enclosure collision or installed-flow qualification. |
| 392-120AB / Sanyo shared concept | `zapote/thermal/cooling-options/proposals/shared-392-120ab-sanyo-120cfm.json` records 170 × 160 × 175 mm assembly allowance; sink 120 × 125 × 135.8 mm, fan 120 × 120 × 38 mm. | A comparison candidate, not promoted. The 120 CFM free-air rating is not installed 100 CFM. |
| Rev38 bridge/PFC layout | No Rev38 native PCB yet (`STATUS.md` U7). | Heat-source positions, support and clearance cannot be collision checked. |
| Inverter and coil | No standalone inverter board or enclosure model in this goal. | Must supply power-stage geometry, pan/coil/ferrite stack, heat rejection and HV access boundaries. |
| Auxiliary/fan circuit | Producer and selected fan pending. | Need connector, wire, fan access, insulation and stall-service space. |

Both cooling concepts require independent chassis support so bridge leads and PCB solder joints do not carry sink or duct load. A provisional duct must account for grille, pressure-flow intersection, inlet heating and recirculation. No current source establishes actual installed flow or a final sensor/trip window. The interlock has a heatsink-fault input, but its remote producer is not selected by these studies.
