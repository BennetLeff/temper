# Passive Rev A protection and thermal disposition

**Status: CONDITIONAL DESIGN CHECKPOINT — not qualified, not routed, not for
powered operation.**

## 1. What this closes

The retained passive baseline is now the explicit comparison unit. Its four
diode elements are contained in the exact GBJ2510-F package, and the retained
loss screen reports 28.304 W of fixed forward-drop loss at its stated operating
point. The coupled
Gmsh/Elmer run is reproducible and converged, but it is conditional on its
prescribed cut and sink temperatures and does not prove the installed board's
temperature.

The protection topology is also explicit. A line-fed fault and an internal
capacitor discharge are different circuits and must not share a fuse argument.

## 2. Topology and fault cases

The next passive schematic shall reserve the following series path:

```text
bulk capacitor +  -- F2 --  U10 cathode / boost-diode side
bulk capacitor -  ---------- U9 source / PFC_BUS_MINUS
```

The intended internal fault is **U10 failed short and U9 conducting or failed
short**. That path is `bank+ -> F2 -> U10 -> a1 -> U9 -> bank-`. F2 is the
only proposed interrupter in that path. U12 is on the rectifier return side,
not in this loop; F1 is in the AC line path and cannot interrupt stored bank
energy.

The cases must remain separate:

| Case | Source | What can act | Current disposition |
| --- | --- | --- | --- |
| Bridge/boost switch line short, U10 healthy | AC mains | F1, if its total clearing is coordinated | **Unestablished**; prospective line impedance and F1 total clearing are missing |
| U10 failed short, U9 healthy | 400 V bank | U9 might turn off after a real detector and bounded delay; F2 remains series backup | **Unestablished**; no detector/latency/survival proof |
| U10 and U9 failed short | 400 V bank | F2 only | **Unestablished**; no capacitor-discharge let-through or MBC data |
| F2 open after an event | residual bank energy | a separately rated discharge path | **Open**; opening F2 does not make the bank safe |

The GBJ2510-F's catalogue `IFSM`/I²t figures, where applicable, describe the
four diode elements inside the passive bridge package. They do not qualify F2
or any active-bridge replacement.
Normal U9 `RDS(on)` must not be used as a failed-short fault resistance.

## 3. F2 selection and exact evidence

The candidate is **Mersen A70QS50-14F**. The retained catalogue gives:

- 50 A rated current and 14 x 51 mm French cylindrical body;
- 890 Vdc capacitor-discharge rating, explicitly limited to a 2.5 ms
  time-constant condition. The catalogue uses `L/R` for some general DC
  tables, but the retained A70QS capacitor-discharge sentence does not
  explicitly define its time constant; the application interpretation remains
  a manufacturer question;
- 280 A²s maximum pre-arcing/melting I²t;
- 1,500 A²s maximum clearing I²t at 700 Vac, which is **AC data and cannot be
  substituted for capacitor-discharge clearing**;
- no published A70QS minimum-breaking-current value; and
- no published 890 Vdc capacitor-discharge clearing I²t or let-through curve.

Those facts support the part class and location only. They do not establish
that this fuse clears the board's fault. The earlier R/L sweep is a sensitivity
screen, not an operating envelope: bank tolerance, semiconductor short
residuals, package inductance, fuse impedance and copper geometry are not
closed bounds.

## 4. Design inputs and qualification gates

Items 1–5 determine the protection ECO and its qualification envelope. A
prototype CAD revision can be prepared with explicit unresolved conditions;
it cannot be released as a coordinated protection design on that basis. Item
6 is subsequent physical qualification, not a prerequisite for drawing the
circuit or building an unpowered prototype:

