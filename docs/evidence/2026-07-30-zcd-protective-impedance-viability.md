# Can U3's ZCD crossing be deleted with protective impedance instead of galvanic isolation?

<!-- provenance: commit=df84a9d0456963061ca99a1b8d9d7c1d7618577b dirty=false -->

**Date:** 2026-07-30
**Base commit:** `df84a9d0` (`origin/main`), isolated worktree, `make venv-isolate` run first.
**Scope:** analysis only. No `elec/src/**`, `pcb/**`, netclass, footprint, or
safety-constant change. `scripts/measure_cross_domain_creepage.py` was
copied in from the unmerged `feat/pairwise-creepage-tool` branch
(`5401a827`) to run the measurement in §4 against this worktree's own board
state, then deleted before commit — it is not part of this change.

## Verdict, up front

**Reject.** Protective impedance is electrically viable in the sense that a
redundant resistor chain *can* be built that satisfies IEC 60335-1's
single-fault construction rule (§2 below) — the arithmetic closes cleanly,
the same way it does for the two OVP-01 dividers already in this design.
But two independent problems keep this from being the right move for ZCD
specifically, and neither is a geometry problem this task is positioned to
wave away:

1. **ZCD is the wrong *class* of signal for this technique.** The OVP
   dividers work as protective impedance because OVP is a coarse
   *threshold* function (is the bus above X volts) evaluated hundreds of
   volts away from its reference. Protective impedance's own construction —
   returning current to earthed `gnd` rather than to the mains-referenced
   node the signal is actually supposed to be measured against — is
   electrically invisible to a threshold function at that scale. ZCD is the
   opposite: it is a *small-signal edge* detector whose entire information
   content lives within a few volts of the crossing itself, and it needs
   that crossing measured against AC Neutral (`dc_bus.gnd_ref`, bonded to
   `ac_n` through the CMC), not against PE (`gnd`). Neutral and PE are not
   bonded inside this appliance (that bond exists only far upstream, at the
   utility service entrance) — a real conductor, real current, real
   installation-dependent N–PE offset sits between them. Re-referencing the
   divider's return leg from `dc_bus.gnd_ref` to `gnd` measures a materially
   different quantity — "L-to-PE phase" instead of "L-to-N phase" — with an
   error that is first-order relative to the signal itself, not a rounding
   error the way it is for OVP's ~170–400V-scale threshold. See §3.
2. **The creepage burden does not disappear — it moves, and the evidence
   this session gathered says it does not obviously get easier.** §4
   measures a real, present-day cross-domain proximity failure
   (R54↔R30, 3.666mm, already below the 8.0mm PD2 floor *today*, on an
   unrelated but physically adjacent protective-impedance node) in the same
   corner of the board a ZCD chain would have to occupy. Deleting U3 removes
   one 8.560mm-limited component; it does not remove the board-area
   constraint that produced that 8.560mm figure in the first place, and
   re-floorplanning to fix it is explicitly out of scope for this task.

Neither problem is fatal on its own — §2 and §5 show the single-fault
arithmetic and the "what's lost" trade are both survivable, roughly on par
with the OVP dividers. It is the combination — a signal class that this
technique is a poor electrical fit for, stacked on a creepage outcome this
session cannot show actually improves on 8.560mm — that makes rejection the
honest call. Flip side, stated plainly: this is *not* the same kind of
rejection as "the fault analysis doesn't close" (it does close, see §2). It
is closer to "the technique closes but doesn't clearly buy anything, and the
one place it might have been decisive — deleting a component whose package
geometry is the actual binder — is unproven."

---

## 1. What U3 does today (traced from `elec/src/modules.ato`, `PowerInput`)

