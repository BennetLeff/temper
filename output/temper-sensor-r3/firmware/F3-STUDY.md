# F3 — cold-soak guard evaluation, 2026-10-16

Base: `ebf8a777b50ecb81040fc0c56fa8bde706720638`. The commands below use the existing C heatsink driver, Pt100 converter and cold-soak check, with the original physical trajectories and noise seeds. Hazard counts use the 277 peak-rule runs and the original 2399 s check time. No EXPECTED_INDEP_NOMINAL value is changed.

The comparison keeps the original partitions fixed. After implementation, the 126 slow-heatsink trajectories move into the zero-latch gate: 954 gated and 78 report-only trajectories per rail variant. The original gated population is 276 physical trajectories × 3 corners = 828 per rail variant (not 828 × 3). The report-only population is 204 per variant: 126 slow-heatsink, 36 frozen-pot, 36 large-water-pot and 6 cold-room trajectories.

## Candidate comparison

Every candidate has 0/828 gated false-latch trajectories in each rail variant. In the table, `F/M` means rail fallback / measured. Coverage columns are nominal temperature-independent leaks, out of 277, at ambients 5, 15, 25, 30, 35, 40 °C. All families and both hazardous corners are included in the retained study output.

| Candidate | Report-only latches F/M (of 204 each) | Slow sink F/M (of 126) | Frozen F/M (of 36) | Cold room F/M (of 6) | Coverage F | Coverage M |
|---|---|---|---|---|---|---|
| baseline | 23/24 | 0/1 | 22/22 | 1/1 | 180 / 212 / 212 / 212 / 212 / 212 | 212 / 212 / 212 / 248 / 248 / 248 |
| off_2tau_7200 | 23/24 | 0/1 | 22/22 | 1/1 | 72 / 72 / 36 / 36 / 36 / 36 | 72 / 72 / 36 / 36 / 36 / 36 |
| off_4tau_14400 | 0/0 | 0/0 | 0/0 | 0/0 | 72 / 72 / 36 / 36 / 36 / 36 | 72 / 72 / 36 / 36 / 36 / 36 |
| flat_tau3600 | 22/22 | 0/0 | 22/22 | 0/0 | 72 / 72 / 212 / 212 / 212 / 212 | 72 / 72 / 212 / 248 / 248 / 248 |
| rate_002 | 23/23 | 0/0 | 22/22 | 1/1 | 180 / 212 / 212 / 212 / 212 / 212 | 212 / 212 / 212 / 248 / 248 / 248 |
| pt_floor_4 | 4/5 | 0/1 | 4/4 | 0/0 | 72 / 72 / 36 / 68 / 104 / 104 | 72 / 72 / 36 / 104 / 140 / 140 |
| threshold_tau3600 | 19/20 | 0/0 | 18/20 | 1/0 | 180 / 180 / 212 / 212 / 212 / 212 | 180 / 212 / 212 / 212 / 212 / 212 |
| pt_floor_6 | 0/0 | 0/0 | 0/0 | 0/0 | 72 / 72 / 36 / 68 / 68 / 104 | 72 / 72 / 36 / 104 / 104 / 140 |

Definitions:

- `off_2tau_7200` / `off_4tau_14400`: require coil-off time ≥ 2 / 4 × a hypothetical 3600 s slowest heatsink time constant. Coverage at 2399 s becomes the converter window alone. The four-hour zeroes on the original report-only set are horizon effects: the cold-room and frozen-pot trajectories end before four hours. The 24-hour continuation latches both at 14400 s in both rail variants.
- `flat_tau3600`: reduce the 15-minute total heatsink range to 0.437823499 K = 1.541494083 × (exp(900/3600) − 1), preserving the old single-exponential residual allowance. It rejects some steady noisy references and loses low-ambient coverage.
- `rate_002`: retain all original limits and additionally require ≤ 0.02 K/min absolute drift between the midranges of the oldest and most recent completed minute buckets. At the default window those buckets are 840 s apart; the allowed change is 0.28 K. The incomplete current bucket remains covered by the original 1 K range test.
- `pt_floor_4` / `pt_floor_6`: skip if the current Pt100 reading or its window minimum is below 4 / 6 °C. The miss-corner frozen pot reads about 5.2 °C, so 4 °C is insufficient; 6 °C also suppresses real leaks.
- `threshold_tau3600`: add 1.979317582 K to both thresholds, the difference between 3600 s and 1800 s heatsink residual bounds for the existing 1 K range. This is an evaluated alternative only; production thresholds stay 19.4 / 16.9 K.

