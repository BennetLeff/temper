<!-- provenance: commit=fbab8022e, dirty=false (branch investigate/drift-gate-1198-ipc2221-decisions, based on origin/main @ 7f6a6bd5c). pcb/temper.kicad_pcb was NOT touched by any of this work (verified: no pcb/ path in the changeset). -->

# Pending-owner decisions, 2026-08-15 — A: drift-gate enablement, B: PR #1198 disposition, C: IPC-2221 bracket table

Three pending owner items, decided with data. Each section states the decision up
front, then the evidence. All three decisions were implemented or documented in
this changeset except where the decision itself is "needs an owner value call" —
those are flagged as such and deliberately NOT executed.

---

## A. Drift-gate enablement — 4 drift families + the tank "functional" tier

**Decisions, up front.**

1. **The "functional" tier is now a first-class tier in the gate.**
   `scripts/check_creepage_clearance_drift.py`'s `_classify_tier` recognizes
   functional insulation (IEC 60335-1 Table 18, cl. 29.2.4) and classifies it
   **last** (after reinforced/basic/working) — the ordering is the whole fix.
   A naive first-priority "functional" check was tried and rejected earlier
   (documented in `generate_kicad_dru.py` and `tank_creepage.py`): it re-tagged
   `netclass_rules.yaml`'s HighVoltageIsolated entries — whose `because` reads
   "reinforced separation to LV/SELV, functional-only to its own HV/ACMains
   neighbours" — out of the reinforced families, shrinking real comparison
   families and turning two genuine MISMATCH reports into OK ones. Classifying
   functional LAST means only a text that names functional and **no other tier
   keyword** classifies as functional; a text that mentions functional as
   context for a reinforced/basic/working figure keeps the more specific tier.
   Measured against the pristine tree: HighVoltageIsolated stays reinforced,
   the tank Table-18 constants classify functional.

2. **The tank tier no longer causes a gate error.** `tank_creepage.py`'s
   `DEFAULT_TANK_CREEPAGE_MM` is restored to the bare-name selection-alias form
   (`= HV_TANK_CREEPAGE_PD3_MM`). The dict-lookup form was a workaround for a
   gate that could not model the functional tier (its alias self-verification
   failed closed with exit 5); with functional modeled, the alias form works
   and satisfies the gate's own "the enforced value must still participate in
   its family" contract: the enforced 10.0mm is a member of
   `[creepage/functional]` and the 6.3mm PD2 fallback is reported under
   "declared but not enforced" (with its enforcing alias and value named).
   The gate now **exits 3 (violation), not 5 (gate error)** — the acceptance
   criterion the task set. (It already exited 3 before this changeset thanks
   to the 2026-08-14 dict-lookup workaround; the point of this change is the
   tier is now *modeled*, not dodged.)

