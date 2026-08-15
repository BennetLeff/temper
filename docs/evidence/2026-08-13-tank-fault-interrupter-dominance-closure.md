<!-- provenance: own worktree /home/bennet/Desktop/temper-tank-fault-interrupter, branch
analysis/tank-fault-interrupting-device-closure, branched from origin/analysis/tank-coil-copper-mass-bound at
commit 0e028a341999a6540bc651cab0385e4fa9bfbed5 (itself analysis/tank-fault-interrupting-device, PR #1120's
branch family, + the coil copper-mass-bound commit). docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-
acquisition.md was copied into this worktree as a single-file addition from
origin/docs/annex-l-ekmq-pulse-current-evidence at commit b337cf4e496bd3f5666d8d39faaf01d1492e926f (`git show
<ref>:<path> > <path>`, not a branch merge — that branch diverged from this one ~30 commits back and a full
merge would have pulled in ~70 unrelated files; the single file was verified byte-identical to that commit's
blob via `diff` before being added, and its own sha256 is unchanged from that document's own self-reported
hash). `git status --porcelain` clean and `git grep -l "^<<<<<<< "` empty, checked before this document was
written. No file under `elec/src/**` or `pcb/temper.kicad_pcb` was opened for writing at any point in this
session. `ngspice` not invoked. Every new fetch this session (§5) was a direct WebFetch with no proxy needed;
each PDF's binary was saved by the tool, independently hashed with `sha256sum`, and read with `pdftotext
-layout` after WebFetch's own text-extraction pass failed on encoded/binary content (the same failure mode,
and the same workaround, recorded in every prior evidence document in this repo that touches a vendor PDF). -->

# Closing the tank-fault interrupting-device specification without the bus capacitors' unobtainable I²t figure — by dominance

**Scope.** `docs/evidence/2026-08-13-tank-fault-interrupting-device-specification.md` (PR #1120's
branch) and its follow-on `docs/evidence/2026-08-13-tank-coil-copper-mass-bound.md` closed every part
of this specification except one: the bus capacitors' (`EKMQ251VSN182MA50S`) I²t withstand, which —
per `docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` (copied into this
worktree, §2 below) — **does not exist as a publishable number**, from this part's own datasheet, the
KMQ series catalog, United Chemi-Con's general engineering literature, or (as far as either edition's
readable text shows) the governing component standard IEC 60384-4. This document stops trying to
obtain that number and instead tests whether the specification closes **by dominance**: if the
fastest real, orderable DC interrupting device that meets the already-fixed requirements lets through
far less I²t than any defensible pessimistic floor on what the capacitor can survive, coordination is
proven without ever knowing the capacitor's true figure.

---

## Verdict, up front

**The specification closes by dominance for a real device family — but the margin is real, not wide,
and it is device-class-specific, not automatic for "any DC-rated fuse in the right current/voltage
bracket."**

**The two numbers that decide it:**

- **Pessimistic floor on the capacitor's I²t withstand, constructed (not measured): ≈639–1,000 A²·s**
  — from Cornell Dubilier's published "please contact us above 1,000 A peak" threshold (§3), reframed
  as a proxy over this fault's own 639 µs–1 ms dominant window. **This is explicitly a bound, not a
  measurement, of a different manufacturer's different part** (§3.4).
- **Published DC total-clearing I²t of the fastest real device class found that meets all fixed
  requirements (≥250 V DC, ≥710 A interrupting, ~22 A continuous): 308 A²·s** — Littelfuse
  POWR-SPEED® L70QS035 (35 A, 700 V AC/DC, 200 kA AC / **50 kA DC** interrupting), read directly off
  its own datasheet's electrical-specifications table, DC test column (§4.1).

**Ratio: 308 A²·s is 2.1–3.2× below the 639–1,000 A²·s floor**, holding across both the installed
(3,600 µF) and recommended (3,000 µF) bus-capacitance values and both the fault's t_peak and 1 ms
horizons (§5). **This is real, sourced margin in the right direction — but it is a single-digit
multiple, not an order of magnitude**, and it does not survive for every real device in the
right current/voltage/interrupting bracket: a second, independently-sourced DC fuse family (SIBA
URDC-ES, a "gRL" energy-storage-class DC fuse rather than a semiconductor-protection-class one) that
also satisfies every fixed requirement publishes a DC total I²t of 850 A²·s at its nearest usable
ampere rating — **inside, not below, this same floor** (§4.2, §5.3). **Device class is therefore
load-bearing for this closure, not just device ratings**, and this document says so as a specification
requirement, not a footnote (§6).

---

## 1. What this document inherits, re-verified

| Quantity | Value | Source |
|---|---|---|
| Fault loop, structural bypass of IGBT gate shutdown | unchanged | `docs/evidence/2026-08-13-tank-fault-interruption.md`, re-verified again in the interrupting-device spec §1 |
| Interrupting rating requirement | ≥ 710 A DC, with real margin above (peak may exceed 710 A — coil saturation caveat, §1.2 of the spec doc) | `docs/evidence/2026-08-13-tank-fault-interrupting-device-specification.md` §2.1 |
| Voltage rating requirement | ≥ 250 V, **DC-rated specifically** | Same doc, §2.2 |
| Continuous/normal duty | 22 A peak / 15 A RMS (DC bus path, not the tank branch) | Same doc, §2.4; `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §3.1 |
| Fault I²t, installed (3,600 µF/half) | 147.32 A²·s @ t_peak (693.6 µs); 254.94 A²·s @ 1 ms | Same doc, §1.1 |
| Fault I²t, recommended (3,000 µF/half) | 117.2 A²·s @ t_peak (638.9 µs); 221.5 A²·s @ 1 ms | Same doc, §6 |
| Bus-cap ESR's share of dissipated fault energy | 28.7% (3,600 µF) / ~32.0% (3,000 µF) of 52.0 J / 43.35 J | Same doc, §4.1, §6 |
| Tank coil — Blocker B closed | ≈126–165 g conservative copper-mass floor; ≈38,700–75,100 A²·s I²t withstand; 150–510× margin | `docs/evidence/2026-08-13-tank-coil-copper-mass-bound.md`, verdict §, §5.3 — arithmetic re-checked in this session and reproduces exactly |
| CT1, PCB copper — closed, not binding | unchanged | Interrupting-device spec §3, §4.2 |
| `EKMQ251VSN182MA50S` — no manufacturer or standards I²t/surge-current figure exists | confirmed, exhaustively, this session's inherited document | `docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` §2 (copied into this worktree; see provenance note above) |

