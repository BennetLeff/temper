<!-- provenance: commit=096eb71a8865575e74f00f8e9b3104a76d393a48 dirty=false -->

> **SUPERSEDED (C6 finding only):** this document's §4.1 verdict that
> TDK/EPCOS `B81123C1222M000` "PASSES 12.6mm, comfortably" is a **false
> solve** — the worst-case lead-spacing tolerance (15.00mm ±0.4mm) puts the
> achievable edge-to-edge gap at 12.2mm, below the 12.6mm requirement. See
> `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` §2.1 for the
> corrected analysis. All other findings in this document (K2/K3, U3, U7)
> are unaffected.

# PD3 (12.6mm) part-selection survey: C6, K2/K3, U3, U7 — real candidates fetched, not assumed

Base commit `096eb71a` (`origin/main`, `fix(drc): coating/courtyard/RULE-1/creepage
fail-open closures (slice 5 of 8)`, PR #443). Branch
`docs/pd3-creepage-part-selection`, created fresh from `origin/main` per this
task's hard rule (not from any local worktree's advanced branch). This is a
**research/reporting pass only** — no design file, footprint, constant, or
netclass is touched. `git status --short` is clean apart from this file
throughout.

## 0. Target provenance — what 12.6mm actually is on this base commit, stated precisely

This matters because the task's own framing treats PD3/12.6mm as already
established, and the record needs to say plainly where that stands **on the
commit this document is measured against**, not on the commit any single
prior evidence file happened to be written against.

**Directly checked, this session, on this base commit:**

- `docs/ENVIRONMENTAL_SPEC.md` §3 still declares **`Pollution Degree | PD2`**
  (line 45), dated 2025-12-17 — not PD3.
- `scripts/check_isolation_keepout.py:173` still enforces
  **`MIN_BARRIER_WIDTH_MM = 8.0`** — the PD2 figure — as the live gate.
- `elec/src/constraints.ato:36,84,96` still declares **`creepage = 8.0mm`** /
  **`min_creepage = 8.0mm`** — the `.ato` source the design actually compiles
  from has not moved off 8.0mm at all (not even to the intermediate 10.0mm
  figure `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`
  derived for the 400V Table 16 row).
- `elec/src/modules.ato`'s own `BusDischarge` docstring (the code comment
  covering K2/K3) already writes both numbers side by side: *"fails the
  8.0/12.6mm coil<->contact creepage requirement (3.50mm edge-to-edge
  measured)"* — i.e. the source tree itself is currently straddling both
  values, not settled on either.

**A substantial, real PD2->PD3 determination exists in this repository's
history** (`docs/evidence/2026-07-28-pd3-retarget-relay.md`,
`docs/evidence/2026-07-28-isolator-sourcing-brief.md`'s successors, and a
long commit chain: `31acc185`, `ea22a58c`, `1c1b6d32`, `5ef309d8`, `c58c94d8`,
etc.) — **but every one of those commits is confirmed, this session
(`git merge-base --is-ancestor <sha> HEAD`), to be absent from `origin/main`
at this base commit.** They live on `origin/docs/methodology-loop-discipline`,
`origin/feat/provable-safety-place-and-route`, and closed PR #382 (never
merged). Two currently **open** PRs corroborate this is a known, tracked,
unresolved gap rather than an oversight:

