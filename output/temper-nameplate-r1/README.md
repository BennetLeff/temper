# temper-nameplate-r1: is the inlet or the tank current temper's power limit?

2026-10-15. All numbers come from `nameplate.py` → `nameplate.json`, which
reruns byte-identically in about 20 s. Everything is an **estimate made before
any measurement**. The script re-uses the power-stage session's own tank model
(task 05 round 6: FHA calibrated to ngspice, round-4 pan classes, round-5
coupling factors). It imports that model read-only from `worktrees/ps-integrate`
at commit b7ff4a857, and records the sha256 of every file it imports.

## Answer

**Tank current limits temper's power, not the nameplate.**

- **At every tank ceiling the board can release today, the nameplate changes
  nothing.** At 18 A (the still-air release request until candidate 39), 21 A
  (still-air C40 after c39, and about the 45 A peak trip) and 22 A (the
  firmware limit), almost every pan hits the tank ceiling first.
  - The pooled pan power is identical for every nameplate option:
    650 / 856 / 931 W at 120 V.
  - That is **0.42 / 0.56 / 0.61×** the Control Freak's estimated pan power
    (1800 W × η_CF 0.85).
- **The nameplate matters only once the ceiling reaches 24–28 A,** which is
  the enclosure-airflow route.

**Pooled pan power at 120 V** (five measured-anchor classes, 220 mm, blower
full). Each cell gives pan power, its ratio to the Control Freak, and the
fraction of pans limited by inlet current rather than tank current.

| Option | 18 A | 21 A | 22 A | 24 A | 28 A |
|---|---|---|---|---|---|
| 12 A, estimated | 650 W, 0.42×, 0.00 | 856 W, 0.56×, 0.17 | 931 W, 0.61×, 0.34 | 1009 W, 0.66×, 0.65 | 1012 W, 0.66×, 0.96 |
| **13.5 A, estimated (today)** | 650 W, 0.42×, 0.00 | 856 W, 0.56×, 0.03 | 931 W, 0.61×, 0.11 | 1091 W, 0.71×, 0.40 | 1148 W, 0.75×, 0.86 |
| 13.5 A, measured (AMC1301) | 650 W, 0.42×, 0.00 | 856 W, 0.56×, 0.01 | 931 W, 0.61×, 0.04 | 1091 W, 0.71×, 0.25 | 1231 W, 0.80×, 0.78 |
| 15 A, estimated | 650 W, 0.42×, 0.00 | 856 W, 0.56×, 0.00 | 931 W, 0.61×, 0.02 | 1091 W, 0.71×, 0.18 | 1283 W, 0.84×, 0.72 |
| **15 A, measured** | 650 W, 0.42×, 0.00 | 856 W, 0.56×, 0.00 | 931 W, 0.61×, 0.00 | 1091 W, 0.71×, 0.08 | **1371 W, 0.90×**, 0.59 |

**At 108 V:** with a 28 A ceiling, pooled pan power is 1033 W today and
1239 W with a 15 A measured nameplate (0.68× → 0.81×). At 18–22 A the options
are again identical.

**Per pan class** (`limit_map_120V_220mm_blower_full`):
- At 21 A, every class is ≥ 87 % tank-limited.
- Even at 28 A with a 15 A measured nameplate, clad multiply (64 %) and
  enamelled steel (55 %) are still mostly tank-limited.
- The small or offset pan is tank- or floor-limited at every ceiling.

## Boil and heat-up

All at 120 V, 220 mm, blower full.

**2 L boil.** The heat loss is backed out of the Control Freak's 10:55 run
(yt:BcSqJ7sZiAQ 04:40), so these times are very sensitive to that run's
unknown conditions. Use the pan-power ratios above for decisions. Times are
given as η_CF 0.80 / 0.85 / 0.90.

| Pan (220 mm) | Today, 21 A | Today, 28 A | 15 A measured, 28 A |
|---|---|---|---|
| 18/10 with magnetic base | 23:03 / 27:53 / 35:18 | 14:49 / 16:41 / 19:05 | 11:35 / 12:42 / 14:02 |
| Clad multiply | 29:29 / 37:54 / 53:01 | 15:16 / 17:15 / 19:50 | 13:11 / 14:38 / 16:27 |
| Cast iron | 17:55 / 20:43 / 24:32 | 14:28 / 16:15 / 18:31 | 11:17 / 12:20 / 13:36 |

The Control Freak's measured time is 10:55.

**Empty pan from 25 to 200 °C.** The Control Freak figures are modelled at
η 0.85.

| Pan | Today, 21 A | 15 A measured, 28 A | Control Freak |
|---|---|---|---|
| Clad | 2:13 | 1:13 | 0:58 |
| Cast iron | 3:59 | 2:38 | 2:22 |
| Thin stainless (carbon-steel-like) | 2:05 | 1:09 | 1:00 |

## What the model assumes

- **The round-6 per-pan frequency rule** (lowest legal frequency, closed
  loop). The firmware implements it.
  - `firmware/components/power/tank_freq.c` approaches from f_max 60 kHz down
    to max(35 kHz, 1.05·f_res), with a phase check.
  - `n21_binding.c` wires it in: `.freq = tank_freq_default()`, plus
    `tank_freq_reset` / obs in the step.

  This was corrected on 2026-10-15 after the power-stage review. The earlier
  "single commissioned frequency" caveat was stale.
- **Bay temperature.** The 21 A column is the still-air ceiling at a 55 °C
  bay. At the 61 °C worst bay, the power-stage session's rough I²
  interpolation of the s41 C40 rows puts it near 19 A, between the 18 A and
  21 A columns. They will compute it properly after candidate 39 merges.
  Firmware `tank_limit_a` is still 22 A (`input_limits.c:13`). It will be set
  to the release ceiling and recorded as a release constant.
- **Model cross-check (power-stage review).** At 22 A, 120 V, 220 mm this
  study gives 931 W pooled. The round-6 ngspice grid gives a 904 W mean
  (15 deterministic cases, 13 tank-limited). The 3 % gap is consistent with
  Monte Carlo draws against grid corners.
- **η_min 0.93,** the firmware's conservative inverter efficiency. With a
  measured input current, the real efficiency would add a little.
- **Pan classes and coupling are ASSUMED,** from published anchors, not
  measured.
- **The thermal pan mapping is an inference** (`PAN_THERMAL`).
- **The boil loss is backed out of one video test.**

## Update 2026-10-15: release ceiling set at 18 A (power-stage DECISIONS 55)

- **Board of record:** s42 (candidate 39, c8665ceb0).
- **Still-air release ceiling:** 18.0 A tank RMS. The gated ceiling is
  20.0 A at a 55 °C bay and 18.3 A at 61 °C, rated on the worst bay. The
  limits are the 68 Ω 2512 turn-on resistors' derating, the laminate block
  and C40.
- **Firmware:** the default goes 22 → 18 A (TANK_CEILING_DEFAULT_A).
- **Today's product is therefore the 18 A column:** about 650 W pooled at
  120 V, 0.42× the Control Freak. Board-face airflow is the only route above
  that (`output/temper-airflow-r1`).
- **Possible controller option:** a bay-air sensor could allow 20 A when the
  bay reads ≤ 55 °C.