```
ac_l ~ r_zcd_top1.p1 (220k)
r_zcd_top1.p2 ~ r_zcd_top2.p1 (220k)
r_zcd_top2.p2 ~ zcd                              # HV-side tap, ~3.78V pk per source comment
zcd ~ r_zcd_bot.p1 (10k) ~ dc_bus.gnd_ref         # divider bottom, returns to power_return
zcd ~ d_zcd_clamp.K, d_zcd_clamp.A ~ dc_bus.gnd_ref   # BZT52C3V3 zener clamp, HV-referenced
zcd ~ r_zcd_opto.p1 (430R) ~ zcd_opto.A (H11L1 LED anode)
zcd_opto.K ~ dc_bus.gnd_ref                       # LED cathode, HV side
--- barrier (U3, H11L1TVM) ---
zcd_opto.VO ~ zcd_out.line, pulled up 10k to vcc_3v3 (SELV)
zcd_opto.GND ~ gnd, zcd_opto.VCC ~ vcc_3v3
zcd_out.line ~ mcu.zcd_in.line (main.ato:923)     # net ZCD_ISO, MCU GPIO13
```

`dc_bus.gnd_ref` (= `power_return` / `PWR_RTN`) is tied to `ac_n` through the
CMC (`ac_n ~ cmc.W2_1; cmc.W2_2 ~ dc_bus.gnd_ref`, `modules.ato:897-898`) —
low impedance at 50/60Hz. So today's "zero crossing" is genuinely an
L-to-N mains phase measurement: the divider is referenced to the *other
mains conductor*, not to earth. This matters directly for §3.

`mcu.zcd_in` (GPIO13, `PIN_ZCD_INPUT` in `firmware/components/hal/include/
temper_pins.h:81`) has **no consumer anywhere in `firmware/`** beyond that
pin definition (`grep -rn PIN_ZCD_INPUT firmware/` returns one hit). It is
not wired into `SafetyInterlock`, OCP, OVP, or WDT anywhere in
`elec/src/main.ato` or `modules.ato` — `power_in.zcd_out.line ~
mcu.zcd_in.line` is the entire connection, a plain data net. **A separate,
unrelated "ZCD" in `firmware/components/control/pll_control.c` is the
resonant-tank *current* zero-crossing (from `ct_sense.ct`, the CT, used for
ZVS/PLL phase control) — a different signal, already SELV-side by
construction (current-transformer isolation), not this circuit.** Do not
conflate the two; only the mains-line ZCD (U3) is in scope here.

---

## 2. Proposed protective-impedance topology, and the single-fault analysis

If pursued, mirroring the two already-declared OVP-01 chains
(`elec/domain_manifest.yaml`'s `protective_impedance_chains`):

```
ac_l ~ r_zcd_top1.p1 (220k, RC1206FR-07220KL, existing BOM part)
r_zcd_top1.p2 ~ r_zcd_top2.p1 (220k, same part)
r_zcd_top2.p2 ~ r_zcd_top3.p1 (220k, NEW third element -- for redundancy margin)
r_zcd_top3.p2 ~ zcd_selv                         # new SELV-domain tap, declared boundary_b
zcd_selv ~ r_zcd_bot.p1 (10k, existing part) ~ gnd   # NOT part of the chain (see below)
zcd_selv ~ d_zcd_clamp.K, d_zcd_clamp.A ~ gnd    # same zener, now SELV-referenced
zcd_selv ~ [NEW: SELV Schmitt buffer, e.g. 74LVC1G17, VCC=+3V3, GND=gnd] ~ mcu.zcd_in
```

`d_zcd_clamp`, `r_zcd_opto`, `zcd_opto` (U3), and `r_zcd_pullup` are all
deleted. A Schmitt buffer is added because the H11L1 was *also* doing
signal conditioning, not just isolation — see §5.

**Why 3 top elements, not 2:** the OVP precedent uses 3 (`min_length: 3`)
even though the standard's own text ("at least two independent
current-limiting elements") is satisfiable with 2 (if one shorts, one
remains, current-limiting is reduced, not removed). 3 is followed here only
for consistency with the established pattern and margin under a *double*
fault, not because 2 fails the letter of the rule.