**Not re-derived here**: the RLC fault model, the coil's mass bound, CT1's thermal bound, and the
Annex L / island-slot creepage question (unrelated to this document's task and untouched). This
document's only new work is §3–§5: constructing a defensible capacitor-withstand floor and testing it
against real device let-through data.

---

## 2. Why the capacitor's own number cannot be obtained — inherited, not re-searched

`docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` §2 (this session's copy,
byte-identical to commit `b337cf4e4`) already exhausted the direct routes: the part's own datasheet,
the KMQ series catalog (re-fetched, re-hashed, matches), United Chemi-Con's 14-page general
engineering technical note (read in full — the governing failure mechanism is electrochemical/
pressure-driven, evaluated by 10,000-cycle endurance testing, not a single-event current or I²t
figure), and IEC 60384-4 (clause 4.21, the one current-based surge clause, is restricted to
solid-electrolyte parts in the 2007 edition's readable TOC text and — per an unresolved gap that
edition text — possibly still restricted, possibly not, in 2016's TOC; either way the only clause that
*could* apply to a non-solid part, 4.20 "Charge and discharge," is conditional and not invoked for
this part). **This document does not repeat that search.** It picks up exactly where that document's
own closing paragraph left off: *"characterize and bound the fault current itself (done)... select or
size an upstream interrupting device against that bound, so the capacitors are never asked to prove a
rating that does not exist."*

### 2.1 One additional attempt this session, on the IEC 60384-4 edition ambiguity specifically

The prior document flagged, as a genuinely open item, whether IEC 60384-4:2016 Edition 5.0's clause
4.21 body text (page 40, behind every preview paywall reached so far) retains Edition 4.0's
TOC-stated "for solid electrolyte capacitors only" restriction. This session made one further,
independent attempt to reach a non-paywalled mirror or secondary quotation of that clause's actual
2016 body text (a `moam.info` document-mirror page found via web search) — it failed on a TLS
certificate error (`unable to get local issuer certificate`), a different failure mode from the two
prior 403s recorded in the inherited document, but still a hard failure, no workaround attempted.
**This remains open, exactly as the inherited document states it, and — as that document's own §2.6
already reasoned — resolving it would not change this document's conclusions anyway**: clause 4.21,
even if it did apply to non-solid electrolyte parts in the current edition, is conditional ("if
required by the detail specification") and this part's own datasheet does not invoke it. No further
search budget was spent on this after the one attempt, consistent with the task's frugality
constraint and the fact that it is not load-bearing for §5's dominance test.

---

## 3. Constructing a pessimistic floor on the capacitor's withstand

Three routes were weighed, per the task's framing. Two are closed out below as not viable from public
data; one is used.

### 3.1 Route not used: IEC 60384-4's current-based surge clause

Covered in §2.1 — remains genuinely ambiguous for the current edition, and even if resolved in the
generous direction (clause 4.21 applying to non-solid electrolyte), it is a conditional clause this
part's own detail specification does not invoke. **No number is obtainable from this route regardless
of the edition question**, so it is not pursued further as a source of a floor.

### 3.2 Route not used: a tab/terminal I²t-fusing calculation from published geometry

Cornell Dubilier's own literature (`docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-
acquisition.md` §2.5, Source A/B) names **I²t fusing of the internal tab/terminal connection** — not
bulk winding ESR heating — as the governing failure mechanism for a fast discharge pulse. This is
exactly the kind of mechanism this repository has already built a defensible bound from elsewhere
(CT1's primary conductor mass, from a land-pattern pin-spacing dimension; PCB copper, from Onderdonk's
equation on the repo's own minimum trace width) — **if a terminal geometry (pin diameter, cross-
section, or material) were published for this part or its case size.**

**It is not.** This session re-fetched the KMQ series catalog directly (`https://chemi-con.com/wp-
content/uploads/2021/05/KMQ-Series.pdf`, sha256 `6642bda567edc29a9651eaad5b81f37c0be1b4df033862baff94
febad1c47d5c` — identical to the hash the inherited document already recorded for this same file,
confirming no server-side content drift) and searched it specifically for terminal/lead dimension
data. **The only lead-geometry table in this document is a radial-lead wire-diameter table (`φd 0.5–
0.8 mm` against case diameters `φD 5–18 mm`) — for the small radial-leaded parts elsewhere in the same
catalog, not the D35×L50mm snap-in case `EKMQ251VSN182MA50S` actually uses.** No snap-in terminal pin
drawing, dimension, or material callout appears anywhere in this catalog. This is a genuine, checked
absence, not an assumption: **the tab-fusing route is blocked by the same kind of gap that blocked the
coil's mass bound before `docs/evidence/2026-08-13-tank-coil-copper-mass-bound.md` found an indirect,
over-determined-system route around it** — except here, unlike the coil, the capacitor's datasheet
does not publish enough independent constraints (inductance, DCR, and an OD ceiling, in the coil's
case) to solve for the missing geometry indirectly. **This route does not close, and this document
does not invent a terminal dimension to force it to.**

### 3.3 Route used: Cornell Dubilier's published current threshold, reframed as a proxy

`docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` §2.5, Source A (CDE/Knowles
*Aluminum Electrolytic Capacitor Application Guide*, 2024, page 8, verbatim, re-confirmed against a
fresh independent re-fetch by that document's own prior correction pass):

> "For very high inrush or sub-millisecond transient currents such as 10,000 amps peak, please
> contact us... their tabs or terminal connections may need to be fortified to prevent overheating or
> even I²t fusing... We would encourage you to contact us when you expect current transients
> involving over 1,000 amps peak."

**Construction.** CDE states this in the context of "sub-millisecond transient currents" generally —
the same regime this fault sits in (639 µs–1 ms dominant window, §1) — and draws its own line at
**1,000 A peak**: below that, CDE's own literature treats such transients as ordinary engineering
(no explicit call to action); above it, CDE wants direct contact. Reading "1,000 A peak, sub-
millisecond" as the boundary of what CDE's own product family is expected to handle without special
engineering, and converting that boundary into an I²t figure over this fault's own two established
time horizons:

```
Floor(t) = (1,000 A)² × t
Floor(t_peak, 3,600 µF, 693.6 µs) = 1,000,000 × 0.0006936 s ≈ 693.6 A²·s
Floor(t_peak, 3,000 µF, 638.9 µs) = 1,000,000 × 0.0006389 s ≈ 638.9 A²·s
Floor(1 ms)                        = 1,000,000 × 0.0010    s = 1,000.0 A²·s
```

**This is a floor of ≈639–1,000 A²·s, depending on which of this fault's own already-established
time horizons is used.**

### 3.4 What this floor is not, stated plainly

- **It is not `EKMQ251VSN182MA50S`'s withstand.** It is Cornell Dubilier's threshold — a different
  manufacturer, for its own general product line, not this specific KMQ-series snap-in part.
- **It is not itself a pass/fail rating even for CDE's own parts.** CDE's own sentence structure
  treats even sub-1,000 A "several-second, 2–4× rated ripple" events as needing case-by-case
  engineering judgment (per the same source's adjacent paragraph, quoted in full in the inherited
  document) — "please contact us above 1,000 A" is a conversation-starting line, not a certified
  withstand rating.
- **The duration multiplication is this document's own construction, not CDE's stated claim.** CDE's
  quote bounds a peak current under a loosely-described "sub-millisecond transient" regime; it does
  not state that 1,000 A held for exactly 639 µs–1 ms is safe. Multiplying by this fault's own
  duration is the most literal, defensible reading available of a threshold stated without an
  attached duration — and it is exactly the route the task's own framing named as worth weighing —
  but it is **a reframing exercise, not a citation of a number CDE actually published.**
- **Labeled, per the task's explicit instruction: this is a bound, not a measurement.** Every ratio
  and every conclusion in §5 treats it as such.

---

## 4. What real DC interrupting devices actually let through

### 4.1 Fastest class found: Littelfuse POWR-SPEED® L70QS series (semiconductor-protection-class, "very low I²t")

**Source**: `https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8914/L70QS-High-Speed-Fuse-
Datasheet.pdf`, direct WebFetch (binary saved; WebFetch's own text-extraction pass failed on the
encoded PDF stream, the same failure mode recorded throughout this repo's other vendor-PDF fetches —
the underlying file was instead read directly with `pdftotext -layout`), 11 pages, 1.0 MB, sha256
`6c8188ef6726231da50b53937ad4412716dce5d77c992d280f8dbce82eb5f360`.

**Specifications, read directly off page 1**: Voltage rating 700 V AC **and** 700 V DC (comfortably
above the ≥250 V DC requirement). Interrupting rating 200 kA AC / **50 kA DC** (far above the ≥710 A
requirement — this class is not stressed by this fault's interrupting-rating requirement at all).
Ampere ratings 35–800 A, the smallest of which (35 A) sits at 1.59× the 22 A continuous peak duty
(§1) — a normal, not oversized, headroom factor for fixed-installation fuse sizing.

**Electrical specifications table, read directly, page 2, verbatim (L70QS035 row)**:

| Catalog number | Amp rating | Voltage (AC/DC) | Interrupt (AC/DC) | Melting (pre-arc) I²t | Total clearing I²t @ 200 kA/700 V **AC** | Total clearing I²t @ 50 kA/700 V **DC** |
|---|---|---|---|---|---|---|
| L70QS035 | 35 A | 700 V / 700 V | 200 kA / 50 kA | 129 A²·s | 332 A²·s | **308 A²·s** |

**The correct figure for this fault is the DC-tested column: 308 A²·s.** (The table's own column
headers separate "200 kA @ 700 V AC" from "50 kA @ 700 V DC" as two independently-tested total-
clearing I²t figures for the same physical fuse — this document uses the DC-tested value throughout,
not the higher AC-tested figure, because this fault is a DC event.)

**A directional cross-check, not a claimed correction to the published number**: this fault's own
prospective peak (619–710 A, §1) is roughly two orders of magnitude below the 50 kA DC condition this
308 A²·s figure was tested at. Current-limiting fuses generally let through *less* total I²t at a
lower prospective fault current than at their full tested interrupting current (faster melt, but at a
current-limited peak that is itself lower) — so **308 A²·s is plausibly a conservative (higher than
actual) estimate for this specific 619–710 A fault**, not an underestimate. This is standard
current-limiting-fuse behavior, stated here as reasoning, not as a number this document claims to have
computed or verified against a real time-current curve for this exact prospective current — none was
published in this datasheet.

**A sanity check against this fault's own I²t-vs-time table (§1)**: the L70QS035's melting I²t (129
A²·s) falls between this fault's I²t at 500 µs (76.26 A²·s) and at t_peak (147.32 A²·s, installed
3,600 µF case) — i.e., **this fuse would already be melting before the fault current reaches its own
natural peak**, consistent with it being a genuine current-limiting device for this fault rather than
one that only reacts after the fact.

### 4.2 A second, independently-sourced DC fuse family that does *not* clearly dominate: SIBA URDC-ES

**Source**: `https://sub02.siba.de/upload/Downloads/Catalogues/URT/SIBA_URDC-ES_pp339-355_Rev1b.pdf`
("Fuses for DC Energy Storage (ES) Applications," class gRL/aR, SIBA GmbH — a German manufacturer
independent of Littelfuse/Mersen), direct WebFetch (binary saved, text-extraction pass failed on the
compressed PDF, read directly with `pdftotext -layout`), 1.8 MB, sha256
`0a5cd699c236648cee09c8f987eca88b352d6be5595d209def250f460855e5c5`.

**Specifications, read directly**: 440 V DC rated, 30 kA breaking capacity (both comfortably clear
this specification's ≥250 V DC / ≥710 A requirements), 14×51mm cylindrical body, IEC 60269-4/UL
248-13 certified, explicitly marketed for **DC battery/energy-storage-bank protection** — a
plausible, real candidate for "a DC-rated fuse in series with a capacitor bank," not a contrived
example.

**I²t table, read directly, verbatim (In=20 A and In=25 A rows, the two ratings nearest this
specification's 22 A continuous duty)**:

| Rated current | Pre-arcing I²t | Total I²t (@440 VDC, L/R=30 ms) |
|---|---|---|
| 20 A | 46 A²·s | 400 A²·s |
| 25 A | 100 A²·s | **850 A²·s** |
| 30 A | 190 A²·s | 1,600 A²·s |

**The 25 A rating is the one that actually clears this specification's 22 A continuous duty with
real margin** (the 20 A rating sits below the 22 A peak figure entirely — before even reaching the
I²t question, a 20 A-rated fuse against a 22 A peak duty is inadequately margined by ordinary fuse-
sizing practice, an external engineering convention not sourced from this repository, stated for
completeness and not relied on as a repo-sourced fact). **At 25 A, this fuse's own published total
DC I²t (850 A²·s) sits inside this document's §3.3 floor (639–1,000 A²·s), not below it** — it clears
the loose end of the floor (1,000 A²·s, a 1.18× margin — not meaningfully "dominant") and **fails to
clear the tight end (639–693.6 A²·s) outright.**

**Why this figure is reported even though it complicates the verdict**: the task instructs testing
dominance honestly, not selecting the number that makes the case. This is a real, independently-
sourced, orderable device that satisfies every fixed requirement in this specification (voltage,
interrupting rating, and — at the 25 A rating — continuous duty) and it does **not** clearly dominate
the pessimistic floor. **The L/R=30 ms test condition this figure was measured at is itself far
slower-decaying than this fault's own ~615 µs L/R** (`L=88 µH / R_total=143.0 mΩ`, from the
interrupting-device spec's own re-derivation) — a slower L/R generally produces *more* let-through
I²t for the same fuse, because current stays high for longer during arcing, so 850 A²·s is plausibly
conservative (an overestimate) relative to what this same fuse would let through in this fault's own
much faster-decaying event. This document does not have a curve to quantify that correction and does
not claim a lower number than the one published — it states the reasoning as a caveat in the
device's favor, exactly as it did for the Littelfuse figure in §4.1, and reports the published number
as-is either way.

### 4.3 What else was tried and did not add data

- **Eaton/Bussmann's CHSF high-speed fuse catalog** — two direct WebFetch attempts timed out (60 s
  limit exceeded on both the initial fetch and a retry via `curl`, which itself failed with no network
  reachable from the bash sandbox — WebFetch is the only network-capable tool available in this
  session, consistent with the task's own environment note). Not pursued further after two failures.
- **Littelfuse KLPC (POWR-GARD) series** — successfully fetched and read directly (sha256
  `13b092a1e9883913d2564ad909a43c9d0244da82a8e75fc897fb840c0397ec10`), but its ampere range is
  **200–6,000 A**, two orders of magnitude above this specification's ~22 A continuous duty. Not
  applicable; not used for anything above.
- **Mersen A70QS Amp-Trap** — the same "35–800 A, 700 V AC/DC, 100 kA DC interrupting" catalog
  numbering as Littelfuse's L70QS (fetched directly, sha256
  `90d2e8c314fa52c20309cfce08edf5182098d162309227efb40475d693408df7`), but the specific page fetched
  was a dimensions/ordering sheet, not the I²t table — no numeric I²t data was obtained from this
  source, and it is not relied on for any number above. Noted only because its existence as a
  parallel catalog line under a different brand is a mild, informal corroboration that the L70QS-style
  "very low I²t" semiconductor-fuse class is a real, multiply-sourced product category, not a single
  vendor's marketing claim — not treated as an independent numeric confirmation.

---

## 5. The dominance test, stated across every combination this document has sourced numbers for

| Comparison | Floor (§3.3) | Let-through (§4) | Ratio (floor ÷ let-through) | Dominates? |
|---|---|---|---|---|
| Fastest class (L70QS035, 308 A²·s) vs. floor @ t_peak, 3,600 µF (693.6 A²·s) | 693.6 | 308 | **2.25×** | Yes |
| Fastest class vs. floor @ t_peak, 3,000 µF (638.9 A²·s) | 638.9 | 308 | **2.07×** | Yes |
| Fastest class vs. floor @ 1 ms (1,000 A²·s, capacitance-independent) | 1,000.0 | 308 | **3.25×** | Yes |
| Energy-storage class (SIBA 25 A, 850 A²·s) vs. floor @ t_peak (638.9–693.6 A²·s) | 638.9–693.6 | 850 | **0.75–0.82×** | **No** — let-through exceeds the floor |
| Energy-storage class vs. floor @ 1 ms (1,000 A²·s) | 1,000.0 | 850 | **1.18×** | Marginal — real but thin |

**Reading this table honestly, per the task's own instruction to say plainly when a margin is not
wide:** the fastest, lowest-I²t real device class dominates the most defensible floor this document
can construct, by a factor of roughly **2–3×**, consistently across both bus-capacitance values and
both fault time horizons already established elsewhere in this evidence chain. **That is real,
sourced, directionally-consistent margin — the specification closes for that device class.** It is
not, however, the 150–510× margin found for the tank coil (§1), and it is not automatic: a second
real, independently-sourced, requirement-satisfying DC fuse family narrowly fails the tighter
comparison and only marginally clears the looser one. **Device class — not just voltage, current, and
interrupting rating — is therefore a load-bearing part of this specification's closure.**

---

## 6. What this means for the specification (amends §2.1/§7 of the interrupting-device spec)

The interrupting-device specification (`docs/evidence/2026-08-13-tank-fault-interrupting-device-
specification.md` §2) already fixes voltage (≥250 V DC), interrupting rating (≥710 A, with margin),
physical position, and continuous duty (~22 A). This document adds one more, previously-unstated
requirement, now load-bearing per §5:

- **The device must be drawn from a fast-acting, current-limiting, semiconductor-protection-class DC
  fuse family — not merely any DC-rated fuse that happens to meet the voltage/current/interrupting
  numbers.** §5 shows a real, correctly-rated device from a different (energy-storage-oriented) class
  does not clearly clear the pessimistic floor this document can construct, while a
  semiconductor-protection-class device does, with real margin. A specifying engineer selecting a
  part against this document should check the device's own published **melting and total-clearing
  I²t** figures directly — not just its voltage/current/interrupting ratings — against the ≈639–1,000
  A²·s floor established in §3, and should prefer the lowest-I²t class available at the required
  current rating.
- **Existence proof only, per the task's explicit instruction — neither part named above is selected
  or recommended.** Littelfuse L70QS035 and SIBA URDC-ES (5012434.25 family) are cited only to
  demonstrate that both a dominant and a non-dominant real device exist in the required class/rating
  window — a specifying engineer must independently verify current datasheets, exact clearing-time
  curves at this fault's actual prospective current (not just the tested interrupting-current
  extremes), and mechanical fit, none of which this document (or `pcb/**`, untouched) addresses.
- **This does not, and cannot, certify the capacitor survives.** It certifies that *if* a
  semiconductor-protection-class DC fuse is used, the I²t it lets through is smaller — by a real
  though not overwhelming margin — than the most defensible floor this document can construct from
  public sources for what a comparable part might withstand. **The capacitor's own true withstand
  remains unknown.** Per §3.4, the floor is explicitly not a citation of `EKMQ251VSN182MA50S`'s actual
  rating; it is a reframed proxy from an unrelated manufacturer's contact-us threshold. A margin of
  2–3× against a proxy floor is a materially weaker closure than the 150–510× margin found for the
  coil, and this document does not overstate it as equivalent.

---

## 7. Interaction with the bus-capacitance recommendation (3,600 µF vs 3,000 µF)

**Does not materially change the verdict.** §5's table already carries both capacitance values
through: the floor shifts from 693.6 A²·s (installed) to 638.9 A²·s (recommended) at t_peak — a 7.9%
tightening, consistent with the fault's own peak-current drop (§1) — while the 1 ms floor
(1,000 A²·s) is unchanged (it depends only on CDE's stated current threshold and this fault's own
already-established 1 ms horizon, not on capacitance). The ratio against the fastest device class
moves from 2.25× to 2.07× at t_peak — a small, not qualitative, change. **The specification's device-
class requirement (§6) holds at both capacitance values.**

---

## 8. What this document does not do

- It does not modify `elec/src/**` or `pcb/temper.kicad_pcb`. Verified clean (`git status
  --porcelain`) before this document was written; no such file was opened for writing at any point in
  this session.
- It does not select or name a real part to buy. §4's two device families are existence proof only —
  one favorable, one not — explicitly labeled as such, per §6.
- It does not obtain `EKMQ251VSN182MA50S`'s actual I²t withstand. That number remains unpublished
  anywhere this repository's evidence chain has reached, across two independent sessions' worth of
  searching (§2). This document closes the specification by dominance instead, with the honest,
  stated caveat that the margin is real but modest (§5) and depends on device-class selection (§6),
  not by claiming the missing number was found.
- It does not resolve the IEC 60384-4:2016 clause 4.21 edition ambiguity (§2.1) — one further attempt
  was made and failed on a TLS error; this remains open and, per the inherited document's own
  reasoning, does not bear on this document's conclusions regardless of how it resolves.
- It does not resolve the pre-existing `i_max = 25A` vs 28.7–31.9A tank-peak conflict
  (`elec/src/constraints.ato:8`) — orthogonal to this device's own DC-bus-path sizing, per the
  interrupting-device spec §2.4, not touched here either.
- It does not run `ngspice` (confirmed absent machine-wide by every prior document in this chain; not
  re-checked again this session as re-confirming an unchanged negative was judged not worth the time
  budget).
- It does not survey the lower half-bus (`c_bus2`/`c_bus2b`) independently — the interrupting-device
  spec's own §2.3/§8 already note this, and nothing in this document changes that scope.

---

## 9. Sources fetched this session

| # | Document | Retrieval | sha256 |
|---|---|---|---|
| 1 | Littelfuse POWR-SPEED L70QS series datasheet | Direct WebFetch, `mm.digikey.com`; WebFetch's own text pass failed on encoded PDF, read directly with `pdftotext -layout` | `6c8188ef6726231da50b53937ad4412716dce5d77c992d280f8dbce82eb5f360` |
| 2 | Mersen A70QS Amp-Trap Form 101 datasheet (dimensions/ordering page; no I²t data obtained, not relied on for any figure) | Direct WebFetch, `us.mersen.com`, same text-pass-failed/direct-read pattern | `90d2e8c314fa52c20309cfce08edf5182098d162309227efb40475d693408df7` |
| 3 | SIBA URDC-ES DC energy-storage fuse catalog, pp. 339-355 | Direct WebFetch, `sub02.siba.de`, same pattern | `0a5cd699c236648cee09c8f987eca88b352d6be5595d209def250f460855e5c5` |
| 4 | United Chemi-Con KMQ-Series.pdf, re-fetched to search for snap-in terminal geometry (not found; only a radial-lead table present, not applicable to this part's case size) | Direct WebFetch, `chemi-con.com` | `6642bda567edc29a9651eaad5b81f37c0be1b4df033862baff94febad1c47d5c` — **identical to the hash `docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` already recorded for this same file**, confirming no server-side content drift between sessions |
| 5 | Littelfuse KLPC (POWR-GARD) datasheet — ampere range 200-6,000A, not applicable, not used | Direct WebFetch, `boltswitch.com` | `13b092a1e9883913d2564ad909a43c9d0244da82a8e75fc897fb840c0397ec10` |

**Fetches attempted and failed, for completeness:**

| Target | Failure |
|---|---|
| Eaton/Bussmann CHSF high-speed fuse catalog | Two attempts (direct WebFetch, then `curl` from bash) both failed — 60s timeout on WebFetch, no network reachable from the bash sandbox on the `curl` retry |
| `moam.info` mirror of IEC 60384-4 (checking for readable clause 4.21 2016 body text) | TLS certificate error (`unable to get local issuer certificate`) |

No proxy/text-extraction-service fallback was needed for any source in this table — every fetch that
succeeded did so directly on the first attempt; the two failures above had no workaround attempted, in
line with the task's environment note that some sessions require a proxy while this one did not need
one for any source it actually used.
