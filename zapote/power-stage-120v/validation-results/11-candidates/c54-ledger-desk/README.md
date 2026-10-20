# c54 ledger desk pass (2026-10-18): electrical ratings for every SIGNAL line, desk gaps, gap classes

Board of record: native-21 stage 53 (frozen BOM `native-21/frozen/default.csv`). This lane is the only one that edits
`native-21/verification/datasheet-ledger/ledger.json`.

## Run order (stdlib + numpy; every step is reproducible from committed inputs)

```
python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/net_stress.py    # results/net_stress.{json,md}
python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/signal_audit.py  # results/signal_audit.{json,md}, ic_pins.md
python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/cx_current.py    # results/cx_current.{json,md} (numpy)
python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/apply_ledger.py  # edits ledger.json (idempotent), datasheets/records.json, results/apply_log.md
python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/gap_classes.py   # results/gap-classes.{md,json}
python3 -I native-21/verification/datasheet-ledger/gate.py                            # PASS
python3 -I native-21/verification/datasheet-ledger/tests/test_gate.py                 # 0 failures
```

`scripts/ds_find.py FILE.pdf REGEX...` prints the PDF page index of a datasheet value. It was used to put a page
number on every rating.

## Method

- **Stresses.** `net_stress.py` reuses the NetModel of `native-21/layout/gates/pin_absmax.py`, with the rail ranges and
  fault envelopes of `pin_absmax_registry.json`.
  - For every two-terminal SIGNAL part it takes V across the part in the op and fault models, and P = V² / Rmin.
  - Divider resistors use the divider chain at adverse tolerance corners. This fixes a NetModel quirk that widened a
    resistor whose end is a hull net to the full bus.
  - IC pins come from `pa.run` (results/ic_pins.md).
  - Output currents and the AC / pulse terms (pump, CT, burden, gate edge) are worked in `signal_audit.py`, which cites
    its sources line by line in results/signal_audit.md.
- **Ratings.** These come from the maker PDFs the temp-ratings / pin-absmax / s45 / s16 lanes downloaded. They are kept
  outside the repo (`worktrees/runs-native21/...`). The sha256 prefixes were re-verified on 2026-10-18 and recorded in
  `datasheets/records.json` with the pages used.
- **Derating rules**, the same conventions as the existing ledger entries:

  | Part type | Rule |
  |---|---|
  | Resistors | V ≤ max working voltage / RCWV; P ≤ 50 % of P70 |
  | Caps | V ≤ 80 % of VR in operation; ≤ 100 % at the fault envelope |
  | ICs | inside the recommended conditions; IO ≤ 50 % of abs max; IOL ≤ the recommended value |
  | Diodes | ≤ 50 % |
  | Connector | ≤ 80 % |

  c28 (28 A ceiling) overruns are gap-severity owner items, as everywhere in the ledger.
- **C1 / C2 ripple current.** `cx_current.py` runs the stage-19b conducted-EMI network (`07-conducted-emi/s19b/
  emi_s19b.py`) with the native-21 L1 (0.75 mH, 8 µH stray) and DC link (2 × 9 µF). It uses the same source spectra
  and takes the X-cap branch current per harmonic. The line-cycle RMS is crest / √2 plus the 60 Hz term in quadrature.
  It is a linear, crest-condition estimate and reads high: the bridge is always conducting, and there is no trace
  inductance between C2 and the DC link.

## Results (ledger counts before → after)

| | VERIFIED | PARTIAL | UNAUDITED | VIOLATION |
|---|---|---|---|---|
| before (HEAD) | 3 | 92 | 0 | 0 |
| after | 3 | 92 | 0 | 0 |

- **Totals.**

  | | Before | After |
  |---|---|---|
  | Gaps | 300 | 209 |
  | Checks | 387 | 522 |
  | Ratings | 366 | 493 |

  The 102 'Not audited' / 'only the temperature rating is audited' gaps are closed by checks. No violation-severity
  check fails.
- **No new VERIFIED, honestly.**
  - 39 lines are PARTIAL only because their local temperature is the B3 body model, not a measurement
    (results/gap-classes.md lists them). They need the bench thermal run.
  - The rest carry bench, certifier, owner or model gaps.
- **Remaining gaps by class** (results/gap-classes.md has each gap and the test or answer that closes it):

  | Class | Gaps |
  |---|---|
  | bench | 54 |
  | certifier | 31 |
  | owner | 46 |
  | B3-estimate | 76 |
  | model-estimate | 2 |

## Findings (gap severity; no VIOLATION)

