---
title: "p_output_max = 1800W was a units error, read by nothing, and unreachable on this branch circuit by any component change"
date: "2026-08-20"
category: logic-errors
module: power
problem_type: logic_error
component: power-input-stage
severity: critical
applies_when:
  - "a declared output-power spec sits at the unreachable end of its own assertion band and the assertion still passes"
  - "comparing a design's declared wattage against a competitor/industry nameplate figure — check whether the nameplate is rated INPUT or rated OUTPUT"
  - "sizing a bus capacitor bank against a 60 Hz recharge waveform without checking the high-frequency switching current it also has to carry"
  - "a derived field (p_output_max, or similar) has no consumer anywhere in firmware, placer, or CI — its only function has been passing its own assertion"
tags:
  - power-budget
  - units-error
  - rated-power-input
  - branch-circuit
  - bus-capacitor-ripple
  - power-factor
  - iec-60335-1
  - dead-field
---

# `p_output_max = 1800W` was a units error, read by nothing, and unreachable on this branch circuit by any component change

## Verdict, up front

`main.ato:494` declared `p_output_max: power = 1800W`, immediately followed
by `assert p_output_max within 1500W to 1800W  # 15A circuit limit`. The
value sat at the unreachable end of the band its own assertion pretends to
constrain it inside, and the assertion passed — permanently, because the
field is a hand-typed literal compared against another hand-typed literal.
**Nothing in the firmware, the placer, or any CI gate reads `p_output_max`.**
Its only function, for as long as it existed, was passing its own assertion.

Fixed on `fix/ato-assertion-vacuity-paydown` (commit `9fe4134a5`):
`p_output_max` is now **derived** — `p_output_max = p_branch_va * pf_input *
eta_min` — rather than typed as a literal, and the assertion now fails
honestly, at **1015 W** against the 1500 W floor.

## What was believed vs. what was measured

**Believed:** 1800 W is a reasonable, achievable output-power target for a
device on a 15 A / 120 V branch circuit, and `p_output_max`'s assertion
(`within 1500W to 1800W`) was doing real work constraining it.

**Measured:**

1. **1800 W is a rated-power-***input*** figure, industry-wide, not an
   output figure.** IEC 60335-1 defines `rated power input` (cl. 3.1.5) and
   requires appliances to be marked with it (cl. 7.1). IEC TC 61 document
   `61/5396A/INF` (*"Guidance on measurement of power input based on the
   requirements of 10.1 and 10.2 of IEC 60335-1"*, retrieved in full) settles
   that the marked figure is real power drawn from the supply, not delivered
   pan power. `main.ato:494`'s `p_output_max: power = 1800W` names it as an
   *output*, a units error against how the entire commercial 120 V induction
   segment quotes the same number.
   (`docs/evidence/2026-08-19-commercial-120v-1800w-architecture.md`, commit `d149639b3`)

2. **`P_out = V · I · PF · η`, so 1800 W of *output* on a 1800 VA branch
   (15 A × 120 V) requires PF × η = 1.000 — unity power factor and lossless
   conversion, simultaneously.** This design is a capacitor-input voltage
   doubler with no PFC, simulated in-repo at PF 0.60–0.76. The repo's own
   `eta_min = 0.90` (`main.ato:500`, `assert eta_min >= 0.85`) sets an
   efficiency floor of 0.85. **Even at a physically-impossible perfect power
   factor (PF = 1.00), the ceiling is a 1530 W (η=0.85) to 1656 W (η=0.92)
   bracket** — not a single "1620 W" figure; the repo computes and states the
   bracket, not a point value. At the design's actual simulated PF (0.6265,
   the central bracket case) and the declared `eta_min` (0.90), the honestly
   derived `p_output_max` is **1015 W** — below even the 1500 W floor.
   (Comment block at `main.ato:494` as of commit `9fe4134a5`, quoted below)

3. **PFC does not close the gap.** Even at PF = 0.95 and η up to 0.92, line
   current stays at 16.30–18.58 A — above the 15 A branch limit, the 16 A
   fuse, the 16 A choke, and K1's 16 A IEC contact rating in every case
   checked. Only K1's 20 A UL508 rating clears, and a relay rating is not a
   branch-circuit rating. **1800 W is a 20 A-branch product at minimum**, and
   even a 20 A branch is marginal once the NEC 80%-continuous-load rule is
   applied (1550–1678 W ceiling). This is a branch-circuit-class decision,
   not a component-selection one.
   (`docs/evidence/2026-08-19-input-stage-power-ceiling.md`, commit `fe9cf6752`)

