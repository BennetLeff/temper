# Startup, bootstrap, and fault timing review

| Item | Schematic treatment | Evidence state |
|---|---|---|
| Cold start | IRM-10-15 is connected directly across AC_L/AC_N, before the boost stage; the active bridge does not need a 390 V bus to wake up. | Topology shown; IRM input tolerance, inrush, and control-rail cold-start waveform are open. |
| Driver supply | UCC21530BQDWKRQ1 VDDA/VDDB are each fed by an explicit ES1J + 220 nF ceramic + 1000 uF/25 V electrolytic bootstrap network. VCCI and VCCI2 use AUX_15V. | TI p.7 gives 8.9 V max turn-on, 8.4 V max turn-off and 9.2 V recommended minimum. The screen compares both the 8-V hard threshold and 9.2-V design floor against IRM-10-15's ±2.5% output tolerance and 200 mVpp ripple: 14.525 V minimum rail minus a conservative 1.1 V diode drop = 13.425 V source. Neither is a hardware qualification. |
| Half-cycle hold-up | Each high-side domain is referenced to HS_L/HS_N and is expected to hold for roughly one 50/60 Hz half-cycle (8–10 ms). | The Rust charge screen (`calc/bootstrap_corner.json`) uses 1000 uF nominal / 800 uF after ±20%, 4.1775 mA hold current (2.5 mA driver allowance + 1.5 mA 10 kohm pull-down + 0.25 mA leakage allowance), and 8.33 ms. The periodic charge/hold solution gives 13.010 V at the end of hold, 5.010 V above the 8-V threshold and 3.810 V above the 9.2-V design floor. This is a conditional charge screen; high-state supply current, ESR/DC-bias derating, diode Vf and recharge waveform remain open. |
| Dead time | UCC21530 DT has a 10 kohm resistor and 1 nF capacitor to HOT_GND. | TI's 10 ns/kohm relation gives a nominal 100 ns setting. Shoot-through and propagation skew remain unqualified. |
| Recharge/startup | Each bootstrap diode is fed through a 47 ohm axial resistor (`RH05047R0FE02`), with pulse capability still unverified. | Rust screen uses the source voltage, diode drop, resistor and load in a periodic exponential model rather than a constant-current recharge shortcut. It predicts 4.66 mA recharge current at the start of the recharge interval and 13.053 V after recharge under the stated assumptions. Startup sensitivity uses the maximum 1200 uF and 14.875 V source: 0.316 A initial current and 0.133 J stored energy per leg. No recharge-time or pulse-survival guarantee is claimed; the exact resistor pulse curve, capacitor ESR/voltage derating and IRM transient response remain required evidence. |
| Gate default | Q1–Q4 each have 10 kohm source-referenced pull-downs; driver EN has 10 kohm pull-up and 100 kohm pull-down. | Fail-off intent is represented; detection latency and failed-short behavior remain unqualified. |
| Healthy switch fault | External CMD_A/CMD_B and EN can be removed, but no current sensor is included in this bridge section. | Gate shutdown is not credited as interruption of a device that has failed short. |
| Surge/fault | Passive GBJ path is retained; the post-boost F2 is outside this unit. | No surge clamp, F2 let-through, MOSFET short-circuit withstand, or PCB spacing claim follows from this schematic. |

The next quantitative experiment must be authored in Rust and use an
independent charge/energy oracle. It should sweep AUX_15V tolerance, diode
forward drop, bootstrap capacitance, UCC21530 quiescent/leakage current, MOSFET
gate charge, 50/60 Hz period, minimum recharge pulse, and UVLO. A passing
schematic/ERC run is not a substitute for that evidence.

## 2026-09-19 startup-supply selection (appended, supersedes the 1000 uF + 47 ohm positions)

Selected: R_boot 220 ohm ERJ-P08J221V (1206 anti-surge) + C_bulk 100 uF/25 V
EEU-FC1E101 per leg; `src/main.ato`, footprints, BOM, native schematic, and
ERC re-run accordingly. Full record: `STARTUP-SELECTION.md`; load inventory:
`LOAD-INVENTORY.md`; model: `calc/startup_model.rs` + `calc/outputs/`
(closure PASS 0.038 mV; ngspice Parts A/B agree to ≤ 11 µV). Headline
numbers: cold-start peak 146 mA total (4.6× under the 0.67 A nominal rating,
5.3× under hiccup-min); worst hold-end 11.18 V at 50 Hz (1.98 V over the
9.2 V floor), 10.72 V under assumed line asymmetry (1.52 V); charge to
9.2 V in ≤ 38 ms at min source. The rows above remain as the prior screen;
the 1000 uF + 47 ohm values did not earn their place and are replaced.
Open: bench checks B-1…B-8 in STARTUP-SELECTION.md §6 (incl. IR11688S/BSP300
current capture, resistor pulse life, ES1J Vf retain, sag/dropout behavior).
No protection, endurance, or hardware-verified claim follows.
