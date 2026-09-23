# Rev38 AC input candidate

`elec/src/ac_input.ato` joins a **fused-line PCB terminal** to the PFC bridge
in the same Atopile entry as the receiver and gate path. This is a
connectivity candidate, not an installed fuse or approved mains input. The
Schurter 5×20 PCB holder was removed from Rev38. `F1-SCREEN.md` nominates an
Eaton Class CC cartridge and off-board block for a proposed general
residential installation envelope and defines the still-unbuilt external
harness. The PCB source represents only the downstream side of F1.

| Conductor | Compiled route |
| --- | --- |
| Fused L | `1714984` board terminal pin 1 → TDK `B82726S2163N030` CMC pins 1–4 → Ametherm `SL32 10015` NTC pins 1–2 → bridge AC pin 2. F1 and the inlet are off-board. |
| N | Board terminal pin 2 → CMC pins 2–3 → bridge AC pin 3. |
| PE | Board terminal pin 3 → Vishay `VY1102M31Y5UQ63V0` Y1 pin 2; Y1 pin 1 reaches HOT0. There is no direct PE–HOT0 copper join. A separate chassis bond is required. |

The TE `RT33K012` normally open contact connects CMC L output to bridge L
in parallel with the NTC. Its coil receives `AUX_PROTECTED` through a 91 Ω
candidate resistor and returns through an `AO3400A` low-side switch to
HOT0. AVR PA2/32 and retained `HOT_RUN_Q` enter the receiver's second
`SN74HCS21PWR` gate; its output drives the switch gate through 1 kΩ. A local
100 kΩ pull-down holds the MOSFET off if HOT logic5 or that output is absent.
`SS14` is across the coil, cathode at the positive
end. The SELV relay request reaches AVR PA5/3 as an input and does not
directly energize the coil.

The TDK `B32922C3224M289` X2 capacitor and Littelfuse `V150LA10AP` MOV
span fused L and incoming N. The netlist audit checks those exact pins,
the fused-board terminal, NTC/contact parallelism, PE capacitor,
coil polarity, and the joined retained-RUN-qualified relay-control nets. Nine AC-specific
positive and deliberate-miswire tests accompany the full Rev38 audit.

## Open physical and protection gates

- The 15 Arms requirement leaves little nominal current headroom: the
  [relay contact](https://www.te.com/en/product-2-1393240-3.html) and
  [CMC](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s2163.pdf)
  are each rated 16 A, the
  [NTC](https://www.ametherm.com/datasheets/sl3210015) lists 15 A maximum
  steady state. These are individual
  component nameplates, not an assembly temperature or endurance proof.
  The NTC's 15 A rating is especially relevant if the relay stays open.
- Build the nominated `LP-CC-20` Class CC cartridge and `BCM603-1P` mounting
  block into the off-board inlet harness, then verify the installed
  fuse, block, wiring and enclosure as one assembly. Coordinate F1/F2
  clearing, available fault current, inrush, and MOV end-of-life behavior.
  The old 5×20 options and their rejection reasons remain in `F1-SCREEN.md`;
  none is present in the Rev38 PCB candidate. The proposed Class CC pair is
  a component nomination, not an installed or electrically qualified F1.
- Confirm certified X2/Y1 and MOV ordering codes, electrical ratings,
  discharge path for X2, protective-earth leakage, required creepage and
  clearance, connector/trace ratings, and line transient exposure at
  108–132 Vac. Footprints marked `TBD_REVIEW_ONLY` are deliberately not
  manufacturing land patterns.
- Establish CMC, NTC, relay contacts, coil resistor, and connector thermal
  limits at the required 15 Arms and 40 °C inlet, including low-line,
  repeated starts, welded/stuck-open contact, and loss of AUX. Select a
  precharge interval from measured bus charging and NTC cooling, then
  prove that the relay cannot close before the permitted condition.
- Verify coil pickup/dropout across the full AUX range and resistor
  tolerance, MOSFET gate levels, flyback voltage and release time, and the
  resulting mechanical contact state. A retained source relay request alone
  cannot drive the gate after HOT RUN clears in the compiled topology;
  physical release latency and stuck/welded contact remain unmeasured. The
  receiver firmware still holds PA2 low pending a precharge policy. The
  relay is a precharge bypass,
  not a fault-current interrupter or a gate-authorization path.
- Join a protected AUX source and assess its startup, hold-up, loss and
  transients against the rail detectors and PFC power path. No upstream
  AUX source is present in this candidate.

No mains energization, thermal qualification, leakage or safety
certification has been performed on this Rev38 circuit.