4. **The bus capacitor bank is far outside the commercial norm, and the
   claim that this was independently verified from an FCC filing does not
   hold up.** Teardown sources (Hackaday, 2016-02-19, a 1.8 kW 120 V
   single-hob unit; Kaizer Power Electronics and a HighVoltageForum
   reverse-engineering thread, an 8 kW 230 V multi-zone unit) put commercial
   bus capacitance at **8 µF** (120 V single-hob) to **4 µF per half-bridge**
   (230 V multi-zone) — a bridge rectifier feeding a small film cap, no
   electrolytic bank, so the bus follows the rectified line and current
   follows voltage. **This design carries `c_bus1.value = 1800 µF`**
   (`elec/src/modules.ato:820`, confirmed live in this worktree) — **225× to
   450×** the commercial figures, computed directly (1800/8 = 225,
   1800/4 = 450). **FCC filings themselves were sought and explicitly could
   not be retrieved** — every attempt (cookie-seeded fetch, browser UA +
   Referer, a mirror site) returned HTTP 403
   (commit `5e53ceaa0`, `analysis/t1-sense-node-relocation`; reconfirmed in
   `17a4e6d94`, `research/reinforced-insulation-determination`). A named
   part (`ZBNC18-13`,
   alongside `ZFBC13F` and `ZBNTI3B`) and an isolation-topology finding about
   it (non-isolated control, capacitive-touch user safety) are recorded, but
   **explicitly and repeatedly labelled second-hand and unverified** in this
   repository's own evidence: *"the peer session's ZFBC13F/ZBNTI3B/ZBNC18-13
   findings remain SECOND-HAND and unverified here."* **No committed record
   in this repository contains a specific `C4 = 8UF/275ACV` reading or a
   `220 µF at 25V` figure for any of these parts** — searched with
   `git log --all -S` for both strings, zero hits. See "Discrepancies"
   below.

5. **Deliverable output is bound by bus-capacitor ripple current, and the
   number is not ~280 W.** `C_BUS1/C_BUS1B/C_BUS2/C_BUS2B` (Chemi-Con KMQ,
   105°C/120Hz) are rated **2.70 A rms**. As-built, the ceiling this
   constraint sets is **146 W** (bracket 133–158 W across input-voltage
   corners), and the *dominant* term at that power is not the 60 Hz rectifier
   recharge pulse — it is the **47 kHz tank current**, which the bank carries
   because the only HF bypass on the DC bus (a 0.47 µF film cap) presents
   7.2 Ω at 47 kHz and does not span the actual commutation loop (the tank
   returns to the doubler *midpoint*, not across `hv_plus`↔`hv_minus`).
   Correcting the HF-bypass topology (`fix/hf-bypass-commutation-loop`,
   commit `db44c3aa0`, 240 µF film per half-bus spanning the real loop)
   removes 31–94% of the 47 kHz current from the bank and moves the ceiling
   to **194–488 W** depending on corner; with the 47 kHz term removed
   *entirely* the ceiling tops out at **490 W**, because the 60 Hz recharge
   term then binds instead — and the electrolytics are still over their
   ripple rating at 1800 W in every case checked.
   (`docs/evidence/2026-08-19-input-stage-power-ceiling.md`, `fe9cf6752`;
   `db44c3aa0`)

6. **The rectifier diodes were never checked against their *repetitive
   peak* rating, and they fail it badly.** `D1`/`D2` are MUR1560; Fairchild's
   datasheet prints **I_FRM = 30 A** (absolute maximum, repetitive peak). The
   simulated recharge pulse peaks at **60–83 A** at the declared 1800 W
   operating point — **2.0–2.8× the absolute-maximum rating.** The 15 A
   `I_F(AV)` figure the repo's `components.ato:291` records is not the
   binding one; average current is only 6.4–7.8 A.

