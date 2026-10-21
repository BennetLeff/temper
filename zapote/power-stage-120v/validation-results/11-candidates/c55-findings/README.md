# c55: the two c54 ledger-desk findings (S30 U13.A slow edge, S31 C2 ripple)

Lane `claude/native21-s54-geometry` (worktree `ps-c54`), 2026-10-20. S31 is a desk result on the s54 board (9c639732);
S30 is fixed in copper as **stage 55, board of record d9ee93a8**. DECISIONS 82.

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

## S30: U13.A slow input edge: fixed at stage 55

U13.A (SN74LVC1G332, non-Schmitt) saw the R134 1 k / C167 100 pF CMTI-filter edge (DECISIONS 33): 93–133 ns/V against
TI's 10 ns/V recommended maximum at VCC 3.3 V (SCES489E p.3).

Checked and rejected:
- **Nexperia 74LVC1G332GV** (C548340, SOT457, same pinout 1 A / 2 GND / 3 B / 4 Y / 5 VCC / 6 C, JLC 1,112). Its
  description says "Schmitt-trigger action at all inputs makes the circuit tolerant of slower input rise and fall times",
  but its recommended operating conditions still cap Δt/ΔV at 10 ns/V at 2.7–5.5 V and it gives no hysteresis (Rev. 12,
  2023-08-18, Tables 6 and 7; LCSC copy sha256 391436f1…). By its own datasheet the breach stays.
- **Nexperia 74AUP1G332** (Δt/ΔV per AUP family). SOT363 only (a footprint change) and 6–100 at JLC.
- **No other 3-input OR** with specified Schmitt inputs exists in SOT-23-6. Configurable Schmitt gates (LVC1G57 / 58 /
  97 / 98) implement 2-input functions only.
- **Retuning R134 / C167 to τ ≤ 8 ns** (BOM only). It meets 10 ns/V but cuts the glitch filter from tens of ns to a
  few, on a U9 crossing already 1.06× over the 1.5× CMTI rule at maximum Qrr (`c54-ledger-desk/results/gap-classes.md`).

**Fix (stage 55):** U47 SN74LVC1G17DBVR (`u_bf_st`, the U15 / U24 / U40 line) buffers the RC node, and U47.Y drives
U13.A on the new net `bus_fault_st`. C179 CC0603KRX7R9BB104 100 nF (`c_bf_st_vcc`, the C47 line) decouples it. No new
BOM line. `scripts/u13_edge.py` gives:

| | stage 54 | stage 55 |
|---|---|---|
| U13.A input edge | 93–133 ns/V (RC) | ≤ 0.83 ns/V (U47: ≥ 24 mA into ≤ 20 pF), ratio 0.083 |
| trip delay through the RC, slow corner | 107.7 ns (U13 at VIH 2.0 V) | 107.0 ns (U47 VT+ ≤ 1.92 V + tpd ≤ 6.5 ns) |
| full-swing upset rejected if shorter than (fast corner) | 24.7 ns (U13 could switch at VIL 0.8 V) | 52.4 ns (VT+ min 1.48 V) |

U47's Schmitt input has no transition limit (SCES351Y p.5, p.11 "where the input is slow or noisy"). Its hysteresis is
0.51–0.83 V at 3 V (p.6).

**FMEA.** If U47 sticks low (output or input), it masks the isolated bus-fault path, just as U9 or U13 stuck low
already would. That is a dormant fault of the same class. Commissioning step 3 finds it: items 2 and 3 (shunt OCP,
bus OVP) record BUS_FAULT for a fault whose path runs U9 → R134 / C167 → U47 → U13.A. On board, DIS = NAND(permit_gate,
bias_good), so a bus fault acts only through BUS_FAULT to the controller. If U47 sticks high, it latches a fault and
fails safe. If C179 opens, U47 still gets its supply from the v3v3 plane via stubbed into its VCC pad. If C179 shorts,
it pulls v3v3 down, and RAIL_OK (P02) trips (COMMISSIONING step 2 brown-out item).

**Copper** (`scripts/edit55.py`, idempotent, every corner 135°): U47 at (31.4, 133.7, 90) takes C167's old place under
U13; C167 moves 3.25 mm south; C179 sits west of U47. The edit lies inside the SELV-spine lock region (x 30–110,
y 130–180), so it ran as the spine owner. The owner approved the reissue on 2026-10-20. `native-21/layout/selv_spine_lock.json`
now has baseline d9ee93a8 and a fourth `reissued` entry listing every key that moved. The first chain run (340def6f)
laid U47.3's east selv_gnd run from the pad centre: a 90° corner with the south run, right angles 51 → 52. The board of
record starts that run at the south run's first bend instead.

**Gates touched:** `audit.rs` (`stage55_schmitt_before_fault_or`; SELV / identity tables), `verify_source.py` (374
components), `bypass_check.py` (U47 ≤ 2 mm: C179 1.71 mm), `pin_absmax_registry.json` (`bus_fault_st`, logic, source
U47.4), `return_path19.py` (`bus_fault_st` on SELV_REF: 0 wrong-reference samples), `write_rules21.py` / `domains.py`
(`u_bf_st-nc` SELV NC), Kelvin s55 entries (s54's band: no OCP part or OCP-net copper change).

**Ledger** (`scripts/apply_ledger55.py`): the SN74LVC1G332DBVR transition check is violation severity and passes at
0.083; the finding gap is closed. U47 joins SN74LVC1G17DBVR with its hysteresis rating; its temperature row is a gap
note: it sits 4 mm from U13 and dissipates microwatts. C179 joins CC0603KRX7R9BB104.

## Reproduce

```
# stage 55 copper (already in native-21/layout/copper.json; idempotent), then the chain:
python3 -I validation-results/11-candidates/c55-findings/scripts/edit55.py native-21/layout/copper.json
sh native-21/layout/gates/chain.sh native21s55 PASSDIR BUILDDIR
python3 -I validation-results/11-candidates/c55-findings/scripts/r46_irms_digitize.py
python3 -I validation-results/11-candidates/c55-findings/scripts/c2_ripple.py
python3 -I validation-results/11-candidates/c55-findings/scripts/u13_edge.py
python3 -I validation-results/11-candidates/c55-findings/scripts/apply_ledger55.py   # idempotent
python3 -I validation-results/11-candidates/c55-findings/scripts/recite55.py        # after the chain
python3 -I native-21/verification/datasheet-ledger/gate.py                          # PASS
python3 -I native-21/verification/datasheet-ledger/tests/test_gate.py               # 0 failures
```

`scripts/jlc_fetch.py` is the sourcing study's fetcher, with its cache in this folder (`scripts/jlc-raw/`: the
74LVC1G332 / 74AUP1G332 / SN74LVC1G332 searches and C548340's record).