3. **The four drift families are resolved or accepted via a new, self-verifying
   acceptance registry** (`ACCEPTED_DRIFT` in the gate). Accepted families are
   still discovered, still printed in full with their justification, and fail
   closed (GateError) the moment they carry a value outside their reviewed set —
   acceptance is documented, not silent (see the registry docstring for the
   contract, which mirrors `KNOWN_TIER_MISCLASSIFICATIONS`).

   | Family | Values | Decision |
   |---|---|---|
   | `[clearance/basic]` | 3.0 vs 6.0mm | **ACCEPTED** — permanent, investigated 2026-07-29: the atopile SSOT's own 135V ACMains→LV basic barrier vs the mains_240v-bucket netclass's own routing figure. Two different requirements sharing the coarse "basic" label; the larger figure at the higher voltage bucket is the expected direction (IEC figures are working-voltage-indexed). This is the gate's own module-docstring case. |
   | `[creepage/basic]` | 5.0 vs 6.0mm | **ACCEPTED** — same pair, same verdict. |
   | `[creepage/reinforced]` | 6.0 vs 12.6mm | **ACCEPTED with a fix** — 12.6mm is the decision-documented, enforced PD3 figure (2026-08-15 data-driven decision + PR #1229). The ato/pcl 8.0mm PD2-era sites were **fixed to 12.6mm in this changeset** (the exact sites the gate's module docstring calls out: "updated check_isolation_keepout.py and generate_kicad_dru.py but never touched constraints.ato or the pcl yaml" — the PD2→PD3 retarget is now complete, in the strengthening direction). The four 6.0mm TEMPER_NET_CLASSES sites (HighVoltage/HighVoltageIsolated creepage_mm in `design_rules.py` + `netclass_rules.yaml`) carry explicit in-tree "UNSOURCED, values unchanged — re-sourcing is a separate attributed decision" flags written 2026-08-15, and are **accepted as-is** pending that decision. **8.0mm (PD2) is deliberately NOT in the accepted set — a reappearing PD2 figure fails the gate closed.** |
   | `[creepage/functional]` | 6.3 vs 10.0mm | **ACCEPTED** — Table 18 row vi (>500-800V): 10.0mm is PD3 (enforced, decision-documented), 6.3mm is PD2 (declared fallback on the HighVoltageTank placer config, cited 2026-08-12, predates the PD3 decision). Both are legitimate row-vi values for the 570.5 Vrms tank node; the enforced/fallback relationship is now modeled by the selection alias. Fix direction if/when the attributed re-sourcing lands: align HighVoltageTank.creepage_mm (netclass_rules.yaml + design_rules.py) to 10.0mm. |

4. **One family stays a hard red — `[clearance/reinforced]` (2.0 vs 6.0mm).**
   This is the honest-red case: the HV→LV barrier clearance is 2.0mm on the
   enforced side (netclass HighVoltage.clearance, cited: Table 16 2500V
   reinforced step + cl. 29.1 soldered adder, keyed to 120V nominal) vs 6.0mm
   on the SSOT side (ato `HV_to_LV.min_clearance`, netclass
   HighVoltageIsolated.clearance — uncited legacy; 6.0 is in **no** recovered
   Table 16 value set {0.5, 1.5, 3.0, 5.5, 8.0, 11.0}). Neither side is
   determinable as "correct" from repo evidence: the DRC's own RULE 4 note
   flags IEC 60664-1 at 400V may require 3.0mm+, and lowering the declared 6.0
   to match enforcement would weaken a declared figure. **Owner decision
   needed**: (a) accept 2.0mm as the truth and align the stale 6.0 sites
   (weakens the declared figure — owner action), or (b) determine the real
   barrier figure (raises enforcement — needs a determination), or (c)
   explicitly accept the family via the registry with a justification. Until
   then the gate stays red on this family, which is the correct, honest state.

5. **CI enablement is partial and deliberate.** The drift gate's 44 unit tests
   now run in CI (always green — synthetic fixtures). The gate step itself
   stays commented because it exits 3 on main with exactly the one honest red
   above; enabling it would red the required Core Tests context on every PR.
   Uncomment the gate step when `[clearance/reinforced]` resolves.

**What the gate now reports on main** (measured, exit 3):
`[clearance/basic]` ACCEPTED, `[clearance/functional]` OK (1), `[clearance/reinforced]`
**MISMATCH (the honest red)**, `[clearance/working]` OK, `[creepage/basic]` ACCEPTED,
`[creepage/functional]` ACCEPTED (6.3 declared-not-enforced vs 10.0 enforced),
`[creepage/reinforced]` ACCEPTED (6.0 UNSOURCED vs 12.6 enforced), `[creepage/working]`
OK. 44/44 gate unit tests pass; the pcl + tank test suites show zero new failures
vs pristine origin/main (2 pre-existing failures in the pcl suite — the
`because`-text tests broken by the 2026-08-15 SSOT migration's UNSOURCED
rewrite of netclass_rules.yaml, which this changeset does not touch).

**Infrastructure hazard found while verifying (worth an owner glance):** the
main checkout's installed `temper_drc_rs` extension was **stale** at the time
of this work — built 2026-08-15 09:07, four hours before PR #1219 (13:33) which
re-pinned its clearance table — so any measurement taken against the main venv
in that window ran the fabricated-14.0-era table. Three of the five
"pre-existing" test failures first attributed to main were in fact this stale
extension (they pass against a fresh build); the boundary suite's
`test_hv_escalation_both_hv` expected 12.6 and received 14.0 from the stale
`.so`. `scripts/check_stale_extensions.py` flags it; `make extensions` fixes
it. Not fixed here (never rebuild into the shared venv while concurrent agents
measure).

**Why acceptance-with-self-verification is not "making a check pass by weakening
it".** The accepted families are still discovered and printed in full on every
run; the registry self-verifies closed against the reviewed value set (a new
value = GateError = re-review, never silent absorption); 8.0mm PD2 is
explicitly excluded. What changed is only the *exit state* for families that
have a complete, cited investigation on record. This is the mechanism the
2026-08-14 CI comment asked for ("once a human has resolved (or explicitly
accepted, the way [clearance/basic]/[creepage/basic] already are) all 4
families") — the investigations existed; the recording mechanism did not.

---

## B. PR #1198 disposition — close, with the salvageable piece re-filed

**Decision: CLOSE (already closed by the owner, correctly).** The closure is
right and this review concurs; no reopen. The salvageable piece — the
internal-layer creepage-reduction non-monotonicity — is re-filed as **issue
#1232** with the full disposition, because it is still unfixed on main.

**Evidence.**

- **The 14.0mm base is fabricated, verified.** Agent 2's verification
  (`docs/evidence/2026-08-15-creepage-base-14-verification.md`) traces 14.0 to
  commit `418fab757` (2026-01-07) with no derivation, no clause, no row; it
  appears in no recovered Table 17 row applicable to this board (max 12.5mm at
  ≤1000V; 14.0 exists only at >1000V / material-group-II rows this board
  cannot occupy). The "Independent IEC 60335 reference tables" test was
  byte-identical to the implementation, created in the same commit.
- **19.6 = 14.0 × 1.4 is doubly unsupportable.** An untraceable base times an
  unsourced multiplier. The cited authority REQ-ELEC-04 §3.2 ("Material Group
  IIIb, FR4 CTI 175-249V") self-contradicts: clause 29.2 defines IIIb as
  100<CTI<175 — CTI 175-249 is **IIIa** — and the governing standard merges
  IIIa/IIIb into one column, so the escalation is not a distinction the
  standard makes. (The real lever is group II, CTI ≥400, which would *lower*
  the bar to 5.6mm.)
- **Superseded on main.** PR #1219 (landed 2026-08-15) migrated VoltageClass
  creepage to recovered Table 17/18 SafetyValue lookups keyed by (bracket, PD,
  material group) and retired 14.0 everywhere, including re-pinning
  `router_clearance.rs`'s live table (`HighVoltage => 12.6` now). The
  base×factor structure #1198 operated on is extinct. #1198 was closed by the
  owner 2026-08-15T20:51Z with exactly this rationale.
- **The salvageable piece is the non-monotonicity floor, still unfixed.**
  `if layer_internal && result > 0.5 { result *= 0.30 }` remains in three live
  sites: `router_clearance.rs:537` (the always-on routed-copper gate),
  `temper-orchestration/src/clearance.rs:489`, and `drc_oracle.rs:413`. The
  `> 0.5` threshold has no citation anywhere; for every result in (0.5, 1.667)
  the reduced value lands *below* the unreduced 0.5mm — smaller output from
  larger input. It is currently **dormant** post-#1219 (every pair's max
  candidate is ≥1.9 before reduction, so the cliff cannot fire) but becomes
  live the moment any candidate lands in (0.5, 1.667). #1198 already proved the
  floor `(result * 0.30).max(0.5)` conservative-only across a 15,552-case
  exhaustive sweep (256 lower → 0 lower; 9720 higher, 5832 equal) — that
  evidence is cited in #1232, which also requires the repo's re-pin discipline
  (fix first, exhaustive conservative-only proof against the **current**
  post-#1219 table, separate re-pin commit, both sides of the differential
  test moving together).
- **#1198's METHOD is the lasting contribution.** Exhaustive sweep,
  conservative-only proof, separate re-pin commit — already applied properly by
  #1219's migration (differential tests pin the new table against the pyclass),
  and re-required by #1232.

**Actions taken:** verified the closure; commented on #1198 with the salvage
disposition; filed #1232 (non-monotonicity floor) with the evidence trail.
**Not taken (deliberately):** no value change to the reduction thresholds —
0.30 and 0.5 keep their values; the floor is a structure change for a dormant
defect and belongs in its own attributed PR (#1232).

---

## C. IPC-2221 bracket table — UNSOURCED label stands, and is now VERIFIED-MISLABELED

**Decision: ACCEPT the UNSOURCED label — and upgrade it.** Cross-validation
against a **recovered free copy of IPC-2221 (1998) Table 6-1** proves the
consolidated bracket table's values appear in **no column of the real table at
any row**. The table is not merely unsourced; it is mislabeled as IPC-2221.
The values are **not corrected** in this changeset — see the risk-direction
argument below — and the recovery route is documented for the future
attributed re-sourcing decision.

**Obtainability — YES, the real table is obtainable (and was obtained).**
IPC-2221B (2012, current) is paywalled, but the **1998 first edition is freely
available**: a full-document copy was downloaded from
`https://tinymicros.com/mediawiki/images/1/15/IPC-2221.pdf` and its Table 6-1
(§6.3, p.39) read directly. Seven independent secondary reproductions
(smpspowersupply.com, philipmcgaw.com, magma.ca, protoexpress.com, ema-eda.com,
pcb-tools.cn, cadxservices.com) agree with it to the digit on the shared rows.
The recovered table (transcribed in the appendix below) is the primary text
for any future re-sourcing.

**Cross-validation result (repo table vs the real Table 6-1).** The repo's
consolidated table is
`(0,15,0.13) (16,30,0.25) (31,50,0.50) (51,100,0.80) (101,150,1.25)
(151,170,1.60) (171,250,3.20) (251,300,6.40) (301,600,8.00) (601,1000,12.00)`.
The real IPC-2221 Table 6-1 (columns B1 internal / B2 external-uncoated / B3
external >3050m / B4 external coated / A5-A7 assembly) contains:
- B2 (the natural column for this gate's use): 0.1 / 0.1 / 0.6 / 0.6 / 0.6 /
  1.25 / 1.25 / 1.25 / 2.5, then per-volt formulae above 500V — matches the
  repo table at **zero** rows (repo's 0.5/0.8/1.6/3.2/6.4/8.0/12.0 appear
  nowhere).
- No column has 0.5 @ 31-50, 0.8 @ 51-100, 1.25 @ 101-150, 1.6 @ 151-170,
  3.2 @ 171-250, 6.4 @ 251-300, 8.0 @ 301-600, or 12.0 @ 601-1000.
- The **bracket boundaries** (15/30/50/100/150/170/250/300) are exactly
  IPC-2221's row structure — whoever wrote the table took the boundaries from
  IPC-2221 and the values from elsewhere.
- Closest partial origin found: **IPC-9592B**'s low-voltage spacing (0.13mm for
  V<15V, 0.25mm for 15≤V<30V — both match; 0.1+0.01×V for 30-100V ≈ 0.5-0.8,
  close but not equal). The 8.0/12.0 tail matches nothing recovered. Origin:
  unidentified; "IPC-2221 (simplified)" is a mislabel, not a simplification.

**Risk direction — the error is conservative, not dangerous.** Wherever the
mislabeled table can win the clearance gate's `max()` over candidates
(measured: Mains120V/240V-class pairs above ~250V working voltage, e.g. ipc
8.0 vs the 4.8mm Table-17-based candidate), it **overestimates** the real
IPC-2221 figure (8.0 vs 2.5 at 301-500V; 12.0 vs ~3.0-5.0 at 601-1000V).
Overestimate = conservative. The two rows where it *under*estimates (0.5/0.8
vs the real 0.6/0.6 at 31-100V) are always dominated by the ≥1.9mm
Table-17/18-based candidate in the same `max()`, so they never win — verified
by reading `get_clearance`'s candidate construction, not assumed. Replacing
the table with the real IPC-2221 values would therefore *lower* a live gate's
floor — a weakening change — which is why it is **not done here** and is
instead documented as a separate attributed decision with the recovery route
in the appendix.

**Actions taken:** cross-validated against the recovered primary text; upgraded
the UNSOURCED labels in `_ipc2221_brackets.py` (shared test-data module) and
`creepage_check.py` to VERIFIED-MISLABELED with the risk-direction note; the
recovered Table 6-1 is transcribed in the appendix below for the future
re-sourcing decision.

---

## Appendix — recovered IPC-2221 (1998) Table 6-1, §6.3 "Electrical Clearance"

Source: `https://tinymicros.com/mediawiki/images/1/15/IPC-2221.pdf` (free full
copy of IPC-2221, first edition 1998), Table 6-1 "Electrical Conductor
Spacing", transcribed 2026-08-15 from the PDF text layer; corroborated by
seven independent secondary reproductions (smpspowersupply.com,
philipmcgaw.com, magma.ca/~legg, protoexpress.com, ema-eda.com, pcb-tools.cn,
cadxservices.com). IPC-2221 gives fixed values only up to 500V; above 500V it
specifies per-volt additions (B1: 0.0025mm/V, B2: 0.005mm/V, B3: 0.025mm/V,
B4/A5/A6/A7: 0.00305mm/V).

| V between conductors (DC or AC peak) | B1 internal (mm) | B2 external uncoated (mm) | B3 external, >3050m (mm) | B4 external, permanent polymer coating (mm) | A5 assembly conformal coated (mm) | A6 assembly component leads coated (mm) | A7 assembly component leads, uncoated? (mm) |
|---|---|---|---|---|---|---|---|
| 0–15 | 0.05 | 0.1 | 0.1 | 0.05 | 0.13 | 0.13 | 0.13 |
| 16–30 | 0.05 | 0.1 | 0.1 | 0.05 | 0.13 | 0.25 | 0.13 |
| 31–50 | 0.1 | 0.6 | 0.6 | 0.13 | 0.13 | 0.4 | 0.13 |
| 51–100 | 0.1 | 0.6 | 1.5 | 0.13 | 0.13 | 0.5 | 0.13 |
| 101–150 | 0.2 | 0.6 | 3.2 | 0.4 | 0.4 | 0.8 | 0.4 |
| 151–170 | 0.2 | 1.25 | 3.2 | 0.4 | 0.4 | 0.8 | 0.4 |
| 171–250 | 0.2 | 1.25 | 6.4 | 0.4 | 0.4 | 0.8 | 0.4 |
| 251–300 | 0.2 | 1.25 | 12.5 | 0.4 | 0.4 | 0.8 | 0.8 |
| 301–500 | 0.25 | 2.5 | 12.5 | 0.8 | 0.8 | 1.5 | 0.8 |
| >500 | 0.0025 mm/V | 0.005 mm/V | 0.025 mm/V | 0.00305 mm/V | 0.00305 mm/V | 0.00305 mm/V | 0.00305 mm/V |

Column-name caveat: B1-B4/A5-A7 labels follow the seven secondary reproductions
(which agree with each other and with the PDF's own text layout; the PDF's
extracted text layer labels the columns "Bare Board B1 B2 / Assembly B3 B4 A5
A6 A7"). Values are the primary content and are confirmed consistent across
all sources. A7's precise definition ("uncoated" vs "with solder mask") is
ambiguous in the OCR layer; do not rely on A7 for a re-sourcing decision
without the printed page — B2 (external uncoated) is unambiguous and is the
column a clearance-gate re-sourcing should use.

This is a *recovered* table for cross-validation and future re-sourcing — the
repo's live bracket table is deliberately NOT replaced with it in this
changeset (weakening direction, see §C).
