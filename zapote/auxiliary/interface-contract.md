# Auxiliary interface contract — draft U1

Source snapshot: `06d9070c3`. This contract records questions the producer and consumers must answer; it does not select a circuit.

| Port | Producer obligation | Consumer/failure obligation |
| --- | --- | --- |
| Rev38 raw auxiliary input | Available at the chosen point of the fused AC path before PFC RUN is requested; branch protection and installed wiring reviewed. | Source loss, brownout and hiccup must leave restart disarmed. |
| `AUX_PROTECTED` referenced to `HOT0` | Bound low/high/ripple/overshoot and startup current under all accepted mains/load cases. | Rev38 supervisors, fast-dip/OV detector and gate-disable behavior must be checked against that bound, including HOT logic5 absent. |
| `HOT_LOGIC5` referenced to `HOT0` | Supply HOT receiver and fault detectors through cold start and declared stop path. | Its absence must not let the driver enable through a floating control. |
| SELV `+15V` and `+3V3` referenced to SELV `GND` | State insulation barrier, source/return, startup and load envelope. | Interlock and MCU outputs must default to inhibit until their rail and sense validity are established. |
| Inverter `+15V_LS` referenced to `HV_RETURN` | Provide a separately reviewed isolated gate rail or prove a compliant shared source. | Gate-drive unit requires its stated J2 boundary; bootstrap startup remains physically unqualified. |

The authoritative Rev38 restart implementation remains in the PFC unit. This auxiliary unit supplies fault and rail-health conditions and must not independently issue a new ARM/PERMIT event. A final U1 contract needs exact voltage/current/time bounds and a chosen one-versus-two-unit architecture.