### Arithmetic (170V peak, matching the OVP dividers' own working figure)

| condition | current | |
|---|---:|---|
| Normal (3×220k + 10k = 670k) | 170V / 670k = **253.7 µA** | |
| One top shorted (450k) | 170V / 450k = **377.8 µA** | |
| Two top shorted (230k) | 170V / 230k = **739.1 µA** | |

Touch-current limit (same source as the OVP dividers, same
UNVERIFIED-at-primary caveat carried forward, not re-sourced here):
IEC 60335-2-6, 0.75mA/kW capped at 5mA → 1.35mA @ 1.8kW. **All three
figures are 1.8×–5.3× under that limit, including the double-fault case** —
comparable margin to the OVP ADC divider's tightest case (0.95mA, ~70% of
limit), actually more comfortable here since ZCD's total series resistance
(670k) is larger than the ADC divider's (517k).

### Resistor rating (Yageo RC1206 1/4W family, 200V working — same
verified figure the OVP dividers use; this ZCD part, RC1206FR-07220KL, is
the same package/family)

| condition | V per top resistor | % of 200V rated |
|---|---:|---:|
| Normal | 253.7µA × 220k = 55.8V | 28% |
| One shorted | 377.8µA × 220k = 83.1V | 42% |
| Two shorted | 739.1µA × 220k = 162.6V | 81% |

Same comfortable margin pattern as both existing chains, even in the
double-fault case. `r_zcd_bot` (10k, 0603, 0.1W) sees at most 739.1µA ×
10k = 7.39V, 5.46mW — nowhere near its 0.1W rating.

### Single-fault directions, element by element

- **Any one `r_zcd_top{1,2,3}` shorts:** current rises to 377.8µA (still
  1.8× under the touch-current limit); the remaining two elements keep
  limiting. **Not a hazard.** Matches the OVP precedent's construction
  exactly.
- **Two `r_zcd_top{1,2,3}` short simultaneously (double fault, stricter than
  the standard requires evaluating):** 739.1µA, 5.3× under the limit.
  **Not a hazard**, same as both OVP dividers' equivalent case.
- **Any one `r_zcd_top{1,2,3}` opens:** loses signal amplitude, not a safety
  event — an open in a series chain never *increases* coupled current. Not
  separately analyzed by the OVP precedent either, for the same reason.
- **`r_zcd_bot` shorts:** `zcd_selv` is pulled directly to `gnd`. The HV-side
  chain (3×220k = 660k) still limits current from `ac_l` into `gnd`
  continuously — 170V/660k = 257.6µA, same order as normal operation, still
  far under the limit. **Not a hazard** — it kills the ZCD *function*
  (node pinned near 0V, no edges), a firmware-visible fault, not an
  electrical one. This is the mirror image of the ADC divider's original
  defect (a single top-side resistor, not a bottom-side one, was the
  original hazard there) — here the bottom resistor isn't part of the
  barrier at all, matching why `r_div_bot`/`r_adc_bot` are declared outside
  their own chains in the manifest.
- **`r_zcd_bot` opens:** `zcd_selv` floats up, clamped by `d_zcd_clamp`
  (now SELV-referenced) to ~3.3V on the positive excursion. Current through
  the still-intact 660k top chain into that clamp: (170V−3.3V)/660k ≈
  252.6µA — trivial against the zener's rating. **Not a hazard, and — unlike
  the ADC divider's equivalent case — the clamp actually keeps the signal
  alive** (a squarer, clamp-defined edge) rather than leaving the node to an
  unverified downstream ESD structure. Better-behaved than the ADC
  divider's own `r_adc_bot`-open case.
- **`d_zcd_clamp` shorts:** `zcd_selv` tied to `gnd` continuously; same
  arithmetic as `r_zcd_bot` shorting above (257.6µA, safe). Function lost
  (pinned low), not hazardous.
