# PFC topology and startup review

Review target: `/private/tmp/temper-power-entry-20260912/elec/src/power_entry_unit.ato`.
This review gives source-validator requirements for the present active-boost
topology. It does not approve a mains assembly.

## Required net relationships

The validator should require these exact relationships, with distinct named
nodes where shown:

1. Rectifier `PLUS` must feed the boost inductor, then the MOSFET drain.
   The SiC diode anodes (`A1`, `A2`) must be at that drain and its common
   cathode (`K`) at `PFC_BUS_PLUS_390V`.
2. The rectifier `MINUS` node is the **rectifier-side** shunt terminal. It
   must connect to `shunt.p2`, and `pfc.ISENSE` must reach that same node
   through the 220 ohm input resistor. The clamp diode anode belongs at this
   node and its cathode at controller ground.
3. `shunt.p1`, MOSFET source, controller GND, and `CONTROL_GND` are the
   controller/power-return side of the shunt. Require `q_boost.S ~ shunt.p1`
   and `pfc.GND ~ shunt.p1`; do not collapse this node with `bridge.MINUS`.
4. The bulk capacitor negative terminals must be on `CONTROL_GND` (the
   MOSFET/controller side of the shunt), while their positives are on
   `PFC_BUS_PLUS_390V`. In the current source `c1.minus..c4.minus` connect to
   `hv_minus`, and `hv_minus` is tied directly to `bridge.MINUS`; this places
   the bank on the wrong side of the current shunt and bypasses the intended
   return sensing. This is the highest-priority topology correction.
5. The Y1 capacitor may connect bus negative to PE only as an explicitly
   safety-rated EMI path. It must not become a DC bond that defeats the
   shunt-side partition.

These requirements follow the UCC28180 Figure 26/current-sense arrangement
and its pin descriptions in the [TI UCC28180 datasheet, pp. 6 and 17–18](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).

## Startup and shutdown gaps

* The source has an NTC and a bypass relay, but no explicit bus-voltage
  threshold circuit or interlock proving that the relay closes only after
  precharge. `relay_ctrl` is an external header, so a validator may report
  “precharge sequencing not represented” rather than treating NTC presence
  as sequencing proof. The relay must remain open until a measured bus-ready
  condition is defined, and must open on fault/power loss.
* There is no represented bleeder/discharge resistor or active discharge
  path across the 2,240 uF, 450 V bus. UCC28180 soft-start/VCOMP discharge
  controls its gate command; it does not make the stored bus energy safe
  after input removal. Require an explicitly rated discharge path and a
  measured decay requirement, or mark post-power-off discharge deferred.
* There is no represented gate inhibit tied to bus-ready, auxiliary-supply
  validity, or downstream fault. UCC28180 UVLO only covers its VCC threshold
  (typical turn-on 11.5 V, turn-off 9.5 V); it is not an input contactor or
  bus isolation interlock. Keep this as an integration gap.
* The 15 V auxiliary return is tied to `CONTROL_GND`, which is connected to
  the hazardous rectifier/bus return. The source comment calls the supply
  separately qualified and isolated, but the netlist does not encode an
  isolation boundary. The validator should require an explicit bias-supply
  reference/isolation declaration before calling the AUX or relay-control
  interface SELV.

## What the structural validator can and cannot conclude

It can reject the current bulk-return/shunt-side contradiction, enforce
bridge/boost/diode polarity, require the 220 ohm ISENSE path and clamp, and
report missing precharge, discharge, and enable interlocks as indeterminate
integration requirements. It cannot establish NTC inrush performance,
relay timing, bus discharge time, controller loop stability, MOSFET/diode
temperature, capacitor ripple life, EMI, or insulation performance. Those
remain explicit physical qualification work after the topology is corrected.
