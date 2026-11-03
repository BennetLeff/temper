# Passive ratings (2026-11-03)

Every capacitor's voltage rating, and every resistor's power and working voltage, checked against the worst case in intended use. The datasheet audit (`../datasheet-audit-rev-f/`) went through the semiconductors, regulators, inductors (S7) and protection parts one by one. This is the complete mechanical pass over the passives, so that none is left unreviewed.

Run it with `python3 validation/passive-ratings/passive_ratings_check.py`. It writes `passive-ratings-check.json` and exits 1 on any finding.

**Result: 88 capacitors and 80 resistors, 0 findings, 1 note (R121).**

## Method

- **Net intervals.** Supply nets take their corners from `../power-spurs/regulator_check.json`: RAW_P ≤ 14.74 V, RAW_N ≥ −14.81 V, ±12 V LDO outputs at 12.38 / −12.19 V. USB_VBUS is held to the 6.5 V hot-plug gate; the worst modelled peak is 6.24 V. The codec and source-stage nets are 0–3.37 V, EXCITE is ±1.7 V, and every other analog net gets the full RAW_N to RAW_P span.
- **Capacitors.** The worst voltage across each one is compared with its rating. The rating comes from the value text or is decoded from the MPN (Samsung CL10C…B8, Yageo CC0603…9BN and Fenghua …500 are all 50 V).
  - Nothing exceeds its rating.
  - No X5R or X7R part is above 80 % of its rating. The tightest are C117 (10 V polymer at 5.5 V), the 25 V X5R parts on 5 V rails, and C62 (16 V at 2.8 V).
- **Resistors.** Where the interval bound is meaningful, the power is (worst voltage)² / R. Series parts get their real current instead, from what drives them; each one cites its source in the JSON:
  - AFE: 1.7 V peak excitation into R104 + Rg with the DUT shorted, giving 11.6 mA on the 100 Ω range (13.4 mW in R40 and R43).
  - Codec dividers: ±11.06 V across 1 k + 1 k, 5.5 mA (30.6 mW).
  - VRLY: four 178 Ω RESET coils at once, 112 mA through R101 1 Ω (12.6 mW).
  - Logic series parts at the RP2040's 12 mA maximum drive.
  - The TPS7A3001 feedback chain.
  - Limit: 50 % of the 0603 rating of 0.1 W, and 50 V working voltage.
- **Out of scope.** Charged-DUT faults on the jacks are audit items AFE-01 to AFE-04, the Rev G clamp study. For example, R43 takes 1.17 W if LCUR is driven to 2.4 V. They are not ratings in intended use.

**R121 (note).** The hot-plug pulse is an energy question, not a power one. Step-charging C113 through any series R and L dissipates ½CV² in the resistances, so R121 takes at most 79 µJ per plug-in, at under 3.7 A for microseconds. UNI-ROYAL publishes no 0603WAF pulse curve. The bench check is bring-up §2a step 3: repeated USB-A plug-ins, then confirm R121 still reads 1.5 Ω.

**Mutation tests,** run on a scratch copy with `LCR_ROOT`:
- C117 at 4 V: caught.
- R12 at 10 Ω (1.13 W): caught.
- C62 at 2.5 V: caught. This test found a bug in the check itself, which read "2.5V" as 5 V; fixed before this run.
