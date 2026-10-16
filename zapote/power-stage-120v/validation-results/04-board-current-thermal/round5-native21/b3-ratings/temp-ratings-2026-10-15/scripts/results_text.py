HEAD = """# Temperature ratings of the native-21 s47 BOM lines with no ledger temperature rating (2026-10-15)

Analysis only; nothing written to PS. Regenerate: `python3 -I scripts/temp_ratings.py` (then `python3 -I ledger_temps.py`).

**Count.** {n} BOM lines ({refs} refs) of the 94 in `native-21/frozen/default.csv` (s47) have no temperature-unit rating
(no TA / TJ / T_op / element row, unit C or K) in `datasheet-ledger/ledger.json` (PS HEAD). That is not "36": **36 is the
number of semiconductor refs** (U / Q / D / BR / PS designators, not BOM lines) in the s47 monitor sweep's "no rating"
list (`11-candidates/c47-ref25-grade/results/monitor-sweep-s47.json`, `sweep_unrated`), which skips every passive,
connector and fuse and every semiconductor with a B3 row or a rating in its own table.

**Thermal basis.** B3 hot-copper BASIS, still air: release case c17.5_h10 at bay 61 C; ratchet c28_h10 at bay 55 C (c22 is
in results.json). Estimator = `b3_ratings_gate.est` (Q(0.25) + 3 |Q(0.25) - Q(0.5)| + bay - 50) on the run-file pad-copper
probe, + P x Rth for a junction / self-heated part (the gate's probe-row rule), or on the B3 body model's tj_c where the
part has a heat row. Resistors: terminal (pad) against the datasheet derating line at the part's P with the gate's 20 %
power margin (G6 rule); element against T_max where B3 has a body.

**Run files.** PS `b3-ratings/runs/` had been re-solved by the other agent (board 63aba33f) before this pass; they were
snapshotted. The vendor copy of the gate reproduces all {margins_rows} rows of the s47 `margins.json` (PS HEAD, board 4139c87b)
from them with max |difference| {margins_max_abs_diff_c} K at the file's 0.1 K rounding, and the c47 monitor sweep's
{sweep_refs} pad estimates within {sweep_max_abs_diff_c} K; the script stops if either check fails. Every ref has a probe.

Ranked by release margin (worst ref of each line in each case)."""

# re-base (S18, 2026-10-15): the same count and estimator on run files of a later B3 model (temp_ratings.py --rebase)
HEAD_REBASE = HEAD.split("**Run files.**")[0] + """**Run files (re-based).** The run files are the B3 BASIS solves of the integration chain on board {board8} with PS2's
body-to-air path (S18, `11-candidates/s18-ps2-body`), snapshotted with that chain's `margins.json`. The vendor copy of the
gate (refreshed to the S18 gate) reproduces all {margins_rows} rows of that `margins.json` from them with max |difference|
{margins_max_abs_diff_c} K. The c47 monitor sweep is the pre-S18 s47 record: its {sweep_refs} pad estimates now differ by up to
{sweep_max_abs_diff_c} K (the S18 model's move: PS2's own pads, which the S18 gate now rates on local air; every other ref within 0.9 K;
reported, not asserted). The numbers quoted under "Did not match" are the s47 (pre-S18) records; the table above is
current. Every ref has a probe.

Ranked by release margin (worst ref of each line in each case)."""

TAIL = """## Did not match

- **"36"**: 36 semiconductor refs, not BOM lines (see Count). The BOM-line count with no temperature rating is 73.
- **PMEG6030EP at c28**: the s47 pad estimates are D7 156.8 / D9 154.0 / D6 149 / D8 140.2 C (sweep), 159.6 C for D7 with
  the 2.8 K turn-off self-heat; the "about 166 C" is the s42 sweep (monitor-probes README: 140-166 C), not s47.
- **BAT54S-7-F** is ledger VERIFIED with only VRWM / IFRM; Diodes DS11005 rates TJ -65..+150 C (p.2). D18 / D20 at c28 are
  124.3 / 123.x C: they pass 150 C by ~26 K (a 125 C TJ would have been a ~1 K margin).
- **TPS7A4700** absolute-maximum TJ is 125 C (SBVS204G p.4 'operating virtual junction'), there is no 150 C abs max; the B3
  gate already uses 125 C.
- **JST VH**: the ledger gap text says 105 C including self-heating; the current eVH.pdf agrees (-40..+105 C incl. rise) and
  the legacy catalogue says 105 C is the UL-registered maximum, but its general range was -25..+85 C.
- **30KPA150CA maker**: ledger Good-Ark (TJ 150 C); the LCSC code on the sourcing row (C19111562) is Littelfuse (TJ 175 C).
  The lower is used.
- **B3 heat file R39**: labelled RC1206FR-071R5L with (I/100)^2 x 1.5 ohm (the stage-20 1:100 CT); the board has the 1:200
  CT and RC1206FR-073RL 3.0 ohm, i.e. (I/200)^2 x 3.0 = half the modelled power. Conservative; the label is stale.
- **B3 body-model labels**: U1 / U2 run-file parts carry mpn 'UCC21550BDWKR' (the BOM is 2EDR8259XXUMA1). Heat is the
  2EDR basis (note text), only the label is stale.
- **b3_ratings_gate MON_R** (advisory monitor-divider rows): still the s42 divider values (e.g. ref-halfref 10 k, src-uv
  4.42 k, p-spanov 133 k ARG03 'Viking'); the s47 BOM has 4.42 k / 750 / 2.94 k / 104 k Yageo RT0603 there (stage 45). The
  powers are mW either way and the rows are advisory, but R87 / R105 / R120's row basis text names the wrong part.
- **Ledger function text** for TPS7A4700RGWR still says 'Tj 89 C, 36 K margin (DECISIONS.md:825)'; B3 now gives 119.9 C at
  the release case (+5.1 K) and 124.7 C at c28 (+0.3 K).

## Not obtained / open

- UL Product iQ entries (E60425 Phoenix, E81895 / E14721 Littelfuse, E60389 JST, E41599 Schurter, E29179 Molex): no vendor
  document states a UL temperature lower than the general range; the UL-side limits were not readable (403).
- Littelfuse 01250003H clip: no temperature rating anywhere. KLDR fuse: no operating range, only the rerating curve.
- Phoenix MKDS 5 derating is for 6 mm2 wire only; J1's own rise with the 14 AWG cord is larger than the scaled 4.1 K, so
  J1's +0.4 K release margin is not a demonstrated pass.
- PMEG6030EP: no hot-Tj VF or IR maximum; the VF table goes only to 3 A at 25 C.
- VOL628A: no thermal resistance published.
- TNPW: rated by 'mode'; the most conservative ('General', 125 C film) is used."""
