# Option P (PERMIT-gated heartbeat) against option S (TPS3808 delay), OPEN-ITEMS B13 H2

Analysis lane, 2026-10-16. Read-only on `worktrees/ps-integrate/zapote/power-stage-120v` (HEAD e1ddf70c6); board of
record s48 (`2b46d90e`, netlist `native-21/frozen/default.net`). Nothing in the repo was edited, built or committed.

Class tags: **G** datasheet limit, **C** computed from G, **S** project SPICE, **E** estimate (bench must confirm).

Re-run (all `python3 -I`, read-only on the repo, PS_ROOT is an optional first argument):

```
python3 -I netq.py <PS>/native-21/frozen/default.net J4 U46 R135 permit hsb_good ...   # netlist trace (results/trace.txt)
python3 -I pump_p_spice.py   # ngspice, committed c24 design-J deck driven as P drives it -> results/pump_p_spice.json (~80 s, 8 procs)
python3 -I fmea_p.py         # FMEA delta on the committed c24 P2H rows, levels, timing -> results/fmea_p.{json,md}
python3 -I layout_p.py       # s48 all-copper export + spine lock: where things are, the re-net, clearances -> results/layout_p.json
```

## Recommendation: adopt P, with R135 at 100 k and the C39 start order in firmware. Do not build S.

The decisive evidence:

1. **The same guaranteed field coverage as S, proved far more often.** On the committed c24/fmea-s47 chain rows, both
   reach **36.9 %** (13.8 % as built). S proves U40 stuck-high / Y–VCC once per mains power-on. P proves it on every
   idle control tick and before every start. With S, a fault that arises while the hob stays plugged in stays dormant
   until the next mains interruption. With P it lasts at most one cooking session. P also catches R_bleed open when the
   hold-node leakage is typical (41.5 %, E).
2. **P costs nothing; S fails the owner's cost rule.**
   - P: $0, 0 BOM lines, 0 placements, 0 vias. R135 moves from the 10 k line to the existing 100 k line.
   - S: +$0.47, +2 lines, +3 placements. On the card S is "costlier with no performance gain", so it would need a cost
     override like stages 45, 47 and 48. P is cost-neutral and better.
3. **No protection is lost, and none is shared.**
   - The DIS truth table is unchanged: NAND(PERMIT, bias_ok ∧ PERMIT) = NOT(PERMIT ∧ bias_ok).
   - PERMIT gains a second, independent stop path through the heartbeat, **≤ 90.3 µs (122.9 µs with one pump cap
     shorted)** behind the direct ns path (S).
   - No single fault defeats both U22/U23 inputs that did not already do so.
4. **The race goes away by construction, not by a timer.** RUN_EN is low through every reset (4.7 k pull-down, preset
   low), so BIAS_GOOD is low at every boot, cold or warm. This holds whatever the PS2/PS3 order and through dropouts.
5. **The layout change sits outside the spine.** R135.1 is **1.3 mm** from the PERMIT leg-B branch. The change is one
   1.43 mm F.Cu stub, with nothing touched in the locked region (§4).

The price of P:
- A **mandatory firmware change** (§5), which must land before or with the GPIO35 routing. As written, check 2 would
  refuse every start: fail-safe, but the hob would not work.
- TP19 shows bias health only while PERMIT is high. The heartbeat is still visible at idle on hb_rx.
- B8 and COMMISSIONING H2 must hold PERMIT high.

## 1. Circuit trace (netlist; MPNs from `resolved-components.json`)

The `libsource part` fields in `default.net` are stale atopile type names. They show U46 as LVC1G00, R135 as 100 Ω and
R146 as 100 k. `resolved-components.json` and `default.csv` give the true parts: SN74LVC1G132, 10 k and 220 k. All MPNs
here come from those two files. Full dump: `results/trace.txt`.

