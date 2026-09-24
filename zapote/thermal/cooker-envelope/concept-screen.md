# Bounded cooling concept screen

This is a U2 screening result for the source snapshot `cbfcc2ebc`, not a candidate selection or whole-cooker thermal qualification. It uses retained numerical inputs exactly where their source identities apply. The `loss-ledger.md` defines those identities. No installed pressure/flow intersection or enclosure CAD exists; assembly ranking is **INDETERMINATE**.

The frozen Rev38 power-path source comes from parent commit `06d9070c34e1244686965893f58d943a3ae0d340`: `elec/src/pfc_power.ato` SHA-256 `e3daa14ea8b74344c307a86908c86cbf4d9b44447af367febeb4b581a84ba761`; `elec/src/driver_stage.ato` SHA-256 `a5896531ef006dfa390b9fdee7ad6a681f87a8105c15f627911d24c39c5b741c`. The parallel active Rev38 checkout has additional uncommitted work; none of its new loss or supply proposals is adopted in this screen. Retained GBU and GBJ PDF hashes are in `loss-ledger.md`. The retained screen input files hash to `c0a70cc620b5dc6ef40cff90afb8b068a97a2f8883707672caae9966c86a4619` (GBU 395 proposal), `7d61199a3ebcdcdecd93335b2459cec6ba9d7b51a5b4426a339f825d0c34263b` (GBU 392/Sanyo proposal) and `b06c1afcac928921a39823cef843fea559e04cac9e17da4a82461c61153ef188` (GBJ passive thermal budget).

## Matched and unmatched inputs

| Screen | Common inputs | Arithmetic result | Pressure and applicability |
| --- | --- | --- | --- |
| Yangjie GBU 395-1AB control | 40 °C inlet, 40 W GBU allowance, assumed 1.25 K/W whole-bridge junction-to-case and 0.25 K/W case-to-sink. | At catalog 0.50 K/W and 500 LFM: `40 + 40 × (1.25 + 0.25 + 0.50) = 120.0 °C` junction. | Requires the **installed** 500 LFM fin path and controlled local PCB reservoir; no system pressure curve or measurement. Retained 107.86 °C PCB neck leaves 2.14 K to its 110 °C screen. |
| Yangjie GBU 396-1AB compact | Same bridge, loss, inlet and assumed package/contact terms as preceding row. | At catalog 1.07 K/W and 500 LFM: `40 + 40 × (1.25 + 0.25 + 1.07) = 142.8 °C`; 17.8 K above 125 °C design ceiling. | This is the cleanest matched GBU sink comparison because the catalog face-velocity condition is the same. Its one 41 CFM free-air fan cannot establish a required installed 500 LFM without a fan/system curve. |
| Yangjie GBU 392-120AB shared | Same GBU bridge allowance, inlet and assumed package/contact terms, **plus 65 W provisional other-PFC heat**. | At the 100 CFM catalog 0.16 K/W distributed-load datum: `40 + 105 × 0.16 + 40 × (1.25 + 0.25) + 105 / 56.92 = 118.64 °C` (rounded). | Different 100 CFM and distributed-load condition, so its 118.64 °C cannot be ranked against the 395's 120 °C as an installed improvement. Sanyo fan is rated 120 CFM free air and 100 Pa shutoff; ~30 Pa at 100 CFM is an initial duct budget, not a measured point. |
| Diodes GBJ 392-120AB checkpoint | **Different bridge and model**. 40 W GBJ allowance, 65 W other PFC and 5.6 W fan allowance; 40 °C inlet. | At catalog 100 CFM and 0.16 K/W: `40 + 110.6 × 0.16 + 110.6 × 0.0175694859 = 59.639 °C` conditional sink, 0.361 K below the GBJ FEM's prescribed 60 °C boundary. | The GBJ FEM's four diode nodes and case/lead network require that exact boundary; GBU aggregate junction term is not portable. Installed flow, loss, spreading and inlet order remain unknown. |

The superseded GBU 392 concept with two 41 CFM Sunon fans cannot reach 100 CFM even at zero pressure: its combined free-air endpoint is at most 82 CFM. No fan curve supports a numerical operating point for the actual grille, duct and enclosure. A free-air rating used as installed flow is an invalid input.

**Necessary airflow checks, before any thermal value is credited:** the GBU 395 gross-face 500 LFM condition needs roughly 43.4 CFM through the fins; the two Sunon fans provide 82 CFM only at zero pressure and at most 44.8 Pa at zero flow **per fan**. The GBU/GBJ 392 catalog point needs 100 CFM; Sanyo's 120 CFM and 100 Pa ratings are opposite endpoints. The retained 12 V Sanyo curve suggests a roughly 30 Pa initial maximum system budget at 100 CFM, which is unverified in a cooker. At 7 V, the fan remains within its operating range but the 12 V curve and 100 CFM catalog sink point cannot be credited. The active airflow gate therefore needs a **measured or validated curve intersection at the chosen supply voltage**, not an endpoint comparison.

## Sensitivity inside each conditional model

These derivatives expose fragility; they do not add new validation. For the GBU 395 control at its assumed forced-flow resistance, **+5 K at the inlet adds 5 K to junction**; **+5 W bridge loss adds 10 K**. At 45 W and 45 °C, the series screen is 135 °C, above the 125 °C engineering ceiling. The GBU 392 shared screen charges added heat differently according to location: an extra 10 W of *other* heat adds approximately `10 × 0.16 + 10 / 56.92 = 1.78 K` at the bridge; an extra 10 W **in the bridge** also adds `10 × (1.25 + 0.25) = 15 K` through the assumed package/contact terms. This depends on the distributed sink model and unproved load partition.