## Every baseline false-latch trajectory

Values below are at the **first** latching evaluation, not the maximum over the trajectory. `gap` is the diagnostic window minimum(heatsink) − maximum(Pt100); `now gap` is the simultaneous reading difference. The retained CSV also includes each trajectory’s maximum-gap latching evaluation. Times are seconds from power-up/end-of-cook; frozen pots hold the model glass at 2 °C after placement. The single warm-restart row has τ_h = 3600 s, τ_g = 408 s and a 18000 s horizon. Frozen trajectories end 10800 s after placement; the cold-room trajectory has a 10800 s horizon.

| Rail | Kind | Ambient °C | Corner | Placement s / τ_g s | Check s | Pt100 °C | Heatsink °C | Window gap K | Now gap K |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| measured | warm_restart | 5.0 | false | 408.0 | 10870 | 4.291079 | 21.287645 | 16.950741 | 16.996566 |
| fallback | frozen_plateau | 5.0 | false | 1800.0 | 3010 | 1.333868 | 21.165527 | 19.422012 | 19.831659 |
| measured | frozen_plateau | 5.0 | false | 1800.0 | 3010 | 1.333868 | 18.715836 | 16.947359 | 17.381967 |
| fallback | frozen_plateau | 5.0 | false | 3600.0 | 4810 | 1.300278 | 21.068516 | 19.457563 | 19.768237 |
| measured | frozen_plateau | 5.0 | false | 3600.0 | 4810 | 1.300278 | 18.608868 | 16.986551 | 17.308589 |
| fallback | frozen_plateau | 15.0 | false | 1800.0 | 3130 | 1.300278 | 27.468525 | 25.741327 | 26.168247 |
| measured | frozen_plateau | 15.0 | false | 1800.0 | 3130 | 1.300278 | 25.547138 | 23.804480 | 24.246860 |
| fallback | frozen_plateau | 15.0 | false | 3600.0 | 4930 | 1.266689 | 27.458973 | 25.761063 | 26.192284 |
| measured | frozen_plateau | 15.0 | false | 3600.0 | 4930 | 1.266689 | 25.536934 | 23.825579 | 24.270245 |
| fallback | frozen_plateau | 25.0 | false | 1800.0 | 3190 | 1.300278 | 34.682693 | 33.135174 | 33.382415 |
| measured | frozen_plateau | 25.0 | false | 1800.0 | 3190 | 1.300278 | 33.186165 | 31.634815 | 31.885887 |
| fallback | frozen_plateau | 25.0 | nominal | 1800.0 | 3190 | 1.972138 | 24.988388 | 22.706879 | 23.016250 |
| measured | frozen_plateau | 25.0 | nominal | 1800.0 | 3190 | 1.972138 | 24.988388 | 22.706879 | 23.016250 |
| fallback | frozen_plateau | 25.0 | false | 3600.0 | 4990 | 1.300278 | 34.689945 | 33.107887 | 33.389667 |
| measured | frozen_plateau | 25.0 | false | 3600.0 | 4990 | 1.300278 | 33.193764 | 31.606209 | 31.893485 |
| fallback | frozen_plateau | 25.0 | nominal | 3600.0 | 4990 | 1.938542 | 24.989273 | 22.690788 | 23.050731 |
| measured | frozen_plateau | 25.0 | nominal | 3600.0 | 4990 | 1.938542 | 24.989273 | 22.690788 | 23.050731 |
| fallback | frozen_plateau | 30.0 | false | 1800.0 | 3190 | 1.300278 | 38.810326 | 37.215126 | 37.510047 |
| measured | frozen_plateau | 30.0 | false | 1800.0 | 3190 | 1.300278 | 37.502335 | 35.902096 | 36.202056 |
| fallback | frozen_plateau | 30.0 | nominal | 1800.0 | 3190 | 1.972138 | 29.944658 | 27.693186 | 27.972520 |
| measured | frozen_plateau | 30.0 | nominal | 1800.0 | 3190 | 1.972138 | 29.944658 | 27.693186 | 27.972520 |
| fallback | frozen_plateau | 30.0 | false | 3600.0 | 4990 | 1.300278 | 38.773827 | 37.148460 | 37.473548 |
| measured | frozen_plateau | 30.0 | false | 3600.0 | 4990 | 1.300278 | 37.464390 | 35.834091 | 36.164111 |
| fallback | frozen_plateau | 30.0 | nominal | 3600.0 | 4990 | 1.938542 | 30.010256 | 27.696939 | 28.071714 |
| measured | frozen_plateau | 30.0 | nominal | 3600.0 | 4990 | 1.938542 | 30.010256 | 27.696939 | 28.071714 |
| fallback | frozen_plateau | 35.0 | false | 1800.0 | 3190 | 1.300278 | 43.023232 | 41.456070 | 41.722953 |
| measured | frozen_plateau | 35.0 | false | 1800.0 | 3190 | 1.300278 | 41.874714 | 40.305416 | 40.574436 |
| fallback | frozen_plateau | 35.0 | nominal | 1800.0 | 3250 | 1.904946 | 35.022675 | 32.814663 | 33.117729 |
| measured | frozen_plateau | 35.0 | nominal | 1800.0 | 3250 | 1.904946 | 35.022675 | 32.814663 | 33.117729 |
| fallback | frozen_plateau | 35.0 | miss | 1800.0 | 3250 | 5.198924 | 25.544281 | 19.961115 | 20.345357 |
| measured | frozen_plateau | 35.0 | miss | 1800.0 | 3250 | 5.198924 | 27.964066 | 22.403585 | 22.765142 |
| fallback | frozen_plateau | 35.0 | false | 3600.0 | 5050 | 1.266689 | 43.103447 | 41.539707 | 41.836758 |
| measured | frozen_plateau | 35.0 | false | 3600.0 | 5050 | 1.266689 | 41.957550 | 40.388493 | 40.690861 |
| fallback | frozen_plateau | 35.0 | nominal | 3600.0 | 5050 | 1.938542 | 35.032440 | 32.838009 | 33.093898 |
| measured | frozen_plateau | 35.0 | nominal | 3600.0 | 5050 | 1.938542 | 35.032440 | 32.838009 | 33.093898 |
| fallback | frozen_plateau | 35.0 | miss | 3600.0 | 5050 | 5.165296 | 25.403574 | 20.012560 | 20.238278 |
| measured | frozen_plateau | 35.0 | miss | 3600.0 | 5050 | 5.165296 | 27.834583 | 22.450867 | 22.669288 |
| fallback | frozen_plateau | 40.0 | nominal | 1800.0 | 3250 | 1.938542 | 39.994865 | 37.807247 | 38.056324 |
| measured | frozen_plateau | 40.0 | nominal | 1800.0 | 3250 | 1.938542 | 39.994865 | 37.807247 | 38.056324 |
| fallback | frozen_plateau | 40.0 | miss | 1800.0 | 3250 | 5.131668 | 31.719070 | 26.272112 | 26.587403 |
| measured | frozen_plateau | 40.0 | miss | 1800.0 | 3250 | 5.131668 | 33.695015 | 28.257071 | 28.563347 |
| fallback | frozen_plateau | 40.0 | nominal | 3600.0 | 5050 | 1.972138 | 39.995594 | 37.814774 | 38.023456 |
| measured | frozen_plateau | 40.0 | nominal | 3600.0 | 5050 | 1.972138 | 39.995594 | 37.814774 | 38.023456 |
| fallback | frozen_plateau | 40.0 | miss | 3600.0 | 5050 | 5.198924 | 31.701599 | 26.295538 | 26.502676 |
| measured | frozen_plateau | 40.0 | miss | 3600.0 | 5050 | 5.198924 | 33.678619 | 28.279070 | 28.479696 |
| fallback | ambient | -5.0 | false | — | 1800 | -5.712666 | 16.125275 | 21.482021 | 21.837941 |
| measured | ambient | -5.0 | false | — | 1800 | -5.712666 | 13.108613 | 18.422585 | 18.821279 |

