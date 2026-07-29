# UCC21550 Interface Contract (Rev1)

This is the implementation authority for the dual isolated gate driver. The
legacy L6491 notes are historical reference only.

| Signal/element | Contract |
|---|---|
| Device/package | UCC21550BDWKR, 14-pin DWK (SOIC). Corrected 2026-07-28: `UCC21550BDW` is not a TI orderable (SLUSE89C packaging addendum lists only `...DWR`/`...DWKR` tape-and-reel parts), and the board's land pattern has 14 pads numbered 1–11, 14–16 — the DWK package, which per SLUSE89C Figure 4-2 has no pin numbers 12 or 13. |
| VCCI | Control-side supply, 3.0–5.5 V; never the +15 V gate-power rail |
| VDDA/VDDB | Gate-side supplies per the selected driver variant and measured bootstrap design |
| DIS | Active-high disable; floating/open is safe (internal pull-up). The board net must be named and driven with active-high semantics. |
| DT | Use the datasheet-supported resistor implementation; the existing 5.1 nF capacitor is not accepted as the contract implementation. |
| Fault shutdown | OCP, OVP, thermal, watchdog, firmware runaway-cut, and the independent default-high RTD hardware path are schematically latched. Component-level SPICE and bench evidence remain release gates. |
| Latch | A real set-dominant SR latch holds shutdown after a fault; clearing the fault does not auto-resume. Reset is explicit and separately qualified. |
| Sensors | Open/short/out-of-range values are faults, not permissive readings. |
| MCU safety pins | WDI GPIO7, watchdog RESET_N GPIO6, reset request GPIO14, active-high runaway-cut GPIO15, and latched fault status GPIO20; PWM GPIO4/5 remain separate. SPI is GPIO8/10/11/12, MAX31865 DRDY is GPIO9, ZCD is GPIO13, relay is GPIO19, and optional I²C is GPIO38/39. |
| Domains | Keep CTRL_GND, HV_RTN, VSSA, and VSSB explicit. Isolation crossings require a named boundary and review. |

The DT starting value is 34.0 kΩ (1%). TI specifies approximately
`tDT(ns) = 8.6 × RDT(kΩ) + 13`; this is 305.4 ns nominal and about 302.5 ns
at the resistor's -1% corner at 25 °C. The bounded in-box model in
`elec/validation/ucc21550_dt_sim.py` also sweeps a 100-ppm/°C resistor from
−40 °C to 150 °C and a ±10% device characterization envelope. Under those
explicit assumptions the 34-kΩ corner range is 270.5–343.2 ns, so it does
*not* prove a 300-ns hardware minimum. Solving for the minimum resistance
across every temperature/TCR corner gives 37.87 kΩ; a nominal 39-kΩ resistor
clears 300 ns under that model (308.6 ns worst corner), but increases dead time
and still requires a board measurement. See the [UCC21550 datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf).

Exit criteria: schematic polarity and supply checks pass; latch truth table is
machine-checked; sensor and watchdog faults reach the latch; and the generated
netlist records the intended isolation boundary and net names.

Implementation status: the half-bridge now separates the 3.3 V VCCI rail from
the 15 V gate-side rail. DIS is active-high and driven by a fault-qualified
set-dominant NAND latch; watchdog RESET_N and firmware runaway-cut feed the
fault bus. The RTD hardware path is captured in the schematic as a
default-high/open-drain circuit with a window comparator, upstream-powered
post-rail monitor, and added fault-OR stage; executable behavioural SPICE and
property tests cover its stated fault states. It is still release-gated on
component-level SPICE and low-voltage bench evidence. DT now uses a resistor,
pending scope correlation.