- **`d_zcd_clamp` opens:** no material change; it was never part of the
  current-limiting path.

**Verdict on this section: the single-fault construction closes, cleanly,
on the same terms the OVP dividers already established as acceptable in
this repo.** This is not where the rejection comes from.

### A caveat inherited from the OVP precedent, not introduced by this proposal

Every protective-impedance connection in this design — the two OVP
dividers, C6, and this proposed one — depends on `gnd ~ pe` being a real,
low-impedance path to earth. `docs/evidence/2026-07-30-insulation-tier-
audit.md` (merged) already established that this bond is **ordinary PCB
copper, not a continuity-tested, impedance-verified protective-earth
conductor** per IEC 60335-1's Class I construction requirements. If that
bond opens (trace fracture, bad joint), *every* protective-impedance
connection in this design loses its safety basis simultaneously, not just a
new ZCD one. This is a pre-existing, shared limitation of the technique as
already deployed here — adding a fourth user of it does not make it worse
per-user, but it does mean this design would now have four things resting
on an unverified bond instead of three. Flagged, not re-litigated here.

---

## 3. Why ZCD is a worse electrical fit for protective impedance than OVP is

This is the part of the assessment that is easy to miss if the single-fault
arithmetic (§2) is the only thing checked, so it is stated as its own
section.

Protective impedance's mechanism, physically: current from the HV node
flows through the resistor chain into `gnd`, which is bonded to PE. The
*touch-current* safety case doesn't care what `gnd`'s potential is relative
to anything else — it only cares that the current is small and has a path
to true earth. But the **signal quality** of whatever voltage is presented
at the SELV tap absolutely does depend on what `gnd` is relative to the
thing the signal is trying to measure:

- **OVP** measures "is `+170V_BUS` above a threshold?" The threshold itself
  (REF2025, 2.5V) is compared against a divider tap that swings between
  roughly `+170V_BUS * (R_bot/R_total)` scaled down to a few volts. The
  *reference* for that measurement is really just "0V, whatever `gnd`
  happens to be" — and because the signal itself spans hundreds of volts, a
  few volts of N-PE offset is a rounding error, not a mismeasurement. This
  is exactly why the manifest's own arithmetic never needed to reason about
  what `gnd` is relative to `ac_n`.
- **ZCD** measures "when does L cross N?" — a question that is *only*
  meaningful relative to N specifically. Referencing the divider to `gnd`
  (PE) instead of `dc_bus.gnd_ref` (N, via the CMC) changes what is
  physically being measured, from L-N phase to L-PE phase. Unlike OVP, this
  error is not diluted by a large full-scale signal — the entire ZCD signal
  *is* a small-signal event near zero, so an N-PE offset of even a volt or
  two lands right in the region that defines the crossing instant. At 170V
  peak, 60Hz, dV/dt near the zero crossing is ≈ 2π·60·170 ≈ 64,000 V/s;
  a 1V N-PE offset shifts the apparent crossing by ≈ 1V / 64,000 V/s ≈
  15.6µs — a genuinely bounded number, but one whose *magnitude* the design
  has no installation-independent way to characterize (N-PE offset depends
  on branch-circuit loading and wiring quality elsewhere in the building,
  not on anything this design controls), unlike every other figure in this
  document, which is derived from parts and geometry this design does
  control.