## Decision and limits

Select the rate guard: it reduces measured-rail report-only false-latch trajectories from 24 to 23 while fallback remains 23, and loses no previously caught per-leak hazard cells over both rail variants, both hazardous corners, six ambients and all six leak families. The frozen-pot and −5 °C cases remain deliberately reported: no evaluated guard removes all of them while retaining the required coverage.

The guard is an additional reason to skip, not proof that the unit is safe. Preserved coverage refers to the recorded steady cold-start grid; a leaking unit whose heatsink is still drifting can have detection deferred, because a skip permits heating as before. This study does not claim preserved detection time on every drifting leaking trajectory. It cannot distinguish a truly steady frozen pot from a leak. The thresholds, original flatness tests, soak timer, NVS credit and latch-clear rule stay unchanged.

Bench dependencies: neither the credible upper τ_h nor the 1 K heatsink-to-ambient standby offset is measured. The study assumes single-exponential tails, the existing sensor/component corners, 3 mV ADC noise and the existing Pt100 noise/self-heating. For a noise-free 3600 s exponential, 0.28 K over 840 s corresponds to a 1.065440 K residual, below the existing 1.541494 K allowance; midrange noise and sensor nonlinearity prevent treating that calculation as a hardware guarantee. The 0.02 K/min limit is validated on those modeled histories; it is not a measured hardware guarantee. Measure post-cook/transport cooling, idle offsets and actual minute-scale noise before qualifying the bound. The frozen-food plateau and below-rated room remain open limitations.