- **PR #455** (`docs(evidence): insulation tier audit -- REINFORCED
  confirmed, U3/U7 blocker stands`), open, states directly: *"several
  orphaned branches contain a prior PD2->PD3 pollution-degree determination
  that would raise the reinforced figure from 10.0mm to 12.6mm ... never
  merged to `main`, not evaluated or acted on here."*
- **PR #457** (`feat(gates): creepage/clearance SSOT-drift gate`), open,
  documents the same fact from the constants-drift angle: even on the
  feature branch that *did* retarget `MIN_BARRIER_WIDTH_MM` and
  `HV_CREEPAGE_PD3_MM` to 12.6, `elec/src/constraints.ato` was "never
  touched by any commit" and still reads 8.0.

**None of this changes what this document does.** Per the task's explicit
instruction, 12.6mm is evaluated throughout as the target, and nothing below
proposes moving it down. This section exists so the reader knows precisely
which number is checked-in-and-enforced today (8.0mm, PD2) versus which
number is the subject of this survey (12.6mm, PD3, real but not yet landed
on `main`) — conflating the two is exactly the failure mode
`docs/solutions/best-practices/measure-the-target-before-resolving-a-fork-2026-07-29.md`
(already in this repo) documents from a sibling incident.

## 1. Verdict up front

**Mixed, and the mix does not split the way the working hypothesis
predicted.** Real, stocked, agency-certified parts reaching >=12.6mm
were found for two of the four named blockers (**C6**, the Y-capacitor, and
**K2/K3**, the discharge relays) — the hypothesis's own primary target. The
two blockers that remain unreachable by part selection are **U3** (the
zero-cross optocoupler) and **U7** (the isolated gate driver), for reasons
that have nothing to do with relay/DC-break physics: no mainstream optocoupler
or gate-driver **package family**, certified or not, was found reaching
12.6mm at all.

| Ref | Current (MEASURED, this session) | >=12.6mm candidate found? | Verdict |
|---|---:|---|---|
| C6 (Y-cap) | 8.000mm | **Yes** — TDK/EPCOS `B81123C1222M000`, 15.00mm lead spacing, Y1/500VAC, Active | **PASS, with caveats on pad diameter (below)** |
| K2/K3 (discharge relay) | 3.825mm (incumbent G5LE-1) | **Yes** — TE Schrack `RT114012` (13.820mm) / `RT314012` (12.760mm), reinforced 10/10mm per IEC 60335-1 | **PASS, but the margin at the RM5mm variant is razor-thin (0.160mm)** |
| U3 (ZCD opto) | 8.560mm (already-landed H11L1TVM fix) | **No** — the H11L1 family's own widest lead form (0.4in/10.16mm) is exhausted; no wider-body reinforced-isolation optocoupler family was found | **FAIL — same-die and cross-family search both exhausted** |
| U7 (gate driver) | 8.100mm (already-landed HV/ISOLATION land pattern) | **No** — TI's own best land pattern for this die is 8.1mm; TI's other reinforced parts checked cap near 8.5mm; the one part found claiming >15mm creepage has every agency certification listed "Pending," not granted | **FAIL — disqualified by the task's own no-fabricated-certification rule** |

**Overall: PD3 is not reachable by part selection alone on this floorplan**
— the hypothesis's bottom-line conclusion survives — **but not for the
reason given in the hypothesis.** The relay is not the blocker; a real
relay exists. U3 and U7 are the blockers, and they fail for a durable,
industry-wide reason (packaged optocouplers and gate-driver ICs do not
ship in >=12.6mm-creepage land patterns as a category) that no amount of
relay research would have surfaced.

## 2. Method

Every "current" and "candidate" spacing below is **MEASURED** this session
by parsing the real `.kicad_mod` S-expression pad geometry (position, size,
shape) and computing the straight-line edge-to-edge distance between the
closest HV-side and SELV-side pad in the governing pair:

```
edge-to-edge = centre-to-centre(pad_a, pad_b) - r_a(direction) - r_b(direction)
```

where `r(direction)` is the pad's elliptical radius toward the other pad
(reduces to `size/2` for the axis-aligned cases that dominate here). This
reproduces every already-committed figure in this repo exactly
(U7 = 8.100mm, U3 = 8.560mm, Finder 40.52 = 5.300mm — see §3), which is the
same governing-pair method `docs/evidence/2026-07-28-pd3-retarget-relay.md`
used, so figures from that document and this one are directly comparable.
Script: `/tmp/.../measure/measure_pads.py` (ephemeral, not committed —
shown inline for reproduction below). Footprints came from two places, named
per figure: this repo's `pcb/libs/`, or the **stock KiCad 9 footprint
libraries** at `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/`
(same convention as `2026-07-28-isolator-sourcing-brief.md`).

Reproduction:

```python
import re, math
def parse_pads(path):
    text = open(path).read()
    pads = []
    for m in re.finditer(r'\(pad\s+"?([^"\s]+)"?\s+(\w+)\s+(\w+)', text):
        start = m.start(); depth = 0; i = start
        while i < len(text):
            if text[i] == '(': depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0: break
            i += 1
        block = text[start:i+1]
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)', block)
        size = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)\)', block)
        if at and size:
            pads.append({"name": m.group(1), "x": float(at.group(1)),
                         "y": float(at.group(2)), "w": float(size.group(1)),
                         "h": float(size.group(2))})
    return pads