**This is not disqualifying by itself** — the signal is currently unused by
firmware (§1), so no live consumer's precision requirement is being
violated today. But it is a real, first-principles reason protective
impedance is not simply "the same trick, applied to a different net": OVP's
threshold-function shape is what makes the technique's reference ambiguity
free; ZCD's edge-function shape is what makes the same ambiguity cost
something, and this analysis has no way to bound that cost against a
standard's requirement, because no such requirement is on record for this
signal (it isn't part of any protection chain — §5).

**Aside not pursued further:** one could imagine keeping the divider
referenced to N (preserving signal fidelity) while trying to route its
current return through some *other* protective-impedance-style path.
That doesn't work — the whole reason protective impedance is licensed here
is that the current returns to an *earthed* reference (`gnd`/PE); a chain
returning to N (an HV, non-earthed-within-the-appliance node) is just the
original, already-fixed "raw resistive ZCD path into SELV" hazard
(`IEC60335_CRITICAL_COMPONENTS.md` §2.1) reintroduced by a different name,
with no earthed-reference argument to license it. This isn't a viable
middle path.

---

## 4. Creepage: what actually still binds

`scripts/measure_cross_domain_creepage.py` (`feat/pairwise-creepage-tool`,
copied into this worktree only to run, not committed) was run against this
worktree's real `pcb/temper.kicad_pcb` and `elec/domain_manifest.yaml`,
current `origin/main` state (`df84a9d0`):

```
uv run --no-sync python scripts/measure_cross_domain_creepage.py \
    --min-creepage-mm 8.0 --compare-to-mm 12.6 --json /tmp/zcd_creepage_result.json
```

**At 8.0mm (PD2): 45 of 21879 pairs violate. At 12.6mm (PD3): 196 of 21879
violate.** (99 HV pads × 221 SELV pads.) U3's own worst pin pair:
**8.560mm**, matching the task brief exactly (own-pins, `body_crossing`) —
confirms this run is measuring the same board the brief describes.

### The key finding: an *existing* protective-impedance-adjacent node
already fails PD2, today, for reasons unrelated to its own construction

R54 (`r_div_bot`, the OVP comparator divider's bottom resistor — both its
pins are on genuinely SELV nets, `safety.ovp.comp-inp` and `gnd`) shows up
in the **8.0mm violation list on the current board**:

| gap (mm) | pair | class |
|---:|---|---|
| 3.666 | R30.1(`tank.c_tank1-p2`, HV) ↔ R54.2(`gnd`) | unknown (R30 has no F.Fab/CrtYd) |
| 4.019 | R30.1 ↔ R54.1(`safety.ovp.comp-inp`) | body_crossing |

R30 is the resonant-tank inductor-coil interface connector — an HV pad —
sitting physically near the OVP-sense area. **This is a real,
un-remediated PD2 violation on `origin/main` right now**, and it has
nothing to do with R54's own chain construction (R54 is not even part of
the declared 3-resistor `ovp01_comparator_divider` chain — it's a plain
SELV-domain resistor). It is a pure whole-board proximity failure: a
legitimately-SELV pad landed too close to an unrelated HV pad elsewhere on
the board.

This is the concrete answer to "does the chain's physical layout introduce
new sub-12.6mm pairs of its own": **the creepage requirement does not
attach to the chain's own components in isolation — it attaches to every
pad on the resulting SELV net against every HV pad on the board,
board-wide.** Converting U3's crossing to a protective-impedance chain
does not exchange "one component's 8.560mm" for "automatically better" —
it exchanges it for "however close the chain's own new SELV tap node
happens to land to the *nearest* HV pad anywhere on the board," and this
session has direct, current evidence that this board's AC-input/OVP-sense
corner is tight enough to already produce sub-8mm failures for unrelated
nodes there.

One data point in the other direction, worth reporting honestly: R54 also
sits close to `F1` (the fuse, on `ac_l`) — **11.590mm / 12.270mm**, i.e.
clears PD2 comfortably but falls just short of PD3 by 0.3–1.0mm. That's the
closest any existing node in this neighborhood gets to 12.6mm without
being a declared isolator package. It suggests 12.6mm is *plausibly*
reachable for a new tap point placed with deliberate care in this region —
but "plausibly reachable with deliberate placement" is a re-floorplanning
claim, and re-floorplanning is explicitly out of scope for this task. This
document does not claim the new topology clears PD3; it reports that the
nearest available evidence is ambiguous, leaning "not free," not "solved."

### What does NOT bind

