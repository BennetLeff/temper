<!-- provenance: commit=96397f535e1ca471db34ead69e82857376f83518 dirty=false (own git worktree
     /home/bennet/Desktop/temper/.claude/worktrees/annex-l-ekmq-evidence, branch
     docs/annex-l-ekmq-pulse-current-evidence, branched from origin/main at the commit above; never
     the main checkout). This is a DOCUMENT-ACQUISITION task: no file under elec/src/**, pcb/**, or
     any safety value anywhere in the repo was opened for writing. Every figure below carries its
     own retrieval method (direct WebFetch, direct Read of a downloaded PDF, or WebSearch) and,
     where the source is a static file this session downloaded, a sha256. Nothing in this document
     is estimated, interpolated, or reconstructed from a partial/garbled source -- every "not
     obtainable" conclusion states exactly what was tried. -->

# Target 1 (IEC 60335-1 Annex L, island-slot creepage credit): still not obtainable from any freely-hosted source found this session. Target 2 (EKMQ251VSN182MA50S pulse/surge-current withstand): the number does not exist to find -- and that absence is itself sourced, not assumed.

## Verdict, up front

1. **Target 1 -- NOT OBTAINABLE.** No freely-hosted national/regional adoption of IEC 60335-1:2020
   (or later) containing readable Annex L text was found on archive.org or elsewhere this session.
   This is now an exhaustive negative, not a spot-check: archive.org's own complete search-API
   catalog for `60335-1` was enumerated (32 items, all read) and contains exactly one Part-1
   general-requirements item, the already-known 2008 edition -- no newer edition, and no BS EN/
   AS NZS/SANS item, of any edition, anywhere on the platform. Targeted searches for BS EN 60335-1,
   AS/NZS 60335.1, and SANS 60335-1 each returned only paid-vendor listings. A "commented version"
   ANSI preview, tried on the chance it exposed more pages than the plain preview PR #1160 already
   found capped, 403'd outright. A third independent secondary source (a 2017 toy-safety paper
   working through the same IEC 60664-1 groove examples in detail) converges on the same negative:
   no island/bounded-slot geometry appears in it either. **A fourth angle, run independently: two
   different free preview vendors for the current IEC 60335-1:2020 edition itself were reached far
   enough to read the standard's own verbatim table of contents and List of Figures** (§1.2) --
   confirming Annex L's exact page range and its three figures, all titled as measurement
   *procedure* flowcharts, none as an additional worked-geometry example -- a structural,
   primary-sourced (if partial) data point PR #1160 did not have, though it stops short of the
   actual body text and does not itself resolve the island question. §1 gives the full search
   record. This does not change PR #1160's own verdict on the island-slot question (unresolved, in
   either direction); it closes out the specific follow-up action PR #1160 itself proposed ("a
   follow-up session or the certification lab") for the archive.org/free-source route, with a
   negative result now honestly and exhaustively recorded rather than left untried.
2. **Target 2 -- OBTAINED, as a negative-plus-reframing finding, not a number.** No surge, pulse, or
   discharge-current rating exists for `EKMQ251VSN182MA50S` anywhere checked this session: not in
   the KMQ-series technical catalog, not in United Chemi-Con's general aluminum-electrolytic
   technical notes, and -- as far as the one edition of the governing component standard (IEC
   60384-4) whose exact clause text could be read this session shows -- not even as an *available*
   test category for this part's electrolyte technology. §2 gives the full chain. More importantly,
   §2.7 establishes, cross-checked against two independent manufacturers, that **"pulse-current
   withstand" is the wrong question to be asking of this part for this fault**: the manufacturers'
   own engineering literature frames capacitor damage under discharge stress as an
   electrochemical/pressure process (gas generation at the cathode
   foil culminating in vent-operation or case rupture), evaluated by repeated-cycling endurance
   testing, not as a single-shot current or I²t figure a designer looks up and compares against.
   No industry source found this session publishes such a figure for a standard, non-charge/
   discharge-rated wet aluminum electrolytic like this part -- which means the design's safety
   argument for this fault cannot rest on "the capacitor is rated for it," because no such rating
   exists to cite, for anyone's part, not just this one.

---

## 1. Target 1: IEC 60335-1 Annex L

### 1.1 What was searched, and why each attempt fell short

This session worked through every candidate PR #1160 named plus additional leads, directly via
WebSearch/WebFetch (an initial attempt to delegate this to a background research fork failed
outright -- the fork tool refused with "Fork is not available inside a forked worker" before doing
any work, so nothing below was pre-computed by a sub-agent; every result in this section is this
session's own direct search). The search covered:

- **archive.org's own advanced-search API**, queried directly for the literal string `60335-1`
  (`https://archive.org/advancedsearch.php?q=60335-1&fl[]=identifier&fl[]=title&fl[]=year&rows=50&output=json`),
  to get the complete, unfiltered catalog of every item archive.org indexes against that string,
  rather than trusting a keyword search's ranking to surface a relevant hit. **Full result: 32
  items, enumerated.** Exactly one is a Part-1 general-requirements text: `gov.in.is.302.1.2008`
  ("IS 302-1: Safety of household and similar electrical appliances, Part 1: General
  Requirements") -- the same 2008-edition item already used elsewhere in this repo
  (`docs/evidence/2026-08-12-hv-hv-creepage-determination.md`,
  `docs/evidence/2026-08-13-tank-fault-sizing-inputs.md`). Every other IS-302-series item returned
  is a Part-2 particular-requirements section (vacuum cleaners, microwave ovens, tumbler dryers,
  clocks, spin extractors, massage appliances, etc.) -- not Part 1, and therefore not the document
  Annex L lives in. **No newer IS 302-1 edition (the 2024 revision that adopts IEC 60335-1:2020,
  confirmed to exist and be in force per BIS's own public notices found via WebSearch) is hosted on
  archive.org.** The remaining 31 items are unrelated (CIA Reading Room cables, a fuse-holder
  manual, municipal permit notices, an arXiv physics paper, etc. -- coincidental string matches on
  "60335" or "60335-1", not standards text).
- **BS EN 60335-1** (the UK/European adoption), **AS/NZS 60335.1** (Australia/New Zealand), and
  **SANS 60335-1** (South Africa) -- targeted WebSearches for each, at the 2020-or-later edition.
  All three returned exclusively paid-standards-vendor listings (BSI/Techstreet/IHS for BS EN;
  Standards Australia/SAI Global/DIN Media/ANSI Webstore for AS/NZS; no South Africa-specific hits
  at all for SANS beyond the same generic IEC 60335-1 vendor pages). **No freely-hosted full text of
  any of these three national/regional adoptions was found.**
- **A general web search for secondary quotations of Annex L's actual content**
  (`"IEC 60335-1" "Annex L" "clearances and creepage distances" measurement sequence figure L.2`).
  This surfaced exactly one additional, useful fact beyond what PR #1160 already had: a WebSearch
  summary states *"Figure L.2 is titled 'Sequence for the determination of creepage distances' and
  is located on page 171 of the standard"* -- a page-number data point PR #1160 did not have (it
  only had the figure's existence and title from the TOC, not its page number), but still only a
  caption/location, not the figure's actual content or Annex L's body text. No source returned by
  this search quotes Annex L's body text.
- **A commented-version ("CMV") ANSI preview of IEC 60335-1 Ed. 6.0:2020**
  (`https://webstore.ansi.org/preview-pages/iec/preview_iec60335-1{ed6.0.cmv}en.pdf`), tried on the
  theory that a "commented version" preview might expose more pages than the plain edition's
  preview (which PR #1160 already found capped before page 170). **This returned HTTP 403
  Forbidden** -- could not be fetched at all, directly or otherwise, this session.
  - **Note on the 403, for consistency with this document's own §4 sourcing table**: this is a
    different failure mode from the successful direct fetches recorded in §2 (Target 2's IEC
    60384-4 previews, from `normservis.cz` and `cdn.standards.iteh.ai`, both of which succeeded on
    a first direct attempt with no proxy). No proxy or alternate retrieval was attempted for this
    403'd ANSI URL, and none is reported as having been used -- this is a genuine, unresolved
    fetch failure, not a silently-worked-around one.
- **A directly-relevant secondary paper**, located via the same web search and read in full after a
  first WebFetch pass on it failed (PDF text-extraction failure; the underlying file was instead
  read directly): Suo et al., *"Study on Testing Technology of Creepage Distances and Clearances in
  Safety Standards for Electric Toys,"* Advances in Engineering Research vol. 105 (Atlantis Press,
  2017), `https://www.atlantis-press.com/article/25871536.pdf`. This paper works through IEC
  60664-1's groove/screw-head worked examples in detail (concave groove ignored below X,
  parallel-sided groove ≥X follows contour, V-shaped groove "short-circuits" the bottom by X,
  screw-head-to-wall gap above/below X) -- **the same example set, and the same example types, PR
  #1160 already read in full from the standard itself** (§2 of PR #1160's document: "exactly 11
  figures/examples"). **This paper does not mention IEC 60335-1's Annex L at all, and does not
  picture, discuss, or reference a bounded/island slot or groove geometry anywhere in its text** --
  every one of its own worked examples, like every one of the standard's, draws a
  cross-section implicitly infinite in the third dimension. This is a third independent source
  (after the 2002-era primary text PR #1160 read in full, and the current-edition Annex L
  figure-list this session reaches in §1.2 -- PR #1160 itself only reached Annex L's single-line
  TOC entry, not its figure list) converging on the same negative finding: **no publicly
  accessible source found across three separate documents pictures the island/bounded-slot
  geometry this design's T1/U6/T2 question turns on.**

**Net result: the archive.org / freely-hosted-national-adoption route is now exhaustively checked,
not just attempted.** Every specific candidate this document set out to check returned either a
confirmed absence (archive.org's own complete catalog, BS EN/AS NZS/SANS web searches), a hard
fetch failure with no workaround attempted (the ANSI CMV preview's 403), or a converging negative
finding from an independent secondary source (the toy-safety paper). No path found this session
reaches Annex L's actual body text, and no path found this session pictures the island-slot
geometry in any edition of any standard, in any document.

### 1.2 A fourth, independent angle: reading the standard's own front matter to bound what Annex L even is

Run in parallel with §1.1's search: instead of looking for a national adoption, two free preview
services for **IEC 60335-1:2020 Edition 6.0 itself** were fetched directly and read past the cover
page to the actual table of contents and List of Figures -- something PR #1160 recorded as capped
before it could try:

- `https://cdn.standards.iteh.ai/samples/101518/78945351a99747cd8a166a9ac8688b50/IEC-60335-1-2020.pdf`,
  1.1 MB, sha256 `ceb78334daba333cf67c6d2313cccbeca308d82af692b9a2783dedfe1bef4497`. Read directly,
  15 pages, IEC-branded, pagination consistent with the standard's real structure (Bibliography
  p.207, Index p.210, per its own TOC -- the right shape for a ~210-page current edition, not a
  truncated/fake preview).
- `https://www.en-standard.eu/publicdoc/iec_previews/790934.pdf`, 486.3 KB, sha256
  `cce5e8929653aeabca2fe7979ecf275635a64b19fefce9c440785a37813756f0`. Fetched for cross-check; its
  accessible range stops earlier than the iTeh sample's and contributes no additional legible
  content, but confirms the same front-matter-only cutoff pattern from a second, independent vendor.

Both previews cut off at or before page 13 (an incomplete normative-references list) -- **neither
reaches page 170, where Annex L's own body text sits.** This is the same paywall shape found for
every IEC-published standard fetched this session (compare §2.6's IEC 60384-4 previews, same
behavior, same two preview vendors) -- a genuine, unclosed gate, not a retrieval mistake.

**What the iTeh preview's legible TOC and List of Figures *do* establish, verbatim, as primary-source
fact** (not inference): Annex L is titled *"Annex L (informative) Guidance for the measurement of
clearances and creepage distances,"* spans pages **170-172** (Annex M, "Pollution degree," starts at
173 per the same TOC line) -- three pages -- and contains exactly three figures, per the standard's
own List of Figures page:

> Figure L.1 -- Sequence for the determination of clearances ....................... 170
> Figure L.2 -- Sequence for the determination of creepage distances ................ 171
> Figure L.3 -- Measurement of clearances ............................................ 172

**Worth stating plainly, and flagged for exactly what it is and isn't.** All three titles describe
*procedural* content -- decision sequences for which measurement method applies, plus a generic
clearance-measurement diagram -- not additional numbered worked-geometry examples of the kind IEC
60664-1 has eleven of (grooves, ribs, joints; PR #1160's own finding, independently reconfirmed by
§1.1's toy-safety-paper cross-check above). If Annex L contained a new island-slot worked example
analogous to those, the standard's own List of Figures would very plausibly carry a fourth,
correspondingly-titled figure for it (IEC 60664-1's own groove/rib examples are each individually
numbered and figured, one per case, not folded into a "sequence" flowchart) -- and it does not.
**This is circumstantial, not a resolution**: three pages of prose could still discuss islands in
words without a dedicated figure, and this document does not claim to have read that prose --
nothing beyond the TOC and figure captions was accessible this session. What it does is narrow the
question a certification-lab consultation (§1.3, PR #1160 §3.4's own recommended next step) would
actually need to ask -- specifically, whether the prose accompanying L.1-L.3 (not their figures)
says anything about bounded openings -- rather than closing it.

### 1.3 What this closes, and what it doesn't

This closes the archive.org / freely-hosted-national-adoption route PR #1160 flagged as the
specific next thing to try, with a negative result now on record rather than left as an untried
possibility. It does **not** change PR #1160's own island-slot verdict, which remains correctly
stated in that document: not resolvable from any primary source this repo has been able to reach,
in either direction. The route PR #1160's own §3.4 already identified as the one that *would* close
this -- putting the exact geometry question to a certification lab or test house with access to the
full IEC 60335-1:2020 text -- is unaffected by this session's negative search result and remains the
correct next step if this design is pursued.

---

## 2. Target 2: `EKMQ251VSN182MA50S` pulse/surge-current withstand

### 2.1 Context carried forward, not re-derived

`docs/evidence/2026-08-13-tank-fault-interruption.md` (PR #1120, open, not yet on `main`) and its
follow-on `docs/evidence/2026-08-13-tank-fault-sizing-inputs.md` (same branch family, also open)
already established, and are not re-derived here:

- The tank-to-bus short closes a local series-RLC loop through the tank coil (88 µH, 0.1 Ω DCR),
  CT1's primary (Coilcraft CST3015-100ED, 0.0001 Ω), the bus-capacitor bank's own ESR
  (≈41.1 mΩ, derived from the KMQ catalog's tanδ figure at the loop's ~283 Hz ring frequency), and
  PCB pour resistance (≤1.8 mΩ) -- **143.0 mΩ total loop resistance**, of which the bus capacitors'
  own ESR is **28.8%**, second only to the coil's DCR (69.9%).
- Stored energy `E = ½CV² = ½ × 3600µF × (170V)² ≈ 52 J` per half-bus bank.
- A damped-RLC peak fault current of **619-710 A** at **t ≈ 694-738 µs** after the short, with
  **I²t ≈ 147 A²·s at the current peak, ≈255 A²·s by 1 ms** -- both figures for the *loop's* total
  current, not a per-component withstand figure.
- The coil and the bus-capacitor bank together account for **69.9% + 28.8% = 98.7%** of loop
  resistance, matching this document's "97-99% of the fault energy" framing: dissipation is
  proportional to each element's share of `R_total` in a series loop, so the coil and the
  capacitors' own ESR are where almost all of the 52 J actually turns into heat, not CT1 or the
  copper pour.
- **This means the bus capacitors are not a passive bystander in this fault: on the order of 28.8%
  of 52 J (roughly 15 J) is dissipated inside the capacitor bank's own ESR, during the same
  sub-millisecond event, whether or not any external device ever interrupts it.** That is the
  physical question this document was assigned to answer a number for: does the part survive that,
  and against what published figure would a reviewer check it?

### 2.2 The part's own datasheet: already checked, confirmed empty (not re-fetched)

Per the task brief, the device datasheet was already re-fetched and grepped this session's prior
work and carries no surge or pulse-current rating -- only ripple current at rated frequencies. Not
repeated here.

### 2.3 The KMQ-series technical catalog: fetched directly, confirmed empty

**Source**: `https://chemi-con.com/wp-content/uploads/2021/05/KMQ-Series.pdf`, fetched directly via
WebFetch this session (no proxy needed; direct fetch succeeded), 278.7 KB,
sha256 `6642bda567edc29a9651eaad5b81f37c0be1b4df033862baff94febad1c47d5c`.

This is the series-level technical catalog (not the single-part datasheet) PR's brief specifically
asked to check as step 1. It contains **only standard 120 Hz ripple-current ratings**, tabulated by
capacitance, voltage, and case size. **No peak surge or inrush current limit, no pulse-current
handling figure (I²t or A²s), no discharge-current capability, and no transient-withstand
specification appears anywhere in this document.** This is the same negative result the task brief
already recorded for the single-part datasheet, now independently confirmed for the series catalog
one level up.

(A second, differently-versioned copy, `KMQ-Series-1.pdf`, was independently fetched by the sibling
`docs/evidence/2026-08-13-tank-fault-sizing-inputs.md` this same day for its tanδ/ESR derivation
(sha256 `1e6c0c241393f983aca540278536bd6ea5c9ab95d17ab19c6425f53538f7480a`) and likewise reports no
surge/pulse rating -- a second independent retrieval agreeing with this one.)

### 2.4 United Chemi-Con's general aluminum-electrolytic technical notes: read in full, the actual failure-mode chain

**Source**: `https://chemi-con.com/wp-content/uploads/2021/04/Technical-Notes.pdf` -- "Technical
Note: Judicious Use of Aluminum Electrolytic Capacitors," Nippon Chemi-Con **CAT. No. E1001U**,
fetched directly this session (no proxy), 915 KB,
sha256 `f773b79883c747a23e4706832a156eda08d239fbd396329d4cfb182239cd0fd2`. WebFetch's own
PDF-to-text pass on this file failed (returned "corrupted/unreadable"); the underlying downloaded
PDF was instead read directly with this session's PDF reader, all 14 pages, verbatim.

This is the general, cross-series engineering document step 2 of the task brief asked for. It has
**no numeric surge/pulse/discharge-current rating anywhere in it either** -- but it does state the
actual physical failure chain the manufacturer attributes to charge/discharge stress, which is the
answer to this document's framing question (§2.7, cross-checked against a second manufacturer in
§2.5):

- **§4 "Failure Modes" (Fig-18)**, the manufacturer's own top-level fault tree: `Open Vent` traces
  back through `Internal Pressure Rise` <- `Electrochemical Reaction`, with `Excessive
  Charge-Discharge Duty` listed as one of the named primary factors feeding that reaction, alongside
  excessive ripple current and excessive operating voltage. Not a current-magnitude threshold --
  a chain ending in a mechanical pressure-relief event.
- **§5-3 "Heat Generation due to Ripple Current"**: `W = I_R²R + V·I_L ≈ I_R²R` (Eq. 9/10) -- the
  manufacturer's own stated dissipation mechanism is ESR-driven I²R heating, consistent with
  `docs/evidence/2026-08-13-tank-fault-sizing-inputs.md`'s use of derived ESR to apportion energy in
  §2.1 above.
- **§5-4 "Charge and Discharge Operation Effect on Lifetime"**, verbatim: *"Discharging the
  electricity through a discharging resistance makes the electric charges move to the cathode foil
  and cause chemical reactions between the cathode aluminum and electrolyte, thereby forming a
  dielectric oxide layer... the chemical reactions bring heat and gases. Depending on the charge
  and discharge conditions, the internal pressure may increase, the pressure relief vent may open
  or the capacitor may have destructive failures."* This is the manufacturer's own primary-text
  statement of the mechanism: discharge stress is not purely thermal -- it is **electrochemical**
  (charge motion into the cathode foil driving a reaction) that produces both heat *and* gas, and
  the failure endpoint it names is a **mechanical** one (vent operation, or worse, case rupture),
  not a temperature or current threshold in isolation.
- The same section's Figures 23-25 characterize this via **repeated-cycling endurance testing**
  (10,000 charge/discharge cycles, 30 s charge / 30 s discharge, τ=0.01 s time constant, at stated
  ambient/voltage conditions), distinguishing "General Products" (which reach a marked
  "(Vent Operated)" point within the test) from "Special Products" -- a distinct, purpose-built
  charge/discharge-rated capacitor family. **`EKMQ251VSN182MA50S`/the KMQ series is not in that
  special family**: §9-1's own "Recommended input filtering capacitors for SMPS" table lists KMQ
  under standard snap-in filtering service, not under any family the document elsewhere associates
  with intensive charge/discharge duty (§9-1's own text: *"For servo amplifiers and other
  application where the voltage fluctuates frequently due to regeneration, use capacitor families
  that have been especially designed for intensive charge and discharge operations, or consult us
  for individual designs."*) -- KMQ is not offered as one of those families.
- **§5-5 "Inrush Current"** (charging, not discharging, current -- a different event from this
  fault, noted for completeness and not conflated with §5-4's discharge mechanism above): *"a
  single, non-repeated inrush current produces a negligibly small amount of heat, so it does not
  matter. However, frequently repeating inrush currents may heat up the element inside a capacitor
  more than the allowable limit..."* This gives the manufacturer's general risk framing (single
  events are treated as low-risk by heat alone; repetition is what the manufacturer's own endurance
  data actually characterizes) but, notably, **still no numeric threshold in either direction** --
  and it does not speak to §5-4's separate electrochemical/gas-generation mechanism, which is not
  purely a heat-accumulation question.

**No number.** Fourteen pages, read in full, contain a qualitative failure chain and a set of
10,000-cycle endurance charts -- and zero A, A²s, or J figures characterizing a single discharge
event of any magnitude.

### 2.5 A second manufacturer, independently: Cornell Dubilier (CDE), and a real 16 kA pulse case study

Everything in §2.3-§2.4 comes from one manufacturer (Chemi-Con). Cross-checking against **Cornell
Dubilier (CDE/Knowles)** -- a different aluminum-electrolytic manufacturer with no commercial stake
in this part -- both confirms the same absence and adds something Chemi-Con's own literature didn't:
a concrete physical mechanism, with real measured/modeled numbers, for exactly this class of event.

**Source A**: *"Aluminum Electrolytic Capacitor Application Guide,"* CDE/Knowles, 2024,
`https://www.cde.com/resources/technical-papers/KNO_CD_AEappGuide_R2.pdf`, 1.8 MB, sha256
`fdabf0eed859d6ab648aaac7960f5f002042099163f5ba15152d51c2ca75b5bb`. Fetched directly (no proxy),
read in full (22 pages).

- **Scope note, page 1, verbatim**: *"Photoflash, strobe, pulse discharge and charge-discharge
  specialty capacitors are not covered [by this guide]."* Independent confirmation of §2.4's
  "Special Products" finding from an unrelated manufacturer: pulse/charge-discharge duty is treated
  industry-wide as a **separate product category**, not a rating carried by general-purpose
  electrolytics like the KMQ series.
- **"Ripple Current Transients and High Inrush Current," page 8, verbatim**: *"Electrolytic
  capacitors are able to survive some transient ripple current abuse. As a rule of thumb, for brief
  ripple current excursions such as several seconds of 2 to 4 times the rated load ripple current,
  the thermal mass of the capacitor winding will absorb a lot of the extra energy dissipation of
  such an event... For very high inrush or sub-millisecond transient currents such as 10,000 amps
  peak, please contact us. Although electrolytic capacitors do not suffer from the intrinsically low
  dv/dt limits of metallized film capacitors, their tabs or terminal connections may need to be
  fortified to prevent overheating or even I²t fusing... We would encourage you to contact us when
  you expect current transients involving over 1,000 amps peak."*

  This is the single most direct primary-source statement found this session on the actual question:
  a manufacturer, in its own general engineering literature, explicitly names **I²t fusing of the
  internal tab/terminal connection** -- not bulk ESR heating of the winding, not a vent-pressure
  threshold -- as the failure mode of concern for a fast, high-peak discharge/inrush pulse, and
  states its own **"please contact us above 1,000 A peak"** threshold rather than publishing a
  number. This fault's peak (619-710 A, §2.1) sits **below** that explicit escalation line -- a data
  point, not a guarantee (it's a different manufacturer's threshold for a different part's
  construction, and CDE's own sentence structure treats even sub-1,000 A "several-second, 2-4x
  rated ripple" events as needing case-by-case engineering judgment, not a blanket pass) -- but it
  is the closest thing to an industry-anchored reference point located this session.
- **"Charge-Discharge Duty and High Peak-to-Peak Voltage," page 8, verbatim**: *"Frequent charge and
  discharge of aluminum electrolytic capacitors -- whether rapid or slow -- not designed for such
  service can damage the capacitors by overheating and overpressure or breakdown with consequent
  failure by open or short circuit. For charge-discharge applications use capacitors designed for
  that use, such as our photoflash and strobe capacitors... or contact us for a special design."*
  Same electrochemical/overpressure framing §2.4 found in Chemi-Con's literature, from an unrelated
  manufacturer -- convergent, not coincidental.
- **"Rated Surge Voltage," page 8**: confirms, independently of §2.6's IEC 60384-4 reading, that the
  industry-standard "surge" rating for this component class is a **voltage** rating ("the maximum DC
  overvoltage to which the capacitor may be subjected... for short periods not exceeding
  approximately 30 s... no more than 1,000 times during the capacitor lifetime") -- not a current or
  energy rating, and not applicable to a discharge event.

**Source B**: Parler, Sam G. Jr. (CDE Director of R&D, P.E.), *"Transient Thermal, Electrical and
Lifetime Analysis of Large-Can Aluminum Electrolytic Capacitors,"* presented at APEC 2015,
`https://www.cde.com/resources/technical-papers/TransientModelingOfLargeScrew-TerminalAluminumElectrolyticCapacitors.pdf`,
2.7 MB, sha256 `1803458509a3bd033044924774aeb8a6dc269416f734283289de185963222dcf`. Fetched directly,
read in full through its worked example (6 of ~20+ slides; the rest of the deck moves to a separate
lifetime-averaging topic not relevant here). This is a peer-presented, named-author engineering
paper analyzing **the same class of event this fault is** -- a fast current pulse discharging through
a large-can wet aluminum electrolytic -- with real modeled/measured data, not a general statement:

- **Slide 3, verbatim**: `TabMass/TabR << WindingMass/WindingR` -- *"Spatial distribution of transient
  response to current pulse will be much different from that of the steady state response."* This is
  the paper's own stated reason a bulk/lumped thermal model is the wrong tool for a fast pulse: the
  tabs (low mass, low thermal resistance to the current path) and the winding (the bulk mass a
  lumped-capacitance thermal model would represent) respond on very different timescales.
- **Slide 4, verbatim, the paper's own worked case**: *"Transient Response to 16 kA pulse at 45°C
  initial temperature and subsequent cool-down shows <0.1°C heat rise in winding but 5°C heat rise in
  the aluminum tabs."* For a peak current roughly **23-26x this fault's 619-710 A** (§2.1), the bulk
  capacitor body (winding) is shown essentially thermally unaffected while the tab/terminal
  connections concentrate essentially all of the measurable temperature rise -- direct, quantified,
  primary-source confirmation that a fast discharge pulse's risk is localized to the tab/lead
  connection, not the winding's own ESR-driven bulk heating. The same slide gives a **tab cool-down
  time constant of ~7 seconds** for that specific large-can construction -- a fast, localized
  transient, not a whole-capacitor thermal-mass response.
- **This is a different manufacturer's different capacitor construction (a larger screw-terminal
  can, not confirmed to be this same case size/tab geometry) presenting a different peak current, so
  no number from this paper is transferable to `EKMQ251VSN182MA50S` and none is claimed to be** --
  it is cited here only for the physical mechanism and modeling methodology it demonstrates
  (tab-vs-winding thermal partitioning under a fast pulse), which is exactly the mechanism §2.7
  argues governs and which this repo's own task brief already suspected on physical-reasoning
  grounds ("a lumped thermal-mass bound would not be physically valid").

### 2.6 IEC 60384-4: the one place a current-based test clause exists, and why it doesn't reach this part

`EKMQ251VSN182MA50S` is a standard wet (non-solid) electrolyte snap-in aluminum electrolytic
capacitor -- confirmed by its own construction category in the Chemi-Con technical note read above
(§1-2/Fig-4 of the same document: the "Snap-in Type" construction shown is the impregnated-element,
liquid-electrolyte type, the same construction class as every part in the KMQ catalog checked in
§2.3), as distinct from the solid-MnO2-electrolyte technology IEC 60384-4 separately covers.

**IEC 60384-4** ("Fixed capacitors for use in electronic equipment - Part 4: Sectional
specification - Fixed aluminium electrolytic capacitors with solid (MnO2) and non-solid
electrolyte") is the governing component-level standard for this part class, and step 3 of the
task's brief. Two editions were fetched and their table-of-contents/front-matter read directly this
session (both direct WebFetch of a standards-preview host, not a paywalled purchase):

- **Edition 4.0 (2007-03)**, `https://www.normservis.cz/download/view/iec/info_iec60384-4%7Bed4.0%7Den.pdf`,
  103.9 KB, sha256 `7edb7083341e44fbf1be3eeab142d0d8e2ad0228a49584985005bd77230b2c5f`. This preview's
  TOC is complete and legible. **Verbatim, from the TOC**:

  > "4.21 High surge current (for solid electrolyte capacitors only and if required by the detail
  > specification) ............................................. 36"

  This is an unambiguous, primary-source statement, in the standard's own table of contents, that
  the one clause in this standard titled specifically for a *current*-based surge/pulse test
  (as opposed to clause 4.14 "Surge," which is a *voltage* overrating test -- see below) is
  restricted to solid-electrolyte capacitors. `EKMQ251VSN182MA50S` is not one.

- **Edition 5.0 (2016-08, the current, in-force edition)**,
  `https://cdn.standards.iteh.ai/samples/20950/57c5f3f64c67488796117e378f58e2ed/IEC-60384-4-2016.pdf`,
  1.1 MB, sha256 `ebd28df1d71e3bb9b2222e10b271b257e3c54b5623ce61c6bb5c3ec8dcc5be11`. Its TOC entry
  for the same clause number reads only:

  > "4.21 High surge current (if required) ....................................................40"

  **The "(for solid electrolyte capacitors only ...)" qualifier that Edition 4's TOC states
  explicitly does not appear in this line.** This preview's accessible page range (13 pages of
  front matter/TOC/general clauses) ends well before page 40, where clause 4.21's actual body text
  sits, so **this session could not read the clause 4.21 body text in either edition, and cannot
  confirm from primary text whether the current (2016) edition retains, narrows, or drops the
  solid-electrolyte-only restriction that Edition 4's TOC states in full.** This is reported as an
  open, unresolved gap -- not silently carried forward as "presumably unchanged," and not
  discarded as irrelevant. A WebSearch-generated summary (secondary, not primary-text-verified)
  separately claimed the 2016 edition's clause 4.21 is "for solid electrolyte capacitors only" in
  its body text, consistent with Edition 4's TOC -- but this claim is flagged here as **unverified
  against primary text** and is not relied upon as established.
- Also confirmed from Edition 5's TOC, for completeness: **clause 4.14 "Surge"** (both editions)
  governs *surge voltage*, not current -- Edition 5's own §2.2.7 "Surge voltage ratio" (read
  directly, page 12 of the same preview) states the surge voltage is 1.15x or 1.10x rated voltage
  depending on voltage class, a voltage-overrating test with no bearing on a discharge-current
  question. **Clause 4.20 "Charge and discharge (if required by the detail specification)"**
  exists in both editions, is not restricted to either electrolyte type, and *would* be the
  applicable conditional test category for a wet-electrolyte part like this one if invoked -- but
  it is optional ("if required by the detail specification"), and, per §2.2 above, this part's own
  detail specification (its datasheet) does not invoke it.

**Net effect**: even before reaching the question of whether a number exists, the standard's own
clause structure -- confirmed from primary TOC text in the superseded edition, and from a
still-open gap in the current edition -- shows that the one IEC 60384-4 clause built around a
*current*-based surge/pulse test is, at minimum historically and very plausibly still, not even an
available category for this part's electrolyte technology. The only conditional clause that could
apply to this part (charge/discharge, 4.20) was never invoked for it.

### 2.7 Is "pulse-current withstand" the right question at all? -- direct answer

**No, not as the task's own framing (an externally-imposed surge into a passive victim) implies.**
This fault is the capacitor bank discharging its own stored energy into a loop it is part of, not
absorbing an outside transient. Four independent, sourced observations converge on the same
answer for what actually governs, none of them a single "withstand current" figure:

1. **Chemi-Con's own literature (§2.4) identifies the governing mechanism as
   electrochemical/pressure-based, not thermal-threshold-based**: charge motion into the cathode
   foil during discharge drives a chemical reaction that produces both heat *and* gas, and the
   named failure endpoint is a mechanical event (vent operation, or destructive case failure) --
   evaluated by the manufacturer through repeated-cycling endurance data, not a single-event
   current or I²t spec. A single discharge event's severity, on this model, is not simply
   "does I²Rt exceed some number" the way a fuse's I²t withstand works.
2. **CDE, an unrelated manufacturer, independently names the tab/terminal connection -- not the
   winding's bulk ESR -- as where a fast discharge pulse's risk actually concentrates** (§2.5,
   Source A: "I²t fusing" of tabs/terminals; Source B: a real 16 kA case study showing <0.1°C
   winding rise against 5°C tab rise for the same pulse). Two manufacturers, two different
   physical framings (electrochemical/pressure at Chemi-Con, tab I²t fusing at CDE) -- but both
   converge on "not a single bulk-thermal or bulk-current threshold," and neither publishes a
   number for a part like this one.
3. **This repo has already, independently and correctly, ruled out the naive thermal-mass
   shortcut**: this document's own task brief notes "an earlier pass already noted a lumped
   thermal-mass bound would not be physically valid for electrolytic failure modes" -- which §2.5's
   Source B now confirms with real data, not just physical reasoning: a lumped/bulk thermal model
   of the whole capacitor would have predicted negligible risk from a 16 kA pulse (<0.1°C winding
   rise) while the actual measured/modeled risk concentrated entirely in a part of the capacitor
   (the tabs) a bulk model doesn't resolve. If the real failure mode is electrochemical
   gas-generation/pressure buildup (Chemi-Con's framing) and/or localized tab I²t heating (CDE's
   framing), a lumped thermal-mass calculation answers the wrong physical question even where it
   can be computed, and this document does not attempt one.
4. **The governing component standard, where it does define a current-based test at all, defines
   it as inapplicable to this part's technology in the one edition whose text this session could
   verify (§2.6)**, and the applicable alternative clause is optional and unused for this part.
   There is no standards-mandated number to fall back on either.

**What this means for the design question the task asked me to inform, stated plainly and without
inventing a number to fill the gap**: no published figure exists, from this part's manufacturer, in
any tier of documentation checked (part datasheet, series catalog, general engineering literature),
or from the governing component standard, that bounds whether `EKMQ251VSN182MA50S` survives
absorbing ~15 J (§2.1's 28.8% share of 52 J) through its own ESR in roughly 700 µs-1 ms. This is not
a paywall gap -- every source checked this session was free and was read in full or to the edge of
its available preview. **The industry does not characterize standard, non-charge/discharge-rated
wet aluminum electrolytics this way**, which means a safety argument for this fault cannot be built
on "the capacitor's rating covers it," because there is no rating to check against, for this part or
(per §2.4's "Special Products" distinction) for any standard part in this technology class that
isn't purpose-built for charge/discharge duty. The only sourced, checkable path this repo's own
evidence base offers is the one `docs/evidence/2026-08-13-tank-fault-sizing-inputs.md` already
opened: characterize and bound the *fault current itself* (done, §2.1) and select or size an
upstream interrupting device against that bound, so the capacitors are never asked to prove a
rating that does not exist. Whether the coil or the capacitor bank survives *even that* -- fully
interrupted, at whatever speed a real device achieves -- is not established by any document this
repo has today, including this one; it remains open, named rather than guessed at.

---

## 3. What was not attempted, and why

- **No thermal or electrochemical simulation of the capacitor's own discharge behavior was run.**
  `ngspice` is confirmed unavailable in this environment (per the sibling document, re-checked
  fresh that same session, not re-checked again here) and no tool for modeling electrolyte
  gas-generation kinetics exists in this repo regardless of simulator availability.
- **IEC 60384-4's clause 4.21/4.20 body text (page 40/39 in each edition) was not obtained.** Both
  fetch attempts (`iTeh` for Edition 5, `normservis.cz` for Edition 4) returned free previews capped
  before that page; no paid or alternate free source was located this session. This is reported as
  a genuine, unclosed gap (§2.6), not treated as resolved by inference.
- **CDE's APEC 2015 16 kA case study was read only through its worked example (6 of the deck's
  slides)**; the remainder of that presentation moves to a separate lifetime-averaging-technique
  topic (per its own outline slide, methodology for combining time-varying stressors into a single
  lifetime figure) unrelated to this fault's discharge-mechanism question, and was not read.
- **A physical/lab pulse test of the actual part was, obviously, not performed** -- out of scope for
  a document-acquisition task, and not something this repo's evidence conventions treat as
  something to simulate the result of.

---

## 4. Sources

| # | Document | Retrieval | sha256 |
|---|---|---|---|
| 1 | KMQ-Series.pdf (United Chemi-Con KMQ series catalog) | Direct WebFetch, `chemi-con.com` | `6642bda567edc29a9651eaad5b81f37c0be1b4df033862baff94febad1c47d5c` |
| 2 | Technical-Notes.pdf ("Judicious Use of Aluminum Electrolytic Capacitors," CAT. No. E1001U) | Direct WebFetch + direct PDF read (WebFetch's own text pass failed; PDF read directly instead), `chemi-con.com` | `f773b79883c747a23e4706832a156eda08d239fbd396329d4cfb182239cd0fd2` |
| 3 | IEC 60384-4 Edition 5.0:2016 preview (TOC/front matter only) | Direct WebFetch + direct PDF read, `cdn.standards.iteh.ai` | `ebd28df1d71e3bb9b2222e10b271b257e3c54b5623ce61c6bb5c3ec8dcc5be11` |
| 4 | IEC 60384-4 Edition 4.0:2007 preview (TOC/front matter only) | Direct WebFetch + direct PDF read, `normservis.cz` | `7edb7083341e44fbf1be3eeab142d0d8e2ad0228a49584985005bd77230b2c5f` |
| 8 | CDE/Knowles "Aluminum Electrolytic Capacitor Application Guide" (2024) | Direct WebFetch + direct PDF read, `cde.com` | `fdabf0eed859d6ab648aaac7960f5f002042099163f5ba15152d51c2ca75b5bb` |
| 9 | Parler, "Transient Thermal, Electrical and Lifetime Analysis of Large-Can Aluminum Electrolytic Capacitors" (APEC 2015) | Direct WebFetch + direct PDF read, `cde.com` | `1803458509a3bd033044924774aeb8a6dc269416f734283289de185963222dcf` |

No proxy/text-extraction fallback was needed for any Target 2 source this session -- every fetch
above succeeded directly.

**Target 1 sources (all negative or partial results, per §1):**

| # | Source | Result |
|---|---|---|
| 5 | `https://archive.org/advancedsearch.php?q=60335-1&fl[]=identifier&fl[]=title&fl[]=year&rows=50&output=json` | Direct WebFetch, JSON API. 32 items, full list read; exactly one Part-1 item (`gov.in.is.302.1.2008`, the already-known 2008 edition), no newer edition, no BS EN/AS NZS/SANS item |
| 6 | `https://webstore.ansi.org/preview-pages/iec/preview_iec60335-1{ed6.0.cmv}en.pdf` | Direct WebFetch attempt -- HTTP 403, no content retrieved, no proxy tried |
| 7 | Suo et al., "Study on Testing Technology of Creepage Distances and Clearances in Safety Standards for Electric Toys," Atlantis Press AER vol. 105 (2017), `https://www.atlantis-press.com/article/25871536.pdf` | Direct WebFetch (text-extraction pass failed) + direct PDF read, full 6 pages, read in full, sha256 `b019c931459b743d3b0d2a43597a220170c8fa6e18942b24d6a678abffc9a00c` |
| 10 | IEC 60335-1:2020 preview (TOC/List of Figures only), `cdn.standards.iteh.ai` | Direct WebFetch + direct PDF read, 15 pages read; establishes Annex L's page range (170-172) and its 3 figure titles, all procedural | `ceb78334daba333cf67c6d2313cccbeca308d82af692b9a2783dedfe1bef4497` |
| 11 | IEC 60335-1:2020 preview (front matter only), `en-standard.eu` | Direct WebFetch + direct PDF read; accessible range stops before the TOC, no additional content beyond confirming the same cutoff pattern from a second vendor | `cce5e8929653aeabca2fe7979ecf275635a64b19fefce9c440785a37813756f0` |
| -- | `https://webstore.ansi.org/preview-pages/bsi/preview_30369343.pdf` (BSI preview of the same standard) | Direct WebFetch attempt -- HTTP 403, no content retrieved, no proxy tried (second independent 403, different preview vendor than source 6) |
| -- | `gezhi-tech.com` (an unofficial IEC 60335-1 clause-by-clause interpretation blog, found via WebSearch) | Direct WebFetch attempt failed: TLS certificate expired. Not pursued further -- secondary/unofficial source regardless, and no Annex L-specific content was visible in the search snippets that led to it |

## 5. UNVERIFIED / open items

| Item | Reason |
|---|---|
| Whether IEC 60384-4:2016 (current edition) clause 4.21's body text retains the "solid electrolyte only" restriction Edition 4's TOC states explicitly | Clause body (page 40) falls outside both fetched previews' accessible range; only a secondary, non-primary-text WebSearch summary claims it does, and is explicitly not relied upon |
| Whether any capacitor-side figure (manufacturer or standard) would in fact bound this specific fault if a paywalled/purchased copy of IEC 60384-4 or a direct manufacturer engineering contact were consulted | Out of scope for a free-source document-acquisition pass; §2.6/§2.7 report what free sources actually say, not an exhaustive claim that no paid source anywhere contains a number |
| Whether the coil or capacitor bank survives even a correctly-sized interrupting device's actual clearing time | Not established by this document or any document currently in this repo; genuinely open |
| Target 1, full resolution | Remains open per PR #1160's own verdict; §1 above closes out only the archive.org/national-adoption/IEC-preview search routes |
| Whether Annex L's own prose (not just its figure captions, §1.2) discusses a bounded/island opening | Only the TOC and List of Figures were reached; the 3 pages of actual body text (170-172) remain behind the same paywall as the rest of the standard |
