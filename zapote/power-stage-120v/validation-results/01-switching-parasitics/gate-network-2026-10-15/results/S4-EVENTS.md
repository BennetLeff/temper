# When S4 happens (task 4): operating events that hard-commutate a body diode

Sources: worktree `ps-integrate` (branch codex/power-stage-integration). FW = `worktrees/ps-integrate/firmware`,
PS = `zapote/power-stage-120v`. Quotes were read on 2026-10-15; line numbers are in that checkout.

## Status of the firmware
- The native-21 control is C, host-tested, never compiled for the ESP32 or run on hardware:
  FW/components/power/Kconfig:7-8 ("Off by default: the source has not yet been compiled against ESP-IDF or run on
  hardware"); FW/components/power/COMMISSIONING.md:5 ("Neither board has been built or powered yet").
- The main checkout's `firmware/` is the older IGBT-era code; it has no native-21 power component.

## Steady state: firmware keeps the tank inductive (by design)
- Frequency loop FW/components/power/include/tank_freq.h:18-20, 33-37: approach from 60 kHz downwards; step down
  only while lag >= 45 deg AND f >= max(35 kHz, 1.05 f_res). Loop update once per closed half line cycle (8.33 ms);
  step down 250 Hz/half, step up 1 kHz.
- Hard backstop: phase latch at 5 deg lag (FW/components/power/n21_signal.c:77-80, "negative = current leads"),
  checked each 625 us acquisition sample, only when RMS >= 2 A (FW/components/power/n21_binding.c:20-22, 265-274).
  The latch only sets state; the gates come off at the next 10 ms control tick (FW/main/main.c:66,
  CONTROL_LOOP_PERIOD_MS 10; power_service.c:40-43). Worst-case response ~10.6 ms = ~370 periods at 35 kHz.
- Frequency clamps 35-60 kHz in two places (fullbridge_adapter.c:6, tank_freq.c:37; PS DECISIONS.md:576-578).
- No hardware phase / capacitive-mode detector. Hardware trips only on over-current (CT 64.6-76.1 A, shunt
  66.4-118.7 A, chain <= ~1.2 us; PS FAULT-INTERFACE.md, DECISIONS.md:568-571).
- Records: "Hard turn-on occurs only when ZVS is lost, so S4 bounds an operating region, not nominal operation"
  (PS validation-results/01-switching-parasitics/round17/d2/README.md:59-60); "the controller stays on the inductive
  side of resonance" (PS DECISIONS.md:68).

## Events, per the records

| event | S4-type (diode conducting at the incoming turn-on)? | edges per event | protection |
|---|---|---|---|
| first edge after idle / power-up | no: this is S5 (0 A, no diode conduction) | 1 per burst/start | F6 bias |
| downward frequency sweep at start | not by design (45 deg + 1.05 f_res test before every step) | 0 if sensing is right | loop test per 8.33 ms, 5 deg latch |
| non-magnetic / aluminium pan | **yes**: resonates at 33-41 kHz; "At 35 kHz the floor probe shows it capacitive at the crest edge, i.e. hard switching" (PS DECISIONS.md:94 area; PS validation-results/05-resonant-tank-envelope/round4-assumed-basis/README.md:118-119). Pan rejection required but not implemented (legacy pan_detect unwired; OPEN-ITEMS S13) | every edge of both legs until the latch: up to ~10.6 ms x 2 edges/period/leg = ~740 per leg at 35 kHz | 5 deg latch only (software) |
| pan lift / removal, boil-over | records treat pan lift as inductive (higher L, Q), i.e. over-current not capacitive; DECISIONS.md:90 names these transients as the reason control-only S4 avoidance is not trusted | not quantified | loop, latch, OCP |
| restart within ~250 ms of a stop | possible: the PWM climbs back to f_max at 1 kHz per tick, so a restart can begin at the previous pan's lower frequency (n21_binding.c:371-379) | until the loop / latch acts | as above; no check below 2 A RMS in the first ~3.4 ms |
| line zero crossing (bus ~0) | no wrong-sign edges >= 20 % of crest in the tank model (05-resonant-tank-envelope README:73); below that low-current edges lose ZVS with the right sign (S3-type, not S4) | - | - |
| OCP / fault shutdown, normal stop | no: all four gates off, current freewheels through the diodes back to the bus, no incoming turn-on | 0 | - |
| low-power burst | burst disabled in this firmware (tank_freq.h:62-65; n21_binding.c:494); phase shift rejected because "the lagging leg hard-switches, which is the S4 failure mode" (DECISIONS.md:80-83) | - | - |
| CT_ZC miscalibration (delay, polarity) | yes, if the lag reading is offset the loop can sit capacitive with the latch blind (COMMISSIONING.md:151, H4) | continuous until found | bench calibration item |

No record gives a measured or assumed S4 event rate (per session, per second or per line cycle).

## Answer
S4 is not a steady-state operating point: the firmware is designed to prevent it. It is a **fault / transient case
that arrives in bursts**: once the tank goes capacitive (non-magnetic pan at the 35 kHz floor, a fast restart, a
sensing error, a load transient), every edge of both legs is an S4 edge until the software latch removes the gates,
which takes up to ~10 ms, i.e. several hundred consecutive hard commutations per leg per episode, with no hardware
backstop other than over-current. Infineon's 70 V/ns / 1,300 A/us diode-commutation limits are ruggedness limits
(per edge, not per hour), so the rating must hold on every S4 edge that can occur: S4 stays a **design case for the
rating**. The frequency matters for the bench plan, not for the pass rule: the D-8 double pulse must reproduce S4 at
280 V, leg A, 150 C (the worst model corner), and a repeated-pulse test (hundreds of consecutive S4 edges, as in an
episode) is the right qualification for a rating that is only 'fault-rare'. A hardware capacitive-mode detector
(CT_ZC vs switch-node edge in logic, us response) would cut an episode from ~740 to a few edges per leg; it is a
controller-session item and is not assumed here.