## Evidence commands and quoted output

The retained `cold_soak_guards.py` is the reproducible study. Run from this directory with `python3 cold_soak_guards.py --out /absolute/scratch/directory`. It builds temporary C libraries from the pinned pre-F3 check and emits `benign.csv`, `coverage.csv`, `false-latches.csv` and the following quoted summary. The CSV includes every ambient/rail/family/corner coverage cell and both the first and maximum-gap latching evaluations. The 24-hour continuation is printed as `EXTENDED` rows.

```text
BENIGN baseline rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN baseline rail_fallback reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE baseline rail_fallback nominal independent [180, 212, 212, 212, 212, 212] / 277
COVERAGE baseline rail_fallback nominal 0.01 [180, 180, 180, 180, 212, 212] / 277
COVERAGE baseline rail_fallback nominal 0.02 [144, 144, 180, 180, 180, 180] / 277
COVERAGE baseline rail_fallback nominal 0.05 [72, 72, 108, 108, 108, 108] / 277
COVERAGE baseline rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 36] / 277
COVERAGE baseline rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE baseline rail_fallback miss independent [72, 36, 108, 144, 144, 144] / 277
COVERAGE baseline rail_fallback miss 0.01 [36, 36, 108, 108, 108, 144] / 277
COVERAGE baseline rail_fallback miss 0.02 [0, 0, 72, 108, 108, 108] / 277
COVERAGE baseline rail_fallback miss 0.05 [0, 0, 0, 36, 36, 36] / 277
COVERAGE baseline rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE baseline rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN baseline rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN baseline rail_measured reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (1, 54)}
COVERAGE baseline rail_measured nominal independent [212, 212, 212, 248, 248, 248] / 277
COVERAGE baseline rail_measured nominal 0.01 [180, 180, 212, 212, 212, 212] / 277
COVERAGE baseline rail_measured nominal 0.02 [144, 180, 180, 180, 212, 212] / 277
COVERAGE baseline rail_measured nominal 0.05 [72, 108, 108, 108, 144, 144] / 277
COVERAGE baseline rail_measured nominal 0.1 [0, 0, 0, 0, 36, 36] / 277
COVERAGE baseline rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE baseline rail_measured miss independent [72, 36, 144, 144, 180, 180] / 277
COVERAGE baseline rail_measured miss 0.01 [36, 36, 108, 144, 144, 144] / 277
COVERAGE baseline rail_measured miss 0.02 [0, 0, 108, 108, 144, 144] / 277
COVERAGE baseline rail_measured miss 0.05 [0, 0, 36, 36, 72, 72] / 277
COVERAGE baseline rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE baseline rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN off_2tau_7200 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN off_2tau_7200 rail_fallback reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE off_2tau_7200 rail_fallback nominal independent [72, 72, 36, 36, 36, 36] / 277
COVERAGE off_2tau_7200 rail_fallback nominal 0.01 [36, 36, 36, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback nominal 0.02 [36, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback nominal 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback miss independent [72, 36, 36, 36, 36, 36] / 277
COVERAGE off_2tau_7200 rail_fallback miss 0.01 [36, 36, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback miss 0.02 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback miss 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN off_2tau_7200 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN off_2tau_7200 rail_measured reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (1, 54)}
COVERAGE off_2tau_7200 rail_measured nominal independent [72, 72, 36, 36, 36, 36] / 277
COVERAGE off_2tau_7200 rail_measured nominal 0.01 [36, 36, 36, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured nominal 0.02 [36, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured nominal 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured nominal 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured miss independent [72, 36, 36, 36, 36, 36] / 277
COVERAGE off_2tau_7200 rail_measured miss 0.01 [36, 36, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured miss 0.02 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured miss 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_2tau_7200 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN off_4tau_14400 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN off_4tau_14400 rail_fallback reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (0, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE off_4tau_14400 rail_fallback nominal independent [72, 72, 36, 36, 36, 36] / 277
COVERAGE off_4tau_14400 rail_fallback nominal 0.01 [36, 36, 36, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback nominal 0.02 [36, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback nominal 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback miss independent [72, 36, 36, 36, 36, 36] / 277
COVERAGE off_4tau_14400 rail_fallback miss 0.01 [36, 36, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback miss 0.02 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback miss 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN off_4tau_14400 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN off_4tau_14400 rail_measured reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (0, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE off_4tau_14400 rail_measured nominal independent [72, 72, 36, 36, 36, 36] / 277
COVERAGE off_4tau_14400 rail_measured nominal 0.01 [36, 36, 36, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured nominal 0.02 [36, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured nominal 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured nominal 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured miss independent [72, 36, 36, 36, 36, 36] / 277
COVERAGE off_4tau_14400 rail_measured miss 0.01 [36, 36, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured miss 0.02 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured miss 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE off_4tau_14400 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN flat_tau3600 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN flat_tau3600 rail_fallback reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE flat_tau3600 rail_fallback nominal independent [72, 72, 212, 212, 212, 212] / 277
COVERAGE flat_tau3600 rail_fallback nominal 0.01 [36, 36, 180, 180, 212, 212] / 277
COVERAGE flat_tau3600 rail_fallback nominal 0.02 [36, 0, 180, 180, 180, 180] / 277
COVERAGE flat_tau3600 rail_fallback nominal 0.05 [0, 0, 108, 108, 108, 108] / 277
COVERAGE flat_tau3600 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 36] / 277
COVERAGE flat_tau3600 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE flat_tau3600 rail_fallback miss independent [72, 36, 36, 36, 144, 144] / 277
COVERAGE flat_tau3600 rail_fallback miss 0.01 [36, 36, 0, 0, 108, 144] / 277
COVERAGE flat_tau3600 rail_fallback miss 0.02 [0, 0, 0, 0, 108, 108] / 277
COVERAGE flat_tau3600 rail_fallback miss 0.05 [0, 0, 0, 0, 36, 36] / 277
COVERAGE flat_tau3600 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE flat_tau3600 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN flat_tau3600 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN flat_tau3600 rail_measured reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE flat_tau3600 rail_measured nominal independent [72, 72, 212, 248, 248, 248] / 277
COVERAGE flat_tau3600 rail_measured nominal 0.01 [36, 36, 212, 212, 212, 212] / 277
COVERAGE flat_tau3600 rail_measured nominal 0.02 [36, 0, 180, 180, 212, 212] / 277
COVERAGE flat_tau3600 rail_measured nominal 0.05 [0, 0, 108, 108, 144, 144] / 277
COVERAGE flat_tau3600 rail_measured nominal 0.1 [0, 0, 0, 0, 36, 36] / 277
COVERAGE flat_tau3600 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE flat_tau3600 rail_measured miss independent [72, 36, 36, 36, 180, 180] / 277
COVERAGE flat_tau3600 rail_measured miss 0.01 [36, 36, 0, 0, 144, 144] / 277
COVERAGE flat_tau3600 rail_measured miss 0.02 [0, 0, 0, 0, 144, 144] / 277
COVERAGE flat_tau3600 rail_measured miss 0.05 [0, 0, 0, 0, 72, 72] / 277
COVERAGE flat_tau3600 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE flat_tau3600 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN rate_002 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN rate_002 rail_fallback reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE rate_002 rail_fallback nominal independent [180, 212, 212, 212, 212, 212] / 277
COVERAGE rate_002 rail_fallback nominal 0.01 [180, 180, 180, 180, 212, 212] / 277
COVERAGE rate_002 rail_fallback nominal 0.02 [144, 144, 180, 180, 180, 180] / 277
COVERAGE rate_002 rail_fallback nominal 0.05 [72, 72, 108, 108, 108, 108] / 277
COVERAGE rate_002 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 36] / 277
COVERAGE rate_002 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE rate_002 rail_fallback miss independent [72, 36, 108, 144, 144, 144] / 277
COVERAGE rate_002 rail_fallback miss 0.01 [36, 36, 108, 108, 108, 144] / 277
COVERAGE rate_002 rail_fallback miss 0.02 [0, 0, 72, 108, 108, 108] / 277
COVERAGE rate_002 rail_fallback miss 0.05 [0, 0, 0, 36, 36, 36] / 277
COVERAGE rate_002 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE rate_002 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN rate_002 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN rate_002 rail_measured reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (22, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE rate_002 rail_measured nominal independent [212, 212, 212, 248, 248, 248] / 277
COVERAGE rate_002 rail_measured nominal 0.01 [180, 180, 212, 212, 212, 212] / 277
COVERAGE rate_002 rail_measured nominal 0.02 [144, 180, 180, 180, 212, 212] / 277
COVERAGE rate_002 rail_measured nominal 0.05 [72, 108, 108, 108, 144, 144] / 277
COVERAGE rate_002 rail_measured nominal 0.1 [0, 0, 0, 0, 36, 36] / 277
COVERAGE rate_002 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE rate_002 rail_measured miss independent [72, 36, 144, 144, 180, 180] / 277
COVERAGE rate_002 rail_measured miss 0.01 [36, 36, 108, 144, 144, 144] / 277
COVERAGE rate_002 rail_measured miss 0.02 [0, 0, 108, 108, 144, 144] / 277
COVERAGE rate_002 rail_measured miss 0.05 [0, 0, 36, 36, 72, 72] / 277
COVERAGE rate_002 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE rate_002 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN pt_floor_4 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN pt_floor_4 rail_fallback reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (4, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE pt_floor_4 rail_fallback nominal independent [72, 72, 36, 68, 104, 104] / 277
COVERAGE pt_floor_4 rail_fallback nominal 0.01 [36, 36, 36, 36, 68, 104] / 277
COVERAGE pt_floor_4 rail_fallback nominal 0.02 [36, 0, 36, 36, 72, 72] / 277
COVERAGE pt_floor_4 rail_fallback nominal 0.05 [0, 0, 0, 36, 36, 72] / 277
COVERAGE pt_floor_4 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 36] / 277
COVERAGE pt_floor_4 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_4 rail_fallback miss independent [72, 36, 36, 36, 36, 36] / 277
COVERAGE pt_floor_4 rail_fallback miss 0.01 [36, 36, 0, 0, 0, 36] / 277
COVERAGE pt_floor_4 rail_fallback miss 0.02 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_4 rail_fallback miss 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_4 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_4 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN pt_floor_4 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN pt_floor_4 rail_measured reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (4, 36), 'transport': (0, 72), 'warm_restart': (1, 54)}
COVERAGE pt_floor_4 rail_measured nominal independent [72, 72, 36, 104, 140, 140] / 277
COVERAGE pt_floor_4 rail_measured nominal 0.01 [36, 36, 68, 68, 68, 104] / 277
COVERAGE pt_floor_4 rail_measured nominal 0.02 [36, 0, 36, 36, 104, 104] / 277
COVERAGE pt_floor_4 rail_measured nominal 0.05 [0, 0, 0, 36, 72, 108] / 277
COVERAGE pt_floor_4 rail_measured nominal 0.1 [0, 0, 0, 0, 36, 36] / 277
COVERAGE pt_floor_4 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_4 rail_measured miss independent [72, 36, 36, 36, 72, 72] / 277
COVERAGE pt_floor_4 rail_measured miss 0.01 [36, 36, 0, 0, 0, 36] / 277
COVERAGE pt_floor_4 rail_measured miss 0.02 [0, 0, 0, 0, 36, 36] / 277
COVERAGE pt_floor_4 rail_measured miss 0.05 [0, 0, 0, 0, 36, 36] / 277
COVERAGE pt_floor_4 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_4 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN pt_floor_6 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN pt_floor_6 rail_fallback reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (0, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE pt_floor_6 rail_fallback nominal independent [72, 72, 36, 68, 68, 104] / 277
COVERAGE pt_floor_6 rail_fallback nominal 0.01 [36, 36, 36, 0, 68, 68] / 277
COVERAGE pt_floor_6 rail_fallback nominal 0.02 [36, 0, 0, 36, 36, 72] / 277
COVERAGE pt_floor_6 rail_fallback nominal 0.05 [0, 0, 0, 36, 36, 72] / 277
COVERAGE pt_floor_6 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 36] / 277
COVERAGE pt_floor_6 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_6 rail_fallback miss independent [72, 36, 36, 36, 36, 36] / 277
COVERAGE pt_floor_6 rail_fallback miss 0.01 [36, 36, 0, 0, 0, 36] / 277
COVERAGE pt_floor_6 rail_fallback miss 0.02 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_6 rail_fallback miss 0.05 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_6 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_6 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN pt_floor_6 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN pt_floor_6 rail_measured reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (0, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE pt_floor_6 rail_measured nominal independent [72, 72, 36, 104, 104, 140] / 277
COVERAGE pt_floor_6 rail_measured nominal 0.01 [36, 36, 68, 32, 68, 68] / 277
COVERAGE pt_floor_6 rail_measured nominal 0.02 [36, 0, 0, 36, 68, 104] / 277
COVERAGE pt_floor_6 rail_measured nominal 0.05 [0, 0, 0, 36, 72, 108] / 277
COVERAGE pt_floor_6 rail_measured nominal 0.1 [0, 0, 0, 0, 36, 36] / 277
COVERAGE pt_floor_6 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_6 rail_measured miss independent [72, 36, 36, 36, 72, 72] / 277
COVERAGE pt_floor_6 rail_measured miss 0.01 [36, 36, 0, 0, 0, 36] / 277
COVERAGE pt_floor_6 rail_measured miss 0.02 [0, 0, 0, 0, 36, 36] / 277
COVERAGE pt_floor_6 rail_measured miss 0.05 [0, 0, 0, 0, 36, 36] / 277
COVERAGE pt_floor_6 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE pt_floor_6 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN threshold_tau3600 rail_fallback gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN threshold_tau3600 rail_fallback reported latched/trajectories={'ambient': (1, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (18, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE threshold_tau3600 rail_fallback nominal independent [180, 180, 212, 212, 212, 212] / 277
COVERAGE threshold_tau3600 rail_fallback nominal 0.01 [144, 180, 180, 180, 180, 180] / 277
COVERAGE threshold_tau3600 rail_fallback nominal 0.02 [144, 144, 144, 144, 180, 180] / 277
COVERAGE threshold_tau3600 rail_fallback nominal 0.05 [36, 72, 72, 108, 108, 108] / 277
COVERAGE threshold_tau3600 rail_fallback nominal 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE threshold_tau3600 rail_fallback nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE threshold_tau3600 rail_fallback miss independent [72, 36, 108, 144, 144, 144] / 277
COVERAGE threshold_tau3600 rail_fallback miss 0.01 [36, 36, 72, 108, 108, 144] / 277
COVERAGE threshold_tau3600 rail_fallback miss 0.02 [0, 0, 72, 72, 108, 108] / 277
COVERAGE threshold_tau3600 rail_fallback miss 0.05 [0, 0, 0, 0, 36, 36] / 277
COVERAGE threshold_tau3600 rail_fallback miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE threshold_tau3600 rail_fallback miss 0.2 [0, 0, 0, 0, 0, 0] / 277
BENIGN threshold_tau3600 rail_measured gated latched/trajectories={'ambient': (0, 18), 'cold_pan': (0, 144), 'hot_pan': (0, 72), 'transport': (0, 432), 'warm_restart': (0, 162)}
BENIGN threshold_tau3600 rail_measured reported latched/trajectories={'ambient': (0, 6), 'cold_pot_large': (0, 36), 'frozen_plateau': (20, 36), 'transport': (0, 72), 'warm_restart': (0, 54)}
COVERAGE threshold_tau3600 rail_measured nominal independent [180, 212, 212, 212, 212, 212] / 277
COVERAGE threshold_tau3600 rail_measured nominal 0.01 [180, 180, 180, 212, 212, 212] / 277
COVERAGE threshold_tau3600 rail_measured nominal 0.02 [144, 144, 180, 180, 180, 180] / 277
COVERAGE threshold_tau3600 rail_measured nominal 0.05 [72, 72, 108, 108, 108, 144] / 277
COVERAGE threshold_tau3600 rail_measured nominal 0.1 [0, 0, 0, 0, 0, 36] / 277
COVERAGE threshold_tau3600 rail_measured nominal 0.2 [0, 0, 0, 0, 0, 0] / 277
COVERAGE threshold_tau3600 rail_measured miss independent [72, 36, 144, 144, 144, 180] / 277
COVERAGE threshold_tau3600 rail_measured miss 0.01 [36, 36, 108, 144, 144, 144] / 277
COVERAGE threshold_tau3600 rail_measured miss 0.02 [0, 0, 108, 108, 108, 144] / 277
COVERAGE threshold_tau3600 rail_measured miss 0.05 [0, 0, 36, 36, 36, 72] / 277
COVERAGE threshold_tau3600 rail_measured miss 0.1 [0, 0, 0, 0, 0, 0] / 277
COVERAGE threshold_tau3600 rail_measured miss 0.2 [0, 0, 0, 0, 0, 0] / 277
LOST_HAZARD_CELLS baseline 0
LOST_HAZARD_CELLS off_2tau_7200 300
LOST_HAZARD_CELLS off_4tau_14400 300
LOST_HAZARD_CELLS flat_tau3600 93
LOST_HAZARD_CELLS rate_002 0
LOST_HAZARD_CELLS pt_floor_4 238
LOST_HAZARD_CELLS pt_floor_6 248
LOST_HAZARD_CELLS threshold_tau3600 26
SELECTED rail_fallback report-only latched trajectories 23 -> 23
SELECTED rail_measured report-only latched trajectories 24 -> 23
ALL F3 GUARD COMPARISONS PASS
```

