<!-- provenance: commit=b14959da381d70532efa8bc7af546ed490c75d25 dirty=false (worktree analysis/tank-fault-interruption, same branch/HEAD docs/evidence/2026-08-13-tank-fault-interruption.md (PR #1120) was written at; `origin/main` has moved on to 849c0ce63 since this branch's base a3e117347 but this document does not depend on anything that changed between them). This is a DATA-GATHERING pass, not a design decision: no file under `elec/src/**` or `pcb/**` is modified here (verified: `git status --porcelain` shows nothing under either path at the end of this session). `which ngspice`, `dpkg -l | grep ngspice`, and a filesystem search for an `ngspice*` binary or `.so` anywhere on this machine all return nothing (exit 1 / empty) -- checked fresh this session per the task's explicit instruction not to trust a prior "unavailable" report at face value; this one holds up. All datasheet and standards-text figures below carry their own fetch method, URL, and (where the source is a static file) a sha256, so a reader can re-fetch and diff. -->

# The four missing sizing inputs, sourced -- and a damped fault-current/I²t estimate to replace the ~1.1kA hand-bound ceiling

**Scope.** `docs/evidence/2026-08-13-tank-fault-interruption.md` (PR #1120, open) named four inputs missing from this repo before anyone could size a series fuse/breaker on the bus-capacitor bank against IEC 60335-1 clause 19.11.2(a): CT1 winding resistance, bus-capacitor ESR, loop trace resistance, and the applicable Table 9 limits. This document sources each one from the repo's own artifacts and real manufacturer/standards primary sources, computes a damped fault-current and I²t estimate from them, and translates that into what an interrupting device would need to survive/interrupt. **It does not choose a fuse, a breaker, or a capacitance value.** That decision is the owner's; this is the data it was waiting on.

**Verdict, up front.**

1. **CT1 is confirmed as the Coilcraft CST3015-100ED** (board reference `T1`, footprint `temper:CST3015`), and its datasheet primary-winding DCR is **0.0001 Ω (0.1 mΩ)** -- fetched directly from Coilcraft's own product page this session. It is electrically negligible in this loop (<0.1% of total loop resistance).
2. **The bus caps are confirmed as `EKMQ251VSN182MA50S`** (United Chemi-Con KMQ series, 1800 µF/250 V, ×2 parallel per half-bus = 3600 µF). The manufacturer's own catalog gives dissipation factor (tanδ), not a direct ESR-vs-frequency table; I derive **ESR ≈ 41 mΩ per half-bus bank at the loop's own ~283 Hz ring frequency** from tanδ and the catalog's ripple-current frequency-multiplier table, labelled clearly as a derived (not directly-tabulated) figure and as an upper bound (tanδ is a "max" spec).
3. **Loop copper resistance is bounded at ≤1.8 mΩ**, from real pad coordinates measured directly out of `pcb/temper.kicad_pcb`, using the repo's own IPC-2221B/2oz-copper method (`TRACE_WIDTH_CALCULATIONS.md`). **A correction to the task's own framing surfaced in the process**: the net the fault loop actually closes through is `PWR_RTN`, not `DC_BUS_RTN` -- they are two distinct, non-touching copper nets on this board (Sec 3.1). I computed the resistance for the net that is actually in the loop.
4. **IEC 60335-1 Table 9 ("Maximum Abnormal Temperature Rise") is recovered, verbatim, from the same primary source the prior creepage determination used** (IS 302-1:2008, archive.org, same file, same sha256). It does **not** give a current or I²t figure for fuse sizing -- it gives temperature-rise ceilings on three specific things (wooden test-corner surfaces, supply-cord insulation, supplementary/reinforced insulation), none of which is "the fuse" or "the coil." The table that would actually bound *this* fault's windings (Table 8, "Maximum Winding Temperature," invoked by clause 19.11) exists in the same source but its class-by-class numeric values are OCR-column-garbled in a way I could not safely reassign, and this repo does not record CT1's or the coil's winding-insulation class regardless. **Named as a real, still-open gap, not filled with a guess.**
5. **Replacing the hand-bound ~1.1 kA undamped ceiling**: with all three now-sourced resistances in the loop (coil DCR 0.1 Ω + CT1 0.0001 Ω + cap ESR ≈41 mΩ + pour ≤1.8 mΩ ≈ **143 mΩ total**), the loop is underdamped (ζ≈0.46, not lightly damped) and the **damped peak fault current is ≈620 A at t≈694 µs** (bracket 619–710 A depending on how much of the derived cap-ESR figure is trusted; both well below, and a materially different design point from, the undamped 1.1 kA/880 µs figure). I²t at the current peak is **≈147 A²·s**; by 1 ms it is **≈255 A²·s**. Sec 6 shows the full working and a model self-check (integrated R-dissipation converges to the independently-known 52 J stored energy).
6. **What that means for a real part** (Sec 7): a DC-rated device (no AC zero-crossing to help interruption) at ≥250 V (matching the cap rating; the half-bus is 170 V nominal), continuous rating compatible with the existing ~15–22 A duty (`TRACE_WIDTH_CALCULATIONS.md`), and let-through I²t low enough to protect whatever Table 8/Table 3's still-missing winding-temperature figures turn out to require -- which is the one number in this chain I could not close. A standard AC glass/ceramic fuse is very likely the wrong physical form for this; a DC-interrupting fuse or breaker class is not.

---

## 1. CT1 winding resistance

### 1.1 What CT1 actually is, verified independently

`elec/domain_manifest.yaml:387-394` names `ct_sense.ct` (OCP-01's CT, the one in the tank-return/fault loop) as `"Coilcraft CST3015-100ED (CST3015_100E), current sense transformer"` -- the same MPN the task said the *manifest* claims the OCP-02 twin (`safety.ocp2.ct`, `domain_manifest.yaml:405-413`) shares. I verified this is not just a manifest claim by checking the actual board: `pcb/temper.kicad_pcb` has exactly one footprint of type `temper:CST3015` (grep, `pcb/temper.kicad_pcb:6466`), board reference **`T1`**, whose own embedded description string (line 6469) reads *"Coilcraft CST3015 SMT current sense transformer (CST3015-100ED, 1:100, 88A sensed, 5000Vrms reinforced isolation, >=8mm creepage/clearance, AEC-Q200 Grade 1)... Replaced CST2010-100L 2026-07-26."* `docs/hardware/BOM.md:244` independently agrees: `CT1 | Current Transformer | CST3015-100ED | Coilcraft | 1 | SMD | 1:100, senses to 88A, 5000Vrms reinforced, >=8mm creepage`. Three independent artifacts (manifest, placed footprint, BOM) agree on the same part. **CT1 is a real, single, correctly-identified Coilcraft CST3015-100ED**, not a stand-in or a stale reference.

### 1.2 The datasheet figure, fetched directly

Coilcraft's product page (`https://www.coilcraft.com/en-us/products/transformers/power-transformers/current-sensing/cst3015/cst3015-100e/`) 403's on a direct `curl`/`WebFetch` (Cloudflare bot-challenge, consistent with the 403s this session hit on DigiKey and Sourcengine for the same reason). I retrieved the same page's rendered content via a text-extraction proxy (`r.jina.ai`) this session, saved verbatim (`cst3015_jina.txt`, sha256 `00e80f71e9aac8fc10d8b8cb3d2e5060b2ade6e5b4d3f8e45a89eb7f8538e95d`), and cross-checked the load-bearing numbers against an independent web search that had returned the same figures before I fetched the primary page myself -- two independent retrievals agree:

**CST3015-100ED, "Specifications," electrical specifications at 25°C (as printed on the page):**

| Inductance (mH) | DCR Pri (Ω) | DCR Sec (Ω) | Turns ratio | Volt-time product (V·µs) | Frequency (kHz) | Sensed current (A) | Terminating R (Ω) | Isolation (Vrms) |
|---|---|---|---|---|---|---|---|---|
| 3.2 | **0.0001** | 1.5 | 1:100 | 638 | 0.78 – >1000 | 88.0 | 1.0 | 5000 |

Note 6 on the same page: *"5000 Vrms, one minute isolation (hipot) winding to winding."* Note 4: *"DC current through the primary... causes a 40°C rise at 25°C ambient."*

**CT1's primary winding DCR = 0.0001 Ω (0.1 mΩ).** This is a real, checkable figure (single-turn primary through a small ferrite core -- a fraction of a milliohm is physically unsurprising for that geometry) and is the number the fault-current model in Sec 6 uses. It contributes **<0.1% of total loop resistance** -- negligible next to the coil's 100 mΩ, but sourced rather than assumed, per the task.

---

## 2. Bus-capacitor ESR

### 2.1 The real part

`docs/hardware/BOM.md:57`: `C_BUS1, C_BUS1B, C_BUS2, C_BUS2B | Bus Capacitors | EKMQ251VSN182MA50S | United Chemi-Con | 4 | Radial Snap-In 35mm | 1800µF 250V 105°C — 2 in parallel per half-bus (3600µF/half)`. `elec/src/modules.ato:795-822` confirms the same MPN, value, and footprint (`Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`) for all four instances (`c_bus1`, `c_bus1b`, `c_bus2`, `c_bus2b`). `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` (read in full, not modified) is the repo's own prior first-principles pass on this same part; it already establishes the ±20% capacitance tolerance (fetched from the DigiKey product page, §5.1) and recommends ~3000 µF/half for an unrelated reason (`BusDischarge` hold-up-time margin, not ripple, not this fault) -- carried forward as context in Sec 8, not re-derived here.

### 2.2 What the manufacturer datasheet actually gives, and what it doesn't

I fetched the primary Chemi-Con KMQ-series catalog directly (`https://chemi-con.com/wp-content/uploads/2021/05/KMQ-Series-1.pdf`, 292,198 bytes, sha256 `1e6c0c241393f983aca540278536bd6ea5c9ab95d17ab19c6425f53538f7480a`, `CAT. No. E1001U`) and read it with `pdftotext -layout`, not a summarizer. It does **not** publish an ESR-vs-frequency table. What it publishes, verbatim:

- **Dissipation factor (tanδ):** *"at 20°C, 120Hz"*, table by rated voltage and capacitance band. For the 160–250 Vdc band at C≥10,000µF: 0.15 (this part is 1800µF, below that band's threshold, but the 250 Vdc row's own standard-ratings table (line 199 of the extracted text) lists `1,800 | 35×50 | 0.15 | 2.70 | EKMQ251VSN182MA50S` directly against the exact MPN -- **tanδ(max) = 0.15 at 20°C, 120 Hz, for this specific part**, not an inferred bucket.
- **Rated ripple current:** 2.70 Arms at 105°C, 120Hz (same row) -- matches `elec/src/modules.ato`'s own comment ("2x 2.7Arms@120Hz ripple rating per half") and `BUS_CAPACITANCE_DERIVATION.md`'s §3 table, both independently.
- **Rated-ripple-current frequency multiplier table** (§"RATED RIPPLE CURRENT MULTIPLIERS," 160–250 Vdc column): 50 Hz→0.81, **120 Hz→1.00, 300 Hz→1.17**, 1 kHz→1.32, 10 kHz→1.45, 50 kHz→1.50.

No ESR number is stated anywhere in this document at any frequency. ESR has to be derived from tanδ, which the datasheet does license (tanδ = ESR·2πfC is the standard definition, not an invented relation).

### 2.3 Deriving ESR at the frequency that actually matters

The switching frequency (~38–40 kHz) and the 120 Hz line-ripple frequency are both the *wrong* frequency for this fault: the fault loop is a series LC ring between the coil (88 µH) and the half-bus bank (3600 µF), and its own natural frequency is **f₀ = 1/(2π√(LC)) ≈ 283 Hz** (Sec 6.1) -- close to line-adjacent, nowhere near the switching frequency. At 120 Hz:

```
X_C(120Hz) = 1/(2π × 120 × 1800µF) = 0.7371 Ω
ESR(120Hz, max) = tanδ_max × X_C = 0.15 × 0.7371 Ω = 110.5 mΩ   (single 1800µF cap)
```

To move this to ~283 Hz I use the datasheet's own ripple-current frequency-multiplier table (Sec 2.2), log-interpolated between its 120 Hz and 300 Hz points to 282.8 Hz: multiplier ≈ **1.159**. The standard vendor convention behind such a table is that the multiplier represents the ratio by which allowable RMS current may increase for equal internal (I²·ESR) heating as frequency rises -- i.e. `ESR(f) ≈ ESR(120Hz) / multiplier(f)²`. This is a **derived quantity from a real datasheet value via a stated, standard formula**, not a fabricated ESR-vs-frequency curve:

```
ESR(283Hz, single cap, upper bound) = 110.5mΩ / 1.159² = 82.3 mΩ
ESR(283Hz, half-bus bank, 2×1800µF parallel) = 82.3mΩ / 2 = 41.1 mΩ
```

**Labelled explicitly:** this is an upper bound (tanδ is a "max" spec, not a typical value) and a derived figure (the datasheet gives tanδ + a ripple-current frequency curve, not ESR-vs-frequency directly). Sec 6.3 shows the fault-current answer bracketed against a "zero cap-ESR" floor so the reader can see how much of the final number rides on this specific derivation.

---

## 3. Loop trace/pour resistance

### 3.1 A correction to the task's own framing, found while measuring it

The task asks to derive resistance for "the `DC_BUS_RTN` / bus-cap loop geometry." Checking `pcb/temper.kicad_pcb` directly (net declarations at lines 41 and 49): **`DC_BUS_RTN` is net 5, `PWR_RTN` is net 13 -- two distinct KiCad nets**, not two names for the same copper. Tracing which one CT1 (`T1`) and the relevant bus caps actually sit on (own s-expression parse of the board file, absolute pad coordinates computed from each footprint's placement `(at x y rot)` plus each pad's local `(at)`, described in full in Sec 3.2):

- `T1` (CT1) pin 2 -- the primary-return pin, i.e. `ct_sense.primary_out ~ power_return` in `elec/src/main.ato:824` -- sits on **`PWR_RTN`**, not `DC_BUS_RTN`.
- The bus caps on that same net are **`C2`** (pad1=`+170V_BUS`, pad2=`PWR_RTN`) and **`C4`** (same pattern) -- these are `c_bus1`/`c_bus1b`, the upper half-bus pair the prior determination's own loop citation names (`c_bus1 + c_bus1b`, `2026-08-13-tank-fault-interruption.md` Sec 2.1).
- `DC_BUS_RTN` (net 5) is a *different* physical node: it's the doubler's bottom rail (`dc_bus_minus`/`hv_minus`), carried by `C3`/`C5` (`c_bus2`/`c_bus2b`, the *lower* half-bus pair) and connects to `PWR_RTN` only through the two IGBTs and the tank, not through any direct copper.

This matches how the rest of this repo treats these two nets -- independently, in at least eight other evidence documents that were not written for this task (`docs/evidence/2026-07-28-hv-isolated-rules-and-creepage-triage.md:299`, `docs/evidence/2026-07-28-pour-strategy-audit.md:115-129`, `docs/evidence/2026-08-11-schematic-elec-drift.md:222`, `docs/evidence/2026-08-11-true-pad-connectivity-baseline.md:103`, and others), all of which list `DC_BUS_RTN` and `PWR_RTN` as two separate nets with separate pad counts and separate zone geometry. **This is not a parsing artifact of this session; it is the board's real, well-established net structure.** I computed the resistance for `PWR_RTN`, the net that is actually in the fault loop the prior document cited, and I'm flagging the naming mismatch so a future reader who goes looking for "the `DC_BUS_RTN` resistance" for *this* loop doesn't measure the wrong node.

### 3.2 Geometry, measured from the board file

Method: parsed `pcb/temper.kicad_pcb` as an s-expression (own script, `/tmp/.../scratchpad/parse_pcb.py` -- not committed, ephemeral per this repo's own convention for scratch analysis scripts), extracted every footprint's placement and every pad's local offset/rotation, and computed absolute board-space coordinates for every pad. Cross-checked against `docs/hardware/BOM.md`/`elec/src/modules.ato` reference-designator mapping.

| Ref | Role | Pad | Net | Absolute position (mm) |
|---|---|---|---|---|
| `T1` | CT1, primary return (pin 2) | 2 | `PWR_RTN` | (60.06, 141.23) |
| `C2` | `c_bus1`/`c_bus1b` (one of the pair) | 2 | `PWR_RTN` | (103.48, 64.84) |
| `C4` | `c_bus1`/`c_bus1b` (the other) | 2 | `PWR_RTN` | (86.46, 198.34) |

Straight-line pad-to-pad distances: **T1↔C2 = 87.87 mm, T1↔C4 = 62.92 mm.**

### 3.3 What copper actually connects them, and why the resistance is a bound, not a measurement

`pcb/temper.kicad_pcb` has **zero routed track segments and zero vias on net 13** (grepped directly: `0 segments, 0 vias`) -- the entire `PWR_RTN` connection is carried by two large copper-fill zones (one per outer layer, `F.Cu`/`B.Cu`, `(zone (net 13) (net_name "PWR_RTN") ...)`). Critically, **the saved board file has zone outlines but no computed `filled_polygon` data** (`grep -c filled_polygon pcb/temper.kicad_pcb` → 0) -- the actual as-poured copper shape has never been computed/saved for this board revision, so I cannot read off a real fill width. What I *can* say: this repo's own `docs/evidence/2026-07-28-pour-strategy-audit.md:115` independently measured `PWR_RTN`'s zone hull at **17,546.3 mm²** on a single outer layer -- roughly half the board's own ~35,000mm²-class area -- so the real pour is very wide relative to a 5mm trace, not a narrow corridor.

Given that, I computed a **deliberately conservative (upper-bound) resistance** using this repo's own stated minimum DC-bus pour width (5.0mm, `TRACE_WIDTH_CALCULATIONS.md` §3.1, "Minimum trace width: 5.0mm (200 mils) with copper pour preferred") and its own copper spec (2oz/70µm outer, same document's Design Parameters table) and resistivity constant (ρ=1.68×10⁻⁸ Ω·m, same document §6):

```
Rs (sheet resistance, 2oz copper) = ρ/t = 1.68e-8 / 70e-6 = 0.24 mΩ/square

R(T1-C2) = Rs × (87.87mm / 5mm) = 4.22 mΩ
R(T1-C4) = Rs × (62.92mm / 5mm) = 3.02 mΩ
```

Both caps return current to `T1` in parallel (they're both part of the same `c_bus1`+`c_bus1b` parallel pair), so the effective loop contribution is their parallel combination:

```
R_pour ≈ (4.22 × 3.02) / (4.22 + 3.02) = 1.76 mΩ
```

**This is an upper bound.** Since the real `PWR_RTN` pour is documented elsewhere in this repo as covering roughly half the board's area (not a 5mm-wide corridor), the true resistance is almost certainly a fraction of 1.76mΩ. I'm reporting the bound rather than a guessed "true" width because the file doesn't contain the fill data needed to compute one honestly. **Either way, this term is small**: even at this conservative bound it's ~1.2% of total loop resistance (Sec 6.2).

---

## 4. IEC 60335-1 Table 9

### 4.1 Same primary source, re-verified

`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` recovered IEC 60335-1's clause and table text this project needed from IS 302-1:2008 (the Bureau of Indian Standards' identical adoption of IEC 60335-1), an OCR'd scan published under India's RTI Act at `https://archive.org/download/gov.in.is.302.1.2008/is.302.1.2008_djvu.txt`. I re-fetched the same URL this session: **312,769 bytes, sha256 `2695a4bc1b2c87dd24a6126d984d01ad30be53c8d905ff196b73241b73f99251`** -- identical to the hash that document records, confirming I'm reading the same artifact, not a different edition or a corrupted re-download.

### 4.2 Table 9, transcribed verbatim

Located at line 4344 of the OCR text layer, under clause 19.13 (the fire/temperature-rise acceptance criterion for the abnormal-operation/fault-condition test -- the same clause the prior determination already quoted in full). **Unlike Table 18 or Table 3 (Sec 4.3), Table 9 is a short table whose values print immediately adjacent to their row labels in the OCR text -- no multi-column reordering to untangle:**

> **Table 9 Maximum Abnormal Temperature Rise** (Clauses 19.13 and 20.1)
>
> | SI No. | Part | Temperature Rise, K |
> |---|---|---|
> | i) | Wooden supports, walls, ceiling and floor of the test corner and wooden cabinets [¹] | 150 |
> | ii) | Insulation of the supply cord [²] | 150 |
> | iii) | Supplementary insulation and reinforced insulation other than thermoplastic materials [³] | 1.5 times the relevant value specified in Table 3 |
>
> ¹ For motor-operated appliances these temperature rises are not determined. [OCR-superscript-damaged footnote markers; the referent of each footnote to its row is legible, the exact footnote-number glyphs are not.]
> ² There is no specific limit for supplementary insulation and reinforced insulation of thermoplastic material. However, the temperature rise has to be determined so that the test of 30.1 can be carried out. [this footnote text appears to belong with row iii per its content, not row ii as OCR position suggests -- flagged, not resolved, see Sec 4.4]

### 4.3 What Table 9 actually constrains -- and the load-bearing negative finding

**Table 9 does not name a current, an energy, or an I²t figure anywhere.** It constrains temperature rise on three specific things: (i) wooden test-corner surfaces and cabinets, (ii) supply-cord insulation, (iii) supplementary/reinforced insulation (via a multiplier on Table 3's normal-operation limits). **None of its three rows is "printed circuit board," "current transformer winding," "inductor winding," or "fuse."** A fuse or breaker sized against "Table 9" is not sized against a number pulled from this table -- it is sized so that *whatever Table 9 does cover that's physically near the fault* (if this appliance has wooden cabinetry, or the supply cord, within thermal reach of the fault) stays under its ceiling during the clause-19 test, which is a physical-test or thermal-model question, not a lookup. This is a genuine, checkable finding, and it means: **even with the fault-current/I²t figure in Sec 6, "does this pass Table 9" is not arithmetic against this document's numbers -- it requires knowing what's physically near the fault site and either testing it or thermally modeling it.**

### 4.4 The table that *does* bear on CT1/the coil, found but not fully recoverable

Clause 19.11 (immediately preceding 19.13, governing the same electronic-circuit fault-condition test 19.11.2(a) triggers) states directly: *"During and after each test, the temperature of the windings shall not exceed the values specified in Table 8."* (line 3863-3865). **CT1 and the tank coil are both windings** -- this is the table that actually bears on the fault path's magnetics, more specific than Table 9. I located it (line 3869, "Table 8 Maximum Winding Temperature," Clauses 11, 19.1, and 19.11) and it exists, structured by insulation class (A/E/B/F/H/200/220/250) and appliance operating regime (impedance-protected vs. protective-device-protected, first-hour vs. after-first-hour). **I could not safely transcribe its numeric values**: the OCR text layer separates the row labels from their values across the multi-column table layout (the same failure mode `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` Sec 7 already flagged for Table 3, and explicitly declined to guess through -- I am applying the same discipline here rather than a different one for a table that happens to matter to my own computation). A visible fragment of numbers (`200, 150, 215, 165, 225, 175, 240, 190, 260, 210`) appears after the row list but I cannot responsibly assign which value belongs to which insulation class/regime without risking exactly the kind of fabricated-looking-real number the task prohibits.

**Independently, this repo does not record a winding-insulation class for CT1 or `inductor_conn` (the tank coil) at all** -- `elec/src/modules.ato:619-622` gives the coil's value, current rating, DCR, and a placeholder MPN (`"CUSTOM_LITZ_COIL"`), but no insulation class; the Coilcraft CST3015 product page (Sec 1.2) likewise states operating temperature range but not an IEC insulation class letter. So even a clean copy of Table 8 would not resolve which column applies without that additional input.

**Stated plainly, as the task asks for a clearly-stated gap rather than an invented figure:** *what is missing* is (a) a non-OCR or better-quality copy of IEC 60335-1 Table 8 (values only -- the row structure and clause citations are already established here) and Table 3 (needed for Table 9's own item iii and for interpreting Table 8's normal-condition baseline), and (b) a stated winding-insulation class for CT1's and the coil's magnet wire, neither of which exists in this repository today.

---

## 5. `ngspice`, verified fresh

Per the task's specific instruction not to trust a prior "unavailable" report without re-checking (the cited `RouterPipeline` stale-`.so` trap): checked independently this session, three ways --

```
$ which ngspice          → (nothing, exit 1)
$ ngspice -v              → "command not found"
$ dpkg -l | grep -i ngspice   → (nothing)
$ find / -iname "ngspice*" -type f  (excluding /proc)  → (nothing, anywhere on the machine)
```

This is a genuine, machine-wide absence, not a stale build artifact -- there is no `ngspice` binary or shared library anywhere on this system to be stale. `simulation/harness/nets/` does exist and contains real `.cir` decks (`ocp01_trip_point.cir`, `zvs_margin_sweep.cir`, etc.) that presumably ran successfully in whatever environment originally produced the RMS/ZVS figures `TANK_COIL_SPECIFICATION.md` and `BUS_CAPACITANCE_DERIVATION.md` cite -- but none of them is a 19.11.2 fault-injection deck (confirmed by directory listing; no filename or docstring references this fault), and none can be run here regardless. **All computation in Sec 6 is a closed-form (undamped-then-damped series RLC) hand/numeric derivation, not a SPICE result**, exactly as the prior determination's figure was, and is labelled as such throughout.

---

## 6. Fault-current and I²t estimate, replacing the ~1.1 kA undamped ceiling

### 6.1 The circuit and its inputs, all now sourced

Loop (from `docs/evidence/2026-08-13-tank-fault-interruption.md` Sec 2.1, restated): `+170V_BUS → short → tank.c_tank1-p2 → L(88µH) → tank.out → CT1 primary → PWR_RTN → c_bus1‖c_bus1b(3600µF) → back to +170V_BUS`. A series RLC, source-free after the initial short (driven only by the half-bus bank's own stored charge, ignoring the slower ~16.7ms mains-recharge cycle the prior document also noted as a secondary sustaining mechanism it did not model).

| Symbol | Value | Source |
|---|---|---|
| V₀ | 170 V | half-bus peak, `elec/src/main.ato` `v_bus_nominal/2`, carried from prior doc |
| L | 88 µH | `elec/src/modules.ato:620`, `inductor_conn.value = 88uH +/- 10%` |
| C | 3600 µF | 2×`EKMQ251VSN182MA50S` per half-bus, Sec 2.1 |
| R_coil | 0.100 Ω | `elec/src/modules.ato:621`, `inductor_conn.dcr = 0.1ohm` -- itself sourced in-repo from a chart-reading of an Infineon eval-board coil (same comment block, lines 577-580), which also flags a *different*, larger AC figure (~0.34Ω at 40kHz, skin/proximity-inclusive) as **not applicable here**: the fault ring frequency (Sec 6.1, ~283 Hz) is close enough to DC that the DC figure, not the 40kHz operating figure, is the right one -- I verified this reasoning against the source comment rather than assuming it. |
| R_CT1 | 0.0001 Ω | Coilcraft CST3015-100ED datasheet, Sec 1.2 |
| R_cap (bank) | 0.0411 Ω | derived, upper bound, Sec 2.3 |
| R_pour | ≤0.0018 Ω | derived, upper bound, Sec 3.3 |
| **R_total** | **≈0.1430 Ω** | sum |

R_total breakdown: coil DCR is **69.9%** of total loop resistance, cap ESR **28.8%**, pour **1.2%**, CT1 **0.07%** -- the two inputs the prior document specifically lacked (CT1 DCR, pour resistance) turn out to be nearly irrelevant to the answer; the coil's own already-known DCR and the newly-derived cap ESR are what actually set the damping.

### 6.2 Damped response, closed form (and a numerical cross-check)

Series RLC step response from an initially-charged capacitor: `i(t) = (V₀/(ω_d L)) e^(-αt) sin(ω_d t)`, with `α = R/(2L)`, `ω₀ = 1/√(LC)`, `ζ = α/ω₀`, `ω_d = ω₀√(1-ζ²)`.

```
ω₀ = 1776.7 rad/s   →   f₀ = 282.8 Hz, T₀ = 3.536 ms   (matches the prior doc's "~3.5ms" almost exactly -- cross-check)
Z₀ = √(L/C) = 0.1563 Ω   (matches the prior doc's Z₀≈0.156Ω -- cross-check)
α  = R_total/(2L) = 812.5 s⁻¹
ζ  = α/ω₀ = 0.457    →  underdamped, meaningfully damped (not a light ring)
ω_d = 1580.0 rad/s   →  f_d = 251.5 Hz  (11% lower than the undamped ring frequency)

t_peak = (1/ω_d)·arctan(ω_d/α) = 693.6 µs
i_peak = 618.9 A
```

Verified two independent ways: (1) the closed-form `t_peak`/`i_peak` above, and (2) a 2-million-point numerical grid evaluation of the same `i(t)` finding its own maximum (693.56µs / 618.91A -- agrees to sub-0.1% with the closed form). (3) **Energy self-check**: integrating `R_total·i(t)²` over the full ring-down (0–40ms, ~11 damped periods) gives **52.02 J**, matching `½CV₀² = 52.02 J` (the independently-known stored energy) to 4 significant figures. This doesn't validate any individual R value, but it does confirm the model is implemented correctly (energy is conserved into the resistance as it should be for a source-free RLC circuit) -- a check the prior document's undamped model couldn't run, since undamped energy never gets dissipated at all.

**Peak damped fault current ≈ 619 A at t≈694 µs** -- down from the prior undamped 1.1kA/880µs bound (this session's own undamped re-run at R=0 reproduces **1087.3 A**, confirming the prior figure), a **~43% reduction** attributable to the now-quantified loop resistance, dominated by the coil's own DCR.

### 6.3 Sensitivity bracket -- how much rides on the derived cap-ESR figure

The cap-ESR figure (Sec 2.3) is a derived upper bound from a "max tanδ" spec, not a measured or guaranteed value -- real parts often run somewhat below the datasheet max, which would mean *less* damping and a *higher* real peak current than 619A. Bracketing:

| Scenario | R_total | i_peak | t_peak | ζ |
|---|---|---|---|---|
| Coil + CT1 + pour only (cap ESR = 0, i.e. if the real ESR turned out negligible) | 0.1019 Ω | **709.5 A** | 737.6 µs | 0.326 |
| **This document's derived figure (cap ESR from max tanδ)** | **0.1430 Ω** | **618.9 A** | 693.6 µs | 0.457 |
| Undamped (R=0), the prior document's own bound, reproduced here | ~0 Ω | 1087.3 A | 884.1 µs | 0 |

**Defensible range: peak fault current is 619–710 A**, both figures a substantial (35–43%) reduction from the undamped 1.1kA ceiling, and both far better characterized (every input sourced, working shown, energy-conserving) than a hand-waved damping factor.

### 6.4 I²t vs. time (available fault energy, for comparison against a candidate device's let-through I²t)

Computed by numerical integration of `i(t)²` at the nominal (R=0.1430Ω) parameter set:

| Horizon | I²t (A²·s) |
|---|---|
| 100 µs | 1.10 |
| 250 µs | 13.95 |
| 500 µs | 76.26 |
| 693.6 µs (current peak) | 147.32 |
| 1000 µs | 254.94 |
| 1761.6 µs (first half damped period) | 348.67 |

**This is the fault's own available I²t as a function of time, not a fuse's let-through I²t** -- a real device interrupts before the current reaches these levels if its own melting/clearing I²t is lower, which is the whole point of choosing one. It is the number a candidate device's datasheet total-clearing-I²t curve needs to be checked against, and (per Sec 4.3-4.4) the number the coil/CT1/PCB's own withstand -- itself gated on the still-missing Table 8 winding-class data -- needs to be checked against from the other side.

---

## 7. What the interrupting device would have to be

Not a part selection -- the four properties a human would screen candidates against, each tied to a number established above:

1. **Interrupting/breaking rating**: must clear a DC fault (no AC zero-crossing to assist arc quenching) with a peak available current of **≥620–710 A** (Sec 6.3's bracket) with real margin -- given the uncertainty already in the chain (cap ESR is a derived bound, not measured; the coil DCR is itself a chart-read approximation per its own source comment, Sec 6.1), sizing toward the top of the bracket, or beyond it, is the conservative direction. A device rated only for its steady-state current (~15-22A, `TRACE_WIDTH_CALCULATIONS.md`) with no stated DC interrupting rating at this current level is the wrong class of part regardless of continuous-current fit.
2. **Voltage rating**: DC, ≥250 V to match the cap's own rating margin (the half-bus is 170V nominal; the caps themselves carry 47% margin over that per `BUS_CAPACITANCE_DERIVATION.md` §1.1). Because this is DC with no natural current zero, the device's voltage rating must be an explicit **DC interrupting rating** (a fuse or breaker's AC voltage rating does not transfer to DC service at the same figure -- this is a standard, well-known distinction in fuse/breaker selection, not a number this repo needed to supply).
3. **I²t withstand**: needs to be characterized against Sec 6.4's table (147 A²·s by the current peak, 255 A²·s by 1ms) on the let-through side, and against whatever Table 8's winding-temperature ceiling for CT1/the coil's actual insulation class turns out to be on the withstand side (Sec 4.4) -- **this second half is the one genuine numeric gap this document could not close**, and it is the one that would actually tell a reviewer whether a given fuse's let-through energy is "clearly safe" or "right at the edge."
4. **Physical form**: in-series with the half-bus bank, continuous-duty-rated for the existing ~15-22A path current without nuisance tripping, in a DC-rated fuse or breaker class (e.g., the same general class used for automotive/EV/solar DC bus protection, which is designed to interrupt DC arcs at voltages in this range) rather than a general-purpose AC glass/ceramic fuse -- which is very likely the wrong physical form here given point 2. Routing/placement impact on `pcb/**` is real but out of this document's scope (no `pcb/**` file was opened for writing this session), and the prior document's Sec 1.4 already flagged that this board's clearance/connectivity budget is already strained before adding a new footprint.

---

## 8. Interaction with `BUS_CAPACITANCE_DERIVATION.md`'s 3000µF/half recommendation

That document (read in full, not modified here) recommends reducing the bus bank from 3600µF/half to ~3000µF/half for an unrelated reason (`BusDischarge` hold-up-time tolerance margin, §5) and flags it as provisional (§7, blocked on a separate tank-Q measurement) with an unverified replacement part (§9). Recomputing this document's own damped-RLC model at that value, same method, same coil/CT1/pour inputs, cap ESR re-derived for a ~1500µF-class cell at the same max-tanδ assumption:

| | Installed (3600µF/half) | Recommended (3000µf/half, UNVERIFIED part) |
|---|---|---|
| Undamped f₀ | 282.8 Hz | 309.8 Hz |
| R_total | 143.0 mΩ | 149.8 mΩ (higher-ESR smaller cans) |
| ζ | 0.457 | 0.437 |
| i_peak | 618.9 A | 576.2 A |
| t_peak | 693.6 µs | 638.8 µs |
| Stored energy E₀ | 52.02 J | 43.35 J |

**Consistent with the prior document's own characterization**: a ~17% energy cut buys a modest (~7%) peak-current reduction, not an order-of-magnitude change, and does not alter the qualitative conclusion of Sec 6 -- the loop is still underdamped, the peak current is still several hundred amps, and an interrupting device sized against the installed 3600µF case is not meaningfully oversized if the 3000µF change lands later.

---

## 9. What this document does not do

- **It does not choose a fuse, a breaker, or a capacitance value.** Sec 7 states requirements, not a part number.
- **It does not run `ngspice`.** Confirmed unavailable machine-wide, fresh, this session (Sec 5). All computation is closed-form/numeric, cross-checked against energy conservation and against the prior document's own undamped figure, but it is not a circuit simulation.
- **It does not close the Table 8 winding-temperature gap.** Sec 4.4 names exactly what's missing (a clean Table 8 + Table 3 copy, and a stated winding-insulation class for CT1/the coil) rather than filling it with a plausible-looking number.
- **It does not resolve the pre-existing tank peak-current conflict** (`elec/src/constraints.ato:8`'s `i_max=25A` vs. the 28.7-31.9A recorded tank peak, `elec/src/modules.ato:585-593`) -- unrelated to this fault loop's own current, not touched.
- **It does not modify `elec/src/**` or `pcb/temper.kicad_pcb`.** Verified clean at the end of this session.
- **It does not re-litigate whether a series fuse/breaker is the right route** vs. the other three routes `docs/evidence/2026-08-13-tank-fault-interruption.md` already enumerated and ranked -- that determination stands; this document only sources the inputs its own Sec 6 recommendation named as missing.
