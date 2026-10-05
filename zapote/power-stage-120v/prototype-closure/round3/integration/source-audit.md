# Round 3 source and interface audit

Design scope: a few guarded engineering prototypes, nominal 120/127 V 60 Hz,
15 A RMS input allocation. No assembled hardware has been supplied. This audit
does not qualify a voltage, current, protection time, or powered test.

## Observed in current source

| Source | Observation | Binding design consequence |
| --- | --- | --- |
| `elec/src/power_stage_120v.ato`, supply section | IRM20-15 controller supply and IRM05-15 gate supply both take power downstream of the inlet/filter. The gate supply additionally crosses the TCO loop. | An upstream contactor cannot depend on either supply for its initial pull-in. Keep an independent upstream auxiliary supply. |
| Same source, controller header | J4.1 is **V15_SELV output**; J4.3 is V3V3 input. J4.2/4/15/16 are ELV return. | Do not parallel an auxiliary 15 V supply onto J4.1. An independently powered controller harness must leave J4.1 isolated unless a separate source-mux/removal ECO is implemented. |
| Same source, fault logic | Loss of HOT5 intentionally reports BUS_FAULT while the isolated output side is powered. | Cold precharge and run qualification must be distinct. A blanket fault bypass during precharge is unacceptable; an unavailable downstream channel may delay qualification but must not defeat upstream thermal/current/timeout protection. |
| Same source, voltage sense | Four 470 kΩ resistors and 15.8 kΩ form a nominal 119.98734:1 divider. AMC1311 input-side supply is HOT5 and its reference is the loaded Kelvin return. | J4 bus feedback cannot independently prove discharge after supply loss, and cannot replace a raw bus capture or dedicated clamp controller. |
| Same source and `native-19/frozen/default.net` | J8 is the positive link's bus-side M4 stud (`BUS_P`); J10 is the negative link's bus-side stud (`HV_RET`). J7/J9 are rectifier-side terminals. | A prototype catch branch may connect through a designed short, guarded J8/J10 interface after mechanical and inductance review. Do not connect its return to LEG_RET or a Kelvin sense terminal. Removing bring-up links does not make the rectifier studs safe. |
| `firmware/main/main.c` | `mcpwm_init()` and `safety_monitor_update()` calls remain commented. | No deployed modulator, precharge state machine, or inlet-current behavior is established by this firmware. Models in round2 are diagnostic load laws. |
| `firmware/main/state_handlers.c` | Calls `power_set_level()` and `pwm_disable_all()` through external declarations; the application states request power. | Implement and verify a real power-stage adapter before these calls can carry safety or modulation claims. |
| `firmware/components/hal/esp32/hal_pwm_esp32.c` and `hal_pwm.h` | Existing PWM HAL targets a half bridge. Its two channels are allocated to GATE and FAN, with separate MCPWM groups. | Native19 needs four coordinated bridge signals and a defined phase/dead-time strategy. Merely uncommenting initialization does not create that adapter. |
| `firmware/components/safety/pwm_guard.c` | Runtime checking skips the frequency comparison when the captured frequency is zero; stored frequency/dead-time values are used for a checksum. | Prove live capture validity, stale/missing-edge faults and synchronized output timing. Do not treat a state-variable checksum or absent capture as an observed waveform pass. |
| `firmware/transition_table.yaml` | INIT → IDLE → PAN_DET can progress to PREHEAT without a represented precharge/bypass/energy-ready sequence. | Add a separate energy-supervisor state machine and a positive READY interlock at every power-request entry, including pan detection. Keep application cooking states separate from physical power sequencing. |

## New sensing range finding

The selected [TI AMC1311, Rev C](https://www.ti.com/lit/ds/symlink/amc1311.pdf)
specifies its linear input range as 0–2 V (pp. 6 and 10). With the present divider,
2 V corresponds to approximately **239.975 V** between BUS_P and the Kelvin
reference, before tolerance/error. A 250–280 V bus clamp/OVP decision cannot rely
on that channel retaining linearity. The part's absolute maximum input rating is
not an extended measurement range. This is an independently checked datasheet
and source calculation, not a measured transfer curve.

Use a separately powered, suitably ranged isolated bus channel for the new
supervisor and energy absorber. Preserve native19's existing OVP until an
explicit, tolerance-checked circuit ECO changes it. A failed, saturated, missing,
or implausible measurement must prevent permission; an apparent zero from a
dead channel is not proof that stored energy is gone.

## Lessons applied

The repository's `docs/solutions/best-practices/fault-latch-fan-in-capacity-budget-2026-07-26.md`
records why a spare-looking input may not reach a latch. New fault signals need
explicit pin/net paths through the new supervisor; do not inherit the legacy
board's fault tree or claim an unnamed spare gate. Likewise, unit tests of cooking
states do not prove that real PWM, contactors, or a physical gate-disable path are
integrated.

## Baseline correction

The final round2 cooling STEP input is
`output/temper-prototype-closure/round2/cooling/native19-r4-round2-cold.step`,
SHA-256 `8102ce63dbf9cad08b30b24fafba7527bb6616d36dadd479a71d8b2313fe50cd`.
It contains the final 565-solid cold study. The older STEP identity in round2's
integration record is historical and must not be used to claim new packaging
fit. Round3 integration records this correction without rewriting round2 evidence.