# edge-to-edge for every (a in group_a, b in group_b) pair, take the minimum.
```

Manufacturer datasheets were fetched live this session (WebFetch/WebSearch,
URLs and fetch context cited per part below) — not reused from memory, not
constructed from a numbering scheme. Distributor stock is a same-session
snapshot; it will drift.

## 3. Current state, per component (re-measured, not assumed)

| Ref | Footprint | Governing pair | c2c | **edge-to-edge** | Source |
|---|---|---|---:|---:|---|
| C6 | `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` (stock KiCad; already landed, `elec/src/modules.ato:958`) | pad 1 <-> pad 2 | 10.000mm | **8.000mm** | MEASURED this session |
| K2/K3 | `Relay_THT:Relay_SPDT_Omron-G5LE-1` (stock KiCad; still declared, `elec/src/modules.ato:1189,1195`) | pad "2" (coil) <-> pad "1" (COM) | 6.325mm | **3.825mm** | MEASURED this session |
| U3 | `Package_DIP:DIP-6_W10.16mm` (stock KiCad; already landed, `elec/src/components.ato:550`) | pad "1" <-> pad "6" | 10.160mm | **8.560mm** | MEASURED this session |
| U7 | `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`, HV/ISOLATION land (already landed) | pad "1" <-> pad "16" | 9.750mm | **8.100mm** | MEASURED this session |
| (for reference) Finder 40.52 DPDT, reverted, footprint still inert in `pcb/libs/temper.pretty/` | — | A1 <-> "12" | 7.500mm | **5.300mm** | MEASURED this session, reproduces `2026-07-28-pd3-retarget-relay.md` exactly |

**K2/K3 note on the 3.50mm vs 3.825mm discrepancy.** `elec/src/modules.ato:1177`'s
own code comment states "3.50mm edge-to-edge measured" for the incumbent
G5LE-1 — the task's framing figure. This session's own re-measurement of the
identical stock footprint gives **3.825mm**, using the elliptical-pad-radius
method in §2 against the real pad geometry (pad "1": 2.5x2.5mm rect at
origin; pad "2": 2.5x2.5mm oval at (-6, 2); both are effectively circular at
that aspect ratio, so `r=1.25mm` each, `6.325 - 1.25 - 1.25 = 3.825`). The
0.325mm gap is plausibly a different pad-projection convention (e.g. a
rectangular-corner treatment instead of an inscribed-circle one) rather than
a different geometry read — **both figures fail 12.6mm by more than 8mm, so
the discrepancy does not affect any conclusion in this document**, but it is
flagged rather than silently reconciled, since I could not find the exact
script that produced 3.50mm to confirm the method difference.

U3, U7, and Finder-40.52 all reproduce the already-committed figures exactly,
which cross-validates the measurement method itself before it is used on new
candidates below.

## 4. C6 — Y-capacitor, mains-derived PE bond

### 4.1 Candidate found: TDK/EPCOS `B81123C1222M000`

**CITED-SECONDARY** (distributor pages; TDK's own datasheet PDF at
`tdk-electronics.tdk.com` returned HTTP 403 to WebFetch this session — flagged
in UNVERIFIED, §8):

| Spec | Value | Source |
|---|---|---|
| Series / dielectric | B81123, metallized polypropylene (PP), "Radial Box" | DigiKey/element14/TTI listings, fetched this session |
| Capacitance | 2200pF +/-20% | matches `y_cap_pe.value = 2.2nF +/- 20%` exactly |
| Class | **Y1** (also X1-rated per some listings) | DigiKey parametric table |
| Rated voltage | **500VAC** | exceeds the 250VAC requirement (`modules.ato:907`) |
| **Lead spacing** | **15.00mm (0.591in)** | DigiKey parametric table, fetched this session |
| Body | 18.00mm L x 7.00mm W, 12.50mm max height | DigiKey parametric table |
| Status / stock | **Active, 198,918 units in stock**, 22-week std. lead time | DigiKey product 679513, fetched this session |

### 4.2 Achievable creepage

Stock KiCad footprint `Capacitor_THT:C_Disc_D18.0mm...` does not exist for
this body; the closest real match by body length/pitch is
`Capacitor_THT:C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_FKP3` (15.00mm pitch, 18mm
body length — matches this part's dimensions). MEASURED against that stock
footprint's own pads (2.4mm dia, oversized for this part's actual lead
gauge, which was not found in any fetched source — see UNVERIFIED):

```
15.000mm (c2c) - 1.2mm - 1.2mm = 12.600mm  (exact, stock 2.4mm pad)
```

**This is a zero-margin pass, structurally identical to K1's already-flagged
8.000mm knife-edge** (`2026-07-28-isolator-sourcing-brief.md` line 191) — the
same box-film-cap family this project already applied a pad-shrink
correction to for the 10.00mm-pitch VY1 (`1.4-1.6mm pad -> 8.6mm` instead of
the stock 2.0mm pad's exact-8.000mm). Applying the identical, already-
established convention here (a realistic 1.4-1.6mm pad for a film cap's
typically <=0.8mm lead, standard THT annular-ring practice) gives:

```
15.000mm - 1.5mm - 1.5mm = 13.500mm   (margin: +0.900mm over 12.6mm)
```

**Verdict: PASSES 12.6mm, comfortably, once the same pad-diameter correction
already applied to C6's own 10mm-pitch predecessor is applied again to this
part's land pattern.** This is the strongest, least-caveated pass of the
four components in this survey.

## 5. K2/K3 — discharge relays

### 5.1 The prior conclusion this section updates

`elec/src/modules.ato:1181-1184` states plainly, as a live code comment:
*"Do not re-introduce Relay_DPDT here without a manufacturer-verified part at
~14.4-14.8mm coil-to-contact pin pitch ... No such part has been found and
verified as of this note."* That figure was derived by doubling the Finder
40.52's 7.5mm pitch — a reasonable order-of-magnitude estimate from the one
data point available at the time, but not a market survey.

### 5.2 Candidates found and verified this session

Both are **TE Connectivity / Schrack**, same family already partially
investigated in `2026-07-28-isolator-sourcing-brief.md` for the (superseded)
8.0mm target — re-verified here specifically against 12.6mm, plus one new
finding (§5.3, DC-break) that document did not have.

| Part | Package (stock KiCad footprint) | Contacts | Governing pad pair | c2c | **edge-to-edge** | Margin vs 12.6mm |
|---|---|---|---|---:|---:|---:|
| `RT114012` | `Relay_SPDT_Schrack-RT1-FormC_RM3.5mm` | 1 Form C (SPDT) | A2 <-> "12" | 16.820mm | **13.820mm** | **+1.220mm** |
| `RT314012` | `Relay_SPDT_Schrack-RT1-FormC_RM5mm` | 1 Form C (SPDT) | A1 <-> "12" | 15.260mm | **12.760mm** | **+0.160mm** |
| `RT424012` | `Relay_DPDT_Schrack-RT2-FormC_RM5mm` | 2 Form C (DPDT) | A1 <-> "12" | 15.260mm | **12.760mm** | **+0.160mm** |

All three: **"5kV/10mm coil-contact, reinforced insulation," "Product in
accordance to IEC60335-1"** — the RT1 and RT2 family datasheets' own cover
features, fetched and read directly this session:

- RT1: `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8`
  (fetched as PDF, read directly — Insulation Data table p.4: "Clearance/creepage
  between contact and coil >=10/10mm," "Initial dielectric strength between
  contact and coil 5000Vrms," Material group IIIa. Approvals p.1: VDE Cert.
  No. 40007571, cULus E214025, cCSAus 1142018.)
- RT2: `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT2%7F1014%7Fpdf%7FEnglish%7FENG_DS_RT2_1014.pdf%7F6-1393243-3`
  (fetched as PDF, read directly — identical Insulation Data figures p.2,
  identical VDE cert number, plus UL E214025, cCSAus 1142018, CQC.)

Coil, both parts, code `012`: **12VDC, operate 8.4V, release 1.2V, 360R
+/-10%, 400mW** — numerically identical to the incumbent G5LE-1's own coil
(`modules.ato:1174`), meaning the existing 100R dropper circuit is unaffected
regardless of which of these three parts is chosen.

**Stock, fetched fresh this session (not reused from the prior brief's
2026-07-28 snapshot):**

| Part | Status | Stock (DigiKey) | Lead time |
|---|---|---:|---|
| RT114012 | Active | **1,224 units** | 14 weeks |
| RT314012 | Active | **7,442 units** | 14 weeks |
| RT424012 | Active | **26,771 units** | 15 weeks |

### 5.3 New finding this session: DC-break capacity at the design's actual current, read directly from the manufacturer's own graph

Every prior pass in this repo's history flagged the relay's DC breaking
capacity at 170-200V as **unresolved** because the manufacturer's own
"Max. DC load breaking capacity" graph is a vector image, reported as "not
extractable" or "not machine-readable" every time it was checked
(`2026-07-28-isolator-sourcing-brief.md` UNVERIFIED list; `modules.ato`'s own
docstring says the same of the G5LE-1). This session rendered both the RT1
and RT2 datasheet pages at 600dpi and cropped/zoomed the graph region
directly (`pdftoppm` + PIL crop, images inspected visually) rather than
relying on text extraction.

**Both RT1's and RT2's own graphs are legible, and both show the same
shape**: DC voltage (y, log, 10-300V) vs DC current (x, log, 0.1-25A). Both
curves are **flat at the chart's own ceiling (~300VDC) from the leftmost
plotted point (0.1A) up to roughly 0.2-0.35A**, then fall steeply. RT2
additionally publishes a second, higher curve for **"2 contacts in series"**
(i.e. both DPDT poles' NC contacts wired in series) sitting well above the
single-contact curve at every current past the flat region.

This design's actual discharge duty is **21.8mA (0.0218A)** — a full decade
below the graphs' own leftmost plotted point (0.1A), squarely inside the
flat/ceiling segment for a **single** contact on both RT1 and RT2. Reading a
monotonically-decreasing breaking-capacity-vs-current curve below its own
plotted range is an extrapolation, not a direct read, and is reported as
such (see UNVERIFIED, §8) — but the qualitative conclusion (lower current
never reduces DC breaking capacity for a resistive load on this contact
technology) is standard relay behavior, not a stretch: **this is a strong,
newly-legible, primary-source indication that a single contact of either
family comfortably clears the 170-200VDC break duty at 21.8mA**, without
needing the "2 contacts in series" DPDT mitigation the Finder 40.52 attempt
was specifically chosen for. This does **not** resolve the open item to
manufacturer-warranted certainty (no manufacturer states a number *at*
21.8mA) but it materially de-risks it beyond every prior pass's "not
extractable" conclusion.

### 5.4 Recommendation, stated plainly

**`RT114012`** is the best of the three found: same reinforced-insulation
rating, same drop-in coil, best distributor stock margin against 12.6mm
(+1.220mm, an order of magnitude more headroom than the RM5mm variants'
+0.160mm), and — because it is SPDT, not DPDT — it is a direct **1-for-1**
replacement for each of K2 and K3 in the existing two-relay topology, with
no topology change and no need for the "2 contacts in series" DC-break
mitigation given §5.3. `RT424012` (DPDT) is flagged as a secondary option
only if a future design specifically wants the "2 contacts in series"
margin or wants to consolidate K2+K3 into one part — neither is needed by
this finding.

**The +0.160mm margin on the RM5mm variants (`RT314012`/`RT424012`) is a
knife-edge, in the same category this repo already treats as "arithmetically
a pass, practically not one"** (K1's exact-8.000mm case,
`2026-07-28-isolator-sourcing-brief.md` line 191) — well inside typical PCB
fab tolerances (pad-position and soldermask registration alone commonly run
+/-0.05-0.1mm per side). `RT114012`'s +1.220mm margin does not have this
problem and is the one to prefer.

## 6. U3 — zero-cross-detect optocoupler

### 6.1 Same-family search: exhausted

`H11L1TVM`'s own datasheet (already fetched and cited in
`2026-07-28-isolator-sourcing-brief.md`) defines the family's full lead-form
ordering table — `S`, `SR2`, `T`, `V`, `TV`, `SV`, `SR2V` — and the package
drawing's *widest* stated lead span is **0.425in (10.80mm)**, barely above
the 0.400in (10.16mm) already in use. Even the absolute widest H11LxM
lead form does not approach 12.6mm; there is no wider variant of this
specific die/pinout to move to.

### 6.2 Cross-family search: no >=12.6mm certified optocoupler package found

Searched this session for wide-body / high-creepage optocoupler families
from Vishay and Broadcom specifically. Vishay's own guidance
(`vishay.com` optocoupler package documentation, fetched via search)
states its **widest** VDE-recognized wide-body option ("Option 6") achieves
creepage/clearance **"greater than 8mm"** — the same ceiling this project's
own H11L1TVM and every other DIP-6/DIP-8 optocoupler surveyed already sits
at. No optocoupler package family (any manufacturer) was found this session
publishing a >=12.6mm creepage figure with a live agency certificate.
**This is reported as a negative result from a bounded search, not as a
market-wide impossibility proof** — see UNVERIFIED, §8.

### 6.3 Elimination path considered (not implemented): protective impedance instead of galvanic isolation

The task's own point 3 asks whether the crossing can be deleted rather than
widened. `elec/domain_manifest.yaml`'s own already-committed OVP-01 section
(lines ~406-450) establishes exactly this precedent for a different signal:
the two `OVP-01` sense dividers bridge the HV half-bus into the PE-bonded
SELV `gnd` domain using **protective impedance** (two independent
current-limiting resistive elements into an earthed reference) — an IEC
60335-1-recognized *alternative* to basic/double/reinforced insulation, not
subject to the 12.6mm creepage figure at all, because it is a different
compliance mechanism, not a smaller insulation gap. `C6` (the Y-capacitor)
is the same technique in reactive form.

**Zero-cross detection is a plausible candidate for the identical
treatment**: it only needs a boolean "AC line near zero volts" edge, which a
resistive protective-impedance divider into the SELV/PE-bonded domain
(same pattern as the OVP-01 dividers, sized for the ZCD's actual signal
requirement rather than the full OVP-01 fault-current budget) could plausibly
deliver without any galvanic isolation component (no U3) at all, provided
the same two-independent-current-limiting-element and touch-current-under-
fault conditions the OVP-01 section's own documented derivation already
satisfies. **This is not implemented, verified, or even schematically
sketched here** — it is a genuine circuit-topology redesign (new signal
path, new fault analysis, likely a comparator or Schmitt-trigger input
stage change on the SELV side), which is a materially different exercise
from "does a wider off-the-shelf part exist," and is flagged as the most
promising avenue for deleting this crossing outright rather than sourcing
around it, consistent with the task's framing.

## 7. U7 — isolated gate driver

### 7.1 Same-die search: exhausted

TI's own SLUSE89C datasheet publishes exactly two land patterns for this
die (already fully cited in `2026-07-28-isolator-sourcing-brief.md`):
IPC-7351 nominal (7.3mm) and "HV/ISOLATION OPTION" (8.1mm, already landed on
this board). There is no third, wider TI-published land pattern for this
specific die.

### 7.2 Cross-part search within TI's reinforced-isolation gate-driver catalog

Checked, this session (TI product pages / search):

| Part | Package | Published creepage/clearance |
|---|---|---:|
| UCC21550 (current) | DWK (SOIC-14, HV option) | 8.1mm (landed) |
| UCC21732 | SOIC-16 (DW) | >8mm ("CLR/CPG > 8mm" per DIN EN IEC 60747-17) |
| UCC5350 | SOIC-8 (DWV, 5kVrms option) | 8.5mm |
| UCC23511 | SO-6 | >8.5mm |

None reach 12.6mm. This is consistent with U3's finding: **standard
IC-package creepage for isolators tops out in the 7-8.5mm band across
multiple TI part numbers and packages**, independent of isolation-voltage
rating — the limit is package geometry (lead pitch on a 300-400mil-class
SOIC/DIP body), not how good the die's own internal barrier is.

### 7.3 One part found claiming >=12.6mm — disqualified by its own datasheet, not by geometry

**Chipanalog `CA-IS3211SCWG`** (Shanghai Chipanalog Microelectronics),
8-pin "super wide body" SOIC (SOIC8-WWB, 6.40 x 14.00mm), datasheet fetched
and read directly this session:
`chipanalog.com/Public/Uploads/uploadfile/files/20250215/CAIS3211SCWGdatasheetVersion1.00en.pdf`.

- **CLR (external clearance): >15mm. CPG (external creepage): >15mm.**
  (S6.6, Insulation Specifications table) — this figure, if certified,
  would clear 12.6mm with room to spare.
- **But S6.7, "Safety-Related Certifications": VDE = "(Pending)", UL =
  "(Pending)", CQC = "(Pending)", TUV = "(Pending)", with every
  Certification Number field literally reading "Pending."** Only a TUV
  "client reference number" (2253313) is populated — a filing reference,
  not a certificate.

**This is exactly the failure mode the task named ("the Isocom lesson"):
a real, plausible-looking creepage figure with no live agency recognition
behind it is not a candidate.** Reported and rejected on that basis, not
adopted. It is also single-channel (drives one FET's gate, split OUTH/OUTL
for turn-on/turn-off resistor separation, not TWO independent channels the
way UCC21550 drives both the half-bridge's high side and low side from one
package) — adopting it would additionally mean two ICs where there is one
today, a real schematic change, not just a footprint swap, even before the
certification problem.

**Verdict: no certified >=12.6mm isolated gate driver was found this
session, in any package, from any manufacturer searched.**

## 8. Overall verdict on the hypothesis

**Refuted for relays specifically; the broader "PD3 unreachable by part
selection" conclusion survives, but for a different, non-relay reason.**

The hypothesis was: *"the required parts may not exist in the necessary
spec combination — especially the relays, needing >=12.6mm coil-to-contact
spacing AND ~170VDC break capability."* Both halves of that specifically
about relays are now answered with real, cited, stocked parts:
`RT114012` reaches 13.820mm (real spacing, +1.220mm margin) and this
session's own graph-reading of the same manufacturer's published DC-load
data indicates (with the extrapolation caveat in §5.3) that the 170-200V/
21.8mA duty sits well inside the flat/maximum region of the relay's own DC
breaking-capacity curve. **The relay is not where PD3 fails on this
floorplan.**

**Where it does fail: U3 and U7, and not for relay-shaped reasons.** No
optocoupler or isolated-gate-driver package family — certified or not,
across TI, Vishay, Broadcom, and one newer Chinese entrant — was found
reaching 12.6mm in this session's search. The one part that does claim it
(Chipanalog CA-IS3211) fails on certification, not geometry, which is a
different and arguably more durable kind of "no" than "the physics doesn't
allow it": it says the *market* has not yet produced a certified part in
this creepage class for this function, not that one is physically
impossible. C6 (the Y-cap) is a clean pass. **Net: PD3 is not reachable by
part selection alone on this floorplan, because of U3 and U7 — the relay
and the Y-cap are not the blockers.**

## 9. What could avoid the crossings outright

Only genuinely evaluated for U3 (§6.3) — a protective-impedance zero-cross
sense, following the already-committed OVP-01 precedent, would delete the
component (and its creepage requirement) rather than needing a wider part,
but this is an unimplemented circuit-topology proposal, not a verified fix.
No equivalent elimination path was found for U7: a gate driver's job is to
cross the barrier with power/logic sufficient to switch a MOSFET gate,
which protective impedance (a high-impedance, current-limited path) cannot
deliver — U7's function is inherently a galvanic-isolation crossing, not a
sense-only one, so "avoid the crossing" is not available to it the way it
might be for U3. C6 and K2/K3 are inherently barrier-crossing by regulatory
purpose (Y-cap PE bond; discharge relay HV contacts) and were not considered
for elimination.

## 10. UNVERIFIED (stated plainly, not guessed past)

- **RT1/RT2 DC breaking capacity AT 21.8mA specifically** is read by
  extending a manufacturer-published curve's own flat segment below its
  lowest plotted point (0.1A) — a reasoned extrapolation from a legible,
  primary-source graph, not a manufacturer-stated number at that exact
  current. No manufacturer contact was made to confirm.
  - **UPDATE, mid-session cross-check**: the currently-open PR #455
    (`docs/evidence/2026-07-30-insulation-tier-audit.md`, not on this base
    commit) is a *tier* audit (reinforced-vs-basic classification), not a
    *voltage-row* audit, and does not address relay DC-break at all — no
    contradiction with this section, just noted as the nearest sibling
    in-flight work.
- **TDK B81123C1222M000's actual lead-wire diameter** was not found in any
  distributor parametric table fetched this session (TDK's own PDF 403'd).
  The 13.500mm figure in §4.2 uses an assumed 1.5mm pad (consistent with
  this project's own prior C6 pad-shrink convention for a similar-class
  lead), not a confirmed lead gauge. The stock-footprint 12.600mm figure
  does not depend on this assumption and is reported as the conservative
  floor.
- **Whether a >=12.6mm certified optocoupler or gate-driver package exists
  somewhere this session's search did not reach** (e.g. non-English
  datasheets, newer 2026 part introductions, or manufacturers not searched:
  Infineon, Skyworks/Silicon Labs, Toshiba, Renesas isolators were not
  individually checked beyond the general web search in §6.2/§7.2). This
  section's negative finding is bounded by what was searched, not a
  market-wide certainty claim.
- **PD3's own final adoption status past this base commit** — §0 establishes
  it is real, extensively derived work, currently orphaned across several
  branches and two open PRs, not yet unified into one merged source of
  truth. Whether/when that lands is out of this document's scope.
- **Whether IEC 60335-1 would actually accept a protective-impedance
  zero-cross sense (§6.3) in place of galvanic isolation** was not verified
  against clause text — the OVP-01 precedent it leans on is itself flagged
  UNVERIFIED-at-primary in `domain_manifest.yaml`'s own comments (paywalled
  standard). This section is a plausible avenue, explicitly not a verified
  fix.
- **RT114012/RT314012/RT424012's exact PCB layout dimension drawing** was
  cross-checked against the KiCad stock footprint (both give consistent
  ~15-17mm spans) but the two were not pixel-registered against each other
  the way `2026-07-28-pd3-retarget-relay.md` did for the Finder 40.52 — the
  agreement is "consistent," not "independently re-derived from the
  manufacturer's raw drawing a second way."

## 11. Sources (fetched this session)

- TE Connectivity / Schrack RT1, `ENG_DS_RT1_0718.pdf` (also refetched as a
  2025-06-20 Rev.3 reissue under the same DocId path) —
  `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8`
- TE Connectivity / Schrack RT2 DC and AC, 10-2023 Rev.3 —
  `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT2%7F1014%7Fpdf%7FEnglish%7FENG_DS_RT2_1014.pdf%7F6-1393243-3`
- DigiKey product pages, fetched this session: RT114012 (1128623), RT314012
  (1128622), RT424012 (1095291), B81123C1222M000 (679513)
- TDK/EPCOS B81123 family, existence and parametrics confirmed via DigiKey
  and search snippets (TDK's own PDF returned HTTP 403 to WebFetch)
- Chipanalog `CA-IS3211SCWG` datasheet v1.00 —
  `https://www.chipanalog.com/Public/Uploads/uploadfile/files/20250215/CAIS3211SCWGdatasheetVersion1.00en.pdf`
