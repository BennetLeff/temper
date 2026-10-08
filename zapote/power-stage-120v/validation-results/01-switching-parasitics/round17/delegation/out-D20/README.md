# D-20 — controller requirements

**Use the 54 testable requirements in [CONTROLLER-REQUIREMENTS.md](CONTROLLER-REQUIREMENTS.md) for the future four-PWM controller: the D-11 ADC1/OPA2388/over-range decisions are fixed, while controller-inserted dead time, protection latency, harness and remaining qualification values stay explicit owner gates.**

Baseline `b30b3ae35a4bd3ad5c22d8c300c4640986e1232a`, 2026-10-02, OpenAI GPT-6. Document only; no hardware or firmware edits. The source keys in the requirements document apply below. D-17 was not present in this baseline; no fault-latency number is invented. D-21 can implement the error/state contract R26–R28 independently, but R25 does not choose its deployed dead-time value.

## Coverage

Each source finding is mapped below; a mapped open item is not a passed test. Source lines refer to the pinned baseline, not moving branch line numbers.

| Source finding | Requirements / disposition |
|---|---|
| D5:15–16 application has no configured MCPWM | R25,R28,R54 |
| D5:17 unsigned request has no default | R25,R28 |
| D5:18,92 tick truncation and unspecified clock tolerance | R25,R28,R29 |
| D5:19 zero/short init bypasses timing | R25–R28 |
| D5:20 setter-only 500 ns clamp and partial failure | R25–R27 |
| D5:21 cached guard 300–1000 ns is not readback | R28,R29 |
| D5:22 missing production config/Kconfig ownership | R25,R54 |
| D5:23 host 500 ns mock is not production | R28,R54 |
| D5:24 root two-PWM binding | R05–R08,R21 |
| D5:28–34 incompatible edge-block reuse, inversion, ignored init errors | R26–R28 |
| D5:40–47 four direct input paths; cable/skew unknown | R05–R08,R21,R29 |
| D5:51–64 unloaded propagation/mismatch/PWD conditions | R24,R29 |
| D5:66–79 max-not-sum rule; DT output interval not double-subtracted | R24,R29 |
| D5:81–99 hypothetical 500 ns and old 39 kΩ estimates are not gate limits | R24,R25,R29,R54; old resistor choice superseded by DEC:57 |
| D10 J4.1 | R01,R17–R19 |
| D10 J4.2 | R02,R20 |
| D10 J4.3 | R03,R18,R19 |
| D10 J4.4 | R04,R20 |
| D10 J4.5 | R05,R21–R29 |
| D10 J4.6 | R06,R21–R29 |
| D10 J4.7 | R07,R21–R29 |
| D10 J4.8 | R08,R21–R29 |
| D10 J4.9 | R09,R19,R32–R34 |
| D10 J4.10 | R10,R19,R30,R31,R33 |
| D10 J4.11 | R11,R35–R48 |
| D10 J4.12 | R12,R35–R48 |
| D10 J4.13 | R13,R49,R51,R52 |
| D10 J4.14 | R14,R49–R51 |
| D10 J4.15 | R15,R20 |
| D10 J4.16 | R16,R20 |
| D10:64–76 counterparts/interlock auxiliary signals, output collisions, software ledger not harness | R09,R10,R17,R18,R32,R51,R53 |
| D10:80–110 mating, rail ownership, current/inrush/derating | R01,R03,R17,R18 |
| D10:112–120 conditional PWM loading/levels | R05–R08,R19,R29 |
| D10:122–145 PERMIT drive, U13 rather than U9, VOL guarantee gap, open-wire limits | R09,R10,R31,R33,R34 |
| D10:149–160 every unpowered/unplug/reset/default case, HOT5 | R19,R28,R32,R33,R46 |
| D10:164–188 local CT burden/clamps, analog ranges, capture/ADC missing, idle chatter | R13,R14,R49–R52 |
| D10:192–217 no differential receiver / no 280 V accurate reading | R11,R12,R35–R48; range policy resolved by D11/DEC:59 |
| D10:221–243 dead time and protection latency unknown | R24–R29,R33 |
| D10:245–256 four returns and functional-earth/second-bond inventory | R02,R04,R15,R16,R20 |
| D10 ranked finding1 full bridge/enable | R19,R21–R34,R54 |
| D10 ranked finding2 bus reading/range | R35–R48 |
| D10 ranked finding3 protection interface | R09,R10,R19,R30–R34 |
| D10 ranked finding4 CT consumers/loading | R13,R14,R49–R52 |
| D10 ranked finding5 harness/supplies | R01–R04,R15–R20,R53 |
| D10 ranked finding6 stale CT/five returns | R02,R04,R13–R16,R20,R49; source discrepancy register below |
| D11:9–24 purpose, magnitude/timing targets and 240 V endpoint | R35,R36,R41,R45 |
| D11:28–70 receiver, bias, ratios, load, common mode, cable, rail sequence | R11,R12,R19,R37,R38,R46 |
| D11:74–78 ADC range/nonlinearity/conditions/calibration fallback | R39,R40,R45 |
| D11:82–109 conditional leakage/temperature/accuracy budget | R35,R36,R45,R46 |
| D11:113 high over-range is not negative fail-safe; VDD2 loss | R36,R43,R46 |
| D11 rule1 startup/20 ksample/s/staleness | R19,R32,R40,R41,R43 |
| D11 rule2 BUS_FAULT wins | R30 |
| D11 rule3 invalid low/calibration/stale/missing rail | R40,R43,R46 |
| D11 rule4 ≥1210 mV unaveraged latch | R41,R42 |
| D11 rule5 qualified range only, open-wire diagnostic limits | R36,R42,R46 |
| D11 rule6 explicit reset with healthy validated cycles | R44 |
| D11:124 conditional threshold separation | R42,R45; not promoted to guaranteed bus threshold |
| D11:128–147 240/260/280 V consistency, U7 spread, aggregate fault | R36,R47,R48 |
| D11:151–153 owner decisions and physical qualification | R35,R39,R42,R44 accepted by DEC:59; R37,R38,R43,R45,R46 retain physical gates |
| DEC:57 precision 49.9 kΩ, estimated 397–488 ns, 443 ns simulation, S4 open | R24,R25,R29,R54; does not select MCU gap |
| DEC:59 accepted accuracy/timing | R35,R41,R45 |
| DEC:59 ADC1 GPIO2 disconnect/reuse and OPA2388 | R37,R39,R40 |
| DEC:59 ≥1.210 V manual-rearm latch; U7 unchanged | R30,R36,R42,R44,R47,R48 |
| DEC:61 D4 carry-over only after D16 verification | R54 |
| POWER §2, §4 frequency/phase/burst strategy | R22,R23,R35,R41,R52 |
| D17 unavailable at pinned baseline | R33/O11 remains blocked pending result |

