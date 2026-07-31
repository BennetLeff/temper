# OVP-01 protective-impedance crossings: standard clause, independent re-derivation, and correction to the repeated margin figure

<!-- provenance: commit=d0553d2617381c40ed850ed775b38c34578d1c48 dirty=false -->

**Date written:** 2026-07-30 (backfilling a citation dated 2026-07-26 in the
files below; the underlying design change is the 2026-07-26 one, this
document did not exist until now — see "Why this document is dated
2026-07-26 but written 2026-07-30" at the end).

**Subject:** the two OVP-01 protective-impedance resistor dividers
(`OVPComparator.r_div_top1-3`/`r_div_bot`, the comparator-sense divider, and
`OVPComparator.r_adc_top1-3`/`r_adc_bot`, the ADC-sense divider,
`elec/src/modules.ato:2085-2405`) that bridge the HV half-bus (`+170V_BUS`
/ `dc_bus_plus`) to the PE-bonded SELV `gnd` domain.

**Cited from:** `elec/domain_manifest.yaml:25`, `elec/domain_manifest.yaml:483`,
`elec/domain_manifest.yaml:671`, `elec/src/modules.ato:388`, and (as a
finding, not a live citation)
`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:142`. All four/five
references have pointed at this exact path since 2026-07-26 or 2026-07-27;
none of them resolved to a file until this one was written. `git log --all
--diff-filter=A -- "**2026-07-26-ovp-crossing-resolution*"` returns nothing
for any commit before this one — independently re-confirmed in this pass.

---

## Falsifier, stated before doing the arithmetic

**This document is unwritable — and must say so instead of writing anyway
— if independently re-deriving the touch-current and voltage/power-rating
arithmetic from the real resistor values, the real half-bus voltage, and
the real rated power in `elec/src` does not reproduce compliance with IEC
60335-1's protective-impedance provision.** A confident-sounding writeup
that could not actually be re-derived would be worse than leaving the
citation dangling, because it would launder an unverified claim under a
`RESOLVED` label on a mains-connected safety boundary.

**Result: the falsifier did not fire for either divider under the
condition IEC 60335-1 Clause 8.1.4 actually requires (one component
open/shorted).** It also did not fire under the stricter, not-required
two-component-shorted condition, though for one of the two dividers that
stricter condition passes with much less margin than the repo's own
repeated "3.5×–10×" summary figure claims — corrected below, not just
restated.

---

## 1. What actually exists in `elec/src` (verified directly, this pass)

`elec/src/modules.ato:2204-2275` (comparator-sense divider):

```
r_div_top1/2/3 = 430kΩ ±1%, Yageo RC1206FR-07430KL, 1206, voltage_rating=200V, power_rating=0.25W  (each)
r_div_bot      = 16.9kΩ ±0.1%, RT0603BRD0716K9L, 0603, power_rating=0.1W
v_bus.line ~ r_div_top1.p1 ~ r_div_top2.p1 ~ r_div_top3.p1 ~ comp.INP ~ r_div_bot.p1 ~ power.gnd (r_div_bot.p2)
```

`elec/src/modules.ato:2361-2404` (ADC-sense divider):

```
r_adc_top1/2/3 = 169kΩ ±1%, Yageo RC1206FR-07169KL, 1206, voltage_rating=200V, power_rating=0.1W  (each)
r_adc_bot      = 10kΩ ±1%, RC0603FR-0710KL, 0603, power_rating=0.1W
v_bus.line ~ r_adc_top1.p1 ~ r_adc_top2.p1 ~ r_adc_top3.p1 ~ adc_v_bus.line ~ r_adc_bot.p1 ~ power.gnd (r_adc_bot.p2)
```

`elec/src/main.ato:511-520`: `dc_bus_plus` (`+170V_BUS`) is the positive rail
of the Delon/cascade voltage doubler, referenced to the doubler midpoint
(`power_return`/`PWR_RTN`), **not** to `dc_bus_minus` — it is the +170V
half-bus, not the 340V full bus. Independent proof this is the correct
reading (not just trusting the net name, which the repo's own history shows
was once wrong for exactly this node — `main.ato:511-516`): `PowerInput.c_bus1`
is asserted `>= v_bus_half * 1.25` (`main.ato:593`; `250V >= 212.5V` passes,
`250V >= 425V` would not), and `v_bus_half` in that same module is set from
`dc_bus_plus`'s own declared node, not from `v_bus_max` (340V, the full-bus
design ceiling, `main.ato:49`).