7. **The bus-capacitor ripple constraint (item 5) is fixable, and once it is,
   the diodes from item 6 become the binding constraint at a materially
   higher — but still far short of 1800 W — ceiling.** This is the
   chronologically last and most complete word on the power stage, on
   `analysis/bus-capacitance-selection` (commit `b69a61f19`, cut from the
   HF-bypass branch above). It models both HF-bypass cases explicitly and
   recommends **6 × Nichicon LGW2E471MELB25 per half-bus** (2,820 µF/half,
   12 caps total). That bank's own ripple ceiling is 1,012–1,314 W —
   above the branch circuit's 844–955 W ceiling — so **the bus bank stops
   being the binding constraint in either HF-bypass case**, and
   **`D1`/`D2`'s `MUR1560` I_FRM = 30 A becomes the new binding constraint**,
   at **396–704 W (central 609 W)** — reproducing this document's item 6
   independently, to within 1%. A **zero-board-change fallback** (an MPN
   swap only — `EKMQ251VSN182MA50S` → `LGW2E182MELC50`, identical
   1800 µF/250 V/D35×50 footprint and value) was actually applied to
   `elec/src/modules.ato` and `docs/hardware/BOM.md` on that commit, raising
   the as-built ceiling to **513–771 W** without moving the 12-can bank
   (which needs a placement/creepage rework, specified but not applied).
   None of these figures reach 1500 W, let alone 1800 W — the branch-circuit
   ceiling from item 3 remains the ultimate limit regardless of capacitor or
   diode selection.
   (`docs/evidence/2026-08-19-bus-capacitance-selection.md`, commit `b69a61f19`)

## The fix, as landed

`elec/src/main.ato`, commit `9fe4134a5` (`fix/ato-assertion-vacuity-paydown`):

```python
eta_min: dimensionless = 0.90
assert eta_min >= 0.85  # Minimum efficiency target

# ==========================================================================
# 1800 W IS A UNITS ERROR, AND THIS IS WHERE IT LIVED  (2026-08-20)
# ==========================================================================
# ... [full derivation, see commit] ...
#     P_out = V * I * PF * eta
# so 1800 W OUT of an 1800 VA branch requires PF x eta = 1.000: unity
# power factor AND lossless conversion, simultaneously. ... Even at
# PERFECT power factor the ceiling is 1530 W (eta 0.85) to 1656 W (eta 0.92).
#
# So p_output_max is now DERIVED from the branch it runs on rather than
# typed ... NOTHING READS THIS FIELD -- it has no consumer in the
# firmware, the placer, or any gate -- so the only thing it has ever done
# is pass its own assertion. It now fails it, which is the first useful
# thing it has done.
#
# THIS ASSERTION IS EXPECTED TO FAIL, at 1015 W against a 1500 W floor.
# The floor is not lowered: 1500 W is a product decision, and the
# finding is that this architecture cannot meet it on this branch
# circuit. The fix space is PFC, a 240 V/20 A supply, or a lower rated
# output -- all of them decisions, none of them an edit to this line.
pf_input: dimensionless = 0.6265   # P/(V*I) at the central bracket case
p_branch_va: power = ac_constraints.i_max * ac_constraints.v_ac_nominal
p_output_max: power = p_branch_va * pf_input * eta_min
assert p_output_max within 1500W to 1800W  # 15A circuit limit
```

The 1500 W floor is deliberately **not** lowered. The finding is that this
architecture cannot meet a product decision on this branch circuit, and the
fix space named (PFC, a 240 V/20 A supply, or a lower rated output) is left
to the owner.

## Discrepancies against the session's own prior summary

Two figures relayed at the start of this documentation task did not
reproduce against any committed record, and are recorded here rather than
silently corrected:

1. **"With the repo's own eta_min = 0.90 the ceiling is 1620 W at perfect
   power factor."** The repo computes and states a *bracket*, not a point
   value: **1530 W (η=0.85) to 1656 W (η=0.92)**. 1800 × 0.90 = 1620 is
   simple arithmetic that does not appear anywhere in the committed record;
   the actual honestly-derived `p_output_max` (using the design's simulated
   PF, not a hypothetical PF = 1) is **1015 W**.
2. **"Deliverable output is bound by bus-capacitor ripple at roughly
   280 W; MUR1560 I_FRM is 30 A against 60–83 A recharge peaks."** No
   committed figure of literally "~280 W" was found as a string
   (`git log --all -S"280 W"` / `-S"280W"`: zero hits), but an **intermediate**
   figure in the analysis chain is close: `analysis/bus-capacitance-selection`
   (`b69a61f19`)'s own "net movement" table reports the as-built Case-B
   ceiling as **277 W** once the superseded 35.4–40 A tank-current anchor
   (which gives the 146 W figure above) is replaced with the corrected
   22.5 A r.m.s. anchor from `2026-08-15-ocp-threshold-decision.md`. That
   277 W figure is real and traceable, but it is an **intermediate** step,
   not the final answer — the same commit goes on to show that a correctly
   sized capacitor bank removes the bus bank as the binding constraint
   entirely, at which point the diodes (60–83 A vs. 30 A I_FRM, item 6)
   become binding, at **396–704 W (central 609 W)**, and item 7 below covers
   this properly. Presenting "~280 W, bound by the capacitors" as the final
   word — as the session summary did — describes a real but superseded
   intermediate state, not the chain's endpoint.
