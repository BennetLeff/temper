# check_tab_gaps.py (OPEN-ITEMS S34)

**What it checks.** The 3.2 mm functional-creepage rule (`write_rules.FUNCTIONAL_CREEPAGE_MM`) only sees copper pads. This gate
checks the exposed TO-247 tab metal of adjacent, same-facing FETs on different tab nets (pad 2 = drain = tab):

- centred gap = pitch - E1 max
- worst gap = centred gap - 2 x (sideways lead play + hole position tolerance)  (flat and corner play; the smaller is used)

and compares the worst gap with the functional creepage floor. Same-net pairs are skipped.

**Inputs (nothing hard-coded).** Board of record `validation-results/08-manufacturing-package/native-21/board-of-record-s57/section.kicad_pcb`
(footprint x/y/rotation, pad-2 net; adjacency derived from positions). E1 max, lead play, hole tolerance and the 3.2 mm floor
come from `validation-results/11-candidates/s32-jlc-fets-m11/s32_calc.py` (imported; it pulls `bench_params`, `bench_mech` and
`write_rules.py`). Controls: the gate fails (exit 2) if its numbers differ from `s32-calc.json` `tab_to_tab`, and (exit 1) if
the board differs from `bench_params.FET_X` / `TAB_NET`.

**Ratchet.** `check_tab_gaps_baseline.json` lists the known-open failing pairs (today Q5|Q6 and Q3|Q2, worst 2.770 mm).
Exit 0 only if the failing set is within the baseline, no baseline pair is worse by > 0.001 mm, and the board's FET set, tab
nets and adjacent-pair set equal the baseline's. Otherwise exit 1. While the baseline is non-empty the run prints that S34 is OPEN.

**How S34 closes.**
1. Measure the 25-part lot's tab width E1 max (same measurement as DECISIONS 90). Put it in `{"e1_max_mm": 13.70}` and run with
   `--lot-e1 FILE`; it passes when E1 max <= 13.720 mm (worst gap >= 3.2 at the 18.0 pitch). Then empty `known_open` in the
   baseline (the gate prints a note for each pair that now passes) and commit the lot file and JSON.
2. Or fit an insulating barrier between adjacent tabs / take the cl. 29.2.4 / clause-19 fault route with the certifier; in
   either case change the model deliberately, record it in OPEN-ITEMS, and empty the baseline.

**Run.**
```
python3 -I tools/check_tab_gaps.py                 # writes tools/check_tab_gaps.json
python3 -I tools/check_tab_gaps.py --lot-e1 lot.json   # writes check_tab_gaps.lot.json (or --out)
python3 -I tools/check_tab_gaps.py --selftest      # negative controls; copies of the board go to the scratchpad, the real file is untouched
```
Selftest: 17.0 mm pitch different nets = new failure; same-net pair skipped; `--lot-e1 13.70` passes both pairs, 13.72
passes and 13.73 fails; Q6 / Q2 moved 1 mm closer fail the ratchet; Q3 moved toward Q6 fails as a new pair.