`elec/src/main.ato:53,494`: `power_max` / `p_output_max` = **1800W**
(1.8kW), asserted `within 1500W to 1800W` (`main.ato:495`, the 15A branch
circuit limit).

All of the above were read directly from source in this pass, cross-checked
against `elec/domain_manifest.yaml:673-693`'s `protective_impedance_chains`
declaration (which names the same six resistors as chain members), and
confirmed by rebuilding the netlist and running the gate that checks this
construction — §5 below.

## 2. Governing standard clause

**IEC 60335-1, Clause 8.1.4** ("Protective impedance"). Not accessible at
primary text in this pass (paywalled, same limitation the manifest itself
already records) — reconstructed from secondary sources consistent with
each other and with a patent (US 6,084,757) describing an equivalent
series-resistor protective-impedance network built to the analogous EN
60730-1 provision, cross-checked against a second, independent secondary
source in this pass (a test-report excerpt quoting the clause's mechanics
directly):

- Protective impedance must comprise **at least two separate components**
  such that no single component failure (open **or** short) removes the
  current-limiting function.
- The touch-current values in the applicable leakage-current clause "must
  not be exceeded if any ONE of the components is short-circuited or
  open-circuited" — i.e. the clause's own fault condition is **one**
  component failing, not two. This matters for §4 below: the design's
  "two resistors shorted simultaneously" analysis (already present in
  `elec/domain_manifest.yaml`) is **stricter than Clause 8.1.4 requires**,
  not a re-statement of the clause's actual pass/fail line.
- **UNVERIFIED-at-primary** (same caveat the manifest already carries,
  re-stated rather than dropped): whether Clause 8.1.4 or its surrounding
  text distinguishes "protective impedance into a PE-bonded earthed
  reference" (this design's case — `gnd ~ pe` is a hard 0Ω DC bond,
  `SELV_ISOLATION_REDESIGN.md` Sec 3) from "protective impedance into an
  accessible metal part" was not confirmed against primary text in this
  pass either. Treated as equivalent on the same first-principles
  reasoning the manifest already states (fault current returns to earth
  through the PE conductor, not through a person), not re-derived
  independently here.

**Touch-current limit: IEC 60335-2-6** (particular requirements for
stationary cooking ranges/hobs/ovens — confirmed in this pass, independent
search, that induction hobs sit in this Part 2-6's scope, not the
portable-appliance Part 2-9), modifying IEC 60335-1's general leakage-current
clause for stationary Class-derived heating appliances: **0.75mA, or
0.75mA per kW of rated input power, whichever is higher, capped at 5mA.**
At 1.8kW: `0.75mA × 1.8 = 1.35mA`. Same figure the manifest and
`docs/evidence/2026-07-26-emc-validators-implemented.md` already carry;
independently re-found in this pass via a second search, not merely copied.
**UNVERIFIED-at-primary**, same caveat as before: not confirmed against
IEC 60335-2-6's own paywalled text.

One point found in this pass that the manifest does not currently carry:
secondary sources describe leakage-current **testing** for heating
appliances as being performed with the appliance operated at **1.15× rated
power input**, a test-condition detail (how hard the appliance is driven
during the measurement), not a change to the kW figure used in the 0.75mA/kW
**limit** formula itself. Flagged as **UNVERIFIED** rather than folded into
the arithmetic below — the two are conceptually separate (test stimulus vs.
limit formula) and only one secondary source was found describing the 1.15×
figure at all.

## 3. Independent re-derivation (own script, not the manifest's numbers copied)