For the GBJ cooling arithmetic, `T_sink = T_inlet + P_shared × (0.16 + 0.0175694859)` at the imposed 100 CFM. **+5 K inlet** moves the sink screen from 59.639 to 64.639 °C; **+10 W shared heat** moves it to 61.415 °C. Both leave the GBJ FEM's prescribed 60 °C nominal sink boundary and require a new package-model solve before any diode/joint temperature can be inferred. Natural-convection 0.50 K/W is a separate GBJ catalog datum, not a substitute forced-flow input.

## Decision gate for a useful U2 ranking

1. Freeze the exact bridge, board, clamp, sink, fan, duct and enclosure revision; do not interchange GBU and GBJ model outputs.
2. Replace assumed bridge/PFC/aux/inverter loss with simultaneous operating-point bounds and assign each source to sink, PCB, air or pan. Record low/high line, full/reduced load and pan state.
3. Determine the fan/system curve intersection at the final grille and fin path, including fan aging, blocked inlet, one-fan loss, heated inlet and recirculation. Measure pressure and flow together. Evaluate both independent and shared paths at **the same total heat and inlet state** once these exist.
4. Check bracket load path, clamp pressure, isolation, creepage, enclosure collisions and service volumes from a dated mechanical model. A sink hanging from bridge leads fails before thermal ranking.
5. Establish transient loss-of-flow and sensor-lag bounds. Current steady-state fan-loss cases cannot set a protective trip time.

A discharge fault adds a separate common-mode heat case: the conditional NC VB resistor bank can draw 27.0 W at the 450 V rating-edge screen, or 40.5 W after one series-resistor short, while the same AUX loss may remove forced airflow. Neither value belongs in the 110.6 W normal GBJ catalog comparison; the resistor-to-chassis/air path and peak temperatures need a no-fan, mains-attached fault model before the NC design can be promoted. See [cooling handoffs](unit-handoffs.md) and [discharge U2 screen](../../discharge/topology-screen.md).

Until these inputs exist, the 395 control and 392/Sanyo shared path remain independent concepts. The compact GBU sink is unfavorable in the matched catalog screen. Rev38's GBJ bridge and partial PFC stage do not have a qualified installed cooling choice.

## Digital acceptance cases for the eventual Rust gate

These cases are executable-test specifications for `zapote-thermal` when that owner receives the complete inputs. `CONDITIONAL_SCREEN_PASS` never means installed thermal acceptance.

| Case | Input mutation or complete bounded input | Required digital result |
| --- | --- | --- |
| `source-changed` | Any file in `sources.sha256` changes without reviewed rebinding. | `INVALID_INPUT`; no old numerical result is replayed as current. |
| `mixed-bridge` | GBU bridge with GBJ four-diode network, or GBJ bridge with GBU whole-bridge 1.25 K/W assumption/395 neck result. | `INVALID_INPUT`; candidate identity and thermal boundary must match. |
| `missing-heat` | Omit bridge, PFC switch, diode, inductor, fan/aux or inverter heat from a proposed **whole-cooker** comparison. | `INDETERMINATE`, never zero-filled. A bridge-only screen may run if explicitly labeled as bridge-only. |
| `free-air-as-installed` | Supply 120 CFM Sanyo or 2 × 41 CFM Sunon free-air endpoint as an installed fin-path value. | `INVALID_INPUT`; require fan/system intersection or direct flow/pressure measurement at same operating point. |
| `unsupported-sink` | Mark heatsink/duct load path through bridge leads, pads or PCB solder rather than an independent chassis bracket. | `INVALID_INPUT`; thermal arithmetic cannot waive mechanical support. |
| `GBU-compact-catalog` | Exact retained GBU 40 W, 40 °C, 500 LFM and 396-1AB data. | `SCREEN_FAIL`: 142.8 °C exceeds 125 °C, even before installed-flow uncertainty. |
| `GBU-395-catalog` | Exact retained 40 W/40 °C/500 LFM and 395-1AB data. | `CONDITIONAL_SCREEN_PASS` for 120 °C junction only; local PCB result is separately 107.86 °C with 2.14 K margin. Assembly applicability remains `INDETERMINATE`. |
| `GBJ-392-catalog` | Exact retained 110.6 W/40 °C/100 CFM and 392-120AB data. | `CONDITIONAL_SCREEN_PASS` for a 59.639 °C sink only. A +10 W or +5 K input must invalidate the old 60 °C FEM-boundary claim until a new solve; assembly applicability `INDETERMINATE`. |
| `fan-stall-and-recovery` | Tach stops after ready, then returns because motor self-restarts. | Cooling healthy sink turns off and latch remains set through recovery; new heating permission needs deliberate reset after fault clearance. |

The present source-locked arithmetic and fan state contract cover the **specification** side of these cases. No production Rust gate, native fan circuit or installed test has been added under this document-only ownership.

## Reproduce the existing arithmetic without new model code

Run the retained GBJ budget's own Rust tests:

```sh
shasum -a 256 -c zapote/thermal/cooker-envelope/sources.sha256
rustc --edition=2021 --test zapote/power-entry/passive-reva/cooling/budget_calc.rs \
  -o /private/tmp/zapote-gbj-budget-test
/private/tmp/zapote-gbj-budget-test
```

The GBU cases follow the four equations in the table above, using the exact proposal files and `zapote/thermal/cooling-options/loss-budget.md`. The table is only a sensitivity screen; the retained GBU local-thermal replay command is in `zapote/thermal/bridge-cooling.md`. Do not copy its result to a changed board or the GBJ bridge. Re-run source hashes before relying on a later checkout. A future production numerical gate belongs in the existing `zapote-thermal` Rust crate once loss, airflow and mechanical inputs are frozen.
