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

The common harness now executes `ERC.PFC.INTERFACE_PINS` against the compiled
source, in addition to source/native graph equality. Consistently relabeling
the HOT return as control ground or restoring a split-bus output label fails
this independent contract. `pfc_interfaces.rs` owns these checks.

The bus voltage above is a nominal setpoint, not a worst-case rating envelope.
The common run separately requires bus-envelope, isolated-bias,
external-supervisor and input-foldback findings. They remain INDETERMINATE
until the corresponding models or producers exist. The static inhibit circuit
does not establish startup, bias-loss or shutdown timing.

The legacy full-cooker `AuxSupply` and discharge arrangement in
`elec/src/modules.ato` still assume a split bus. They are not wired into this
standalone unit and are not accepted PFC consumers. The next auxiliary-power
unit must select its input architecture, budget every output load, and keep
HOT bias and control-side supply returns distinct.
