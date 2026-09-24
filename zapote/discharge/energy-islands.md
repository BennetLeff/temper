# Rev38 stored-energy islands — U1 source inventory

Status: **source-derived topology and nominal analytical screen; discharge acceptance open**. Rev38 is a compiled candidate with no routed discharge unit, no output connector, and no measured bus voltage or discharge time. The source `pfc_power.ato` is at commit `c70288a00d40fac5581105d64ea891b1d8ac5f41`, SHA-256 `e3daa14ea8b74344c307a86908c86cbf4d9b44447af367febeb4b581a84ba761`; this branch started at `cbfcc2ebcff9adfcab0f8d3adc1b6dde32005e02`.

## Electrical island graph

```text
fused L,N -- CMC / NTC or bypass -- GBJ2510-F bridge -- 760800301 --
BOOST_SWITCH -- C3D20065D boost diode --> VD_LOCAL -- F2 --> VB_BANK
                                         |                 |           |
                              22 uF + 470 nF       3 x 150 kΩ    4 x 560 uF
                              to HOT0              to HOT0       to HOT0
                              F2 divider +                        F2 divider
                              VSENSE ladder                        to HOT0
                              to HOT0
HOT0 -- 10 mΩ sense shunt -- bridge MINUS
VB_BANK/HOT0 --> future inverter; its local capacitance/disconnect is external.
```

`HOT0` is the common return, not the historical voltage-doubler midpoint or PE. F2 is the source-declared VD–VB positive-rail separator. F2 opening splits VD and VB despite their common return. An inverter input capacitor directly from VB to HOT0 joins VB; if a later connector, contactor, fuse or switch separates it, that capacitor is a third energy island. F2 alone cannot isolate the bank from a downstream inverter short.

Source joins: `pfc_power.ato:70-126`, `pfc_controller.ato:129-168`, `f2_detector.ato:81-130`, `power_entry_integrated_38.ato:60-75` and `ac_input.ato:83-119`, all under `zapote/power-entry/passive-reva/protection/interface-integration-38/elec/src/`.

| Island | Source parts and connection | Candidate C interval | Energy at 390 V, nominal / tolerance-high | Energy at 400 V, nominal / tolerance-high |
| --- | --- | ---: | ---: | ---: |
| VD local | `local_c` TDK `B32776P6226K000`, 22 µF ±10%, 630 V; `hf_c` TDK `B32672P6474K000`, 470 nF ±10%, 630 V; VD–HOT0, diode side of F2 | 20.223–24.717 µF | 1.709 / 1.880 J | 1.798 / 1.977 J |
| VB bank | `bulk1`–`bulk4` Nichicon `LGX2W561MELC50`, 560 µF ±20%, 450 V each; VB–HOT0, bank side of F2 | 1792–2688 µF | 170.352 / 204.422 J | 179.2 / 215.04 J |
| Future inverter input | No selected capacitor, output connector or disconnect in Rev38 | `C_inv` unknown | `0.5 C_inv × 390²` | `0.5 C_inv × 400²` |

The intervals use manufacturers' stated initial capacitance tolerances, not all frequency, temperature, aging or fault effects. Part evidence: [TDK 22 µF](https://product.tdk.com/en/search/capacitor/film/dc-link/info?part_no=B32776P6226K000), [TDK 470 nF](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32672P6474K000), [Nichicon LGX data](https://www.nichicon.co.jp/english/series_items/catalog_pdf/e-lgx.pdf). Rev38 `PFC-POWER.md` uses 400 V for a nominal-energy screen; it does not establish the maximum operating voltage. The bank's 450 V nameplate is a component rating, not an allowed steady voltage or transient. At 450 V the tolerance-high energies would be 2.503 J VD and 272.16 J VB, only a rating-edge screen. The conditional 500 V VD screen in `timing-analysis.md` does not apply to the 450 V VB bank.

## Existing resistor paths, including the easy-to-miss VD paths

