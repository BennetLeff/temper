# Power-entry interfaces

| Boundary | Nets | Domain | Contract |
|---|---|---|---|
| AC input | `AC_L_RECTIFIED_INPUT`, `AC_N_RECTIFIED_INPUT`, `PE_CHASSIS` | mains/chassis | 120 VAC input, PE through Y1 boundary |
| Auxiliary bias | `AUX_15V_IN`, `AUX_15V_RETURN` | HOT bus-minus referenced | external isolated 15 V source; return is HOT, never SELV |
| Permit/inhibit | `PERMIT_CTRL`, `INHIBIT_CTRL` | HOT control | external bias and sequencing; never direct MCU GPIO |
| Relay control | `RELAY_BYPASS_CTRL` | HOT control | external gate drive / isolation required |
| PFC bus | `PFC_BUS_PLUS_390V`, `PFC_BUS_MINUS` | hazardous HV | single 389.615 V nominal bus; no midpoint |
| Output | `HV_OUT_PLUS`, `HV_OUT_MINUS` | hazardous HV | Phoenix 1714971, 9.52 mm pitch, 32 A / 1000 V class |

The performance target is 1,800 W nominal AC input at 120 VAC, PF 0.99, so real input power is approximately 1,782 W while RMS current remains capped at 15 A. Low-line foldback is an explicit integration item and is not implemented as a qualification claim.
