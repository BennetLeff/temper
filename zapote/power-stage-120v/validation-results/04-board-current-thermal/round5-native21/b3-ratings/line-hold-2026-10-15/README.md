# B3 ratings basis at the 13.5 A inlet bound (2026-10-15)

Question, from temper-8d (`sensor-c1-impulse-mining:output/temper-aux-load-r1/`, 031a1f567): the firmware's aux
allowance (`blower_aux.c` 1.35 / 1.93 / 2.57 A) is mostly unspent. If it is cut, the power-stage hold rises 1.0–1.5 A.
Do the s41 B3 cases (and the still-air ceiling, laminate 22.3 A / C40 21.1 A, DECISIONS 53) still cover the board?

    python3 scripts/line_hold.py --i-line 13.5     # ~6 min, board s41 d4b2445c; -> margins-line13p5.json
    python3 scripts/compare.py margins-line13p5.json

## Why 13.5 A, not the proposed new hold

The B3 cases (`run_basis.py`, `b3/run_study.py` OPS c28) take the board's line current as the **11.1 A** inlet hold.
That was never a bound:
- the firmware limits `inlet_bound = I_ps·(1 + est_error) + I_aux ≤ 13.5 A` (`input_limits.h`, `n21_binding.c`
  `inlet_target_a = 13.5`, `input_limits.c` `est_error = 0.10`);
- so with today's allowance the true power-stage current can already reach 11.05 × 1.10 ≈ 12.2 A whenever the
  estimator reads low;
- with any aux allowance, the line path (J1 → F1 → L1) carries at most the 13.5 A target, and BR1 carries less.

13.5 A therefore bounds both the current firmware and temper-8d's proposal.

## What moves with line current in the model

Every tank-current row stays at its case I_t and does not move: R5, R39, the bank, C5 / C6, the hv_mixed / bus_mixed copper through
R5, sw_a / sw_b and the legs. R5 is modelled at I_t RMS, which is above any bus current. Three inputs move:

1. the ac_l / ac_n line copper, scaled by (I_line / 15)²;
2. L1's heat row, scaled by (I_line / 11.1)²;
3. BR1's share of the heatsink load in `fet_case.t_case`.

   The fan loop holds the sink at its 88.6 °C setpoint, so only the pedestal term moves: about 0.07 K.

## Result (s41, bay 55 °C, h 10)

| Row | c22 at 11.1 A | c22 at 13.5 A | c28 at 11.1 → 13.5 A |
|---|---|---|---|
| C40 (sets the 21.1 A ceiling) | −2.7 K (112.7 °C) | −2.7 K (112.7 °C) | −24.6 → −24.6 K |
| C38 | +0.1 K (109.9 °C) | **−0.0 K (110.0 °C)** | −22.2 → −22.2 K |
| Laminate, 1 mm block | +1.2 K | +1.1 K | −25.1 → −25.1 K |
| Laminate, FET row | +1.1 K | +1.0 K | −25.2 → −25.2 K |
| Any other gated row | | at most −0.1 K | at most −0.1 K |
| L1 climatic 125 °C (advisory) | +39.5 K | +27.6 K | +37.1 → +25.1 K |
| C5 / C6 (advisory) | +26.4 / +30.9 K | +25.0 / +29.7 K | −1.5 / −1.3 K |

## 15 A line current (nameplate question, temper-8d mining round 3)

`python3 scripts/line_hold.py --i-line 15` → `margins-line15.json`. At 15 A, as at 13.5 A, every gated row moves 0.1 K or
less: C40 at c22 goes −2.7 → −2.8 K, C38 +0.1 → −0.0 K, the laminate rows +1.2 → +1.1 K. L1 (advisory, 125 °C) goes
+39.5 → +18.9 K at c22 and +37.1 → +16.4 K at c28; C5 / C6 lose about 2.5 K. Line-path part ratings at 15 A (from the datasheet ledger): F1
KLDR025 25 A, re-rated to 16.5 A carrying at 55 °C bay (0.91); L1 20 A IR (0.75); BR1 25 A; J1 30 A. So a 15 A
nameplate needs no board change on these rows. Not computed here: the conducted-EMI change from the higher line
current, and L1 / F1 local air, which the ledger still lists as bench gaps.

## Conclusions

- **The still-air ceiling does not move.** C40 sets it, and C40 does not respond to line current. The laminate rows move
  by 0.1 K.
- **The aux re-allocation needs no board change.** The tank-current ceiling (≤ 18 A requested) still bounds R5, C40 and
  the FET row, whatever the inlet hold.
- **C38 at c22 reaches its 110 °C limit at 13.5 A** (margin +0.1 → −0.0 K). That is inside the model's resolution. It
  matters only because C38 already sits at its limit at 22 A, and the release ceiling is set below that by C40.
- **The basis should be 13.5 A, not 11.1 A**, because 11.1 A is not a bound. Moving `run_basis.py` / `fet_case.py` /
  `run_study.py` to I_line 13.5 waits until candidate 39 has merged: that lane edits the heat model. It is recorded as
  a follow-on in OPEN-ITEMS.

## Adopted: the gate basis at 13.5 A, with a release case (2026-10-15, after DECISIONS 55; board s42 9e075b4b)

`run_study.I_LINE_A = 13.5` is now the one line-current value: it feeds OPS c28, `run_basis.py` and
`fet_case.t_case(i_line=)`. The three inputs above move exactly as in `line_hold.py` (checked: identical case strings and
heat files for c22 / c28). `b3_ratings_gate.BASIS` gives each case its own bay:

- **Release case `c18_h10` at bay 61 °C.** This is the 18.0 A release ceiling at 18.9 A trip. The `b3_ratings` release
  gate is decided on this case alone. The card metric is `b3_release_margin_K`.
- **Ratchet cases `c22_h10` and `c28_h10` at bay 55 °C.** These feed `b3_laminate_margin_K` and `b3_rated_part_margin_K`.

`python3 run_basis.py` (6 solves, ~12 min at 4 workers) produces `../margins.json`: **PASS**.

| c18_h10, bay 61 °C, I_line 13.5 A | margin |
|---|---|
| R10 2512 terminal derating (worst) | +0.7 K (131.2 / 131.9 °C) |
| R20 derating; C40 | +1.1 K; +1.1 K (108.9 °C) |
| R18 derating; C41 | +1.8 K; +3.7 K |
| Laminate, 1 mm block; FET row | +4.1 K; +7.0 K |

The ratchet cases move as the s41 table above predicted. Every gated row moves 0.1 K or less: the c22 FET row goes
−3.5 → −3.6 K and the c28 FET row −30.6 → −30.7 K, so the card's laminate value goes −30.6 → −30.7 K. Rated parts stay
at −33.4 K. On the advisory rows, L1 loses 12.0 K and C5 / C6 lose about 1.3–1.5 K.

**Ceiling at bay 61 °C and 13.5 A.** `python3 run_basis.py --cases c22_h10@61,c28_h10@61 --runs runs/bay61-line13p5
--out line-hold-2026-10-15/margins-bay61-line13p5.json` gives this pair. `c39-gate-network/scripts/ceilings.py` then
gives:

- all gated rows **18.3 A** (R10 derating);
- laminate 18.5 A, laminate + film 18.4 A (C40), R_off 21.4 A.

These are identical to the 11.1 A result (`c39-gate-network/results/margins/s42-bay61.json`).

The I_trip² interpolation to 18.9 A agrees with the direct c18 solve within 0.2 K on R10, R20, C40 and the FET row. On
the laminate block it reads 2.7 K low (+1.4 against +4.1 K), so for that row it is conservative.
