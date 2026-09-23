# Rev38 AC input candidate

`elec/src/ac_input.ato` joins the mains connector to the PFC bridge in the
same Atopile entry as the receiver and gate path. This is a connectivity
candidate, not an approved mains input or an installed fuse.

| Conductor | Compiled route |
| --- | --- |
| L | Connector pin 1 → Schurter `0031.2510` **holder** pins 1–2 → TDK `B82726S2163N030` CMC pins 1–4 → Ametherm `SL32 10015` NTC pins 1–2 → bridge AC pin 2. |
| N | Connector pin 2 → CMC pins 2–3 → bridge AC pin 3. |
| PE | Connector pin 3 → Vishay `VY1102M31Y5UQ63V0` Y1 pin 2; Y1 pin 1 reaches HOT0. There is no direct PE–HOT0 copper join. |

The TE `RT33K012` normally open contact connects CMC L output to bridge L
in parallel with the NTC. Its coil receives `AUX_PROTECTED` through a 91 Ω
candidate resistor and returns through an `AO3400A` low-side switch to
HOT0. AVR PA2/32 drives the switch gate through 1 kΩ; a local 100 kΩ
pull-down holds it low. `SS14` is across the coil, cathode at the positive
end. The SELV relay request reaches AVR PA5/3 as an input and does not
directly energize the coil.

The TDK `B32922C3224M289` X2 capacitor and Littelfuse `V150LA10AP` MOV
span fused L and incoming N. The netlist audit checks those exact pins,
the fuse-holder series route, NTC/contact parallelism, PE capacitor,
coil polarity, and the joined AC and relay-control nets. Nine AC-specific
positive and deliberate-miswire tests accompany the full Rev38 audit.

## Open physical and protection gates

- The 15 Arms requirement leaves little nominal current headroom: the
  [relay contact](https://www.te.com/en/product-2-1393240-3.html) and
  [CMC](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s2163.pdf)
  are each rated 16 A, the
  [NTC](https://www.ametherm.com/datasheets/sl3210015) lists 15 A maximum
  steady state, and the [holder](https://www.schurter.com/en/datasheet/typ_FUP.pdf)
  lists 16 A VDE at 23 °C with ambient derating. These are individual
  component nameplates, not an assembly temperature or endurance proof.
  The NTC's 15 A rating is especially relevant if the relay stays open.
- Select the actual F1 cartridge, verify the holder and cartridge as one
  assembly, and coordinate F1/F2 clearing, available fault current,
  interrupting rating, inrush, and MOV end-of-life behavior. The holder
  alone has no defined fuse characteristic.
  The retained baseline's Schurter `0034.3129` is a 16 A FST link whose
  [published breaking capacity](https://www.schurter.com/en/datasheet/typ_FST_5x20.pdf)
  is `10 × In` at 250 VAC, or 160 A; it is not a qualified default for this
  unknown prospective fault current. Schurter's
  [FUP holder sheet](https://www.schurter.com/en/datasheet/typ_FUP.pdf)
  references FST and SP 5×20 links, but does not list SPT 5×20. The
  [16 A SPT link](https://www.schurter.com/en/datasheet/typ_SPT_5x20.pdf)
  has a 500 A at 250 VAC breaking-capacity entry and lists other matching
  holders. Do not treat that link and FUP as a validated pair or 500 A as
  sufficient until available fault current, time/current coordination,
  holder match, and 40 °C power acceptance are established.
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
  resulting mechanical contact state. The relay is a precharge bypass,
  not a fault-current interrupter or a gate-authorization path.
- Join a protected AUX source and assess its startup, hold-up, loss and
  transients against the rail detectors and PFC power path. No upstream
  AUX source is present in this candidate.

No mains energization, thermal qualification, leakage or safety
certification has been performed on this Rev38 circuit.