1. **Holder candidate (now sourced):** use one Mersen **UltraSafe US141**
   single-pole 14 x 51 mm holder, catalogue/reference **Z331153**. Mersen's
   product sheet lists **UL DC ratings** of 1000 Vdc, 50 A and 50 kA,
   separately from its 750 Vdc general rating; it also lists 8 kV impulse
   withstand and IP20. The 50 kA holder rating is not an independent ability
   to interrupt current. The sheet specifies non-load operation, 5 W
   dissipation at its 50 A free-air thermal rating, ambient derating and
   fuse-class/wire-size dependent operational-current limits. These conditions
   must be checked against the exact fuse and installation. This is a better
   source match than a generic clip because it is the fuse manufacturer's
   holder family for 14 x 51 mm A70QS links. It is a DIN-rail/enclosure holder,
   not a PCB footprint: the ECO must define its mounting, cable terminals,
   touch/creepage, terminal heating and interconnect R/L. Its rating does not
   qualify the fuse's capacitor-discharge clearing.
2. **Fault envelope:** a reviewed R/L/voltage/energy envelope using maximum
   bus voltage and capacitor tolerance, with U10/U9 failed-short states kept
   separate from the healthy-U9 detector case.
3. **Fuse application data:** an exact-part DC capacitor-discharge let-through
   curve or manufacturer application confirmation covering the envelope,
   including minimum breaking current and the stated time-constant condition.
   If the manufacturer cannot support it, the candidate is rejected or a
   supported alternative is selected; no AC I²t substitution is allowed.
4. **Withstand coordination:** bank, copper, diode, switch and enclosure
   withstand must exceed the applicable let-through and arc energy. A fuse
   opening is not evidence that the remaining bank is discharged.
5. **Line path:** establish source impedance and F1 total clearing against the
   passive bridge's fault withstand. F2 is not a replacement for F1.
6. **Physical test:** an approved, current-limited fault test on the exact
   assembly is required before `CoordinationDemonstrated` or `HardwareVerified`.

The holder source is captured as
`sources/Mersen-US14.pdf` (SHA-256
`776c47a6781b1d82d762a827d2ceed9d7e17b15439217b9fb5dc259aa9884562`) from
Mersen's [US14 data sheet](https://www.mersen.com/sites/default/files/medias/PIM/files/DS-Semiconductor-Modular-Fuse-Holders-UltraSafe-US14-EN.pdf);
the [US141 product record](https://www.mersen.com/en/products/ultrasafe-us14-modular-fuse-holders/z331153-us141)
confirms the exact reference. Those sources support a concrete enclosure
holder candidate; they do not close the combined fuse assembly.

For this checkpoint, the status remains `protection_identified` /
`part_selected`; neither coordination nor hardware verification is claimed.
A clean ERC/DRC result, a schematic netlist, or a catalogue current rating
cannot promote it.

## 5. Thermal gate for the passive baseline

The existing bridge model reports a **40 W package heat allowance** for its
thermal solve; the separate 28.304 W fixed-forward-drop value is a loss screen,
not the heat input used to produce the temperatures. Under the prescribed
reservoirs, the finest nominal case gives approximately 80.2 °C package
temperature and 84.3 °C hottest joint. A weak-assembly sensitivity reaches
approximately 96.0 °C package and 117.8 °C joint; a fan-loss case is
approximately 119.5 °C package. These are model outputs, not measured or
installed-board temperatures.

The passive baseline is thermally defensible enough to be the comparison
baseline, but not yet thermally qualified. Before release, bind:

- the actual heatsink, interface material and copper/FR-4/via heat paths;
- enclosure airflow and ambient limits;
- bridge body and joint temperature limits for the exact GBJ2510-F;
- 108–132 V, startup and overload loss cases; and
- a calibrated powered test with thermocouples or equivalent junction method.

If the installed result exceeds the product limit, reopen the active-bridge
comparison. Until then, the passive board remains the honest baseline.

## 6. Result

This checkpoint improves the design basis but does **not** reach the requested
protected/thermally defensible hardware milestone. It has a concrete topology,
an exact F2 and enclosure-holder candidate, and a bounded thermal evidence
statement. Coordination, installed cooling and physical qualification remain
open. The next useful action is to resolve the holder/interconnect installation
and fuse application data, then route one passive revision through the normal
Atopile → KiCad → Rust validation flow.