**PERMIT** (controller U37 SN74LVC1G08 = interlock latch Q AND RUN_EN, controller R103 10 k pull-down):
- J4.9 → net `permit` {J4.9, R6.1, R14.1; TP17 at (33.15, 113.27)}.
- R6 100 Ω → `leg_a-permit_gate` {R7 100 k to selv_gnd, U22.1}.
- R14 100 Ω → `leg_b-permit_gate` {R15 100 k, U23.1}.
- U22/U23 SN74LVC1G00: Y = NAND(permit_gate, bias_good) → `leg_x-driver_dis` {U1.5 / U2.5 (2EDR8259X DIS), R73/R76
  10 k pull-up to v3v3}. DIS high means disabled.

PERMIT has no other consumer on s48, and no isolator: the 2EDR8259X DIS is on its SELV input side.

**Heartbeat:**
1. LS good node `monitor_ls-good` = {U29 LM2901B open-collector outputs (pins 1, 2, 13, 14), R91 10 k to ls_v5, D18.1
   (HS-A veto from U43.6 `mon_good_ha`), D20.3 (HS-B veto from U44.6 `mon_good_hb`), U45.1}.
2. U45 SN74LVC1G132 RC oscillator (R131 4.99 k, C162 330 pF; 0.42–2.09 µs) → `hb_tx`.
3. U32 CA-IS3720HW, pin 4 → pin 13 → `hb_rx` (SELV, VCC2 = v3v3) → **U46.2 (B)**.
4. **U46.1 (A) = `hsb_good` ← R135 10 k ← v3v3.**
5. U46.4 `hb_bufo` → R132 220 Ω → C164 1 nF → C165 1 nF → `hb_x` → D19 BAT54S (shunt to selv_gnd, series) →
   `hb_hold` {C166 1 nF, R133 49.9 k, U40.2}.
6. U40 SN74LVC1G17 → `bias_good` {U22.2, U23.2, R146} → R146 220 k → `bias_good_j4` → J4.1. TP19 sits on bias_good.

**BIAS_GOOD feeds U22.2, U23.2 and R146 only.** No other protection uses it or the heartbeat.

Decisions read:
- D52: the vote moved to the LS domain, R135 became U46's pull-up, and the B8 EOL veto test is a condition.
- D59: the monitor FMEA basis.
- D67: H2 is the R146 220 k read-back. 220 k was chosen so that a J4.1–J4.9 short holds PERMIT_GATE at 0.68 V.
- fmea-s47 §4 H2: 13.8 % / 36.9 %.
- c24 `m1_pump_spice` design J.

## 2. Behaviour under P

**Protection.** DIS_x = NAND(P_x, B), where B = bias_ok ∧ P(U46.A). Both are the one `permit` net, so DIS =
NOT(PERMIT ∧ bias_ok), which is identical to today. The heartbeat gives PERMIT a second stop path that does not share
U22/U23's A input:
- **PERMIT low → hold below U40 VT−min ≤ 90.26 µs (122.87 µs with one pump cap shorted)** (S).
- P always stops into the "U46.Y static high" state, which is the committed worst corner. 96 corners per case.

**Start latency** (`pump_p_spice.py`: committed deck, BAT54 model, G17 thresholds and corner set; pump at rest with
U46.Y high, as P leaves it; PERMIT phase swept):

| Step | Value | Class |
|---|---|---|
| PERMIT ↑ → hold ≥ VT+max | 1.95–11.76 µs (6.57 µs with one cap shorted) | S |
| R135 100 k × ~15 pF on U46.A to VT+max | ≤ 1.8 µs | E |
| U46 / U40 / U22 propagation | ns | G |
| Drivers enabled after PERMIT | ≤ 13.6 µs + the 2EDR8259X DIS-to-output delay (unpublished, controller C39) | C |
| GPIO35 ≥ VIH after PERMIT (J4.1 RC τ 177–198 µs, rise 444–514 µs) | ≤ 0.53 ms | C |
| GPIO35 ≤ VIL after PERMIT ↓ | ≤ 0.36 ms | C |
| Restart after any PERMIT low | ≤ 11.13 µs | S |
| A PERMIT low < 30 µs | BIAS_GOOD does not drop (DIS still follows PERMIT directly) | S |
| End-of-run margin | 0.148 V (0.245 V with a cap shorted), the committed J value | S |

