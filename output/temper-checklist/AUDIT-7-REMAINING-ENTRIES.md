# Audit pass 7: the four remaining register entries (2026-10-20)

C11, C25, C34 and C35 re-checked against source. This leaves only C1 and C30 unsettled (both need a bench). Paths: PS = `zapote/power-stage-120v`.

| # | Verdict | Basis |
|---|---|---|
| C11 FET soldering | **Real gap.** PS/DECISIONS.md:473 requires a seat-before-solder fixture (tab faces coplanar within 0.05 mm, square within 0.3°, 0.665 mm step at BR1). The JLC order remark in `fab/FAB-NOTE.md:72` says only "seat the package on the lead shoulders, not flush on the board"; no fixture, no coplanarity figure, and FAB-NOTE:71 says JLC hand-solders every THT part. Nothing in the order package asks JLC to meet 0.05 mm. | PS/DECISIONS.md:473; FAB-NOTE.md:71-72; a search of FAB-NOTE and `owner-items/order/*.md` for "fixture" found nothing |
| C25 CR-5 resistor | **Stale text, later decision wins.** `output/temper-sensor-r3/firmware/DECISIONS.md` (on origin/main; 3187 lines) D-RIMLIM (line 1092 section) recommends 76.8 k and a bench limit of ≤ 244.5 °C. D-BARRIER (2026-10-16, section near line 2361, later in the file) says "CR-5 unchanged" and "stays at 86.6 k". So 86.6 k and ≤ 252 °C stand. D-RIMLIM's own date was not read, so "later" rests on file order and D-BARRIER's explicit statement. | those two sections, read from origin/main |
| C34 plan 09 | **Stale text.** `validation-plan/00-MASTER-PLAN.md:239` says "not started", but `validation-plan/enclosure-fit/plan-result.json` has `pass: true` for six collision boxes and sink thermal at 20 and 30 CFM, and `validation-results/09-rubric-review-s19b` exists. Fix the master-plan row. The pass result was read, not re-run. | plan-result.json; directory listing |
| C35 aux at mid blower | **Not a contradiction.** The firmware model (`blower_aux.c`, constants in `blower_aux_native21`) gives, at 108 V low-line and 15 % margin: 0.31 A off, 0.887 A at full speed, and a curve in between: duty 0.4 → 0.663 A, duty 0.5 → 0.597 A. OPEN-ITEMS' 0.60 is duty 0.5; the README's "0.65 typical" is about duty 0.4. Both sit on one curve; "typical" is undefined in the README. Computed with a 10-line script from the file's constants, not run through the C test. | `firmware/components/power/blower_aux.c` |

## Fixes to make (not made here)
- C11: add the fixture and a coplanarity requirement to the JLC order remark, or decide the comb clamp makes it unnecessary and record that. Owner/fab decision.
- C25: none (the decision stands); optionally mark D-RIMLIM's 76.8 k text superseded.
- C34: update `00-MASTER-PLAN.md:239`.
- C35: have the README name the duty it means by "typical".
