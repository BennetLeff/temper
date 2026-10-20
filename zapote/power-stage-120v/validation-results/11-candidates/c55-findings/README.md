# c55: the two c54 ledger-desk findings (S30 U13.A slow edge, S31 C2 ripple)

Lane `claude/native21-s54-geometry` (worktree `ps-c54`), 2026-10-20, on the s54 board of record (9c639732). DECISIONS 82.

## S31: C2 ripple current: release case closed at the desk

The c54 desk read KEMET's 22.5 mm ripple graph (R46, F3095 2026-05-13, p.8) as "two upper traces, 1.5 and 1.9–2.0 A;
the leader lines do not attribute 1 µF, so the lower is taken", and rated C2 at 1.5 A. The leader lines are ambiguous,
but the traces are not. Below the knee each trace is the voltage limit I = 2πfCV, so the five low-frequency asymptotes
must stand in the ratio of the five legend capacitances at one test voltage.

| Trace (bottom → top) | C | implied V | 35 kHz | 90 kHz |
|---|---|---|---|---|
| yellow dashed | 0.15 µF | 246 V | 0.70 A | 0.77 A |
| blue | 0.33 µF | 247 V | 1.06 A | 1.14 A |
| grey | 0.47 µF | 249 V | 1.25 A | 1.33 A |
| black | 0.68 µF | 248 V | 1.60 A | 1.68 A |
| yellow dotted | **1 µF** | 248 V | **1.97 A** | 2.08 A |

That order spreads the implied voltage by 0.9 %. The next-best order spreads it by 71 %. So the c54 desk's 1.5 A reading
was the 0.68 µF trace (`results/r46-irms.md`, `scripts/r46_irms_digitize.py`).

KEMET p.6 defines Th as the hotter of the ambient around the capacitor and its hottest contact point, and derates
Irms by √((110 − Th) / 40) above 70 °C. `scripts/c2_ripple.py` rates the c54 stress model (`c54-ledger-desk/results/cx_current.json`:
worst variant, crest condition, reads high) against two Th bases:

| Case | C2 stress | Th max | L1 body (bound) | ratio there | C2 pad / bay | ratio there |
|---|---|---|---|---|---|---|
| release (17.5 A ceiling, 18.375 A trip) | 1.153 A | 96.3 °C | 92.1 °C | **0.874** | 58.2 / 61.0 °C | 0.584 |
| c28 (28 A) | 1.743 A | 78.8 °C | 90.1 °C | 1.253 | 63.6 / 55.0 °C | 0.884 |

The L1 body is the hottest surface beside C1 / C2, so the air it heats cannot be hotter. At the release case C2 holds
even at that bound, with no part change. The ledger (`scripts/apply_ledger55.py`) carries:
- the 1.97 A rating;
- two violation-severity checks: ripple at the L1-body Th, and the Th bound vs the Th the ripple allows. The Th check is
  keyed to margins.json, so a re-solve that heats L1 re-opens it.

28 A stays with the airflow route (S24): it passes at C2's own copper and bay air but not at the L1-body bound. The
stress is still a model estimate, so the bench gap (current probe and thermocouple on C2) stays.

## S30: U13.A slow input edge: not resolved here

U13.A sees an edge of 93–133 ns/V. The ledger gives TI's limit as 10 ns/V at VCC 3.3 V (SCES489E p.3). The edge comes
from the R134 1 k / C167 100 pF CMTI filter (DECISIONS 33).

Checked and rejected:
- **Nexperia 74LVC1G332GV** (C548340, SOT457, same pinout 1 A / 2 GND / 3 B / 4 Y / 5 VCC / 6 C, JLC 1,112). Its
  description says "Schmitt-trigger action at all inputs makes the circuit tolerant of slower input rise and fall times",
  but its recommended operating conditions still cap Δt/ΔV at 10 ns/V at 2.7–5.5 V and it gives no hysteresis (Rev. 12,
  2023-08-18, Tables 6 and 7; LCSC copy sha256 391436f1…). By its own datasheet the breach stays.
- **Nexperia 74AUP1G332** (Δt/ΔV per AUP family). SOT363 only (a footprint change) and 6–100 at JLC.
- **No other 3-input OR** with specified Schmitt inputs exists in SOT-23-6. Configurable Schmitt gates (LVC1G57 / 58 /
  97 / 98) implement 2-input functions only.

The fix that holds on paper is a Schmitt buffer between the RC and U13.A. That means U47 SN74LVC1G17DBVR (the U15 / U24
/ U40 line) plus C179 100 nF CC0603KRX7R9BB104 (the C47 line): no new BOM line, about 4 ns added to the OCP chain.

It cannot be done inside the current locks. The SELV-spine lock (`native-21/layout/selv_spine_lock.json`, region x
30–110, y 130–180) holds:
- R134 and C167 (pad centres y 133.5);
- U13 pins 3 and 4 (y 130.7);
- the `bus_fault_flt` copper between them.

In the chain's default mode the gate compares every track of a net that touches the region, so rewiring U13.A fails it.
The documented route is the spine owner's (`SPINE_OWNER=selv`, contract nets and planes still exact) plus a lock reissue
on the new board. That is the owner's call, the one left pending in DECISIONS 81.

A BOM-only alternative exists: retune R134 / C167 to τ ≤ 8 ns so the edge meets 10 ns/V. It drops the glitch rejection
from about 64 ns to about 5 ns. The U9 crossing's CMTI is already 1.06× over the 1.5× rule at maximum Qrr
(`c54-ledger-desk/results/gap-classes.md`, CA-IS3720HW), so that trade is rejected.

## Reproduce

```
python3 -I validation-results/11-candidates/c55-findings/scripts/r46_irms_digitize.py
python3 -I validation-results/11-candidates/c55-findings/scripts/c2_ripple.py
python3 -I validation-results/11-candidates/c55-findings/scripts/apply_ledger55.py   # idempotent
python3 -I native-21/verification/datasheet-ledger/gate.py                          # PASS
python3 -I native-21/verification/datasheet-ledger/tests/test_gate.py               # 0 failures
```

`scripts/jlc_fetch.py` is the sourcing study's fetcher, with its cache in this folder (`scripts/jlc-raw/`: the
74LVC1G332 / 74AUP1G332 / SN74LVC1G332 searches and C548340's record).