```python
V = 170.0  # +170V_BUS nominal (dc_bus_plus, half-bus) -- elec/src/main.ato:511-520

# Comparator divider: r_div_top1-3 = 430k each, r_div_bot = 16.9k
r_top, r_bot = 430e3, 16.9e3
i_normal = V / (3*r_top + r_bot)   # 130.1 uA
i_one    = V / (2*r_top + r_bot)   # 193.9 uA
i_two    = V / (1*r_top + r_bot)   # 380.4 uA

# ADC divider: r_adc_top1-3 = 169k each, r_adc_bot = 10k
r_top2, r_bot2 = 169e3, 10e3
i2_normal = V / (3*r_top2 + r_bot2)  # 328.8 uA
i2_one    = V / (2*r_top2 + r_bot2)  # 488.5 uA
i2_two    = V / (1*r_top2 + r_bot2)  # 949.7 uA
```

| Divider | Normal | One shorted (Clause 8.1.4's actual fault condition) | Two shorted (stricter than required) |
|---|---|---|---|
| Comparator (3×430k+16.9k) | 130.1µA | 193.9µA | 380.4µA |
| ADC (3×169k+10k) | 328.8µA | 488.5µA | 949.7µA |

Against the 1.35mA limit (§2):

| Divider | Normal margin | One-shorted margin (required) | Two-shorted margin (not required) |
|---|---|---|---|
| Comparator | 10.4× | 7.0× | 3.5× |
| ADC | 4.1× | 2.8× | **1.4×** |

Every one of these six figures matches `elec/domain_manifest.yaml:528-530,623-625`'s
own inline arithmetic exactly (130.1/193.9/380.4µA and 328.8/488.5/949.7µA) —
independently re-derived from the real resistor values in `elec/src`, not
copied and trusted.

**Correction to the repeated "3.5×–10×" figure** (`elec/domain_manifest.yaml:36`,
`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:66,106`, and this task's own
brief, all three copying the same phrase): that range is the **comparator
divider's own normal-to-two-shorted span** (10.4× down to 3.5×). It is not
the range across both dividers, and it does not describe the ADC divider's
two-shorted margin at all — which is **1.4×**, not 3.5×, the tightest
margin of any crossing in either manifest or this document. `elec/domain_manifest.yaml:626-629`
already states this correctly in its own inline comment ("0.95mA, ~70% of
the limit — the tightest margin of any crossing in this manifest, but still
under the limit") — the discrepancy is only in the three-times-repeated
**headline** phrase, which generalizes the comparator divider's range to
both dividers without saying so. This does not change the compliance
verdict: 1.4× is still >1× (compliant), and it is the *not-required*
double-fault case — the actually-required single-fault margins are a
comfortable 2.8×–7.0× across both dividers. But "3.5×–10×, even under a
double fault," stated as a single range covering both dividers, is not
accurate, and repeating it a fourth time here without this correction would
have been exactly the kind of "restate the figure without reproducing it"
this task was designed to catch.

## 4. Resistor voltage and power rating check (voltage rating already in the manifest; power rating is new in this pass)

Datasheet-verified in a prior pass (`elec/domain_manifest.yaml:541-543`) and
re-used, not re-fetched: Yageo RC1206FR-07 family (both `r_div_top1-3` and
`r_adc_top1-3` share this exact MPN prefix) — rated/working voltage 200V,
1/4W = **250mW** power rating.

| Divider | Case | V per resistor | % of 200V rated | P per resistor | % of 250mW true family rating | % of the *declared* `power_rating` field |
|---|---|---|---|---|---|---|
| Comparator | two-shorted (worst) | 163.6V | 82% | 62.2mW | 25% | 25% (declared 0.25W matches datasheet) |
| ADC | two-shorted (worst) | 160.5V | 80% | 152.4mW | **61%** | **152%** (declared 0.1W, wrong) |

**New finding this pass, not in the manifest:** `r_adc_top1/2/3`
(`elec/src/modules.ato:2363,2375,2382`) declare `power_rating = 0.1W`, but
they are the same Yageo RC1206FR-07 family, same 1206 footprint, as
`r_div_top1-3` — which correctly declare `power_rating = 0.25W` for that
family two dividers apart in the same file (`modules.ato:2206,2213,2220`).
A 1206 chip resistor in this family is a 1/4W (250mW) part; 100mW is the
0603 bottom resistors' rating (`r_div_bot`/`r_adc_bot`, correctly 0.1W for
their 0603 footprint), not the 1206 top resistors'. This reads as a
copy/mis-entry in the `power_rating` field, not a different physical part —
the `mpn` field (`RC1206FR-07169KL`) and `footprint`
(`Resistor_SMD:R_1206_3216Metric`) are internally consistent with the
250mW family, only `power_rating` is out of step.

**Consequence, bounded, not alarming:** against the true 250mW family
rating, the worst case (152.4mW, double-fault, not required by Clause
8.1.4) is 61% of rating — comfortable. Against the *declared* (apparently
wrong) 100mW field, that same case is 152% over — which would read as an
overstressed part if anyone trusted the field as-is (e.g. a future
automated BOM/rating-check gate keyed off `power_rating`). **`elec/src` is
read-only for this task; not fixed here.** Flagged as a precise, line-cited
follow-up: `r_adc_top1.power_rating`, `r_adc_top2.power_rating`,
`r_adc_top3.power_rating` at `elec/src/modules.ato:2363,2375,2382` should
read `0.25W`, matching `r_div_top1-3`'s pattern for the identical part
family.

## 5. Single-fault direction and construction-integrity gate (re-run, not assumed)

`r_div_bot` (R54) opening — the originally-flagged hazard direction — is
already analyzed correctly in `elec/domain_manifest.yaml:568-588` and not
repeated in full here: with `r_div_bot` open, `comp.INP` clamps to ~3.6V via
the TLV3201's ESD structure (rated 10mA continuous; actual current ~130µA,
comfortably survivable), which sits above `comp.INN`'s 2.5V REF2025
reference — `comp.OUT` goes HIGH, OVP-01 trips. Confirmed fail-safe, not
fail-open, on this fault. `r_adc_bot` opening is the MCU-ADC-only failure
already noted as non-hazardous (firmware reads a pinned value; the OVP trip
path is entirely independent of the ADC divider) and already carries an
explicit UNVERIFIED tag in the manifest for the ESP32-S3 clamp behavior —
not re-verified here.