## Environment and validation apparatus

The restored checkout started on `work` at `20073ab98`, clean. After the scratch-board check, the source branch was fetched with an explicit remote-tracking refspec (the snapshot fetch configuration only tracked main), and `cloud/sensor-c1-soak-tau` was created at the required base.

```text
ASSERT-BASE OK: HEAD == origin/cloud/sensor-c1-leak (ebf8a777b50ecb81040fc0c56fa8bde706720638)
server: 10.99.0 (10.99.0-5431-g444312064)
client_schema: 10.99.0 (10.99.0-4383-gdcadf9baa)
board: temper-onboarding.kicad_pcb; footprints: 1; tracks: 6
NumPy 2.5.4 SciPy 1.18.1
cc (Debian 14.2.0-19) 14.2.0
cmake version 3.31.10
idf.py: unavailable
```

The GUI scratch-board lock restored from the snapshot was dismissed with the GUI; KiPy then passed the live version/document check. No board edits. SciPy was absent and installed into the prepared venv without changing manifests/lockfiles. The initial Linux host build also lacked `-lm` for the power-gate target; `cmake -S firmware/test -B firmware/test/build -DCMAKE_C_STANDARD_LIBRARIES=-lm` supplies it in the untracked build cache. With that setting CTest passed all 26 suites; the brief’s pre-existing `test_profiles.c` compilation failure remains.

