# U2 topology screen — no circuit selected

This is a bounded comparison using the Rev38 source snapshot in [energy-islands.md](energy-islands.md). The product discharge voltage/time limit, initial voltage envelope, inverter capacitance, mains-isolation behavior and single-fault rule are open. Consequently, no resistor, relay, semiconductor or safety rating is selected here. Run the source-contained arithmetic fixture in `evidence/discharge_screen.rs` to reproduce the nominal and mutation screens.

## What the historical target would cost

The earlier split-bus plan targeted <34 V in <60 s from roughly 170 V per half-bus. That target is neither a Rev38 requirement nor proof of an allowed bus voltage. As a **hypothetical 400 → 34 V sensitivity example**, an ideal 2688 µF tolerance-high VB bank must see total equivalent resistance at most

```text
R ≤ 60 / [0.002688 × ln(400/34)] = 9054.96 Ω.
I at 400 V = 44.17 mA; P if continuously energized = 17.67 W.
Initial stored energy at 400 V = 215.04 J; at 450 V = 272.16 J.
```

A path meeting that example must handle the bank's pulse energy on power removal and its **continuous** dissipation if engaged while mains is still present. At 450 V and the same 9.055 kΩ, continuous resistor power is about 22.36 W; 450 V is a bank rating-edge calculation, not permitted operation. A real design needs resistor tolerance, derating, hot enclosure, DC switching, inrush, timing margin and physical clearance. The proposed value is not a part selection. At tolerance-high VD C, either existing ladder alone takes 60.49–61.72 s for the same illustrative 400 → 34 V drop even before resistor tolerance; both intact take about 30.55 s. Thus a single-open path can cross that historical target, and the existing ladders cannot be declared fault-qualified.

## Alternatives

| Architecture | Nominal benefit | Failure and cost to prove |
| --- | --- | --- |
| Existing paths only | No new parts; both islands have some passive conductance with F2 open. | VB is roughly 28.5 min nominal to historical 34 V target with all paths, over 91 min if the bank bleeder opens. VD has no dedicated bleeder. None of these paths has accepted safety status or observation. |
| New passive paths on both VD and VB | Physical power-off behavior independent of logic; avoids DC switch action. | VB continuous dissipation becomes substantial for a short target. Each path must survive maximum energized bus, temperature, failed-short and single-open cases. Parallel redundancy may be needed. VD and VB still require separate measurement. |
| Normally engaged active path plus passive backup **per island** | Potentially low normal-run loss with faster discharge after supply loss. | AUX can disappear while mains still feeds the rectifier through NTC and boost diode. An engaged path may see continuous live-bus power. NC relay contacts need verified high-voltage **DC** make/break and coil collapse timing, or semiconductor SOA and default bias. A stuck-open contact falls back to the passive path's time; a stuck-closed device faces prolonged heat. |
| One active path on VB only | Fewer devices. | **Rejected as complete topology:** F2-open VD retains its own capacitor, and a later inverter disconnect can strand another reservoir. It cannot satisfy the island requirement. |

The legacy `BusDischarge`'s 170 V relay, snubber and resistor evidence does not establish DC operation at this bus voltage. Neither a catalog AC contact rating nor a resistor's continuous wattage by itself proves pulse, contact arc or hot enclosure behavior.

## Negative cases to carry into circuit selection

| Case | Required result in a future model/test |
| --- | --- |
| F2 open and both islands charged | Independently compute VD and VB decay; fail if only VB is drained. |
| F2 open and both VD ladders open | Current source has no VD-to-HOT0 resistor; require a new independent path or explicit failed-service disposition. |
| One bank bleeder resistor open | Existing detector-only path is very slow; fail any fast nominal target. |
| Active contact fails open or resistor fails open | Use remaining passive path, not nominal active time; report whether normal criterion still holds. |
| Active contact welded closed, mains live | Compute continuous power and component temperature with source-fed bus, not a finite-energy pulse only. |
| AUX collapses while mains remains | Do not solve an isolated RC; passive bridge/inductor/diode can replenish VD and, with F2 intact, VB. |
| Partial charge | Evaluate from each allowed initial voltage, including a restart request before discharge completes. |
| `VD = VB > 0` | Equal readings do not prove either safe charge or F2 continuity. Deny restart until absolute and continuity/precharge requirements are independently met. |
| Inverter local input capacitor disconnects | Model it as another isolated capacitor and require its own path/measurement. |
| Inverter bridge shorts VB | Do not credit F2 as a bank-side interrupter; assess bank energy and available source fault current. |

The Rust fixture checks the source-derived nominal topology and several negative mutations. It deliberately contains no assertion that a service limit is met. Circuit selection waits on the six decisions in [interface-contract.md](interface-contract.md).
