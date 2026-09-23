# Rev38 stored-energy islands — U1 in progress

Source snapshot: `06d9070c3`, `interface-integration-38/elec/src/pfc_power.ato`. Component values below are source candidates; tolerances, maximum operating voltage and physical discharge remain unqualified.

| Island | Candidate source elements | Return and isolation | Nominal energy screen at 400 V | Existing discharge path |
| --- | --- | --- | ---: | --- |
| VD diode-side local reservoir | 22 µF TDK `B32776P6226K000` plus 470 nF TDK `B32672P6474K000`, both 630 V candidates | `VD_LOCAL` to `HOT0`; F2 separates VD from VB | 1.798 J using 22.47 µF | No dedicated VD bleeder appears in `pfc_power.ato`. Sense/control loading cannot be credited without a guaranteed path. |
| VB bank | Four 560 µF Nichicon `LGX2W561MELC50` in parallel, 450 V candidates | `VB_BANK` to `HOT0`; F2 lies between VB and VD | 179.2 J using 2240 µF | Three 150 kΩ Yageo elements in series, nominal 450 kΩ; single-open behavior unresolved. |
| Downstream inverter | No selected standalone input capacitor or tank yet | Connection and disconnect boundary pending inverter U1 | Unknown | Unknown; cannot be recorded as zero. |

The nominal VB bleeder time constant is `450 kΩ × 2240 µF = 1008 s`. An ideal constant-capacitance screen from 400 V to **34 V** gives `1008 × ln(400/34) = 2484.8 s`, about 41.4 min. The 34 V point is an older project target used only for comparison here; it is **not adopted as this unit's requirement**. Capacitor tolerance, leakage, resistor tolerance/voltage sharing, auxiliary paths and faults are excluded. One open series bleeder removes the described bank path. VD may stay charged after F2 opens.

## Required state cases

| Event | VD | VB | Required next evidence |
| --- | --- | --- | --- |
| Mains removed, F2 intact | Coupled to VB while F2 conducts | Existing bank bleed candidate | Prove input isolation, discharge current paths and safe threshold/time. |
| F2 opens while charged | Separate local reservoir | Separate bank | Each needs its own bounded path and observation. |
| Auxiliary power lost | No firmware response may be assumed | No firmware response may be assumed | Active path must default to its intended state from physical rail behavior. |
| One active device/contact or bleed resistor fails | Potential retained charge | Potential retained charge | Single-fault coverage and service verification. |
| Restart with VD=VB >0 | Equal voltage does not prove continuity or safe charge | Equal voltage does not prove continuity or safe charge | Rev38 must separately authorize restart after residual-charge and F2 checks. |

## U1 exit gaps

Adopt an authoritative service/restart voltage-time criterion; determine maximum actual VD/VB voltage and capacitor tolerance; map any inverter-side input capacitance; name accessible nodes and measurement method; freeze the exact Rev38 source hash before topology sizing.
