# Power-entry exact-parts audit

This is a read-only parts resolution record for source-build-16. It does not
qualify the PFC at 1800 W or establish distributor stock.

## Passive candidates

| Function | Value | Candidate identity | Package / rating evidence |
|---|---:|---|---|
| Gate / pull-down / compensation / frequency / sense resistors | 10 Ω, 10 kΩ, 1 kΩ, 100 kΩ, 220 Ω, 16.2 kΩ, 13 kΩ, 22.6 kΩ | Yageo RC1206FR-07 series, value suffixes 10RL, 10KL, 01KL, 100KL, 220RL, 16K2L, 13KL, 22K6L | 1206, 1%, 0.25 W; verify each exact suffix and working-voltage limit before release |
| HV feedback chain | 200 kΩ x5 | Vishay TNPW1206200KBEEA family candidate | 1206 thin-film, 200 kΩ, 0.1%; verify 200 V working rating and exact order code; five series parts are required |
| Relay dropper | 91 Ω | Yageo RSF100JB-73-91R | Axial metal-film, 1 W, 5%; existing repo evidence identifies this exact part |
| Controller bypass | 1 µF / 50 V | Murata GRM21BR71H105KA12L | 0805 X7R candidate; verify exact capacitance and voltage code |
| ICOMP | 2.2 nF, C0G, 50 V | Murata GRM21C5C1H222JA01L candidate | 0805 C0G candidate; verify exact order code |
| VCOMP | 10 µF / 10 V and 330 nF / 50 V | Murata GRM21BC71A106KE51L and GRM21BR71H334KA01L candidates | 0805 X7R candidates; verify DC-bias and exact order codes |
| VSENSE feed | 680 pF and 1 nF, C0G, 50 V | Murata GRM21C5C1H681JA01L and GRM21C5C1H102JA01L candidates | 0805 C0G candidates; verify exact order codes |

The source currently carries generic passive MPN fields inherited from the
first native transport. They must be replaced with verified exact suffixes
before a qualification claim. The TI compensation values are provisional from
the separate calculation record.

## Interface parts

The intended mains connector is Phoenix Contact MSTB 2,5/3-ST-5,08, a
three-position 5.08 mm terminal system. Its local footprint is retained under
`pcb/libs/temper.pretty/MSTB_2,5_3-G-5.08.kicad_mod`; connector current and
creepage still require datasheet and enclosure verification.

The auxiliary/control header identity `Wurth WR-PHD 61300211121` is an
existing verified 1x2 header identity, but it is not a mains connector. The
required 10 A / 600 V, 10.16 mm pitch output connector has no resolved part in
source-build-16 and remains an explicit integration blocker.

References: [Ametherm SL32 10015 mechanical/electrical data](https://www.ametherm.com/datasheets/sl3210015), [Vishay IHV series drawing](https://www.vishay.com/docs/34022/ihv.pdf), and [TI SLUP348 reference design](https://www.ti.com/seclit/ml/slup348/slup348.pdf).
