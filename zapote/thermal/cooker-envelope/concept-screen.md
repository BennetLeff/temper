# Bounded cooling concept screen

This is a U2 screening result for the source snapshot `cbfcc2ebc`, not a candidate selection or whole-cooker thermal qualification. It uses retained numerical inputs exactly where their source identities apply. The `loss-ledger.md` defines those identities. No installed pressure/flow intersection or enclosure CAD exists; assembly ranking is **INDETERMINATE**.

## Matched and unmatched inputs

| Screen | Common inputs | Arithmetic result | Pressure and applicability |
| --- | --- | --- | --- |
| Yangjie GBU 395-1AB control | 40 °C inlet, 40 W GBU allowance, assumed 1.25 K/W whole-bridge junction-to-case and 0.25 K/W case-to-sink. | At catalog 0.50 K/W and 500 LFM: `40 + 40 × (1.25 + 0.25 + 0.50) = 120.0 °C` junction. | Requires the **installed** 500 LFM fin path and controlled local PCB reservoir; no system pressure curve or measurement. Retained 107.86 °C PCB neck leaves 2.14 K to its 110 °C screen. |
| Yangjie GBU 396-1AB compact | Same bridge, loss, inlet and assumed package/contact terms as preceding row. | At catalog 1.07 K/W and 500 LFM: `40 + 40 × (1.25 + 0.25 + 1.07) = 142.8 °C`; 17.8 K above 125 °C design ceiling. | This is the cleanest matched GBU sink comparison because the catalog face-velocity condition is the same. Its one 41 CFM free-air fan cannot establish a required installed 500 LFM without a fan/system curve. |
| Yangjie GBU 392-120AB shared | Same GBU bridge allowance, inlet and assumed package/contact terms, **plus 65 W provisional other-PFC heat**. | At the 100 CFM catalog 0.16 K/W distributed-load datum: `40 + 105 × 0.16 + 40 × (1.25 + 0.25) + 105 / 56.92 = 118.64 °C` (rounded). | Different 100 CFM and distributed-load condition, so its 118.64 °C cannot be ranked against the 395's 120 °C as an installed improvement. Sanyo fan is rated 120 CFM free air and 100 Pa shutoff; ~30 Pa at 100 CFM is an initial duct budget, not a measured point. |
| Diodes GBJ 392-120AB checkpoint | **Different bridge and model**. 40 W GBJ allowance, 65 W other PFC and 5.6 W fan allowance; 40 °C inlet. | At catalog 100 CFM and 0.16 K/W: `40 + 110.6 × 0.16 + 110.6 × 0.0175694859 = 59.639 °C` conditional sink, 0.361 K below the GBJ FEM's prescribed 60 °C boundary. | The GBJ FEM's four diode nodes and case/lead network require that exact boundary; GBU aggregate junction term is not portable. Installed flow, loss, spreading and inlet order remain unknown. |

The superseded GBU 392 concept with two 41 CFM Sunon fans cannot reach 100 CFM even at zero pressure: its combined free-air endpoint is at most 82 CFM. No fan curve supports a numerical operating point for the actual grille, duct and enclosure. A free-air rating used as installed flow is an invalid input.

## Sensitivity inside each conditional model

These derivatives expose fragility; they do not add new validation. For the GBU 395 control at its assumed forced-flow resistance, **+5 K at the inlet adds 5 K to junction**; **+5 W bridge loss adds 10 K**. At 45 W and 45 °C, the series screen is 135 °C, above the 125 °C engineering ceiling. The GBU 392 shared screen charges added heat differently according to location: an extra 10 W of *other* heat adds approximately `10 × 0.16 + 10 / 56.92 = 1.78 K` at the bridge; an extra 10 W **in the bridge** also adds `10 × (1.25 + 0.25) = 15 K` through the assumed package/contact terms. This depends on the distributed sink model and unproved load partition.

For the GBJ cooling arithmetic, `T_sink = T_inlet + P_shared × (0.16 + 0.0175694859)` at the imposed 100 CFM. **+5 K inlet** moves the sink screen from 59.639 to 64.639 °C; **+10 W shared heat** moves it to 61.415 °C. Both leave the GBJ FEM's prescribed 60 °C nominal sink boundary and require a new package-model solve before any diode/joint temperature can be inferred. Natural-convection 0.50 K/W is a separate GBJ catalog datum, not a substitute forced-flow input.

## Decision gate for a useful U2 ranking

1. Freeze the exact bridge, board, clamp, sink, fan, duct and enclosure revision; do not interchange GBU and GBJ model outputs.
2. Replace assumed bridge/PFC/aux/inverter loss with simultaneous operating-point bounds and assign each source to sink, PCB, air or pan. Record low/high line, full/reduced load and pan state.
3. Determine the fan/system curve intersection at the final grille and fin path, including fan aging, blocked inlet, one-fan loss, heated inlet and recirculation. Measure pressure and flow together. Evaluate both independent and shared paths at **the same total heat and inlet state** once these exist.
4. Check bracket load path, clamp pressure, isolation, creepage, enclosure collisions and service volumes from a dated mechanical model. A sink hanging from bridge leads fails before thermal ranking.
5. Establish transient loss-of-flow and sensor-lag bounds. Current steady-state fan-loss cases cannot set a protective trip time.

Until these inputs exist, the 395 control and 392/Sanyo shared path remain independent concepts. The compact GBU sink is unfavorable in the matched catalog screen. Rev38's GBJ bridge and partial PFC stage do not have a qualified installed cooling choice.
