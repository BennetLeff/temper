# D-18 thermal allocation into an integrated R4 build

This is a transfer of the recorded 2026-10-03 decision in `zapote/power-stage-120v/DECISIONS.md` and its calculation at `zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D18/README.md` in the frozen `ps-oracle` worktree. The source is the current native-18 device arrangement, not the older enclosure's nominal 25 W assumption. The R4 assembled CAD must be rebuilt with this hardware.

## Accepted design allocations, not measured performance

| Quantity | Recorded allocation | What must be checked on the actual build |
| --- | --- | --- |
| Heatsink inlet | 50 °C design air at sink inlet inside enclosure | Measure there, not at room ambient; include pan heat soak and coil duct interaction. |
| Shared PE-bonded sink | `RθSA <= 0.15 °C/W` at operating flow | Obtain chosen assembly mounting curve and repeat at installed fan operating point. |
| Delivered sink flow | `>= 20 CFM` through dedicated duct, coil/right to mains/left | Measure installed flow/pressure and capture fan tolerance, blocked vent, dust and aging cases. |
| MOSFET interfaces | `RθCS <= 1.0 °C/W` per device, with electrical insulation | Selected ceramic/contact/clamp pressure and thermal/electrical tests; D-18 rejects SIL PAD K-10 (~1.75 °C/W for area transfer) and SIL PAD 400. |
| Bridge interface | D-18 *model* uses `0.45 °C/W` | Check actual contact footprint, mounting pressure and bridge case temperature. This was not an approved vendor guarantee. |
| Fan rail | Dedicated SELV 12 V supply, not PS1/J4.1 | Two catalog example fans are 11.4 W each, already above PS1's 21 W; selected fan load and stall protection remain open. |
| R5 | WSK2512R0010FEA retained; local ambient `<=100 °C` at worst sustained point | Thermocouple the shunt's local board environment and record current; reassess if hotter. D-18 calculated 0.68504 W candidate maximum, 2.0570 W across unprotected cases. |

At 50 °C inlet, D-18's conditional 62-case set with 20 CFM, `0.15 °C/W` sink and `1.0 °C/W` MOS interface predicts worst Q5 junction **105.59 °C**, leaving **19.41 °C** to the chosen 125 °C design target. That is not a guaranteed device-temperature bound: hot `RDS(on)` maximum is absent, the positive-terminal switching proxy is deliberately conservative but is not dissipative heat, the actual switching-event histogram is missing, and the model excludes some driver, CT, conversion and enclosure loads. The 125 °C number is the D-18 design target, not a derived certification limit.

The cited D-18 candidate example, Wakefield SFA2B1L, has a 305 × 60 mm sink with 68 mm fin/base height before two 25 mm fans, guards and brackets; its 0.094 °C/W catalog point assumes a simulated fully ducted assembly. A 305 mm sink **cannot be declared to fit** because native-18 is 240 × 160 mm, R4's old PCB import is historical, device contact span, leads, inlet/exit plenums and protective compartment are not joined in current CAD. A different class or split assembly needs a recalculated thermal and bond scheme. Do not remove the protective compartment to make the envelope pass.

## Thermal mule setup

Reuse `output/temper-engineering-validation/integration/channel-map.csv` (T06 sink inlet, T07 exhaust, T08 power hotspot, T04 sensor seal, T09 knob magnet, T10 UI sensor, T11 external ambient, D01 actual power, D04 fan state) and its `part-temperature-limits.csv`. Add separately located, calibrated sensors for **each MOSFET case**, bridge case, each interface-adjacent local sink spot, R5 ambient/element vicinity, the selected fan supply, display/carrier, glass bond and exterior touch points. Record sensor attachment method because a case reading is not a junction reading. Use independent flow/pressure measurement in the operating duct and time-align power, tank current, frequency, pan identity and temperature series. The power engineer defines instrument isolation and safe station before energization.

The minimum matrix is low/half/full requested power across the selected pan families, input-line corners, cold and heat-soaked enclosure, worst allowed user orientation/clearance and normal cooldown. Repeat controlled fan-slow/stall and obstructed intake as *fault* runs with protection active, never as continuous rated operating cases. Capture local maximum temperature and expanded uncertainty. A proposed pass calculation is `measured maximum + expanded uncertainty <= approved derated part/assembly limit`; leave limit blank until exact part, material, application standard, and engineering derating are signed. The shunt's <=100 °C local-ambient allocation and delivered-flow allocation are already recorded decisions but still require measurement.

Before heat testing, independently establish actual fan curve at system pressure, clamp/contact resistance, PE continuity including sink, controller response to fan fault, and the complete fault path in the separate T02 work. Do not infer fault survival from this steady heat budget. A change to sink, pad, fan, duct, board placement, or R4 cover invalidates affected thermal/insulation results and requires a new paired manifest.