Each individual resistor's own creepage across its own body is not the
constraint — this was already established for the OVP dividers (1206/0603
package body lengths of ~1.2-3.2mm comfortably clear the ~1.2-2mm basic-
insulation figure the ~56-166V per-resistor working voltages call for, per
IEC 60664-1 pollution-degree-2 reasoning already in the manifest) and the
same per-element voltages apply here (§2). The interior nodes between
`r_zcd_top1`/`top2`/`top3` are, following the OVP precedent, left domain-
unclassified (neither HV nor SELV — genuinely mid-chain by voltage), so the
pairwise creepage tool does not check them against anything, matching how
the OVP chains' own interior nodes are treated. **The requirement lives at
the two ends: the new `zcd_selv`-adjacent SELV pads against every HV pad on
the board.**

---

## 5. What galvanic isolation provides that protective impedance does not

- **Survives faults an impedance chain does not.** A shorted opto (die
  failure bridging LED/phototransistor) is a known, testable, low-probability
  failure mode with agency data behind it (UL 1577 / IEC 60747-5-5,
  cited in `IEC60335_CRITICAL_COMPONENTS.md` §3 for this exact part). A
  resistor chain's failure modes are *inferred* (§2's fault table), not
  independently certified the way the opto's barrier rating is — the
  manifest's own UNVERIFIED note on whether safety-role resistors need
  IEC 60065 14.1(a)-style qualification (not just being a generic 1%
  chip part) applies here exactly as it does to the OVP dividers.
- **Noise immunity.** The H11L1's LED/phototransistor pair provides real
  common-mode transient immunity — relevant on a board with a resonant
  tank switching at tens of kHz a few centimetres away. A resistive
  divider's SELV tap is directly coupled (through 660k, not isolated) to
  whatever common-mode noise appears on `ac_l`/`gnd`; the proposed topology
  in §2 tries to claw some of that back with a clamp + Schmitt buffer, but
  that is signal conditioning, not isolation, and doesn't reject
  common-mode injection the way a galvanic barrier structurally does.
- **Signal conditioning was riding along with the isolation function.**
  The H11L1's internal Schmitt-trigger phototransistor output was already
  turning the divided/clamped analog waveform into a clean digital edge —
  not a separate feature, but a side effect of how opto isolators are
  built. Deleting it for protective impedance means that function has to be
  rebuilt explicitly (the added Schmitt buffer in §2's topology), which is
  a small but real added part count, not a wash.

### Is ZCD a safety-required isolation point, or a conventional one?

**Conventional — confirmed by tracing the design, not assumed.** §1
establishes `mcu.zcd_in` has no consumer in firmware today, and is not
wired into `SafetyInterlock`, OCP, OVP, or WDT anywhere in `elec/src/
main.ato`/`modules.ato`. It is a plain timing/telemetry input. This is the
one place this analysis can be more permissive than a strict reading of
"never touch a safety isolation point" might suggest — but it cuts against
this proposal for a different reason: if ZCD's precision requirement is
genuinely unconstrained today (nothing consumes it), the case for accepting
§3's uncharacterized N-PE reference error is *weaker*, not stronger — there
is no requirement on record this proposal can point to and say "this error
budget is acceptable for that." The absence of a consumer removes the
"this would break a safety interlock" objection; it does not supply the
"and therefore any timing error is fine" argument, because nobody has
stated what timing error would be fine.

---

## 6. Verdict and reasoning

**Reject.** Restated with the standard clauses this reasoning relies on
(same UNVERIFIED-at-primary caveats the manifest itself already carries for
these — IEC 60335-1's primary text is paywalled and was not independently
re-fetched in this pass):

- IEC 60335-1's protective-impedance provision (as reconstructed in
  `elec/domain_manifest.yaml`'s own STANDARD CLAUSE block, UNVERIFIED-at-
  primary): protective impedance is licensed as an alternative to
  reinforced insulation *provided* (a) at least two independent
  current-limiting elements such that no single failure removes the
  current-limiting function, and (b) touch current stays under the
  applicable limit in normal and single-fault operation. §2 shows this
  construction rule is satisfiable for ZCD, on the same terms as the two
  existing OVP dividers. **This is not where the rejection comes from.**
