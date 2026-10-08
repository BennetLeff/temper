# D-18: loss and thermal budget on the round-17 results (task 03) — heatsink and airflow for the enclosure

**Read [README.md](README.md) first (ground rules, board facts).**
Power-stage task 03 follow-up; indexed here with the other delegated work.

## Why it matters

The owner is designing the **enclosure now**. Heatsink size, thermal-pad
choice and airflow direction (still open: `DECISIONS.md` D2 "Airflow direction
is still not chosen") set its layout. Task 03 round 3
(`validation-results/03-loss-thermal-budget/round3/`, incl.
`heatsink_requirement.md`) is **PARTIAL / BLOCKED for D2 and B3**: it used
27 °C-model switching events at reference inductances and a typical-RDS(on)
conduction estimate, and flagged an unconstrained case that exceeds the shunt
R5's 1 W rating if sustained.

Round 17 now supplies, for native-18's 443 ns dead time (`DECISIONS.md`
2026-10-03): switching-overlap energies on the extracted board matrix (D-15
`out-D15/`, D-13 `out-D13/` incl. 100/150 °C), body-diode conduction during the
dead time (D-15), and the board matrix itself (`round17/d2/legA-h0-best.matrix.txt`).

## Task

1. **Loss table at native-18:** rebuild round 3's per-device loss table
   (`round3/scripts/losses.py`; keep its structure, heat partition and unknown
   list) with: MOSFET conduction at the hot RDS(on) (datasheet maximum at the
   junction temperature you iterate to, not typical), switching from D-15's
   overlap proxy at 443 ns (state it is a proxy), body-diode conduction
   during the dead time, BR1, R5, and the gate-drive power. Operating points:
   round 3's tank cases (incl. the 1,710 W cast-iron case) at 120 and 140 V
   line, the tank frequencies of `docs/hardware/power-section-120v/POWER-SECTION.md` §2.
2. **Heatsink requirement:** the maximum sink-to-ambient thermal resistance
   and the interface (pad) budget that keep every MOSFET's Tj ≤ a stated limit
   (≤ 125 °C design target unless the sources justify otherwise) and BR1
   within rating, at 40 °C and 50 °C ambient inside the enclosure (state the
   assumption). Iterate RDS(on)(Tj).
3. **Airflow direction (input to D2):** for the shared PE-bonded heatsink along
   a long edge (`DECISIONS.md` D2), compare the two flow directions in terms of
   which devices get preheated air and the resulting worst-device Tj; give a
   recommendation with its basis. Off-the-shelf heatsink + fan examples that
   meet the requirement (datasheet Rth vs airflow; cite), with their size,
   so the enclosure can be laid out.
4. **R5:** the shunt's dissipation at the worst sustained operating point vs
   its 1 W rating and derating; say if a part change is needed.

## Deliverable

`round17/delegation/out-D18/README.md`: one-line answer (required sink Rth and
airflow, worst device, margin), the loss table, the heatsink/airflow
comparison, R5 check, and the committed script and outputs. Proposals only:
no board, netlist, `elec/`, `pcb/` or firmware edits.

## Acceptance

Every RDS(on)/Rth/rating value cites a datasheet page; losses state which are
proxies vs bounds; the Tj iteration converges and is shown; assumptions
(ambient, partition, pad area) are explicit and varied where they dominate.