The board-contract script is skipped as instructed: its unpushed board branch is unavailable. The ESP-IDF target build cannot run here (`idf.py: unavailable`). Broader repository checks were also sampled before changes: import-linter is unavailable in the prepared venv (`Failed to spawn: lint-imports`); the derived-artifact check already fails because `output` has no entry in `DIRECTORY_PURPOSE`. The pre-existing `cold_soak.py` Ruff findings are C416 and C420; they are unchanged. These are not represented as firmware passes.

Regression check against rebuilt, unchanged C objects, with only the new tests compiled in a scratch file:

```text
test_c1_units.c:744:test_soak_slow_heatsink_does_not_false_latch:FAIL: Expected 7 Was 2
test_c1_units.c:770:test_soak_rate_keeps_leaks_below_limit_and_skips_both_directions:FAIL: Expected 7 Was 2
54 Tests 2 Failures 0 Ignored
REGRESSION_BEFORE_EXIT 2
PAIRED_NOISE_SWEEP nominal independent cells= 3072 seeds=1..32 additional_misses= 0
```

## Full-pipeline provenance limitation

The unmodified baseline `./run.sh` stopped after all runtime/runaway gates passed:

```text
ALL RUNAWAY CHECKS PASS
SENSOR FAIL CODES PASS
T1 FAIL: derivation gates failed: source_inputs_clean
```

The preceding steps had regenerated `leak-checks.json`, which is a T1 provenance input. Its five changed float values include rim-fault times shifted by up to 0.4 s; the hazardous/benign headline counts are unchanged. All six regenerated JSON files and their differences were recorded and restored as the brief permits. The direct check on the clean baseline then printed:

```text
T1 PASS
```

A separate constraint applies to F3: T1 also pins hashes of all control C/header inputs in its committed evidence, while T2 compares firmware/study inputs against fixed base `03c28e76bd893a716c1b080bd34ccbfffd42993e`. The requested implementation therefore requires a future canonical evidence refresh to pass those provenance comparisons. This task does not change those gates, pins or committed JSON. The full run must not be reported as `ALL C1 FIRMWARE CHECKS PASS`.
