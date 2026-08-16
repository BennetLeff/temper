<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 (origin/fix/board-schematic-resync,
     the same baseline PR #1146/#1151 used), dirty=false except this file. Own git worktree
     (.claude/worktrees/agent-a374c69e35366ad12, branch docs/t2-aperture-ct-replacement-determination),
     never the main checkout. No pcb/temper.kicad_pcb or elec/src/** file touched -- `git status
     --porcelain` shows only this document under version control; `git grep -l "^<<<<<<< "` empty.
     All fetched vendor PDFs saved under this session's scratchpad
     (/tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/pdfs/),
     each retrieved via `curl` with a browser user-agent (vendor sites 403'd WebFetch's default UA
     this session, matching the environment note) or, where that also 403'd, via WebFetch itself
     (which fetches through a different path and succeeded where direct curl got a bot-challenge
     HTML page) -- retrieval method and a SHA-256 recorded per source in Sec. 5. One WebFetch
     fetch (`lpsr_series.pdf` via the vendor's own URL) silently returned an unrelated Littelfuse
     fuse datasheet instead of the requested LEM document; caught by checking the returned text's
     own title line before trusting any figure from it, then re-fetched successfully via a DigiKey
     mirror of the same LEM document (SHA-256 recorded, Sec. 5) -- flagged here because it is
     exactly the failure mode the task's hard constraints warn about (a plausible-sounding but
     wrong source), and because catching it changed a number this document does not use (a
     web-search-summarized "9.9mm" LPSR creepage figure, superseded below by the true
     manufacturer-drawing figure, 8.26mm). No new part, ratio, or burden value was written into
     elec/src -- every electrical figure below is either quoted from a datasheet or arithmetic
     shown in full. -->

# No off-the-shelf part closes both T2 problems; the closest candidates found close neither in a way that helps this board

## Verdict, up front

**No part found this session meets all four bars simultaneously**: (a) the
functional requirement (current-sensing, ~55-65A trip window, adequate
headroom against saturation), (b) >=12.6mm primary-to-secondary PCB
creepage, (c) a footprint that plausibly places on this board, and (d)
agency-recognised reinforced isolation that actually applies to this
board's real operating conditions (>250-400V working voltage, PD3).
**PR #1151's recommendation stands: do not populate OCP-02 with a
CT-based design now; T1's identical CST3015 creepage defect remains a
separate, standalone decision.**

This document extends #1151's open item (the aperture/donut-primary
mechanism, left "no verified reinforced-insulation certificate... out of
scope") with a session of primary-source part research across two
mechanism classes -- passive donut/aperture current transformers (Talema,
ICE Components, re-checked) and active closed-loop Hall-effect current
transducers (LEM, six product families, not checked in any prior document
on this repo) -- plus one genuinely new, board-general finding that
applies regardless of which part is picked (Sec. 3.3).

**What is new here, not a restatement of #1146/#1151:**

1. A systematic check of LEM's compact closed-loop Hall-effect current
   transducer line (LES/LKSR/LPSR/HO-S/CDSR), which *does* carry genuine,
   verifiable third-party agency recognition (UL 508 File # E189713) and
   an explicit "reinforced insulation" datasheet claim -- unlike every CT
   checked in #1146/#1151, which had none. **Every one of these
   real-certificate parts still measures less PCB creepage than the
   incumbent CST3015's own 9.100mm** (7.7-8.26mm for the compact 20-50A
   family; 12.2mm only on a part built for a different function --
   residual-current/GFCI detection, not phase overcurrent -- and whose UL
   508 listing the datasheet itself states is "Ongoing submission," not
   issued). Certified reinforced isolation and adequate PCB creepage are
   not the same axis, and this session found no compact part where both
   land above 12.6mm at once.
2. **A structural finding independent of any single part's creepage
   number**: LEM's own "reinforced insulation" claim for this whole
   product class is itself conditioned on "used in a pollution degree 2
   environment or better" (printed verbatim in every datasheet checked,
   Sec. 2). This board's own prior determination
   (`docs/evidence/2026-08-12-pollution-degree-resolution.md`) is that
   the PD2 compartment prerequisite is unmet and **PD3 governs the
   as-built board**. So even a hypothetical LEM part with enough raw
   creepage would not actually carry a *valid* reinforced-insulation
   claim on this specific board -- the same "the certificate doesn't
   cover this board's real conditions" problem CST3015 has (#1146 Sec.
   2), reached here from the opposite direction (a real certificate, but
   one whose own stated precondition this board fails).
3. **The aperture/no-primary-pad mechanism's standards reasoning holds**
   under this repo's own treatment (Sec. 4) -- but no *certified* part
   using it was found, confirming rather than overturning #1151 Sec. 6's
   open gap.
4. **Placement**: not independently re-run this session (Sec. 6 explains
   why), but PR #1151's own already-executed courtyard-area sweep
   (0-`fixed_copper`, courtyard-only, T2/C37/R65 jointly free, 165 other
   components frozen) already tested synthetic courtyards from 90% down
   to 25% *linear* scale (6.25% of CST3015's real area, 45.7mm²) and
   found every tier infeasible. Every real candidate's footprint measured
   this session falls inside that already-tested, already-infeasible
   range (Sec. 6). Placement is very plausibly still blocked even for a
   part with adequate creepage, independent of which part is chosen --
   though this is inference from a prior, comparable-size sweep, not a
   fresh run against this session's specific candidates.

---

## 1. What OCP-02 actually needs (elec/src, read this session)

`SecondaryOCPComparator` (`elec/src/modules.ato:2580-2848`), OCP-02's real
module, not a stale design doc:

- **Trip window**: 55-65A, 60A nominal target
  (`docs/FUNCTIONAL_TEST_CRITERIA.md:48-49`, this project's own internal
  acceptance line, no external clause cited).
- **Current design**: `ct = new CST3015_100E` (the same incumbent part as
  T1, 1:100, 88A sensed) + `r_burden = 4.12ohm` + REF2025 2.5V precision
  reference + TLV3201 comparator. `I_trip = N * V_ref / R_burden = 100 *
  2.5V / 4.12ohm = 60.68A` nominal, **59.31-62.10A worst-case**, inside the
  window with 4.31A/2.90A margin to the low/high edges.
- **The 1:100 ratio is not architecturally load-bearing.** It is one term
  in a burden-resistor equation, not a fixed requirement -- the module's
  own docstring works this exact substitution for T1 already (a 1:1000
  aperture-primary part: `R_burden_new = 2.5V / (50A/1000) = 49.85ohm`,
  "a single resistor value change... reduces continuous burden
  dissipation," `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`
  Sec. 3.5). The same substitution is available for OCP-02 at any ratio: a
  1:1000 part at the 60A trip point needs `R_burden = 2.5V / 0.06A =
  41.67ohm` (nearest standard values bracket this: E96 41.2 -> 60.55A,
  E96 42.2 -> 59.24A -- both land inside the 55-65A window with margin
  comparable to the incumbent's, by the same arithmetic pattern already
  used and verified for the current design). **Confirms the task's own
  instruction: 1:100 is not a hard requirement to search against.**
- **Sensed-current headroom is real, not optional.** OCP-01's own
  docstring explains *why* CST2010 (47A sensed) was rejected for a 50.1A
  trip: below-rating sensing risks core saturation and a late/missed trip
  -- the exact failure mode a replacement must not reintroduce. The
  incumbent's own margin at OCP-02's trip ceiling is `88A / 62.10A =
  1.42x`. This document uses that as the working bar for "meaningfully
  above trip," not an invented number.
- **Not itself IEC 60335-1-mandated.** #1151 Sec. 7 already established
  this (no clause found requiring redundant overcurrent sensing) and
  Sec. 7 of this document does not reopen it -- carried forward, not
  re-derived.

---

## 2. Part search: two mechanism classes, six new families

### 2.1 Passive donut/aperture current transformers (Talema, ICE) -- reconfirmed, not improved

`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` Sec. 3.5 already
measured ICE CT07-1000's mechanical drawing (secondary pins clustered
7.62x7.62mm around a 9.20mm bore, no primary PCB pad at all) and found no
third-party reinforced-insulation certificate. This session re-checked
Talema's own **published Product Approvals page**
(`talema.com/product-approvals/`, fetched this session) directly, rather
than relying on datasheet marketing language: it lists real UL/DEKRA/CB
certificates, but **every one of them is scoped to Talema's power
isolating-transformer families (EN/IEC 61558-1/-2-4/-2-6, "to 3000VA")**
-- nothing on that page covers a current-sense transformer, and nothing
mentions VDE, ENEC, or IEC 60335-1/60664-1. Talema's own **AS series**
datasheet (`talema.com/wp-content/uploads/datasheets/AS.pdf`, fetched via
`curl`, SHA-256 in Sec. 5), the donut/wire-through-hole family with
primary current ratings to 80A (AS-407, 1:500, 80A), states only "Meets
VDE norms" and "UL94V-0 recognized materials" -- no certificate number, no
reinforced-insulation claim, no creepage figure in mm. This is the exact
gap #1146 Sec. 2.1 already named for CST3015 (a datasheet claim with no
agency file behind it), reproduced here for the other obvious donut-CT
manufacturer. **No update to #1151's verdict on this mechanism class.**

### 2.2 LEM closed-loop Hall-effect current transducers -- a new mechanism class, checked here for the first time on this repo

Not evaluated in any prior document on this repo. LEM's compact,
PCB-mount, closed-loop Hall-effect family (LES/LKSR/LPSR, all sharing one
physical package; HO-S, a larger sibling; CDSR, a residual-current
variant) is the one current-sensing product line found this session with
a **real, checkable third-party file number and an explicit "reinforced
insulation" claim** on the primary datasheet itself -- worth checking on
its own merits even though it is not a transformer in the CST3015 sense
(active Hall element + amplifier, needs a 5V supply, outputs an analog
voltage or, for LPSR, a factory-calibrated digital overcurrent flag).

All figures below are **MEASURED** (read directly off the manufacturer's
own dimensioned drawing/table, method shown) or **CITED-PRIMARY**
(datasheet text quoted), never inferred, per PDFs fetched and hashed this
session (Sec. 5).

| Part family | I_PN options | Creepage `dCp` (pri-sec) | Certification | Notes |
|---|---|---|---|---|
| **LES** (voltage-out only) | 6/15/25/50A | **7.7mm** (`les_series.pdf` p.17, "Insulation distances" drawing, MEASURED) | UL 508 File # E189713 Vol 2 Sec 11 (real, CITED-PRIMARY); "Reinforced insulation... 300V CAT III, PD2" per IEC 61800-5-1 | Package 21.91 x 20.3mm body |
| **LKSR** (voltage-out, +Vref pin) | 6/15/25/50A | **8.26mm** (`lksr_series.pdf` p.19 "dCI/dCp" table, MEASURED) | Same UL 508 file; "Reinforced insulation... 600V CAT III, PD2" | Same package family |
| **LPSR** (voltage-out + built-in overcurrent-detect pin) | 6/15/25/50A | **8.26mm** (`lpsr_series.pdf` p.19, same table, MEASURED) | Same UL 508 file; "Reinforced insulation... 600V CAT III, PD2" | See Sec. 2.3 -- functionally the closest match found |
| **HO-S** (bus-bar aperture, larger) | 50/100/150/200/240/250A | **>8mm** (datasheet's own printed feature line and table minimum, CITED-PRIMARY) | UL 508 File # E189713 Vol 2 Sec 5; "Reinforced insulation... CAT III PD2" per IEC 61800-5-1 | Bigger package, bigger current range, still short of 12.6mm |
| **CDSR 0.07-TPDT** (residual-current, wrong function) | 32A carry (mA-level trip) | **12.2mm** (datasheet Insulation Coordination table, CITED-PRIMARY, closest of anything found) | UL 508: **"Ongoing submission"** (not issued); "Reinforced insulation... IEC 60664-1 or IEC 61010-1, CAT III, PD2" | Senses residual/leakage current (IEC 62752/62955, EV-charging RCD use), not phase overcurrent -- wrong function for OCP-02 even before the certification-status and 0.4mm shortfall are counted |

**None clears 12.6mm.** The closest (CDSR, 12.2mm) is disqualified twice
over independent of creepage: it measures ground-fault leakage current in
mA, not the tens-of-amps phase overcurrent OCP-02 needs, and its own
datasheet states its UL 508 listing is still pending, not a live file.

### 2.3 LPSR is the closest *functional* match found, and it is worth stating why, even though it does not solve Problem B

`LPSR 15-NP`'s built-in overcurrent-detection comparator trips at "4.1 x
IP_N" (CITED-PRIMARY, headline datasheet feature), with a stated
**detection-threshold band of 4.02-4.17 x IP_N** (datasheet table). At
IP_N = 15A: **60.3-62.55A** -- inside OCP-02's 55-65A window, with margin
(4.7A low-side, 2.45A high-side) in the same order as the incumbent's own
worst-case band. This is a fixed-ratio, factory-calibrated digital
overcurrent flag on a CMOS pin (`OCD`), needing **no burden resistor, no
external voltage reference, and no comparator IC** -- electrically simpler
than the current CT + R_burden + REF2025 + TLV3201 chain. **This is
reported as a real, notable functional near-match, not a recommendation**:
its creepage (8.26mm) is *worse* than the incumbent's 9.1mm, so adopting
it would trade a working electrical simplification for a larger creepage
shortfall (4.34mm vs. 3.5mm) -- the opposite of what this task needs.

---

## 3. Why "reinforced insulation" on the LEM datasheets does not close the gap

### 3.1 Raw creepage shortfall (the same axis CST3015 fails on)

Every LEM figure above (7.7-8.26mm compact family, >8mm HO-S) is smaller
than CST3015's own measured 9.100mm (#1146 Sec. 1). A genuinely
third-party-certified part can still have less PCB creepage than an
uncertified one -- certification and creepage are different physical
facts about a part, the same lesson #1146 Sec. 2.2 already drew for a
relay's *internal* barrier vs. the board's *external* pad-to-pad path,
reproduced here for a different component class.

### 3.2 The "PD2 environment or better" precondition -- a new, board-general finding

Every LEM datasheet checked this session (LES, LKSR, LPSR, HO-S, CDSR)
prints, under "Conditions of acceptability" for its UL 508 recognition,
the identical clause (CITED-PRIMARY, quoted verbatim from `les_series.pdf`
p.2, reproduced across every sibling checked):

> "3 - The LES, LESR, LKSR, LPSR, LXS and LXSR Series shall be used in a
> pollution degree 2 environment or better."

and separately states its "reinforced insulation" application-example
rating (per IEC 61800-5-1) as **"CAT III, PD2"** -- not PD3. This board's
own prior, already-committed determination
(`docs/evidence/2026-08-12-pollution-degree-resolution.md`) is that the
PD2 compartment prerequisite (`docs/specs/pd2_compartment_evidence.yaml`)
does not exist and its own gate script fails: **"PD3 governs the as-built
board now."** A LEM part's own reinforced-insulation credential is
therefore not actually valid as installed on this board today, regardless
of its raw mm figure -- the identical "certificate doesn't cover this
board's real conditions" defect #1146 Sec. 2 found for CST3015 (there:
zero certification at all; here: a real certification whose own stated
precondition this board fails). **This is a structural finding about this
board, not about any one part** -- it would apply to any LEM-class part
adopted without first closing the PD2-compartment gap, independent of
which member of the family is chosen.

### 3.3 Working-voltage headroom, checked and found adequate for LKSR/LPSR (a correction to a bad web-search citation, not a new problem)

LES's "reinforced insulation" application example is stated at only 300V
(CAT III, PD2) with a separate, lower "basic insulation" example at 600V
-- if taken at face value this would be a *third* problem (this board's
governing working-voltage band is >250-400V, per
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Table 17, which already
governs T1/T2 per #1146). **Checked directly against LKSR's and LPSR's own
datasheet tables (not assumed to match LES's)**: both print "Reinforced
insulation... 600V CAT III, PD2" -- i.e. their reinforced rating, *if* the
PD2 precondition held, would cover this board's working voltage with
margin. This axis is not what disqualifies LKSR/LPSR; Sec. 3.1 (raw
creepage) and Sec. 3.2 (the PD3-vs-PD2 precondition) are.

---

## 4. Does the aperture/no-primary-pad reasoning hold under this repo's own standards treatment?

**Yes, structurally** -- but it requires the primary conductor to actually
be built as a discrete, routed/secured conductor away from PCB copper, not
a free pass from geometry.

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec. 5.1 states creepage is
measured **"Along Surface"** (the table's own heading) -- consistent with
#1146 Sec. 1's method (`pad_pair_distance`, the shortest copper-to-copper
path along the board). For a part like CST3015 or any LEM part in Sec. 2
above, the primary is a PCB pad soldered at a fixed position relative to
the secondary pads on the same molded body -- the creepage number is an
intrinsic, non-adjustable property of the part. For a true donut/bore part
(ICE CT07/08/10, Talema ASM -- **not** the LEM family in Sec. 2, which
*does* have PCB primary pins despite being "aperture" in the sense of a
built-in bus bar) there is no primary pad at all: the mains conductor is a
wire or bus-bar segment the designer routes through the core's bore. The
distance from that conductor's own surface to the nearest secondary
copper becomes **a board-layout choice**, not a fixed component figure --
the same principle this repo's own DRU already exploits deliberately for
routed isolation slots (`HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec. 6.1:
"Effective creepage = 2 x slot width + surface across slot," a real
in-repo mechanism for stretching a physical distance into a longer
creepage path).

**What this implies for routing/securing the primary, stated concretely,
not left abstract**: the AC line at this splice point could no longer be
continuous PCB copper through the CT's footprint region -- it would need
to become a discrete conductor (insulated wire or a formed bus-bar tab)
threaded through the core's bore, mechanically secured (so tolerance,
vibration, and thermal cycling cannot let it drift closer to the secondary
pins than the design intends), and kept clear of the secondary pin cluster
and any other LV copper by >=12.6mm measured along that actual physical
path -- not merely a straight-line board-layout intent. This is real,
non-trivial mechanical/assembly engineering (a discrete-conductor
transition, a strain-relief/secure-routing detail, and a follow-up
`kicad-cli`-class DRC-equivalent measurement once built), which is exactly
why #1151 Sec. 6 called it "an `elec/`+mechanical redesign" rather than a
drop-in swap. **This document confirms the reasoning is sound; it does not
make it free, and it still requires a certified part to be worth
building** -- which Sec. 2.1 above re-confirms does not exist yet for this
mechanism.

---

## 5. Sources (fetched this session; SHA-256 + retrieval method)

| Source | URL | Method | SHA-256 |
|---|---|---|---|
| Talema Product Approvals | `talema.com/product-approvals/` | WebFetch | (HTML page, not hashed as a file; content quoted verbatim in Sec. 2.1) |
| Talema AS series datasheet | `talema.com/wp-content/uploads/datasheets/AS.pdf` | `curl` w/ browser UA | `108718f9c5895fcd21cb51a417e70927d75e9380b42350f3775bc143e2856ae6` |
| LEM LES series datasheet | `lem.com/sites/default/files/products_datasheets/les_series.pdf` | WebFetch (direct `curl` 403'd) | `2207096ea13d79d9dadd27a4801093cc2f9fe913ee990a885a7c31573490eb53` |
| LEM LKSR series datasheet | mirrored via `media.digikey.com/pdf/Data Sheets/LEM USA PDFs/lksr_series.pdf` (vendor URL 403'd `curl`) | `curl` w/ browser UA, DigiKey mirror | `37e41c17fca74899a2807334a01e9d7a0c77fb5550216d25720c218d82e42e85` |
| LEM LPSR series datasheet | mirrored via `media.digikey.com/pdf/Data Sheets/LEM USA PDFs/lpsr_series.pdf` (vendor URL's own WebFetch returned an unrelated Littelfuse fuse PDF -- caught by checking the returned title, not used) | `curl` w/ browser UA, DigiKey mirror | `c3829fb8fd27aad9763570adfd46f37a8789d2df36e1f6d12fa3fd9fce758618` |
| LEM HO-S series datasheet | `lem.com/sites/default/files/products_datasheets/ho-50__250-s_v7.pdf` | `curl` w/ browser UA | `da224a4f922b7d3b4a953928144d2ae836ab6ca29da8cd903eadc1e97727cfae` |
| LEM CDSR 0.07-TPDT datasheet | `lem.com/sites/default/files/products_datasheets/cdsr_0_07-tpdt.pdf` | `curl` w/ browser UA (encrypted PDF, permissions allow text extraction) | `e60a4d765c7aebb7e7533a22719efcf30f61b814e9a76b53681b25d96dcfaed8` |
| In-repo | `elec/src/modules.ato`, `elec/src/constraints.ato`, `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`, `docs/FUNCTIONAL_TEST_CRITERIA.md`, `docs/evidence/2026-08-12-pollution-degree-resolution.md`, `docs/evidence/2026-08-13-cst3015-reinforced-isolation-capability.md` (PR #1146), `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` (PR #1151), `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` | Read from git history at commit `ac5e62f8c` / `bfff1f4bb` (not yet merged to this worktree's baseline) and from this worktree | n/a, in-repo |

Every dimensioned-drawing figure (LES/LKSR/LPSR `dCp`/`dCI`) was read from
a 300dpi render of the datasheet's own page, not OCR'd or estimated --
`pdftoppm -png -r 300` then read directly, the same method #1151 used for
ICE CT07's bore dimension.

---

## 6. Placement: not independently re-run this session, and why

No candidate in Sec. 2 clears the creepage + valid-certification bar, so
this document does not have a part worth spending a `temper-placer
repair-unplaced` run on -- per the task's own framing, "a smaller part
that still cannot be placed has not solved Problem A," but a part that
fails Problem B first was never going to solve *either* problem, and a
placement result for it would not change this document's verdict.

**For completeness, the placement question was not left unaddressed**:
PR #1151 Sec. 2 (Option 0) already ran exactly this kind of test --
courtyard-only (no `fixed_copper`, no `domain_clearance`), T2/C37/R65
jointly free, the other 165 components frozen -- across synthetic
courtyards at 90%, 75%, 50%, 35%, and 25% of CST3015's real *linear*
dimensions (25% linear = 6.25% of its real 761mm² area, 45.7mm²), and
found **every tier infeasible**, 828-930ms each. The compact LEM package
measured this session (21.91 x 20.3mm case envelope; a standing/SIP-style
part, so its actual PCB footprint is smaller than that envelope, closer to
21.91mm along the pin row by a single-digit-mm depth -- not independently
extracted to an exact courtyard box this session) falls, on any reasonable
reading of that envelope, inside the 90%-to-25%-linear range #1151 already
tested and found UNSAT jointly with C37/R65 among the same 165 frozen
components. **This is inference from a directly comparable prior sweep,
not a fresh measurement of this session's specific candidates** -- flagged
as such, not presented as an independently re-verified placement result.
Given none of Sec. 2's candidates clear Problem B, re-running the solver
to nail this down more precisely would not change the recommendation
below, and this document does not spend the disk/time budget on it (the
environment note this session: 91% disk, `git stash` blocked, prior
sessions already filled the disk running placer solves across many
worktrees).

---

## 7. What this changes, and what it doesn't

- **#1151's verdict is not overturned.** Option 5 (do not populate
  OCP-02 with a CT-based design now) remains the recommendation; Option 4
  (aperture/donut CT mechanism, T1+T2 jointly) remains the only
  technically plausible long-term path, still blocked on the same open
  gap #1151 already named (no verified reinforced-insulation certificate
  for a no-primary-pad part) -- this session searched harder for that
  certificate (a new mechanism class, LEM, plus a re-check of Talema's own
  approvals page) and did not find it.
- **New for this document**: LEM's closed-loop Hall-effect family is a
  mechanism nobody had checked on this repo before. It is close on
  function (LPSR's built-in overcurrent detector lands almost exactly in
  OCP-02's trip window) but not on creepage, and its real certification
  turns out to be conditioned on the same PD2-environment precondition
  this board's own prior work already found unmet -- a board-general
  finding, not specific to LEM, that would need to be closed (a real,
  inspected PD2 compartment) before *any* PD2-conditioned reinforced-
  insulation part's certificate could be trusted on this board, separate
  from and in addition to whatever raw creepage number that part has.
- **Not established here** (explicit, per the task's evidentiary bar): no
  exhaustive search of every current-transducer manufacturer on Earth was
  performed -- Sec. 2 covers the families most structurally relevant
  (passive donut CT: Talema, ICE, re-checked; active closed-loop Hall:
  LEM, six families, new). A manufacturer not checked here (e.g.
  Vacuumschmelze's metering-grade toroidal CTs, briefly searched but not
  datasheet-verified this session; Sensitec, Melexis, or other Hall-IC
  vendors, not checked at all) could in principle carry a part this
  session did not find -- this document reports what was found and
  measured, not a proof that nothing exists anywhere.