| Path | Rev38 source | Nominal resistance to HOT0 | Effect of an open element |
| --- | --- | ---: | --- |
| VD F2 detector divider | `4 × 200 kΩ + 187 kΩ + 200 Ω + 5.62 kΩ` | 992.82 kΩ | Removes this VD path and invalidates its observation. |
| VD PFC VSENSE ladder | `5 × 200 kΩ + 13 kΩ` | 1.013 MΩ | Removes this VD path; controller behavior is fault-dependent. |
| VB F2 detector divider | Same shape as VD detector divider | 992.82 kΩ | Removes this VB path and its observation. |
| VB bank bleeder | Three Yageo `RC2512FR-07150KL` in series | 450 kΩ | Any one open removes the dedicated bank bleed path. |

These are passive resistor connections and can conduct without AUX or firmware. VD has **no dedicated bleeder**, but it does have the two listed ladders. None is yet qualified as a service-discharge path: resistor voltage/power, single-fault coverage, diagnostics, input behavior on rail collapse and installed spacing remain open. Capacitor leakage has no guaranteed minimum and cannot be credited. With F2 open, nominal equivalent resistances are 501.40 kΩ VD and 309.65 kΩ VB. With F2 closed, these independent RC values are not a coupled-network proof.

At constant nominal C/R, an illustrative 400 → 34 V screen is 27.8 s VD and 1710 s (28.5 min) VB with all paths intact. VB detector-only after one bank bleeder opens: 5482 s (91.4 min); bank-bleeder-only after detector opens: 2485 s (41.4 min). Either surviving VD ladder alone takes roughly 55–56 s. Both VD ladders open after F2 opens leaves **no source-declared VD-to-HOT0 resistor**. These times omit tolerances, activation delay, AC recharging, powered or unpowered device currents and inverter capacitance; they are not accepted service times. Reproducible arithmetic and fault examples are in `evidence/discharge_screen.rs`.

## State and fault map

| State | VD | VB / inverter | Evidence needed |
| --- | --- | --- | --- |
| Mains removed, F2 closed | Coupled to bank while F2 conducts. | Candidate resistors can drain the coupled bus. | Prove mains is absent at circuit; bound initial charge and threshold/time. |
| F2 opens charged | Local film caps retain independent energy. | Bank plus attached inverter input retain their energy. | Independent paths and observations; F2 interruption envelope. |
| AUX/HOT logic lost while mains remains | Bridge, inductor and boost diode can passively replenish VD even with gate inhibited; NTC remains an AC path when bypass drops. | Conducting F2 can replenish VB. | Rate any engaged discharge path for continuous energized stress or prove mains isolation. |
| Active contact stuck open, resistor open | Depends on separately intact passive VD paths. | Depends on bank bleeder/divider and inverter topology. | Explicit fault/time disposition, no silent nominal pass. |
| Active contact stuck closed while energized | New resistor could see sustained input/PFC bus. | Same for bank side. | Continuous power, temperature and DC contact/switch ratings. |
| VD=VB with residual charge | Equality proves neither F2 continuity nor low voltage. | Restart can encounter a charged bank and inverter. | Absolute VD and VB measurement plus Rev38 restart policy. |
| Inverter bridge short or input disconnect | F2 may separate VD if it opens, subject to fault behavior. | F2 does not separate VB from an attached short; disconnected local C is a new island. | Inverter current and disconnect contract. |

## Requirement and access decision gates

The legacy split-bus plan `docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md` targets **<34 V in <60 s per ~170 V half-bus**. The older EMI plan `docs/plans/2026-07-15-007-fix-emi-surge-frontend.md` describes 34 V via an IEC 60335 interpretation, but does not establish the exact clause, edition, appliance subpart, accessible-node class or timing for Rev38. Neither plan is adopted as a requirement for this 390 V bus. Select an applicable product/service and restart limit with its authority and test method before sizing U2.

Rev38 has a fused-board AC input terminal, but **no VD/VB output/service connector or test-point geometry** in its joined source. Its divider observations require HOT logic and `F2-DETECTOR.md` leaves their threshold, injection and timing unqualified. Define whether VD/VB can be touched after opening the enclosure, how each is measured against HOT0, instrument insulation/category, and how powered-off verification works. A powered-off comparator output is not a voltage measurement. Freeze the inverter's capacitance and disconnect before closing this map.