**Construction-integrity gate, re-run in this pass against a freshly built
netlist** (not trusted from a prior run):

```
$ make netlist        # elec/build/ is gitignored, rebuilt fresh for this pass
... Build complete!
$ uv run python scripts/check_domain_partition.py
Checked 54 declared nets across 2 domains (HV, SELV), 10 declared isolators,
2 declared protective-impedance chain(s) (6 chain member(s) total), over
162 compiled nets / 169 components.
PASSED -- 0 domain crossings, 0 isolator-barrier breaches, 0
protective-impedance chain defects
```

This confirms the *construction* both dividers rely on (three real,
distinct, series-wired resistors between the HV boundary and the declared
chain endpoint, none shorted or tapped in the compiled netlist) is intact
today — it does not re-derive the arithmetic (§3-§4 do that) or the
standard clause (§2 does that); those are independent of the netlist and
were re-checked separately in this pass.

## 6. Verdict

**Both dividers are legitimate IEC 60335-1 Clause 8.1.4 protective-impedance
connections from the HV half-bus to the PE-bonded SELV `gnd`,** on the same
basis this design already relies on for `power_in.y_cap_pe` (C6): `gnd ~ pe`
is a hard 0Ω DC bond, so fault current pushed into it returns to earth
through the building's PE conductor rather than through a person in series
with much higher body impedance.

- Both dividers comprise three independent series top-side elements — no
  single component failure (the actually-required fault condition) removes
  the current-limiting function.
- Touch current under that required single-fault condition stays under the
  1.35mA IEC 60335-2-6 limit with 2.8×–7.0× margin across both dividers —
  independently re-derived in §3, not restated.
- Resistor voltage rating (200V, datasheet-confirmed) is respected with
  18–20% margin even in the two-shorted (not required) case for both
  dividers.
- Resistor power rating is respected against the *true* Yageo RC1206FR-07
  family rating (250mW) with margin in every case, including the
  not-required double-fault case (§4) — but the *declared* `power_rating`
  field on `r_adc_top1-3` is wrong (0.1W instead of 0.25W) and should be
  corrected the next time `elec/src` is touched (not this task).
- The previously-repeated "3.5×–10×" summary figure is corrected in §3: it
  describes only the comparator divider's own range, not a bound on both
  dividers. The true worst case (ADC divider, two-of-three shorted, a
  condition Clause 8.1.4 does not require evaluating) is 1.4×, still
  compliant.

