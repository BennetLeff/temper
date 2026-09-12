# Power-entry interfaces

These are exact native/source22 net names. References apply to this unit only.

| Connector | Pins / nets | Contract |
|---|---|---|
| U42 mains, Phoenix 1714984 | 1 `AC_L_RECTIFIED_INPUT`; 2 `AC_N_RECTIFIED_INPUT`; 3 `PE_CHASSIS` | 120 VAC; PE is capacitively coupled to HOT bus-minus through Y1, with no DC bond |
| U43 auxiliary bias | 1 `AUX_15V_IN`; 2 `PFC_BUS_MINUS` | External isolated regulated 15 V; return is HOT |
| U44 relay control | 1 `RELAY_BYPASS_CTRL`; 2 `PFC_BUS_MINUS` | External isolated controller sequences precharge and bypass |
| U45 permit | 1 `HOT_PERMIT_EXTERNAL`; 2 `PFC_BUS_MINUS` | HOT logic; default-off inhibit circuit; never direct MCU GPIO |
| U52 output, Phoenix 1714971 | 1 `PFC_BUS_PLUS_390V`; 2 `PFC_BUS_MINUS` | Single 389.615 V nominal bus, no midpoint |

The 1,800 W nominal AC-input target is bounded by the 15 A RMS input limit.
At 120 V and PF 0.99 this is 1,782 W real input; output power is lower because
of losses. Low-line RMS foldback is required external integration work.