1. **U13.A (SN74LVC1G332) slow input edge.** 93–133 ns/V through R134 1 k / C167 100 pF against TI's 10 ns/V recommended
   maximum for a non-Schmitt input (τ 106 ns). It is a recommended-condition breach, not an overstress. BUS_FAULT may
   chatter at threshold: nuisance edges in the trip direction, not a missed trip. Under the LM2901B / 2EDR convention
   (recommended conditions at violation severity) it would be a VIOLATION, so it is the owner's decision. Options:
   accept it with the DECISIONS.md:1128 bench probe, or move the RC behind a Schmitt input at the next spin.
2. **C2 (R463N410050N1K) ripple current.** 1.15 A line-cycle RMS at the release trip and 1.74 A at 28 A, against
   ≥ 1.5 A at Th ≤ 70 °C (KEMET p.8, lower candidate trace) derated by √(ΔTlim / 20 K) (p.6).
   - Release holds only while C2's Th ≤ 86.4 °C. With the L1 body beside it (92.4 °C) as Th, it is 1.16 of the rating.
   - 28 A exceeds the rating at any Th.
   - C1 behind the inlet module carries ≤ 0.15 A. Without the module (the bench bypass only) it carries 1.6–2.4 A,
     because C1 / L1 stray / C2 resonate near 80 kHz.
   - Closing test: a current probe and a thermocouple on C2 at the release ceiling. Owner: the 28 A route (a
     higher-current X2 or series impedance).
3. **Thin items now in the ledger:**
   - R39 burden at c28: 0.52 of P70 (an owner gap).
   - TLV3201 CT inputs at the 155.7 A CT fault: 0.96 V above VCC, current-limited to 0.97 mA (bench).
   - C64 25 V and C11 / C18 25 V under single faults (certifier).
   - The R53 / PMEG / 0603 jumper pulse and surge bases (owner maker questions, and certifier / bench).

## Desk gaps (8) and S21 record fixes

| Gap | Outcome |
|---|---|
| R5 element | +6 K worst audited mesh correction → 130.1 °C, 0.765 of 170 °C (check added). Now B3-estimate, closed by a thermocouple; the stale `b3_ratings_gate.py:21` cite is now `:21-23`. |
| Bank F_T | Chord of the two published IRMS table points: 26.09 K, 24 A ratio 0.767 (check added). Residual is an owner maker question: 1.0005 with no interpolation credit. |
| Bank approval basis | Relabelled certifier (end-product evaluation). |
| C5 / C6 footprint name | owner (library record). The BOM still names TDK_B32656G0275J000. |
| L1 digitisation | Merged into the bench local-air gap: the release check is 0.649 at −3 %. |
| L1 ALT-D3 8 µH stray | model-estimate: about 2–4 % more surge current. ALT-D3's surge.py / cwg_fit.py are not committed, so it was not re-run. |
| C1 / C2 DM current | Computed (finding 2); the gaps are now bench plus owner. The stale L1-body citation (102.2 °C at c18) is refreshed to s52 (92.4 °C at c17.5). |
| R1 / R2 RV1 Vc at 750 A | Figure 4 is re-read and cannot be attributed. Now bench. |

**S21 record fixes:**
- 30KPA150CA: the Littelfuse sheet is recorded (identical row; TJ 175 °C, UL E230531, αT 0.1 %/°C typical). Good-Ark
  TJ 150 °C stays binding, and the delivered maker becomes an owner record.
- TPS7A4700: the function text now gives TJ 120.6 / 125 °C at release. The 'Tj 89 C, 36 K' came from the stage-15 h25
  model.
- SN74LVC1G132: the +5 % VCC stand-in is replaced by the registry's 5.11 V.

## Stale items found (not fixed here: outside this lane)

- **B3 heat-file labels** (OPEN-ITEMS S21): R39 is 1.5 Ω on 1:100, and U1 / U2 are labelled 'UCC21550'. B3 MON_R still
  uses the s42 dividers.
- **IPW65R018CFD7 'F7 loop re-extraction open'** may be covered by the s51 FEM matrices (S3).
- **TPS70950QDBVRQ1** U37–U39 have no temp-ratings rows to cite.
- **Stage 54** (from the lead) re-keys 25121WF680JT4E → PS122WF680JT4E, 0603WAF4991T5E → ERJ-PA3F4991V, and moves
  R44 / R45 onto RT0603BRD0711KL. This pass audited the s53 lines. net_stress / signal_audit cover new designators only
  once the BOM changes and they are re-run.
