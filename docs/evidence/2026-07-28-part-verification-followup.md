<!-- provenance: commit=c83f5af91f0b65200788334edd9be7e7d58245fa dirty=false -->

# Follow-up verification of the two gaps PR #401 left open, plus the tank capacitor's AC/frequency rating

Branch `docs/part-verification-followup`, from `origin/main` at `c83f5af9`
("Merge pull request #401 from BennetLeff/fix/tank-cap-and-isolator-footprints").

`dirty=false`: this branch adds this document and nothing else. Every repo
figure quoted below was read from the clean `c83f5af9` tree; no `.ato`, no
BOM, no board, no allowlist, and no gate was modified. This is verification,
not change.

PR #401 flagged two of its own claims as unverified and asked for them to be
closed. This pass answers both from primary sources, and in doing so found a
**third issue that PR #401 did not look for and that is more consequential
than either of the two it flagged.**

---

## Verdicts

| # | Question | Verdict |
|---|---|---|
| 1 | Is `FKP1T031507G00JSSD` a real, orderable part number? | **Part verified, part could not verify.** Every one of the 18 characters is now traced to a WIMA-printed table (PR #401 had only the first 12). **No distributor listing for the full string exists** — Findchips returns "No results". Not fabricated; orderability still open. |
| 2 | What isolation rating and certification does `H11L1TVM` actually carry? | **VERIFIED, and it refutes PR #401's premise.** The datasheet *does* publish creepage and clearance. Certified to DIN EN/IEC 60747-5-5, V_IORM = 850 V peak, UL 1577 4170 V<sub>ACRMS</sub>/1 min. **External creepage ≥ 7 mm — 1 mm below this repo's own 8.0 mm reinforced-creepage requirement.** |
| 3 | *(not asked, found here)* Is the tank capacitor adequately rated at 47 kHz? | **REFUTED.** On the DC axis PR #401 is right and has 5× margin. On the axis that actually binds — WIMA's published permissible **AC current vs frequency** — each tank cap runs **~1.7× over** the published limit at the design's own committed 1.8 kW operating point. |

**Gap 2 is closed. Gap 1 is closed as a fabrication question and remains open
as a procurement question. Issue 3 is new and is a design finding, not a
paperwork finding.**

---

## Gap 1 — `FKP1T031507G00JSSD`

### 1.1 What is now sourced that was not before

PR #401 wrote that the base number came from WIMA's ordering table but that
"the six trailing positions … **are carried over unchanged** from the previous
declaration" — i.e. inherited from the known-wrong string `FKP1U021507E00JSSD`
rather than sourced. That is the exact move the MPN gate exists to prevent, so
it was re-derived from scratch.

**Source: WIMA FKP 1 datasheet, revision `03.26` (printed in the page footer),
`https://www.wima.de/wp-content/uploads/media/e_WIMA_FKP_1.pdf`, fetched
2026-07-28. Text extracted locally with `pdftotext -layout`; quotes below are
verbatim from that extraction.**

Sheet numbered **65** in the page corner ("Continuation page 67" in the
footer), General Data table, **1600 VDC/650 VAC** column, 0.15 µF row:

```
   0.15 „     17   29   41.5 37.5   FKP1R031507E_ _ _ _ _ _    20   39.5  41.5 37.5   FKP1T031507G_ _ _ _ _ _
```

So for the 1600 VDC part: **W 20, H 39.5, L 41.5, PCM 37.5, stem
`FKP1T031507G`** — matching `modules.ato`'s declared dimensions and the
assigned `C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` land exactly. **PR #401's
reading of this row is correct.** (The left-hand columns are the 1250 VDC
part, `FKP1R031507E`, in a smaller 17 × 29 case — a useful distractor, and
PR #401 did not confuse them.)

The **"Part number completion" box printed on that same sheet**, verbatim:

```
Part number completion:
Version code: 2-pin    = 00
              4-pin    = D4
Tolerance:    20 %     =M
              10 %     =K
              5 %      =J
Packing:      bulk     =S
Pin length:   6-2      = SD
Taped version see page 133.
```

`00` + `J` + `S` + `SD` = **`00JSSD`**, exactly six characters, exactly the
declared completion. **This is a stronger provenance than PR #401 claimed for
itself**: the completion is not inherited from an unrelated (and wrong) part
number, it is the completion box that governs this very ordering table, on the
same printed sheet as the row. Read from source, not inferred.

### 1.2 The completion string is demonstrably real in commerce

Independent corroboration that `…00JSSD` is a live ordering code on this exact
series and voltage class, not merely legal grammar — real listings for **other
rows of the same table**:

| Listed part | Row it completes | Where seen |
|---|---|---|
| `FKP1T002204B00JSSD` | 220 pF / 1600 V / PCM 15 | EVE Electronics catalogue page |
| `FKP1T012205A00JSSD` | 2.2 nF / 1600 V / PCM 22.5 | EVE Electronics catalogue page |
| `FKP1T011504D00KSSD` | 1.5 nF / 1600 V / PCM 15 (±10 % variant) | EVE Electronics catalogue page |
| `FKP1T031007E00JSSD` | **0.1 µF / 1600 V / PCM 37.5** — the row directly above ours | Avnet Abacus, via Findchips (stock 0) |
| `FKP1R032207F00JSSD` | 0.22 µF / 1250 V / PCM 37.5 | EVE Electronics catalogue page |

Each of these stems appears verbatim in the same datasheet table, and each is
completed with the identical `00JSSD`. The construction rule is real and in
commercial use.

### 1.3 What could NOT be verified

**No distributor listing for the exact 18-character string
`FKP1T031507G00JSSD` was found.**

- **Findchips** (`findchips.com/search/FKP1T031507G00JSSD`, fetched
  2026-07-28) returns, verbatim, **"No results were found for
  FKP1T031507G00JSSD."** Its only near match is `FKP1T031007E00JSSD` (Avnet
  Abacus, **0 in stock**) — the 0.1 µF row, not ours.
- **EVE Electronics** stocks many neighbours from this table (§1.2) but two
  constructed catalogue URLs for the 0.15 µF/1600 V part both returned HTTP
  404, and their site search endpoint 404'd. Absence from my URL guesses is
  **not** evidence of absence from their catalogue.
- **Mouser** (`mouser.com/c/?q=FKP1T031507G`) timed out; **TrustedParts**
  returned HTTP 403; **onsemi/DigiKey-class direct fetches** were variously
  blocked. These are tooling failures, not negative results, and are reported
  as such.

**Verdict: the string is not fabricated.** Unlike `DE1E3KX222MA4BA01` — which
spliced two incompatible codes and matched no datasheet row — every character
of `FKP1T031507G00JSSD` traces to a WIMA-printed field on a single sheet, and
the completion pattern is confirmed live on five sibling parts. **But
orderability is unconfirmed**, and the one aggregator that answered reports
zero distributor listings and zero stock on the nearest real neighbour. Treat
as a procurement risk. PR #401's instruction to "confirm at procurement"
stands and should not be relaxed on the strength of this document.

---

## Gap 2 — `H11L1TVM` isolation rating and certification

### 2.1 The premise of the open question was wrong

`elec/src/components.ato` (H11L1 docstring) and PR #401 both state:

> "the datasheet publishes V_ISO and a VDE 0884 file number but **NO
> creepage/clearance figure for the package**"

**This is refuted.** The datasheet publishes both, in a dedicated table.

The reason the earlier pass believed otherwise is visible in the scratch
artefacts: the onsemi copy it tried to fetch
(`onsemi.com/download/data-sheet/pdf/h11l1m-d.pdf`) returned a **403 Access
Denied HTML page**, saved with a `.pdf` extension. The document was never
actually read. The claims attributed to it were taken from elsewhere.

**Source obtained here: `H11L1M, H11L2M, H11L3M — 6-Pin DIP Schmitt Trigger
Output Optocoupler`, Fairchild Semiconductor (now onsemi), footer
`H11L1M, H11L2M, H11L3M Rev. 1.0.7`, © 2005. Retrieved from the Farnell
mirror `https://www.farnell.com/datasheets/1874889.pdf`, 2026-07-28, 10 pages,
text extracted with `pdftotext -layout`.** DigiKey's own datasheet link for
`H11L1TVM` (product 401266) points at `onsemi.com/pub/Collateral/H11L3M-D.PDF`
— the same document family, confirming this is the governing datasheet for
this orderable.

Note the `.ato` cites "rev. 1.0.0"; the document read here is **rev. 1.0.7**.

### 2.2 The orderable suffix — confirmed, with one correction

Ordering Information table, verbatim:

```
H11L1M        DIP 6-Pin                                                Tube (50 Units)
H11L1SM       SMT 6-Pin (Lead Bend)                                    Tube (50 Units)
H11L1SR2M     SMT 6-Pin (Lead Bend)                                    Tape and Reel (1000 Units)
H11L1VM       DIP 6-Pin, DIN EN/IEC60747-5-5 Option                    Tube (50 Units)
H11L1SVM      SMT 6-Pin (Lead Bend), DIN EN/IEC60747-5-5 Option        Tube (50 Units)
H11L1SR2VM    SMT 6-Pin (Lead Bend), DIN EN/IEC60747-5-5 Option        Tape and Reel (1000 Units)
H11L1TVM      DIP 6-Pin, 0.4” Lead Spacing, DIN EN/IEC60747-5-5 Option Tube (50 Units)
```

**`H11L1TVM` is an explicitly listed orderable.** `T` = 0.4" lead spacing,
`V` = the safety option, `M` = family. PR #401's decoding is **correct**.

**Correction:** the option is named **DIN EN/IEC 60747-5-5**, not "VDE 0884".
`components.ato` says `TV = VDE 0884 + 0.4" lead spacing`. IEC 60747-5-5 is
the successor standard to DIN VDE 0884 for optocoupler safety qualification,
so the intent is right and the part is the right part — but the string "VDE
0884" appears **nowhere** in this datasheet, and the `.ato` attributes it to
this datasheet's ordering table. Cosmetic, but it is a citation that does not
check out against the cited document.

### 2.3 The isolation ratings — this is the answer to the question

**Safety and Insulation Ratings** table, verbatim, including its preamble:

> As per DIN EN/IEC 60747-5-5, this optocoupler is suitable for "safe
> electrical insulation" only within the safety limit data. Compliance with
> the safety ratings shall be ensured by means of protective circuits.

| Parameter | Value | Unit |
|---|---|---|
| Installation Classifications per DIN VDE 0110/1.89 Table 1, For Rated Mains Voltage < 150 V<sub>RMS</sub> | I–IV | |
| … For Rated Mains Voltage < 300 V<sub>RMS</sub> | I–IV | |
| Climatic Classification | 55/100/21 | |
| Pollution Degree (DIN VDE 0110/1.89) | 2 | |
| Comparative Tracking Index | 175 | |
| V<sub>PR</sub> Method A, V<sub>IORM</sub> × 1.6, type/sample test t<sub>m</sub> = 10 s, PD < 5 pC | 1360 | V<sub>peak</sub> |
| V<sub>PR</sub> Method B, V<sub>IORM</sub> × 1.875, 100 % production test t<sub>m</sub> = 1 s, PD < 5 pC | 1594 | V<sub>peak</sub> |
| **V<sub>IORM</sub> Maximum Working Insulation Voltage** | **850** | **V<sub>peak</sub>** |
| V<sub>IOTM</sub> Highest Allowable Over-Voltage | 6000 | V<sub>peak</sub> |
| **External Creepage** | **≥ 7** | **mm** |
| **External Clearance** | **≥ 7** | **mm** |
| **External Clearance (for Option TV, 0.4" Lead Spacing)** | **≥ 10** | **mm** |
| DTI Distance Through Insulation (Insulation Thickness) | ≥ 0.5 | mm |
| T<sub>S</sub> Case Temperature (safety limit) | 175 | °C |
| I<sub>S,INPUT</sub> Input Current (safety limit) | 350 | mA |
| P<sub>S,OUTPUT</sub> Output Power (safety limit) | 800 | mW |
| R<sub>IO</sub> Insulation Resistance at T<sub>S</sub>, V<sub>IO</sub> = 500 V | > 10⁹ | Ω |

Features section, verbatim:

> Safety and Regulatory Approvals:
> – UL1577, 4,170 V<sub>ACRMS</sub> for 1 Minute
> – DIN-EN/IEC60747-5-5, 850 V Peak Working Insulation Voltage

### 2.4 What this means for this design — the finding

**The `T` lead form improves the wrong parameter.**

- It raises **external clearance** from ≥ 7 mm to ≥ 10 mm.
- It does **not** change **external creepage**, which the datasheet gives as
  **≥ 7 mm** with no TV-specific variant. That is physically expected:
  creepage runs over the package body surface, which the lead bend does not
  alter; only the through-air path between the spread leads gets longer.

`scripts/check_isolation_keepout.py` states its requirement in its own module
docstring and constant:

```
approximately 6.4mm CLEARANCE and 8.0mm CREEPAGE for reinforced insulation.
MIN_BARRIER_WIDTH_MM = 8.0
```

and prints `Required minimum barrier width: 8.0mm (REINFORCED creepage …)`.

So, against this repo's own numbers:

| Axis | Requirement | `H11L1TVM` published | Verdict |
|---|---:|---:|---|
| Clearance | ~6.4 mm | ≥ 10 mm (TV option) | **PASS**, comfortably |
| **Creepage** | **8.0 mm** | **≥ 7 mm** | **SHORT BY 1 mm** |
| Working voltage | ~170–340 V across the barrier (per `components.ato`) | V<sub>IORM</sub> = 850 V<sub>peak</sub> | **PASS**, ~2.5× margin |

PR #401 measured the *land pattern's* HV↔SELV pad separation at **8.560 mm**
and reported the U3 geometry as fixed. That measurement is not disputed — but
it measures **copper on the board**, and the **component sitting on that
copper only guarantees 7 mm of creepage across its own body.** The barrier is
only as good as its weakest element, and after PR #401 the weakest element is
the part, not the board.

**Stated as inference, clearly labelled as such** (this is my reasoning, not a
datasheet quote): under IEC 60664-1, reinforced insulation at ~250 V<sub>RMS</sub>
working voltage, pollution degree 2, material group IIIa (CTI 175 falls in
100 ≤ CTI < 400) calls for roughly 5.0 mm of creepage. On that basis ≥ 7 mm
would be adequate for the actual working voltage, and the conflict is
specifically with this repo's uniformly-applied 8.0 mm figure rather than with
the physics. **I am not recommending that 8.0 mm be relaxed** — the number was
chosen deliberately at the top of a stated range and this document changes no
thresholds. I am reporting that the part and the project's own requirement
disagree, and that a human has to reconcile them.

### 2.5 Pinout and die — confirmed unchanged

PR #401 assumed "same die, same pinout, different lead form". **Confirmed:**

- The datasheet's Figure 1 schematic gives **1 ANODE, 2 CATHODE, 3 (no
  connection), 4 V<sub>O</sub>, 5 GND, 6 V<sub>CC</sub>** — identical to the
  pin map in `components.ato`, and identical to the Everlight H11LX pinout
  (`DPC-0000022 Rev. 6`) the component was originally verified against.
- All seven orderables in §2.2 share one electrical specification table in one
  datasheet, and Note 3 states the part-number system "also applies to the
  H11L2M and H11L3M product families" — i.e. suffixes select lead form and
  safety-option testing, not die.

### 2.6 Two `.ato` claims that do not check out against the cited source

`components.ato` states the onsemi file numbers are "**UL E90700 vol.2 and
VDE #102497 per the H11LxM datasheet Features section**".

Searched in the extracted text of rev. 1.0.7: **`E90700` — 0 occurrences.
`102497` — 0 occurrences. `VDE 0884` — 0 occurrences. `reinforced` — 0
occurrences.** The Features section lists only the two lines quoted in §2.3.

These file numbers may well be correct — `102497` does surface in third-party
search results as onsemi's VDE file for this family — but they are **not in
the document the `.ato` cites for them**, and the word "reinforced" appears
nowhere in the datasheet at all. Flagged; **not corrected here**, because
`elec/src/*.ato` is out of scope for this branch.

---

## Issue 3 — the tank capacitor's AC rating at 47 kHz (**new; refutes PR #401**)

The task asked whether 1600 VDC covers the expected tank voltage, and
specifically whether the part's separate **AC** rating — which falls steeply
with frequency for film capacitors — was checked. **It was not, and it does
not.**

### 3.1 The design's own numbers

`elec/src/modules.ato` `ResonantTank` contains exactly one voltage check:

```
v_tank_peak: voltage = 400V
assert c_tank1.voltage_rating >= v_tank_peak * 1.43
```

i.e. 1600 V ≥ 572 V. **That is a DC comparison, and it is the only rating
check in the design.**

`docs/evidence/2026-07-27-zvs-operating-point.json` (provenance
`faf5171ad4a367d709a59a64f6bf36b9b765039a`) reports, at the committed
operating point — cast-iron/stainless pan, the full-power case:

| Quantity | Value |
|---|---:|
| `f_sw_hz` | 46 973.8 |
| `i_tank_rms_a` | **20.74** |
| `i_tank_pk_a` | 28.755 |
| `p_pan_w` | 1 803.65 |
| `v_ctank_max_v` | 331.05 |

The two capacitors are in parallel (`modules.ato`: "the two are in parallel
for 300nF total"), so **each carries 10.37 A RMS**.

**Consistency check (mine):** V<sub>rms</sub> = I / (2πfC) =
20.74 / (2π × 46 973.8 × 300 nF) = 20.74 / 0.088546 S = **234.2 V RMS**,
× √2 = **331.3 V peak** against the simulator's reported 331.05 V — agreement
to 0.08 %. The tank current does flow through the tank capacitors and the two
reported quantities are the same physical thing. That validates using
`i_tank_rms_a` as the capacitor current.

### 3.2 What WIMA actually permits at this frequency

**The 650 VAC in the ordering-table header must not be used here.** Its
footnote, verbatim from the same sheet as the ordering row:

```
* AC voltages: f ≤ 1000 Hz; 1.4 x Urms + UDC ≤ Ur
```

The 650 VAC figure is qualified **f ≤ 1000 Hz**. At 47 kHz the governing data
is the datasheet's frequency-derating charts.

**Source: same datasheet rev. `03.26`, sheet numbered 70, "Permissible AC
current in relation to frequency till 15° C internal temperature rise (general
guide). The information behind the cross bar denote the PCM of the measured
value."** Read by rendering the page at 200 dpi (`pdftoppm`) and reading the
plotted curves — `pdftotext` recovers the axis labels but not the curve
positions.

- **1600 VDC panel** plots `0.33 µF/37.5`, `0,047 µF/37.5`, `0.022 µF/27.5`,
  `4700 pF/22.5`, `100 pF/15`. **Our 0.15 µF/37.5 is not plotted**, but it is
  bracketed by the two PCM-37.5 curves: plateaus read ≈ **6.5 A** (0.33 µF)
  and ≈ **4 A** (0.047 µF). 47 kHz is well above both knees, so the plateau
  applies.
- **1250 VDC panel plots `0.15 µF/37.5` explicitly** — our exact capacitance
  and PCM, one voltage class down (in a smaller 17 × 29 case, so if anything
  conservative for the larger 20 × 39.5 mm 1600 V part). Its plateau reads
  ≈ **6 A**, with the knee at a few kHz.

**Taking ~6 A RMS as the permissible AC current at 47 kHz** (bracket 5–7 A,
given that reading a value off a log-log chart image carries real
uncertainty, and that the 0.15 µF curve is interpolated on the 1600 V panel):

| | Per capacitor |
|---|---:|
| Permissible AC current at 47 kHz (WIMA chart, 15 K rise) | ~6 A RMS |
| **Actual at the committed 1.8 kW operating point** | **10.37 A RMS** |
| **Overload factor** | **≈ 1.7×** (1.5× at the 7 A end of the bracket, 2.1× at the 5 A end) |

Equivalently on the voltage axis — the same constraint, since U and I are
linked by 1/(2πfC): permissible U<sub>rms</sub> = 6 A / (2π × 46 973.8 ×
0.15 µF) = **135.5 V RMS**, against an actual **234.2 V RMS**. Ratio 1.73 —
identical to the current ratio, as it must be. The two derating axes agree.

**At the pre-PR-#401 35 kHz operating point it was worse:** `i_tank_rms_a` =
33.021 A → **16.5 A per capacitor**, ≈ 2.7×.

### 3.3 What *does* pass, stated so the finding is not overread

- **DC voltage rating: passes with large margin.** 331.05 V peak observed
  against 1600 VDC — ~4.8×. PR #401's statement that the voltage rating is
  "unchanged at 1600 V, and now true" is correct **as a DC statement**.
- **dV/dt: passes by orders of magnitude.** Datasheet "Maximum pulse rise
  time" table gives **11 000 V/µs** for 0.1…0.22 µF at 1600 VDC. A 47 kHz
  sinusoid at 331 V peak has max dV/dt = 2πf·V<sub>pk</sub> ≈ 9.8 × 10⁷ V/s =
  **0.098 V/µs** — five orders of magnitude under. (Arithmetic mine; the
  11 000 V/µs figure is quoted.)
- **The 1600 VDC class is the right class.** Nothing here suggests a
  lower-voltage part.

**The failure is thermal, not dielectric.** The part will not flash over; it
will run hot.

### 3.4 Supporting estimate — explicitly my inference, not datasheet text

Dissipation-factor table, quoted: tan δ for 0.1 µF < C ≤ 1.0 µF is
**6 × 10⁻⁴ at 10 kHz**; the 100 kHz column for that capacitance band is
**"–" (not published)**. Using 6 × 10⁻⁴ as a floor:

ESR = tan δ / (2πfC) = 6 × 10⁻⁴ / 0.044273 S = 13.6 mΩ per capacitor
P = I²R = 10.37² × 0.0136 ≈ **1.5 W per capacitor** (and higher in reality,
since tan δ rises with frequency and 47 kHz is above the 10 kHz datum).

WIMA's chart defines its ~6 A limit as the current producing a **15 K internal
rise**. Loss scales as I², so 10.37 A implies ≈ 3× the reference dissipation
and — if rise is roughly proportional to power — an internal rise on the order
of **45 K**. Inside an induction-cooker enclosure the local ambient is
plausibly 50–60 °C, putting the internal temperature near or above the series'
**105 °C** maximum, in a region where the datasheet already mandates a
**1.35 %/K voltage derating above 75 °C for AC**. This chain is inference and
should be treated as motivation for a measurement, not as a number to design
to.

### 3.5 Why this matters and what it is not

- It is **not** an MPN-fabrication problem. `FKP1T031507G00JSSD` denotes a
  real catalogue part with the declared capacitance, voltage and case.
- It **is** a part-selection problem: the FKP 1 in this case size is a
  *pulse* capacitor, and the resonant tank of a 1.8 kW induction hob is a
  **continuous high-frequency AC** duty. Continuous-AC duty in this class is
  normally served by a resonant/induction-heating-rated film capacitor
  specified directly in A<sub>rms</sub> at tens of kHz.
- The natural mitigations — more capacitors in parallel to divide the current,
  or a series-resonant part rated in A<sub>rms</sub> — both change the BOM and
  the board, which is out of scope here.
- **This does not reopen the 300 nF value.** PR #401's ten-fold-value argument
  is independent of this and, as far as this pass can tell, correct: 300 nF is
  what the 47 kHz operating point, the PLL's 30–50 kHz range and every sweep
  in `simulation/harness/` are built on.

---

## Contradictions with PR #401, collected

1. **"the datasheet publishes … NO creepage/clearance figure for the
   package"** (`components.ato` docstring; PR #401 §B.2) — **false.** Rev.
   1.0.7 publishes external creepage ≥ 7 mm, external clearance ≥ 7 mm, and
   ≥ 10 mm clearance for the TV option. The earlier pass's copy of the
   datasheet was a 403 error page saved as `.pdf`.
2. **"Voltage rating: unchanged at 1600 V, and now *true*"** (PR #401 §A.4) —
   true on the DC axis, but the DC axis does not bind. The AC/frequency rating
   is exceeded by ~1.7×.
3. **`TV = VDE 0884`** (`components.ato`) — the datasheet names the option
   **DIN EN/IEC 60747-5-5**; "VDE 0884" does not appear in it.
4. **"UL E90700 vol.2 and VDE #102497 per the H11LxM datasheet Features
   section"** (`components.ato`) — neither number appears anywhere in the
   datasheet.
5. **The six completion digits were better-sourced than PR #401 claimed for
   itself** — a contradiction in the design's favour. They are not "carried
   over unchanged"; they are readable directly from the completion box on the
   same sheet as the ordering row.

---

## What I read from a source vs. what I inferred

**Read from a source:** every quoted table row, ordering code, completion box,
safety-rating value, footnote and feature line in §1.1, §2.2, §2.3, §3.2 and
§3.3; the Findchips "no results" string; the DigiKey datasheet-link target;
the `MIN_BARRIER_WIDTH_MM = 8.0` constant and its docstring; all figures
quoted from `2026-07-27-zvs-operating-point.json` and `modules.ato`.

**Read off a rendered chart** (weaker than text, disclosed as such): the
plateau currents in §3.2 — ~6.5 A (0.33 µF/37.5, 1600 V), ~4 A (0.047 µF/37.5,
1600 V), ~6 A (0.15 µF/37.5, 1250 V). A ±1 A reading error does not change the
verdict; a ±5 A one would.

**Inferred (mine, not sourced):** the 234.2 V RMS / 331.3 V peak consistency
check; the 135.5 V RMS permissible-voltage restatement; the 0.098 V/µs dV/dt;
the entire §3.4 thermal estimate; the IEC 60664-1 ~5 mm reinforced-creepage
comparison in §2.4; the claim that the TV lead form cannot change creepage.

**Could not verify:** a distributor listing or stock for
`FKP1T031507G00JSSD`; whether ±5 % (`J`) is actually stocked at 0.15 µF /
1600 V; a VDE or UL **certificate number** for `H11L1TVM` from a certifying
body's own register (only the datasheet's standard-and-rating statements were
obtained); onsemi's first-party copy of the H11L1M datasheet (403 on every
attempt — the Farnell mirror was used instead, and DigiKey's own link
corroborates the document family).

---

## Hard-constraint compliance

- `elec/src/*.ato`: **not modified.**
- `docs/hardware/BOM.md`, `pcb/temper.kicad_pcb`: **not modified.**
- `mpn-fabrication-allowlist.yaml`, `.evidence-provenance-allowlist`: **not
  modified**, nothing added.
- No gate, threshold or baseline touched in any direction.
- No part number was constructed, completed or pattern-matched. `00JSSD` was
  **re-derived from the datasheet's completion box**, not inferred from
  grammar and not carried over.
- This branch adds one file: this document.
