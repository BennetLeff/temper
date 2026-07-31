<!-- provenance: commit=d510f4ede1ce0f3db343776f024c0f8a36085675 dirty=false -->

# Touch-current budget, corrected, and C6's four routes re-evaluated against it

**Task:** establish the real IEC 60335 earth-leakage/touch-current budget for
Temper (a 1.8kW stationary Class I induction hob) before evaluating any C6
(Y-capacitor) route, then evaluate C6's routes against that budget and
against the standard's own single-fault text. Analysis only -- no design
file, footprint, netclass, or constant touched; `git status --short` clean
apart from this document.

**Worktree:** `/Users/bennet/Desktop/temper-c6-leakage`, branch
`research/c6-leakage-touch-current`, created fresh from `origin/main` at
`d510f4ed` per this task's hard rule (a separate worktree from the
K1/C6/T1 part-selection thread this task points at for background,
`/Users/bennet/Desktop/temper-pd3-parts`, branch
`research/pd3-part-selection-k1-c6-t1`, not modified by this session).

**Primary-text access, stated up front:** this session located a
previously-fetched **full text** of IEC 60335-1 (edition "IEC:2001+A1:2004")
at
`/private/tmp/claude-501/-Users-bennet-Desktop-temper/413756c0-69f4-4db3-98b7-0b98b4a5e1f8/scratchpad/pdfs/iec60335-1_full.txt`
(7223 lines, clauses 1-19 and more in full, not a preview/TOC-only
fetch like several other cached PDFs in the same directory). This is an
older edition than the current one (Ed. 6, 2020) but every clause quoted
below was independently corroborated for the **current 2020 edition**
via secondary sources that quote its text directly (WebSearch, cited
inline) -- the specific wording checked (clause 13/16 structure, the
classification-dependent limit table, the "protective impedance and
radio interference filters disconnected" provision, the "doubled if
radio interference filters" provision) reads identically in both. IEC
60335-2-6 (the particular standard for cooking appliances) itself
remains **paywalled and not fetched** in this pass -- flagged as
UNVERIFIED throughout where it matters, not silently assumed unchanged.

Provenance labels follow this repo's established convention
(`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` and
`docs/evidence/2026-07-26-ovp-crossing-resolution.md`): **CITED-PRIMARY**
(fetched primary text, read directly this session), **CITED-SECONDARY**
(distributor/secondary source, used only where labelled), **MEASURED**
(computed from a real file/value, method shown), **DERIVED** (arithmetic
on labelled inputs), **UNVERIFIED** (flagged for a human).

---

## Verdict up front

| Question | Answer |
|---|---|
| **Is 1.35mA the right limit?** | **Yes, CITED-PRIMARY, clause identified precisely.** IEC 60335-1 Clause 13.2/16.2's own table: "stationary class I heating appliances: 0,75 mA or 0,75 mA per kW rated power input... whichever is higher" (max 5mA) -> `0.75 x 1.8kW = 1.35mA`. Confirmed against the fetched full-text PDF verbatim, both clauses, and independently corroborated for the current 2020 edition via secondary source. 3.5mA (used in three other repo docs -- `HV_SAFETY_TEST_PROCEDURE.md`, `GROUNDING_EMI_STRATEGY.md`, `REQUIREMENTS.md`) is the **wrong figure for this product** -- it is the *motor-operated* appliance limit, not the *heating*-appliance one; those three documents are stale/wrong on this point, a pre-existing defect this task did not introduce. |
| **Is the design within budget today?** | **Yes -- and by more margin than the task's own two-term estimate suggested**, once the standard's actual test methodology is applied instead of naively summing worst-case fault currents into a normal-operation figure. See Part 1. A newly-found leakage contributor (the isolated AuxSupply module, <=250uA per its own datasheet) was **not** in the task's list (X2/CMC/MOV) or the prior evidence chain, and is added here. |
| **(a) Two Y-caps in series** | **Dead. Fails single-fault analysis, corroborated by primary-adjacent standard text and converging industry practice**: a series Y-cap pair's qualified single-fault behaviour puts the *full* mains voltage across whichever capacitor survives, and that survivor's *own* creepage -- not the pair's summed creepage -- must clear 12.6mm alone. No ceramic Y1 clears 12.5mm industry-wide (already established); no primary or secondary source found credits summed creepage for this construction. See Part 2(a). |
| **(b) Reduce capacitance** | **Does not solve C6's actual blocker.** The blocker is creepage/lead-spacing, and ceramic Y1 lead spacing is flat at 12.5mm **regardless of capacitance** (already established) -- going lower doesn't unlock a new spacing tier, it only trades away CM-EMI margin for no creepage benefit. Not viable as a path to 12.6mm. |
| **(c) Delete C6** | **Not blocked by touch-current or creepage rules (removing the component removes the crossing) but not free** -- C6's stated role (`modules.ato:908-910`) is the Class-I EMI return bond from `power_return` to PE; deleting it is a conducted-emissions risk this repo has no measured or simulated margin data to bound. The specific "prior brainstorm ruling deletion out" this task references **could not be located** anywhere in `origin/main`, the `temper-pd3-parts`/`pd3-inter-component`/`pd3-isolation-mechanisms` worktrees, or any reachable branch -- reported as not found, not as confirmed or refuted. |
| **(d) Anything else** | **TDK B81123C1562M000 (5.6nF, 22.5mm lead spacing) now clears *both* gates** -- creepage (already MEASURED in the cited prior document, +7.1mm margin) and, per this document's corrected Part 1 budget, touch current too, **even under the most conservative reading this document could construct** (no protective-impedance exemption, no radio-interference-filter doubling credit): 1.15-1.24mA against 1.35mA, 9-15% headroom. This reverses the prior document's "plausibly exceeds budget" hedge on the same part. |
| **Is PD3 reachable, or does it die on C6?** | **PD3 is reachable.** C6 = TDK B81123C1562M000 (5.6nF Y1, 22.5mm lead spacing) is a real, creepage-margined, touch-current-budget-compliant candidate under the corrected accounting in this document -- with the caveats in "UNVERIFIED" below (mainly: IEC 60335-2-6's own text was not read, and one interpretive question about whether the OVP-01 dividers are properly "protective impedance" under Clause 8.1.4 is flagged, not resolved, though the conclusion holds either way). |

---

## Part 1 -- the real touch-current budget

### 1.1 The governing clause and limit, verified against fetched primary text

**IEC 60335-1 Clause 13** ("Leakage current and electric strength **at operating
temperature**") and **Clause 16** ("Leakage current and electric strength",
room temperature) both carry the *same* classification-dependent limit
table, read directly from the fetched full text (lines 2144-2230 and
2454-2510):

```
– for class II appliances                                0,25 mA
– for class 0, class 0I and class III appliances          0,5 mA
– for portable class I appliances                         0,75 mA
– for stationary class I motor-operated appliances         3,5 mA
– for stationary class I heating appliances                0,75 mA or 0,75 mA per kW rated
                                                            power input of the appliance with a
                                                            maximum of 5 mA, whichever is higher
```

Temper is a stationary, Class I (earthed, `gnd ~ pe` per
`SELV_ISOLATION_REDESIGN.md`), 1.8kW **heating** appliance (an induction hob,
IEC 60335-2-6's own scope per independent web corroboration this session,
consistent with the repo's existing finding). `0.75mA x 1.8 = 1.35mA` -- **CONFIRMED**,
not merely re-asserted. This also settles, in passing, a real
pre-existing inconsistency in the repo: `docs/hardware/HV_SAFETY_TEST_PROCEDURE.md:94`,
`docs/hardware/GROUNDING_EMI_STRATEGY.md:270`, and `docs/specs/REQUIREMENTS.md:409`
all cite **3.5mA** as "the IEC 60335-1 limit" for this product -- that is
the *motor-operated* appliance figure, not the *heating*-appliance one
that actually governs Temper; those three documents are stale/wrong
(a pre-existing defect, not introduced by this analysis, flagged here
because Part 1 depends on getting this right).

### 1.2 The test methodology -- this is where the task's framing needs correcting

Both clauses' opening sub-clause (13.1, 16.1) state, verbatim, a fact the
task's own two-term starting estimate did not apply:

> **Clause 13.1:** "Protective impedance and radio interference filters
> are disconnected before carrying out the tests." (line 2164, fetched
> text; heating appliances operated at **1.15x rated power** for this test)
>
> **Clause 16.1:** "Protective impedance is disconnected from live parts
> before carrying out the tests." (line 2461, fetched text; test performed
> at room temperature, appliance not connected to supply mains, subjected
> to 1.06x rated voltage)
>
> **Clause 16.2** (not present in 13): "The values specified above are
> doubled if ... the appliance has radio interference filters. In this
> case the leakage current with the filter disconnected shall not exceed
> the limits specified." (lines 2483-2489)

Independently corroborated for the **current, 2020, edition** (not just
the 2001+A1:2004 text fetched) via a WebFetch summary of a secondary
source quoting IEC 60335-1-2020 directly: "Protective impedance and
radio interference filters are disconnected before carrying out the
tests," matching verbatim.

**What this means concretely for Temper's actual leakage contributors:**

- **Clause 13** (the "hot," 1.15x-power test): protective impedance
  *and* C6/`c_x2`/the CMC (all bona fide radio-interference-filter
  components by declared circuit role, `modules.ato:695-741,908-910`)
  are physically lifted before this test runs. None of them are measured
  by Clause 13 at all.
- **Clause 16** (the "cold," 1.06x-voltage test): C6/`c_x2`/CMC remain
  connected, but because Temper **has** radio interference filters, the
  limit for this specific measurement is **doubled to 2.7mA**, with a
  second, mandatory check (filter physically disconnected) that must
  clear the un-doubled 1.35mA -- trivially true, since removing C6
  removes essentially all of the filter-attributable leakage.

**This directly contradicts the shape of the task's own opening estimate**,
which summed the OVP-01 ADC divider's *two-resistors-simultaneously-shorted*
figure (949.7uA -- a **double-fault**, not-required-by-the-standard stress
case, per `docs/evidence/2026-07-26-ovp-crossing-resolution.md` Section 3,
already committed to this repo's evidence chain and independently
re-derived, not merely copied, in this pass -- see 1.4) directly against C6's
**normal**-operation leakage, and did so without applying either the
disconnection or the doubling provision. That is not how the standard's own
test structures the number. Section 1.4 below recomputes it correctly.

### 1.3 Complete leakage-current inventory -- traced from source, not assumed

The task named X2, the CMC, and the MOV as omitted terms and asked for a
complete enumeration. Tracing every net that reaches `pe` (directly) or
`gnd` (bonded to `pe` at `main.ato:754`, hard 0-ohm DC bond) in
`elec/src/modules.ato`/`main.ato` this session (`grep -n "~ pe\b" elec/src/*.ato`
-- only two direct hits: `y_cap_pe.p2 ~ pe` and `gnd ~ pe`; everything else
reaches PE only by first reaching `gnd`):

| Contributor | Declared PE-referenced path? | Normal-operation current | Basis |
|---|---|---|---|
| **C6 (`y_cap_pe`, 2.2nF Y1)** | Yes, direct: `dc_bus.gnd_ref ~ y_cap_pe.p1`, `y_cap_pe.p2 ~ pe` (`modules.ato:971-972`) | 172.8uA nominal (2.64nF worst-tolerance: 207.4uA) | DERIVED, `I = V*2*pi*f*C`, 250VAC/50Hz, same basis the repo already uses |
| **AuxSupply (PS1, Mean Well IRM-10-15)** | Yes: `aux_supply.power_out.gnd ~ gnd` (`main.ato:273`) | **<=250uA** | **CITED-PRIMARY, new to this analysis** -- Mean Well's own `IRM-10-SPEC` datasheet (file name `IRM-10-SPEC 2025-08-08`, fetched in a prior session, re-read this pass), INPUT specification table: `LEAKAGE CURRENT < 0.25mA/277Vac`. This module's isolated secondary is the source of `vcc_15v`/`vcc_3v3`, and its own internal I/O leakage (standard spec for this class of isolated AC/DC module, the same "primary-to-secondary Y-capacitance" concept C6 embodies discretely) was **not counted anywhere in the prior evidence chain or the task's own list** -- it is larger than C6's own contribution. |
| **OVP-01 dividers (comparator-sense + ADC-sense)** | Yes, direct resistive: `v_bus.line ~ r_div_top1-3 ~ ... ~ power.gnd` and same pattern for `r_adc_top1-3` (`modules.ato:2204-2275,2361-2404`) | **458.9uA combined, both dividers, no fault** (130.1uA + 328.8uA, DERIVED, re-computed this session, matches `docs/evidence/2026-07-26-ovp-crossing-resolution.md` Section 3 exactly) | See 1.4 for whether this belongs in the Clause 13/16 budget at all |
| **C_X2 (0.22uF X2)** | **No** -- `fuse.p2 ~ c_x2.p1`, `c_x2.p2 ~ ac_n` (`modules.ato:864-865`), line-to-neutral only, no PE pin | ~0 by topology | MEASURED from netlist, not assumed |
| **MOV (RV1, V150LA10AP)** | **No** -- `fuse.p2 ~ mov.p1`, `mov.p2 ~ ac_n` (`modules.ato:862-863`), line-to-neutral only | ~0 by topology (plus MOV standby current at rated line voltage, well below its clamp voltage, is itself in the low-uA-or-less range for this class of part, not independently re-verified this session) | MEASURED from netlist |
| **CMC (L_EMI)** | **No declared pin to PE** -- `cmc.W2_2 ~ dc_bus.gnd_ref` (`modules.ato:898`), and `dc_bus.gnd_ref`/`power_return` is a *different* net from `gnd` (post-2026-07-26 fix; confirmed distinct nets per `IEC60335_CRITICAL_COMPONENTS.md` Section 2.2-2.3) -- the only path from `dc_bus.gnd_ref` to `pe` is *through* C6, already counted once above, not a second time | Not a second, independent PE leakage path; any winding-to-core stray capacitance is a parasitic, not a declared circuit node, and was not quantified (plastic bobbin per the part's own datasheet, `IEC60335_CRITICAL_COMPONENTS.md` row for L_EMI: "polycarbonate base plate" -- not a grounded metal core) | Not quantified; expected small (single-digit uA at most for this construction), flagged not computed |
| **H11L1 (zcd_opto, U3)** | Isolator, HV-side LED referenced to `power_return`, SELV-side referenced to `gnd` | Not quantified -- typical DIP-optocoupler inter-pin capacitance (<2pF) implies well under 1uA at 250V/50Hz | Estimated by component-class reasoning, not datasheet-sourced; flagged |
| **UCC21550 (gate driver)** | Both sides HV-referenced (per `IEC60335_CRITICAL_COMPONENTS.md`'s own table row) | N/A -- does not cross into the PE-bonded SELV domain at all | Confirmed by that document's own analysis, not re-derived here |

**Corrected normal-operation total, everything with a real declared PE
path, summed:** `172.8 (C6) + 250 (AuxSupply) + 458.9 (OVP, both dividers,
no fault) = 881.7uA`, plus an unquantified-but-small CMC/opto/MOV residual
(expected single-digit uA). **Call it ~885-890uA against the 1.35mA limit
-- 66% of budget, a real ~34% headroom**, not the ~83%-with-172uA-of-headroom
the task's rough two-term estimate found, and not over budget the way the
task worried it might already be.

### 1.4 Does the OVP-01 divider belong in this budget at all? -- flagged, not resolved, computed both ways

This is a genuine interpretive question this document surfaces rather than
inferring past. IEC 60335-1's own glossary (fetched text, line 844-847):

> **3.3.6 protective impedance:** "impedance connected between live parts
> and accessible conductive parts of **class II constructions** so that
> the current, in normal use and under likely fault conditions in the
> appliance, is limited to a safe value"

Temper is **Class I**, not Class II (`gnd ~ pe`, hard bond, "the standard
answer for a Class I appliance" per `SELV_ISOLATION_REDESIGN.md:103`,
already the design's own stated framing). The formal glossary definition of
"protective impedance" -- the term `elec/domain_manifest.yaml` and
`OVPComparator`'s own docstring invoke to justify the OVP-01 dividers under
Clause 8.1.4/22.42 -- is textually scoped to Class II by IEC 60335-1's own
definition. Clause 8.1.4 itself ("An accessible part is not considered to
be live if... separated from live parts by protective impedance") exists to
let a Class II design avoid earthing a part by using a controlled-current
bridge instead; Temper's OVP-01 dividers bridge into `gnd`, which is
**already earthed** by direct 0-ohm bond, not a part relying on
protective impedance for its not-live classification. This suggests the
repo's own "Clause 8.1.4 protective impedance" framing for the OVP-01
dividers -- inherited by this document's own Section 1.3 table via the
prior evidence chain -- **may be a misapplication of a Class-II-scoped
concept to a Class I construction**, not confirmed one way or the other
against IEC 60335-1's full current-edition text or against actual
certification-lab practice in this pass (**UNVERIFIED**, listed again below).

**Both readings are computed so the conclusion does not depend on
resolving this:**

- **If the dividers ARE legitimate Clause 8.1.4 protective impedance:**
  they are excluded from the Clause 13/16 leakage-current measurement
  entirely (both clauses disconnect protective impedance before the
  test) and are instead checked against Clause 8.1.4's own separate
  limit -- "the current... shall not exceed 2mA for d.c." (this bus is
  DC, `+170V_BUS`/`dc_bus_plus`, not AC, so the DC figure applies, not
  the 0.7mA-peak AC figure). Worst documented case, 949.7uA (two
  resistors shorted, not a required test condition per Clause 8.1.4's own
  fault model of "any ONE component" -- `docs/evidence/2026-07-26-ovp-crossing-resolution.md`
  already established this), is 47% of the 2mA limit -- passes with
  margin, on an entirely separate accounting from the whole-appliance
  touch-current budget.
- **If the dividers are NOT protective impedance in the defined sense**
  (the more conservative reading, and arguably the textually better-supported
  one given the Class-II scoping): their normal-operation current (458.9uA
  combined) is included in the Clause 13/16 whole-appliance total, as
  already done in Section 1.3's inventory above.

**Either way, the design is within budget today** -- 66% under the
conservative inclusion, or lower still if the dividers are properly
excluded. This is the decisive answer to Part 1's question.

### 1.5 Correcting the task's own starting arithmetic, explicitly

The task's framing summed "C6 172.8uA + OVP worst case 949.7uA = 1122.5uA."
That combination mixes a **normal**-operation figure (C6's leakage in
ordinary use) with a **double-fault** figure (two resistors shorted
simultaneously in the ADC divider, a condition Clause 8.1.4 does not
require testing for, and which -- per 1.4 -- may not even belong in this
budget category at all). The standard's own Clause 13/16 test measures
the appliance in **normal operation** (13: at 1.15x rated power; 16: with
1.06x rated voltage applied) -- not with a component pre-failed. The
correct normal-operation comparison is `172.8uA (C6) + 458.9uA (OVP, both
dividers, healthy) + 250uA (AuxSupply, newly added) = ~881.7uA`, not
`1122.5uA` -- and even that lower figure already includes a term
(AuxSupply) the original estimate never counted. **The direction of every
correction found in this pass moves toward "more compliant," not less** --
the one genuinely new addition (AuxSupply's 250uA) is smaller than the one
genuinely removed conflation (949.7uA standing in for 458.9uA).

---

## Part 2 -- C6's four routes against the corrected budget

### 2(a) Two Y-capacitors in series -- dead, and the reason is textual, not just arithmetic

The task's own framing of the hazard is exactly right, and this pass
found converging confirmation rather than a reason to soften it.

**The failure mode that matters:** IEC 60384-14-qualified Y-class
capacitors are constructed and tested to fail **open**, not short --
confirmed via multiple independently-converging secondary sources this
session (WebSearch: "the entire point of the Y classification... is to
guarantee a controlled, non-hazardous failure mode -- a Y-cap whose
insulation never breaks down enough to electrify the chassis"; a second,
independent search returned the same claim in matching language from a
different source set). No primary IEC 60384-14 text was fetched this
session (**UNVERIFIED-at-primary**, same caveat class this repo's evidence
chain already uses elsewhere), but the convergence across independent
sources, with no contradicting source found, is treated the same way this
repo's own prior evidence documents already treat this evidentiary tier.

**Why "fails open" does not save the series construction:** when one
capacitor of a series pair opens, the *other* capacitor no longer shares
the voltage -- the full mains-referenced voltage appears across it alone.
This is not a Temper-specific inference; it is the explicitly documented
behaviour of the exact "two Y-caps in series for reinforced insulation"
construction the task is asking about, described in matching language by
two independent WebSearch results this session: **"each capacitor must be
capable of withstanding the full voltage during a single fault
condition"** and **"if the withstand voltage at both ends of the Y
capacitor is insufficient... pay attention to... avoid uneven voltage
causing the withstand voltage at both ends of a single Y capacitor to
exceed the rated voltage."** This is a well-established, widely-used
industry pattern (2xY2-in-series as a reinforced-insulation-equivalent to
1xY1) -- and its own governing rule is that **each component must
independently clear the full-voltage creepage requirement**, not a summed
or shared figure. IEC 60335-1's own Clause 22.42 (protective impedance
construction rule, quoted in full in `docs/evidence/2026-07-26-ovp-crossing-resolution.md`)
states the adjacent principle explicitly: "If any one of the components is
short-circuited or open-circuited, the values specified in 8.1.4 shall not
be exceeded" -- i.e. even the standard's own multi-component
current-limiting construction is evaluated against the single-remaining-part's
performance under either failure direction, not a summed one.

**Applying this to Temper's specific candidates:** two 4.4nF (or any
split) ceramic Y1 capacitors in series, each at the industry-wide-flat
12.5mm ceiling (already established, not re-derived here), would require
the survivor -- alone -- to clear 12.6mm. **12.5mm < 12.6mm before any
manufacturer tolerance is even applied.** The series construction does not
change this; it makes it worse, since it adds an intermediate node and
does not relax the per-component requirement. **No clause was found in
the fetched primary text, and no source was found in this session's
research, that credits summed creepage across series-connected components
for a mains-bridging path.** The task's own suspicion is confirmed:
**IEC 60335-1 does not credit summed creepage here, and a Y1 capacitor's
own qualified failure mode (open) is exactly the mechanism that defeats
the series construction, not a mitigation of it.**

(A film-Y1-family variant of the same idea -- two TDK B81123 22.5mm-tier
parts in series, each already independently clearing 12.6mm on its own --
would technically survive single-fault analysis, since each component
individually already meets the bar. But at that point the series
arrangement adds a node, roughly halves net capacitance to ~2.8nF (5.6nF/2,
still outside the 2.2nF+/-20% window and no closer to spec than one part
alone), and adds board area for no benefit over simply using **one**
22.5mm-tier part directly -- which is route (d) below. Not a distinct
recommendation from (d).)

### 2(b) Reduce capacitance below 2.2nF

**Does not address C6's actual blocker.** The blocker established in the
cited prior document (Section 2.3, not re-derived here) is **lead
spacing/creepage**, and ceramic Y1 lead spacing is a **flat 12.5mm ceiling
across the entire capacitance range each series covers** (Vishay VY1: "10.0mm
or 12.5mm... for the entire capacitance range... 10pF to 4.7nF"; WKP and
AY1: identical statement). Reducing C6's value from 2.2nF to, say, 1nF
does not move a ceramic Y1 part off that 12.5mm ceiling -- there is no
lower-capacitance tier with more spacing to unlock. The film family
(TDK B81123) runs the *opposite* direction: more spacing requires **more**
capacitance (22.5mm only from 5.6nF), not less. **Reducing capacitance has
no creepage benefit in either family and only costs CM-EMI filtering
margin** (Y-cap common-mode attenuation scales with capacitance in this
role; `modules.ato:908-910`'s own comment states C6's function is "EMI
return path... without a DC short," and `docs/hardware/GROUNDING_EMI_STRATEGY.md`
Section 5.3's filter-performance table -- while describing a different,
stale topology not matching current `elec/src`, flagged rather than relied
on for numbers -- correctly captures the qualitative direction: less Y
capacitance means less CM attenuation at every frequency in the table).
**Not viable as a path to 12.6mm.**

### 2(c) Delete C6

Deleting the component trivially removes the crossing (nothing to route),
so it is not blocked by the 12.6mm/touch-current rules this task's hard
constraints protect. But it is not free: C6's declared role is the
Class-I EMI return bond from `power_return` to PE
(`modules.ato:908-910`'s own comment), and this repo has **no measured or
simulated conducted-emissions margin data anywhere** (`grep` for
CISPR/conducted-emission/corner-frequency across `docs/evidence/` and
`docs/hardware/` returns exactly one hit, the already-reviewed
`2026-07-26-emc-validators-implemented.md`, which itself does not contain
a margin figure for this specific topology). Deleting C6 trades a
solved-by-removal safety/creepage question for an **unquantified** EMC
compliance question this repo cannot currently bound either way.

**The specific "prior brainstorm ruled deletion out... no substitute" this
task references was searched for and not found.** Checked: `origin/main`
(`grep -rln "delete.*C6\|no substitute\|needed for EMC" docs/`, no hits),
the `temper-pd3-parts` worktree (same grep, no hits), the
`pd3-inter-component-measurement` worktree (no hits), and the
`pd3-isolation-mechanisms` scratchpad worktree (no hits). **Reported as
not locatable in any reachable repo state, not as confirmed or refuted.**
If it exists, it is in a session transcript or scratchpad note this
analysis did not have access to.

### 2(d) Other -- TDK B81123C1562M000 (5.6nF, 22.5mm), re-evaluated against the corrected budget

The prior document (`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`
Section 2.5, cited per this task's "Read first" instruction, not
re-derived from scratch) already established, MEASURED: 22.5mm lead
spacing, `22.5 - 0.4(tolerance) - 2.4(pad convention) = 19.7mm`, **+7.1mm
margin over 12.6mm even worst-case** -- the creepage gate is already
cleared with real margin, not a knife-edge pass. That document's own
follow-up (Section 2.5) computed a **rough, two-term** touch-current
estimate (949.7uA OVP-worst-case + 439.8uA at 5.6nF = 1389.5uA) and flagged
it as exceeding 1.35mA, "not established as electrically safe."

**Recomputed here against the corrected, complete inventory from Part 1**,
same conservative posture (no protective-impedance exemption credited, no
radio-interference-filter doubling credited -- i.e. the *strictest*
plausible reading, deliberately not the most favorable one):

```
C6 @ 5.6nF:                439.8uA  (5.6nF nominal; 527.8uA at +20% worst tolerance)
AuxSupply (PS1):           250.0uA  (datasheet max, already worst-case)
OVP-01, both dividers, no fault:  458.9uA
Misc (X2/MOV/CMC/opto):    ~5uA    (unquantified small residual, not zeroed out)
---------------------------------
TOTAL, nominal:            1153.7uA  ->  85.5% of 1.35mA  (14.5% headroom)
TOTAL, C6 worst-tolerance: 1241.7uA  ->  92.0% of 1.35mA  ( 8.0% headroom)
```

**Compliant even under the strictest reading this document could
construct** -- reversing the prior document's "plausibly exceeds budget"
hedge on the same part. The margin is real but thin (8-15%), and if
either favorable-but-flagged reading from Part 1 applies (protective
impedance properly excluded, and/or the Clause 16 doubling credit taken),
the margin widens substantially (to ~54-67% headroom against 1.35mA, or
~54-70% headroom against the doubled 2.7mA figure). **This document does
not resolve which reading a certification lab would apply** -- it reports
that the part clears the budget under the *worst* of the readings found,
which is the decision-relevant fact for whether this route is worth a
human's further attention.

No other >=18mm-lead-spacing Y1 film capacitor at ~2.2nF was found at any
manufacturer in the prior document's search (TDK, Vishay x3, KEMET, WIMA
partial) and this pass did not re-run that search -- cited, not repeated.

---

## Final answer

**PD3 is reachable. C6 does not kill it.**

TDK B81123C1562M000 (5.6nF Y1, 500VAC, 22.5mm lead spacing) clears both
gates that matter: **creepage** (+7.1mm margin, already MEASURED in the
cited prior document against the manufacturer's own dimensioned drawing
and printed tolerance) and **touch current** (8-15% headroom under this
document's corrected, strictest-case accounting, wider under either
favorable-but-flagged reading). This reverses the prior document's
tentative "plausibly exceeds budget" conclusion on the same part -- that
conclusion rested on conflating a double-fault OVP-divider figure with a
normal-operation budget and omitted a real, datasheet-documented leakage
contributor (the AuxSupply module) that happens to be smaller than the
error it's being added alongside.

**This is not a zero-caveat green light.** The 5.6nF value is a genuine
2.5x change from the incumbent 2.2nF -- an EMC/filtering-performance
decision, not just a leakage-budget one, and Part 2(b)'s conclusion that
lower capacitance doesn't help creepage does not mean higher capacitance
is free of engineering consequence elsewhere (Section 2(d)'s own EMC
caveat applies in reverse here: more C6 capacitance should, if anything,
*improve* CM-EMI margin, not hurt it, but this repo has no quantified
model to confirm by how much). And the margin computed above (8-15% in
the strict case) is thinner than any of this project's other already-solved
PD3 crossings (K1's +5.0mm creepage margin, or U7's ISO7741FQDWWRQ1
per the same prior document's Section 1) -- a human should treat the 8%
worst-case headroom as real but not spacious, and should get IEC
60335-2-6's own text (paywalled, not read in this pass) before treating
this as final, since a Part-2 modification to Clause 13/16's disconnection
or doubling provisions -- not found, but not ruled out either -- would
change which of this document's two computed totals (881.7uA-normal vs.
1153.7-1241.7uA-strict) actually governs.

---

## UNVERIFIED (explicit list)

- **IEC 60335-2-6's own text was not fetched or read this session**
  (paywalled, same limitation the prior evidence chain already records).
  A 2024-edition change-summary found via WebSearch lists Clause **16.2**
  among clauses receiving "conversion of notes to normative text" in that
  edition -- content not confirmed, but it establishes that Part 2-6 *does*
  touch Clause 16 in some way for this appliance category. This could
  change the disconnection/doubling mechanics Part 1 relies on. Flagged,
  not assumed away.
- **Whether the OVP-01 dividers are correctly classified as Clause 8.1.4
  "protective impedance"** given IEC 60335-1's own Class-II-scoped
  glossary definition (Section 1.4) -- a real, primary-text-grounded
  question this document surfaces and computes both ways, but does not
  resolve. Does not change the Part 1 or Part 2(d) verdicts either way
  (both readings stay within budget), but would change *which* clause and
  *which* limit family governs the dividers specifically.
- **IEC 60384-14's own primary text on Y-capacitor qualified failure mode**
  (Section 2(a)) was not fetched -- relied on two independently-converging
  secondary sources with no contradicting source found, the same
  evidentiary tier this repo's prior documents already use for
  similar claims.
- **CMC winding-to-core stray capacitance, MOV standby leakage at rated
  voltage, and H11L1 inter-pin capacitance** (Section 1.3) were reasoned
  about by component-class/topology argument, not independently measured
  or datasheet-sourced this session -- each is expected small
  (single-digit-uA or sub-uA) but not quantified to a specific figure.
- **Whether TDK's ENEC-05495/UL E97863 certificates for the B81123 family
  cover the 22.5mm/5.6nF+ tier specifically** -- already flagged
  UNVERIFIED in the prior document (Section 2.2/4), not re-checked here.
- **The "prior brainstorm" ruling out C6 deletion for EMC** (Part 2(c)) --
  searched across every reachable repo location and not found. Not
  confirmed, not refuted.
- **This document's own leakage totals are a hand/script-computed
  estimate, not an IEC 60990-network measurement or a SPICE simulation**
  -- appropriate for a design-stage budget check, not a substitute for
  the actual test a certification lab would run before sign-off,
  consistent with how this repo's own prior OVP-crossing document frames
  its own arithmetic.

---

## Hard-constraint compliance

- **No design file, footprint, netclass, or safety constant modified.**
  Only this document was written this session (plus the worktree's own
  git housekeeping); `git status --short` clean apart from it, checked
  before writing this section.
- **Own git worktree**, `/Users/bennet/Desktop/temper-c6-leakage`,
  branched fresh from `origin/main` at `d510f4ed`.
- **No `git stash` used.**
- **No sub-agents spawned**, per this task's explicit instruction.
- **No relaxation of 12.6mm, no pollution-degree change, no domain
  reclassification proposed anywhere in this document.** The 5.6nF
  recommendation in Part 2(d) is reported with its real, computed margin
  (8-15% strict case) stated plainly, not smoothed into a false "solved
  with wide margin" claim the way the task's own evidence standard warns
  against.
- **No touch-current-limit-exceeding route proposed.** Both series-Y-cap
  variants considered in 2(a) were rejected specifically because they
  cannot be shown to stay within the creepage requirement under single
  fault, not adopted with a caveat.
- Not pushed, no PR opened.