## Open items and owners

| ID | Decision / evidence still required | Owner | Requirements |
|---|---|---|---|
| O01 | Receiving connectors, contact/AWG/cable length, numbered continuity and all separate harness branches | Controller hardware + harness owner | R17,R53 |
| O02 | Converter choice, complete 15 V/3.3 V load, inrush and derated thermal budget, fan loads if present | Controller power owner | R01,R03,R18 |
| O03 | Reset/brownout/partial-power/hot-unplug behavior and no enable pulses | Firmware + interlock + bench owners | R19,R28,R32 |
| O04 | Return allocation, allowable voltage offsets and all PE/USB/instrument bonds | System grounding owner | R20 |
| O05 | Four PWM GPIO/operator/timer allocation and leg phase relationship | Controller hardware + firmware owners | R21 |
| O06 | Allowed frequency/duty/phase range, capacitive-phase inhibit, burst sequencing and sensor-validity policy | Control + power-stage owners | R22,R23,R52 |
| O07 | Explicit controller gap/minimum, rounding/tolerance and update policy consistent with DT hardware | Power-stage timing + firmware owners | R25–R28 |
| O08 | Measured four-output timing at inputs, driver outputs and gates over conditions; fitted R9/R17 verification | D16 + D8/bench owners | R24,R29,R54 |
| O09 | BUS_FAULT low-level guarantee at actual load and PERMIT gate-high/dynamic drive | Interlock + controller hardware owners | R31,R34 |
| O10 | Selected BUS_FAULT input and watchdog/reset/SENSOR_LIVE/HOT5-valid architecture and restart behavior | Interlock + firmware owners | R10,R32,R53 |
| O11 | D17 result and complete fault/lost-supply-to-gate-off latency maximum with measurement conditions | Protection/bench owner | R33 |
| O12 | Exact reference-divider order codes, receiver/layout/harness capacitance, environment, ADC/settling/leakage and wiring-fault qualification | Controller analog + bench owners | R37,R38,R45,R46 |
| O13 | Proposed 150 µs stale, 100 mV invalid, 1100 mV re-arm values and validated-line-cycle criterion; fault-service scheduling | Firmware + controller analog owners | R43,R44 |
| O14 | CT ADC/capture allocation, input/acquisition load, attenuation, transient range and phase/filter calibration | Controller analog + firmware owners | R50–R52 |