There is no cumulative ramp over repeated starts.

**Firmware start sequence.** Checked against `state_handlers.c` and `n21_binding.c`:
- Check 2 is taken at PAN_DET entry, before PERMIT. Under P it would refuse every start.
- Check 3 runs from PAN_DET entry. The binding raises RUN_EN only after pre-arm (line_ready / report, at least one line
  half-cycle), so under P check 3 would latch `BIAS_GOOD_LOST` at 20 ms.
- **Both must be keyed to PERMIT (§5).**

**Pan detection** needs the drivers. PAN_DET runs `power_set_level(5)`, so the bridge runs and PERMIT stays high for the
whole detection. The legacy ping (`power_service_pan_pulse`) is disabled in this build, and low-temperature burst is
excluded from this release. PERMIT does toggle whenever fullbridge `run` changes (request 0, conductance 0) and at every
`pwm_disable_all()`. Under P each re-raise is a fresh start. Any future ping design must pulse the PWM with PERMIT held
high, not pulse PERMIT.

**Found: the binding raises RUN_EN with the PWM running. Controller DECISIONS C39 requires the opposite** ("raise RUN_EN
only with the PWM idle (RUN_EN rising re-arms the detector)").
- `sample()` pre-arm makes the pads live while the gate is off. `fullbridge_apply()` → `set_request(run)` raises the
  gate later.
- The MCU pads drive J4.5–8 directly; there is no hardware PWM gate on the controller.
- Under P the drivers enable 2–14 µs after PERMIT. At 35–60 kHz that is up to a whole half period (8.3–14.3 µs) after
  the CM flip-flops arm. The first leg-A turn-off can then sample CT_ZC with no tank current, which risks a nuisance
  CAP_FAULT.
- The P sequence in §5 removes this by construction. It is a C39 compliance item whatever is chosen.

**U46 levels (SCES546E 5.5, −40..125 °C, interpolated to VCC 3.135 / 3.465 V; PERMIT from U37, ≤ 37.5 Ω (C), into
~0.4 mA of pull-downs):**

| R135 | U46.A high / VT+max | U46.A low / VT−min | U37 Hi-Z (PERMIT on 8.33 k) + hsb_good at v3v3 → PERMIT | Verdict |
|---|---|---|---|---|
| 10 k | 3.01 / 1.95 V (+1.06) | 0.11 / 0.89 V (+0.78) | **1.58 V** (> VIL 0.8 V of U22/U23) | not chosen |
| **100 k** | 2.92 / 1.95 V (+0.97) | 0.20 / 0.89 V (+0.69) | **0.27 V** | **chosen** |

Notes on the levels:
- II is ±1 µA (G). The added load on PERMIT is one CMOS input behind 100 k, so there is no fan-out or threshold issue.
- The input is Schmitt, so a slow edge is fine.
- With U37 driving, the ripple injected into PERMIT by a pin 1–2 short is ≤ 1.3 mV (C).
- 100 k is the existing 0603WAF1003T5E line (R7, R15, R136…; 8 refs), with the same footprint. The 10 k line keeps
  9 refs.

**Hold-up and repeated starts.** The HOT side is untouched: U45 and U32 run on, and the monitors and their supplies
never see PERMIT. While PERMIT is low the SELV pump idles with U46.Y static high. There is no DC path (C164 and C165
block it), and the pump's AC draw stops at idle (a few mA, E).

## 3. FMEA delta (`fmea_p.py`, c24 P2H rows unchanged, chain 13.0 FIT·rails)

| Field DC of the BIAS_GOOD chain | base | k_u 0 | k_u 1 | k_o 0.5 | passives ×5 |
|---|---:|---:|---:|---:|---:|
| s48 as built (boot race lost, c49) | 13.8 | 0.0 | 17.2 | 7.8 | 9.1 |
| S (boot POST, TPS3808 delay) | 36.9 | 58.8 | 31.6 | 20.7 | 24.2 |
| **P, guaranteed** | **36.9** | 58.8 | 31.6 | 20.7 | 24.2 |
| P, typical hold-node leakage (E) | 41.5 | 58.8 | 37.3 | 23.3 | 39.4 |

How each row group fares:
- **U40 stuck high / Y–VCC (3.0 of 13.0).** Covered by both S and P. The proof-test interval differs, as described in
  the recommendation.
- **R_bleed open (0.6).** Only P can see it: after PERMIT falls, the hold keeps its charge. The 2 ms idle check catches
  it while the leakage is below ~0.7 µA (E). G17 II ±5 µA and BAT54 IR are not guaranteed that low, so it counts as 0
  on the G basis.
- **HS link, diode and LDO-OV rows (8.6).** Dormant in all three variants. They are B8 EOL only.

**New rows for P** (c24 component basis):

| Fault | Effect under P | Class |
|---|---|---|
| R135 open | U46.A floats. Low: no start. High: the idle check fires. Oscillating: nuisance | announced |
| R135 short | The basis has no short mode. A PCB bridge removes only the second-fault protection | — |
| U46 pins 1–2 (A–hb_rx) | The wave follows hb_rx regardless of PERMIT, and the idle check fires | announced; P-only detection, benign today and under S |
| U46 pins 2–3, 4–5, stuck, open | The wave stops | announced, as today |
| PERMIT stuck high: U37 | DIS is still gated by bias_ok, as today | already caught by PERMIT_RB checks |
| PERMIT stuck high: a power-board short to v3v3 | Same gating | **new detection**: BIAS_GOOD high with RUN_EN low |
| PERMIT stuck low, J4.9 open, R14 open | Drivers off, "NO POWER BIAS" | announced. The message is ambiguous; PERMIT_RB high with BIAS_GOOD low narrows it |

**`hsb_good` trace shorts.** This is the existing 81.5 mm trace. P leaves it unchanged, and S uses it too. Neighbours
closer than 0.5 mm, from `layout_p.json`:

| Neighbour | Gap | Effect under P |
|---|---|---|
| v3v3 (C168.1; In1 plane) | 0.2 mm | today's behaviour; the idle check fires |
| line_zc_raw via | 0.275 mm | A toggles at 60 Hz while PERMIT is low; the idle check fires |
| selv_gnd (via; In2 plane) | 0.286 / 0.2 mm | no start |
| U40.1 (NC) | 0.3 mm | harmless |
| hb_rx | 0.35 mm | the idle check fires |
| permit via | 0.475 mm | R135 is bypassed; benign alone |
| **hb_hold (C166.1)** | **0.425 mm** | see below |

The hb_hold short is a shared residual:
- As built and under S it is a hard mask: the hold sits at 2.6–2.9 V, above VT−max, so BIAS_GOOD follows the pull-up.
  Under S, RESET pulls it low only during the delay, so the POST passes and the mask follows.
- Under P with 100 k the hold sits at 1.04–1.32 V, inside U40's VT− band (0.95–1.44 V). It is no longer a hard mask,
  but it is not guaranteed either (E).
- It is a PCB fault outside 19.11.2's component modes. B8 screens it at EOL in every variant.

**Common cause.** U22/U23 input A is PERMIT; input B is bias_ok ∧ PERMIT. A PERMIT fault defeats A, as today, and B
keeps bias_ok. A bias-chain fault defeats B and leaves A, and under P it is detected at the next idle. The 'dis' rows
(U22/U23 Y stuck low) are the same in every variant. **No new single point, dormant or announced, on the c24 basis.**

**One new double-fault path, and the reason for 100 k:** U37 Hi-Z (announced) plus a v3v3-level source on hsb_good.
With 10 k this puts PERMIT at 1.58 V, inside U22/U23's undefined band; with 100 k it puts it at 0.27 V.

**J4.1–J4.9 harness short** (adjacent pins, 3 mm pitch). It masks the read-back in every variant, because J4.1
follows PERMIT. D67's no-latch result still holds under P: 0.68 V is below VT−min 0.84 V, so BIAS_GOOD cannot hold
PERMIT up. P alone can detect the short (optional check (d) in §5).

**TP19 at idle.** TP19 is low whenever PERMIT is low. Bias health at idle is visible only as the hb_rx square wave at
U46.2 / U32.13, which has no pad. B8 and COMMISSIONING H2 must drive J4.9 high with the PWM idle.

**Mains dropouts.**
- P: every boot sample is valid, because PERMIT is low through any reset. The reset-reason carve-out in check 1 can go.
- S: the 1.2–4.8 s delay restarts on any v3v3 dip below 2.79 V, including dips that do not reset the ESP32 (2.44 V
  brown-out). In mid-cook that drops BIAS_GOOD and latches `BIAS_GOOD_LOST`, unless the controller's RAIL_OK window
  trips first (not checked, E).

## 4. Physical feasibility on s48 (`layout_p.py`, all-copper `2b46d90e`, lock baseline `596ba3bf`)

**Where things are:**
- **U46** is at (94.5, 132.0), **inside** the spine region [30, 130]–[110, 180]. U46.1 is 19.1 mm from the nearest PERMIT
  copper (F.Cu (77.8, 124.2)–(79.4, 122.6)). A re-net at U46 would need a new permit branch inside the spine, and so a
  lock reissue.
- **R135** is at (31.7, 108.3), **outside** the region. R135.1 (32.525, 108.3) is **1.3 mm** from the PERMIT leg-B F.Cu
  branch (x = 33.95, y 70.2–110.0). TP17 (permit) is at (33.15, 113.27).

**The change (R135 repurposed as the series resistor; U46.1 and all hsb_good copper unchanged):**
- **Netlist:** R135 pin 1 moves from `v3v3` to `permit`. R135 goes from 10 k to **100 k** (R100k0603,
  0603WAF1003T5E). Pin 2 stays on `hsb_good`.
- **Source:** in `f6_bias.ato` Heartbeat, add `signal permit`, `rgate = new R100k0603`, `rgate.value = 100kohm`, and
  `rgate.p1 ~ permit`. In `power_stage_120v.ato`, add `hb.permit ~ PERMIT`.
  - **Keep the net name `HSB_GOOD`.** Renaming it would change hsb_good track keys inside the spine region.
  - Update the Heartbeat docstring and comments, and the ledger U46 function text (it still says "gated by HS-B's
    ISO7710F verdict").
- **Copper:**
  - Delete the F.Cu v3v3 stub R135.1 → (32.5, 109.675).
  - **Keep that via.** C168.1's stub and a B.Cu v3v3 run land on it.
  - Add a 0.25 mm F.Cu `permit` track from R135.1 to (33.95, 108.3), 1.425 mm long, T-joined to the leg-B branch.
    Split that segment if the router needs a vertex there; it lies outside the region.
- **Clearances:**
  - Stub to other copper: ≥ 0.95 mm (the kept via). R135.1 pad, now on permit, to that via: 0.60 mm. Rule: 0.2 mm.
  - No F.Cu zone lies within 0.2 mm.
  - No via is added or removed, and nothing changes layer, so return paths are unaffected.
- **Spine lock:** every changed primitive is at y ≤ 109.7, outside the region. The permit, v3v3 and hsb_good tracks that
  cross the region are byte-unchanged, and U46's pads keep their nets. **Expect PASS with no reissue.** Run
  `spine_lock.py`, `track_geometry.py` (the T adds a junction), return_path, bypass, the ledger and the scorecard. The
  card should read parts $, lines, placements and vias unchanged.

## 5. Firmware delta for P (not made; inert until `CTRL_GPIO_BIAS_GOOD_RB` exists)

The checks:

| Check | Today | Under P |
|---|---|---|
| 1 | Low at the power-on boot sample; warm resets exempt | **Low whenever PERMIT_RB has been low ≥ T_IDLE = 2 ms** (5.6× the 0.36 ms worst fall). Every control tick, every state, INIT included. 3-sample debounce. Fail → latched `FAULT_BIAS_GOOD_STUCK` (the renamed `_POST`), cleared by power cycle. The reset-reason logic and the boot-sample race go. |
| 2 | High at PAN_DET entry, before PERMIT | **High at T_START = 2 ms after RUN_EN is raised with the pads forced low** (3.8× the 0.53 ms worst rise). Else RUN_EN goes low, "NO POWER BIAS", back to IDLE (`EVENT_BIAS_GOOD_LOW_AT_START`, not a fault). Only then are the pads released (the C39 order). Applies on every gate rise. |
| 3 | Unchanged semantics | Low for ≥ 20 ms → `FAULT_BIAS_GOOD_LOST`. Qualified by "PERMIT_RB high and ≥ T_START since its rise", not by state. Run reset at each rise. |

Optional checks, P only:
- **(d)** GPIO35 high 50–406 µs after RUN_EN rises means the read-back is bypassed (J4.1–J4.9 short). A healthy board
  cannot reach VIH before 444 µs.
- **(e)** A high at about 0.5 ms after a commanded PERMIT fall means slow hold decay (R_bleed open). This is a warning
  only (E).

Also take c49's (c): timestamp with `esp_rtc_get_time_us()`.

**Codegen and test impact:**
- `config.yaml` → `gen_config.py` → `config.h`: add `BIAS_GOOD_PERMIT_RISE_MS` and `BIAS_GOOD_PERMIT_FALL_MS`.
- `transition_table.yaml`: `EVENT_BIAS_GOOD_STUCK` from every state, replacing the INIT-only POST row. Regenerate
  `transition_table.h`, `fault_list_generated.h`, `test_transition_table_generated.c`, `test_fault_list_generated.c`,
  `tools/transition_model.py` / `state_machine_reachability_report.json` and `test_transition_model_checks.py`.
- `platform_logic.{c,h}`: replace `platform_bias_post_ok` with an idle-step function and key the start and run checks to
  the PERMIT edge. `test_platform_logic.c` (58 refs) is rewritten.
- `platform_esp32.c` and `state_handlers.c`: check 2 leaves PAN_DET entry; check 3 is gated by PERMIT.
- `n21_binding.c` start sequence: RUN_EN first with the pads low, T_START, check, then the pads. Plus
  `test_n21_binding.c`.
- `state_machine_stubs.c`, `test_state_machine.c` (56 refs), `test_sil_fault_injection.c`, the three
  `trace_fault_bias_good_lost*.csv` traces and the manifest (plus a POST-fail trace), and `test_mutation_sweep.py`.
- Docs: firmware/README.md, COMMISSIONING.md H2, FAULT-INTERFACE.md, BRINGUP-PROBES.md TP19, and the D67 "not done"
  wording.

The controller needs nothing beyond what S also needs: GPIO35 and the J13 merge.

## 6. What stays for the bench

1. Scope J4.9, `hsb_good` (R135.2), hb_hold (C166), BIAS_GOOD (TP19), one DIS and GPIO35 across 20 starts at 25 °C and
   hot:
   - PERMIT ↑ → DIS ↓ ≤ 13.6 µs plus the DIS-to-output delay (measure it; it is C39's open item);
   - GPIO35 ↑ ≤ 0.53 ms;
   - PERMIT ↓ → TP19 ↓ ≤ 90 µs;
   - GPIO35 ↓ ≤ 0.36 ms.
2. Hold-node decay with R133 lifted, at 25 / 70 °C: this settles whether check (e) and the R_bleed-open E coverage are
   real.
3. The C39 items under the new order: CT_ZC rest state with no tank current, and the first truncated pulse after pad
   release.
4. B8 and the H2 COMMISSIONING steps with J4.9 driven high (PWM idle), and checks 1–3 on mains, including dropouts of
   20 ms, 100 ms, 500 ms and 2 s. The c49 sequencing measurement is no longer a coverage decider under P; record it for
   information only.

## Files

- `netq.py`: netlist query.
- `pump_p_spice.py`: SPICE run.
- `fmea_p.py`: FMEA delta, levels and timing.
- `layout_p.py`: layout feasibility.
- `results/`: `trace.txt`, `pump_p_spice.json`, `fmea_p.{json,md}`, `layout_p.json`.