- TI product pages/search for UCC21732, UCC5350, UCC23511 (creepage figures
  as published in each part's own datasheet, per search-result extraction)
- Vishay optocoupler package guidance (searched; "Option 6" wide-body >8mm
  figure per Vishay's own published package documentation)
- In-repo: `elec/domain_manifest.yaml`, `elec/src/modules.ato`,
  `elec/src/components.ato`, `docs/ENVIRONMENTAL_SPEC.md`,
  `scripts/check_isolation_keepout.py`, `elec/src/constraints.ato`,
  `docs/evidence/2026-07-28-pd3-retarget-relay.md`,
  `docs/evidence/2026-07-28-isolator-sourcing-brief.md`,
  `docs/evidence/2026-07-28-relay-board-resync-decision.md`,
  `docs/solutions/best-practices/measure-the-target-before-resolving-a-fork-2026-07-29.md`
- `gh pr view 382/455/457` — open/closed PR states and bodies, this session

## 12. Hard-constraint compliance

- **No design file, constant, footprint, or netclass modified.** Only this
  document was written; `git status --short` clean apart from it.
- **12.6mm never proposed downward.** Every verdict above is stated against
  12.6mm as given; §0's provenance note documents what is *currently
  enforced* (8.0mm) without recommending it as sufficient.
- **No relay/circuit change to `discharge` proposed or implied to be
  fail-safe-breaking.** §5's recommendation is a same-topology,
  same-coil-spec 1-for-1 part substitution (SPDT for SPDT); the existing
  fail-safe mechanism (energized coils hold NC open; power loss closes NC,
  engaging discharge with no MCU involvement) is unchanged by substituting
  which SPDT relay occupies that role.
- **No fabricated or pattern-guessed MPN.** Every part number in this
  document was read from a fetched manufacturer datasheet or distributor
  product page this session; the Chipanalog part is reported and explicitly
  rejected, not adopted, specifically because its certifications are
  unconfirmed.
- **Own git worktree**, branched fresh from `origin/main`; not one of the
  many pre-existing worktrees/branches for this repo. Not pushed, no PR
  opened.
- No `git stash` used.