D-11's three owner choices in DEC:59 are already settled and are not re-opened. Its detailed physical/service targets remain qualification items where the decision did not fix them. R25 is deliberately unresolved: the 49.9 kΩ board decision alone cannot prove a particular firmware delay is appropriate.

## Source discrepancies and stop-rule disposition

- POWER:79 still says the CT secondary reaches J4.13/14; POWER:88–93 and D10:164–170 explicitly document the corrected native-17 topology. D10 ranked finding6 already records this stale documentation. The requirement references D10's checked native/frozen endpoint sets, not an invented design correction.
- Delegation ground facts and D5's historical table retain 39 kΩ/348 ns. DEC:57 explicitly supersedes the resistor choice for native-18, subject to D16 verification; the new range is an estimate, not a datasheet guaranteed interval.
- D10's request for a 280 V linear-range remedy and D11's old “owner decisions remaining” paragraph are superseded by DEC:59 and the D11 owner decision to keep the shared divider. No divider or U7 change is authorized.
- The brief calls PERMIT an “output”; relative to the complete control/interlock assembly it is an output, but J4.9 is a power-board input driven by interlock J2.6. D10 is explicit. R09/R32 prohibit converting this shorthand into a competing MCU driver.
- U13 VOL and PERMIT VOH remain unclosed guarantees, not proven contradictions with a part's specified limits. They are retained as blockers O09 rather than silently choosing a new level, pullup or circuit.

No new unresolved board/frozen-netlist/datasheet contradiction was found during this document consolidation. The already identified discrepancies above have an explicit source supersession or remain open. If D16, D17 or subsequent hardware contradicts these checked facts, stop the affected design/release and return it to the owner; do not reconcile by editing hardware under D20.

## Verification

Read D5/D10/D11 and the recorded decisions against every requirement and coverage row. Checked that R01–R54 are unique/contiguous, all have source and verification fields, all 16 pins and O01–O14 are covered, and every cited source file exists at the pinned revision. No arithmetic model or firmware was changed; all numerical values are traced to committed reports or their cited primary datasheets. No Rust/native/firmware build is relevant to this document-only change.

Repository gates: import boundary check — 5 kept, 0 broken; `scripts/regen_derived.py --check` — all derived artifacts consistent. Read-only regeneration check respects the document-only scope. Main-context review checked completeness, source supersessions and unsafe default assumptions; no independent reviewer or physical qualification is claimed.
