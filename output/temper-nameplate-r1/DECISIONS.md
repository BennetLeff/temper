# temper-nameplate-r1 decisions (2026-10-15)

The owner asked to "experiment and justify" the nameplate decision. Evidence:
`nameplate.py` → `nameplate.json`, an estimate on the power-stage session's
round-6 tank model, read-only at b7ff4a857.

## D1. The tank ceiling sets temper's power; the nameplate does not

At the ceilings available today (18 A still-air release request, 21 A after
c39 and the peak trip, 22 A firmware), every nameplate option delivers the
same pan power: 650 / 856 / 931 W pooled at 120 V. That is **0.42–0.61× the
Control Freak**. A 15 A nameplate on today's board buys nothing.

## D2. Priority 1: raise the tank ceiling toward 26–28 A

Only at 24 A and above does the inlet start to bind. 28 A with a 15 A measured
nameplate reaches 0.90× the Control Freak (1371 W pooled at 120 V).

Per power-stage OPEN-ITEMS S2, the only route to 28 A is **board-face
airflow** from the enclosure: 2 oz copper cannot do it in still air. The other
board-side items from round 6 come with it:
- OCP thresholds;
- tank copper ≥ 9.8 mm;
- coil R_ac ≤ 0.23 Ω;
- a bank hot-spot measurement (1.12× the TDK curve at 28 A);
- FET R_SA ≤ 0.233 °C/W.

**Firmware:** the per-pan closed-loop frequency rule. Without it, neither
limit is reached at all.

**Owners:**
- enclosure line: airflow;
- power-stage session: ceiling, OCP, copper;
- controller/firmware: the frequency rule.

## D3. The nameplate

- **Plan certification for a 15 A nameplate,** with a measured input current
  (AMC1301 on R5). Put it to the lab at the early NRTL meeting.
- **Keep the firmware at the 13.5 A estimated target until the ceiling is ≥ 24 A.**

**Why:**
- At 28 A, going from 13.5 A estimated to 15 A measured is worth +19 % pan
  power at 120 V (1148 → 1371 W) and +20 % at 108 V (1033 → 1239 W).
- The AMC1301 is needed anyway, for measured pan power, η/C identification
  and pan classification (coil-driver-r1 item 2).
- Asking the lab costs nothing now, and changing the nameplate later is a
  re-certification.
- 12 A is dominated by every other option once the ceiling rises (1012 W at
  28 A).

**What it costs:**
- F1 runs at 0.91 of its 16.5 A derated rating.
- The conducted-EMI delta, and the L1/F1 local-air temperatures at 15 A, are
  unmeasured.
- The lab must accept a 100 % listing for a portable unit (NEC 210.23(A)(1)
  says 80 %).

## D4. What does not change

- **The aux patch and the AMC1301 add nothing at ceilings ≤ 22 A.** They
  start to pay at 24 A and above. They are still worth doing, for the
  measured-power uses and so they are ready when the ceiling rises.
- **No pan class reaches Control Freak parity in this model.** 28 A with a
  15 A measured nameplate is 0.81–0.90× at 108–120 V, depending on η_CF.
  "Matches the Control Freak" is a stretch goal, not a promise.

## Must be confirmed (lab and bench)

**Lab:**
- 100 % listing at 15 A for a portable induction cooker under UL 858 or
  UL 1026;
- the rated-input tolerance.

**Bench:**
1. Measured coil R_ac, and pan L/R for the six classes. The whole tank model
   is ASSUMED.
2. The tank current each pan needs for 1.2–1.4 kW.
3. Board temperatures at 21–28 A, with and without airflow (C40, laminate,
   bank hot spot).
4. Inverter efficiency, where the model assumes 0.93.
5. The L1/F1 local air and the EMI delta at 15 A.
6. **A same-pot boil reference.** The Control Freak's 10:55 run has unknown
   conditions, so instead run temper against a $50, 1800 W UL-listed portable
   (for example the Amazon Basics unit in yt:ctVXMv_4Glw) in the same 2 L
   pot. That replaces the backed-out loss with a measured comparison.