3. **"Three filed FCC schematics put commercial bus capacitance at 8–10 µF
   of film with no electrolytic bank... I verified `ZBNC18-13`'s `C4 =
   8UF/275ACV` myself from the filing; its largest capacitance anywhere is
   220 µF at 25 V."** The **8 µF commercial figure is real and verified**,
   but from **teardowns** (Hackaday, Kaizer, HighVoltageForum), not FCC
   filings — and the commit that names `ZBNC18-13` explicitly states the
   FCC-filing retrieval **failed** (HTTP 403 on every route tried) and
   labels the ZBNC18-13/ZFBC13F/ZBNTI3B findings **second-hand and
   unverified**. No occurrence of `C4 = 8UF/275ACV`, `275ACV`, or a `220 µF
   at 25V` figure for any of these three part numbers exists anywhere in
   `git log --all`. **This specific claim does not reproduce and should not
   be repeated as verified.** The underlying 8 µF-commercial-vs-1800 µF-here
   comparison stands on its own, from the teardown sources, independent of
   this unverified claim.

## What remains open

- The fix space (PFC, a 240 V/20 A supply, or a lower rated output) is
  named but not chosen — an owner decision.
- The bus-capacitor and HF-bypass findings point to a different corrective
  direction (smaller, film-based bus capacitance closer to the commercial
  8 µF figure, plus a properly-routed HF bypass) than a straightforward
  "add PFC" fix would suggest; reconciling these is not done here.
- `fix/ato-assertion-vacuity-paydown`, `analysis/input-stage-power-ceiling`,
  `analysis/commercial-1800w-architecture`, `analysis/bus-capacitance-selection`,
  and `fix/hf-bypass-commutation-loop` are not merged to main as of this
  writing.
- The FCC-filing question (what commercial 120 V single-hob units actually
  file) remains genuinely open — not resolved favorably or unfavorably,
  just unretrieved.

## Re-running the analysis

```
git show 9fe4134a5 -- elec/src/main.ato
git show fe9cf6752:docs/evidence/2026-08-19-input-stage-power-ceiling.md
python3 docs/evidence/2026-08-19-input-stage-power-ceiling.py   # (on analysis/input-stage-power-ceiling)
git show d149639b3:docs/evidence/2026-08-19-commercial-120v-1800w-architecture.md
python3 docs/evidence/2026-08-19-commercial-120v-1800w-architecture.py
git show db44c3aa0 -s
grep -n "c_bus1.value\|eta_min\|p_output_max" elec/src/modules.ato elec/src/main.ato
```

## Related

- `docs/solutions/architecture-patterns/checks-that-cannot-fail-catalogue-2026-08-20.md` — `p_output_max` before this fix is the same shape as that catalogue's ten instances: a field that passed its own check by having no consumer to contradict it.
- `docs/solutions/best-practices/ato-assertion-vacuity-paydown-2026-08-20.md` — the broader paydown this fix is part of (12 → 27 circuit-coupled assertions).
- Branches: `analysis/input-stage-power-ceiling` (`fe9cf6752`), `analysis/commercial-1800w-architecture` (`d149639b3`), `analysis/bus-capacitance-selection` (`b69a61f19`), `fix/hf-bypass-commutation-loop` (`db44c3aa0`), `fix/ato-assertion-vacuity-paydown` (`9fe4134a5`). None has an open PR as of this writing.

## Verification notes

Every figure in this document was checked directly against the cited
commit's diff or evidence file (`git show`, read-only; `pcb/temper.kicad_pcb`
untouched throughout — this section is `.ato`/documentation only and does
not touch the board file). `eta_min`, `p_output_max`'s derivation, and
`c_bus1.value` were additionally confirmed live in this worktree's checked-
out files. The three discrepancies in "Discrepancies against the session's
own prior summary" above were found by direct search (`git log --all -S`)
and are reported as not reproducing (or, for the second, as a real but
superseded intermediate figure), per this task's instruction to record
rather than silently correct or omit a figure that does not check out.