- IEC 60335-2-6's touch-current limit (0.75mA/kW capped at 5mA → 1.35mA
  @ 1.8kW, carried forward from `docs/evidence/2026-07-26-emc-validators-
  implemented.md` Sec 10, not re-sourced against primary text here): all
  fault currents in §2 clear this with 1.8×-5.3× margin. **Not where the
  rejection comes from either.**
- The rejection is: (1) §3 — protective impedance's own mechanism (earth-
  referenced return current) is electrically indifferent to what it costs a
  *threshold* function (OVP) but is not indifferent to what it costs an
  *edge* function referenced to the other mains conductor (ZCD), and this
  design has no standard or requirement on record to bound that cost
  against; and (2) §4 — this session has direct, measured evidence
  (R54↔R30, 3.666mm, a live PD2 violation today) that the physical
  neighborhood a ZCD chain would occupy is already producing sub-threshold
  cross-domain proximity, so "delete U3, gain 12.6mm" is not a claim this
  analysis can support without the re-floorplanning work this task puts
  out of scope.
- Rejecting here does **not** mean protective impedance is the wrong tool
  in general — the OVP dividers remain a sound precedent for a
  *threshold*-shaped signal referenced to an earthed node. It means this
  specific signal (a small-signal, N-referenced edge detector, currently
  unconsumed by firmware) is a poor match for the technique's own physics,
  independent of whether the fault arithmetic closes.

## 7. Flagged, not established (do not treat as resolved)

- **The magnitude of a real installation's N-PE voltage offset** (§3) —
  not measured, not sourced from any wiring-practice reference in this
  pass. The 15.6µs/volt figure is a first-principles dV/dt calculation,
  not a measured or datasheet number.
- **Whether 12.6mm is actually achievable for a new ZCD SELV tap node**
  with deliberate placement (§4) — the F1↔R54 11.59-12.27mm figure is
  suggestive, not a placement study. Re-floorplanning is out of scope here.
- **ESP32-S3 GPIO absolute-maximum/ESD clamp current rating** for the
  `r_zcd_bot`-open fault direction (§2) — carried the same UNVERIFIED flag
  the ADC divider's equivalent analysis already carries in the manifest;
  not pulled from the datasheet in this pass.
- **Whether IEC 60335-1 requires safety-role resistors to carry their own
  qualification** beyond being a generic 1% chip part (§5) — same open
  item the manifest already flags for the OVP dividers, inherited here
  unchanged.
- **`gnd ~ pe` bond continuity/impedance verification** — established as
  unresolved by a separate, already-merged audit (`docs/evidence/
  2026-07-30-insulation-tier-audit.md`), not re-investigated here; noted
  in §2 as a shared precondition of every protective-impedance connection
  in this design, existing ones included.

## 8. Constraints honoured

- No `elec/src/**`, `pcb/**`, netclass, footprint, or safety-constant
  change anywhere. `scripts/measure_cross_domain_creepage.py` was copied
  in to run §4's measurement and removed before commit — not part of this
  change's diff.
- No proposal to relax 12.6mm, change pollution degree, or reclassify a
  domain. §6's rejection stands on the analysis, not on loosening the
  target.
- Single-fault criterion not weakened: §2's construction requires no two
  faults to occur together for safety (the double-fault case is reported
  for margin, not required to close the argument).
- No board re-floorplanning performed or proposed as fact; §4 explicitly
  declines to claim 12.6mm is achieved.
- Built in an isolated worktree (`git worktree`), branched from
  `origin/main`, `make venv-isolate` run before any measurement. No
  `git stash` used. `uv run --no-sync` used for the one tool invocation.
  No sub-agents spawned.
