# Discharge interface contract — U1 candidate

Status: **design inputs and outputs, not an accepted circuit**. Source identity and island derivation are in [energy-islands.md](energy-islands.md).

| Port | Producer / consumer | Contract to freeze |
| --- | --- | --- |
| `VD_LOCAL`, `HOT0` | Rev38 diode-side reservoir → discharge unit | 22 µF + 470 nF candidate is upstream of F2. Account for VD when F2 is open. |
| `VB_BANK`, `HOT0` | Rev38 bank → discharge unit and inverter | Four 560 µF bank capacitors and directly connected inverter C stay bank-side of F2. |
| F2 state | Rev38 protection → analysis | Sole source-declared VD–VB separator. Equal voltage is neither continuity proof nor restart permit. |
| `C_inv`, disconnect, fault states | Inverter → discharge unit | Declare maximum input C, return, any separable local reservoir, bridge short and fault behavior. Re-run sizing after changes. |
| `AUX_PROTECTED` / HOT logic5 | Auxiliary / Rev38 → any active controller | Loss and partial collapse need a physical default. MCU command cannot be the sole power-loss trigger. With mains still applied, VD may recharge through the bridge, NTC, inductor and boost diode. |
| Residual-charge observations | Discharge → service procedure and Rev38 restart authority | Observe VD and VB **separately** as absolute voltage or justified equivalent. Specify accuracy, open-sense detection, powered-off availability and unsafe/unknown response. Existing HOT-powered F2 detector is not yet a service instrument. |

Rev38 implements no dedicated discharge-control/status port and no VD/VB output/service connector. These are requested interfaces, not claimed implementation. A proposed residual-charge output defaults to **unknown/unsafe** when its supply or sense path is absent. Firmware may consume evidence and sequence startup, but cannot establish that stored energy has fallen by itself. A documented technician measurement may instead satisfy service verification if the product access and restart requirements permit it.

## Scenarios before integration

1. **F2 open at maximum allowed initial VD and VB charge:** each side has a rated path and independent remaining-voltage verification. Bank-only discharge fails.
2. **Mains removed and AUX absent:** physical defaults engage required paths and meet adopted time/voltage across C/R, temperature and timing bounds.
3. **AUX absent but mains attached:** retained NTC and passive bridge/boost-diode route count as live. Engaged paths survive continuous powered stress, or a proved mains isolator prevents it.
4. **Single discharge element open, active contact stuck/welded, sense divider open, F2 open, or inverter input disconnect:** record each separately, including when the normal time requirement is not met.
5. **Restart with residual charge, including `VD = VB > 0`:** Rev38 denies restart until adopted absolute-voltage and F2/precharge conditions are met.
6. **Downstream inverter bridge short:** F2 is not a VB-side isolator. Bound bank energy and source current independently of gate inhibition.

## Decisions needed for U2

1. Adopt voltage/time limits for accessible service nodes and restart, with authority and verification method. Legacy 34 V/60 s applies to the old split-half-bus plan only.
2. Freeze actual maximum initial VD and VB voltage and fault-transient envelope. The 450 V bank rating is not the limit; Rev38's conditional 500 V VD screen cannot be copied to VB.
3. Declare inverter input capacitance, DC link disconnect, output/service connector and enclosure access geometry.
4. Decide whether one failed resistor or actuator must still meet normal discharge time, or whether failure detection plus manual verification is acceptable.
5. Define normal stop with mains attached, mains removal, AUX collapse with mains attached and restart: when an active path engages/releases and how energized continuous load is bounded.
6. Select exact switch/contact, resistor, observation and insulation parts only after these inputs; verify DC make/break, pulse/sustained energy, sharing, spacing and thermal envelope.

The historical `elec/src/modules.ato:BusDischarge` has two ~170 V half-buses, a different return and relay contacts with no established ~390 V DC duty. It is a comparison, not a circuit source.