**This RESOLVED annotation is substantiated.** It is not weakened or
qualified by anything found in this pass — the corrections above sharpen
the picture (a materially tighter true worst-case margin than the
repeated headline suggested, and a mis-entered BOM field) without changing
the compliance verdict.

## 7. Other dangling evidence citations found (swept, not fixed)

A repo-wide sweep for `docs/evidence/YYYY-MM-DD-*.{md,json,log,py}` citation
patterns across `elec/`, `docs/`, `packages/`, `scripts/`, `.github/` found
147 distinct cited paths, of which **25 do not exist on disk**, in addition
to this document (now fixed by this commit). Severity varies:

- **Safety/production-code-adjacent** (worth prioritizing): six citations to
  `2026-07-28-drc-*`/`2026-07-28-conformal-coating-pd1.md`/`2026-07-28-creepage-determination-brainstorm.md`
  from `scripts/generate_kicad_dru.py` and its test file (active DRC-rule
  generation, HV creepage); `2026-07-28-hv-isolated-rules-and-creepage-triage.md`
  from `packages/temper-placer/configs/netclass_rules.yaml` and
  `design_rules.py`; three citations from the still-existing
  `docs/evidence/2026-07-30-pollution-degree-determination.md` to sibling
  evidence files (`2026-07-28-isolator-creepage-slots.md`,
  `2026-07-28-pd3-retarget-keepout.md`, `2026-07-28-pd3-retarget-slots.md`)
  that were apparently never written or were renamed without updating the
  citing document.
- **Tooling self-reference**: `scripts/check_evidence_provenance.py` and
  `scripts/_lib/provenance.py` both cite
  `docs/evidence/2026-07-26-measurement-provenance.md`, which does not
  exist (a similarly-named `2026-07-28-measurement-provenance.md` does —
  likely the intended target, dated three days later).
- **Historical/planning references, lower severity**: the remaining ~16
  (routing baselines, bus-capacitor reselection, net-domain worksheets,
  learnings docs in `docs/solutions/best-practices/`) point at evidence
  that was apparently planned or superseded but never landed under the
  cited name.

Full list (path, citing files) generated for this pass and not committed as
a separate artifact — reproducible via a straightforward grep for the
`docs/evidence/YYYY-MM-DD-...` pattern across the four directories above,
filtered to paths that fail `os.path.exists`.

**Recommendation: a cheap gate is worth building for this class**, on the
same monotonic-shrink-allowlist pattern `scripts/check_evidence_provenance.py`
already uses for missing-provenance files. It would not be a new script from
scratch: `check_evidence_provenance.py` already walks `docs/evidence/` and
has the allowlist/shrink machinery; extending it (or a small sibling script
sharing `scripts/_lib/gate_allowlist.py`) to additionally scan *all*
tracked text files (not just `docs/evidence/` itself) for the
`docs/evidence/YYYY-MM-DD-*` citation pattern and fail on any citation that
does not resolve to an existing file would have caught this exact defect —
a `RESOLVED` annotation on a mains-to-SELV safety boundary citing a document
that was never written, silently unverifiable for four days across two
files and one already-corrected audit document. The 25 pre-existing
dangling citations found in this sweep would need to seed that gate's
initial allowlist (same monotonic-shrink shape: no new dangling citations
allowed, existing ones ticketed and fixed over time) rather than blocking
CI immediately on landing.

---

## Why this document is dated 2026-07-26 but written 2026-07-30

The four citing lines (`elec/domain_manifest.yaml:25,483,671`,
`elec/src/modules.ato:388`) are read-only source that already names this
exact filename and date. Renaming this document to today's date would
create a *second* dangling reference (the original four citations would
still point at the old name) instead of resolving the existing one. The
provenance comment at the top of this file carries the true commit this
analysis was performed and written at (`d0553d2617381c40ed850ed775b38c34578d1c48`,
2026-07-30) — the filename is fixed by the citations it resolves, the
provenance line is what is actually trustworthy about when the content was
produced, per `docs/METHODOLOGY.md` Sec 5's own "a measurement carries the
commit it was taken at" rule.
