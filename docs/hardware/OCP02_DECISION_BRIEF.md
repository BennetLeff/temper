<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 (worktree-agent-a79e198a124568852, based on origin/main), dirty=false except this file -->

# OCP-02 — Secondary Overcurrent Protection: Decision Brief

> **DECISION SUPERSEDED 2026-08-16.** This brief's recommendation — "build it — second current
> transformer at `DC_BUS_RTN`" — was implemented (Option A, 2026-08-07) and then **de-scoped** on
> 2026-08-16: the CST3015 CT's 9.100mm intrinsic primary↔secondary creepage cannot reach the
> 12.6mm PD3 reinforced bar in any placement, no alternative mechanism clears it (Hall ICs
> 4.0–4.2mm, AMC1301 8.5mm — datasheet-verified in `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md`),
> and OCP-02 is not IEC 60335-1 clause-mandated. The brief's common-mode analysis and option
> assessment remain the correct record of the 2026-08-07 decision; the de-scope decision record is
> `docs/evidence/2026-08-16-ocp02-descope-implementation.md`. The aperture-CT reinstatement path it
> could not have evaluated remains the standing long-term fix (blocked on a verified
> reinforced-insulation certificate).

**Date:** 2026-08-07
**Decision required:** which sensing topology resolves OCP-02's blocked
common-mode problem, or whether to de-scope the requirement instead.
**Recommendation:** **build it — second current transformer at `DC_BUS_RTN`,
mirroring OCP-01's CT.** Reasoning below. De-scoping was seriously
considered (it was the right call for DESAT) and rejected on the evidence;
a human should still accept or reject this explicitly before `elec/` is
touched.

This brief does not modify `elec/`, `pcb/`, or `docs/hardware/BOM.md`. It
is the analysis needed to make and implement that decision.

---

## 1. What is actually blocked, derived not assumed

`SecondaryOCPComparator` is fully specified in `elec/src/modules.ato:2650-2783`
(2 mΩ shunt, INA240A1 G=20, 3.74k/10k reference divider, TLV3201 comparator,
60.0 A nominal trip, 59.0–61.1 A worst case) but is **not instantiated**
(`modules.ato:3053-3058`, `# ocp2 = new SecondaryOCPComparator`), and
`fault_or3.B1` — the fan-in input reserved for it — is tied to GND
(`modules.ato:3154`). `main.ato:760-778` documents why: the design places
its shunt in `DC_BUS_RTN`, and that node's common-mode voltage is not what
the original design doc assumed.

**Deriving the common-mode voltage, from the schematic, not the docstring's
claim:**

- `main.ato:511-522`: `dc_bus_plus` is the **+170 V half-bus**
  (`dc_bus_plus.override_net_name = "+170V_BUS"`), and `dc_bus_minus` —
  `DC_BUS_RTN` — is its complement. Both are outputs of `PowerInput`'s
  Delon/cascade voltage doubler.
- `main.ato:527-528`: `power_return` is named explicitly as "the doubler
  MIDPOINT," tied to `power_in.dc_bus.gnd_ref`.
- `main.ato:754`: `gnd ~ pe` — signal ground is DC-bonded to protective
  earth, and (per the SELV redesign) is referenced through the doubler
  midpoint side of the circuit, not floating.
- `main.ato:806-807`: `tank.out ~ ct_sense.primary_in; ct_sense.primary_out
  ~ power_return` — confirming `power_return` is the node the resonant
  tank (and OCP-01's CT) actually returns to, i.e. the ~0 V reference for
  this board.

`dc_bus_plus` and `dc_bus_minus` sit on either side of the doubler midpoint,
each nominally **170 V** from it, opposite polarity. **`DC_BUS_RTN` is
therefore ≈ −170 V relative to signal ground**, not "the bulk return, near
0 V" as `docs/hardware/OCP02_DESIGN.md`'s original text assumed. Against
the INA240's **−4 V to +80 V** absolute maximum common-mode rating
(`components.ato:461`, read from TI SBOS662A/SBOS808E directly), an INA240
referenced to signal ground and wired into `DC_BUS_RTN` sees roughly double
its rated maximum common-mode voltage. This is confirmed independently in
three places in the tree (`OCP02_DESIGN.md`'s correction note,
`SecondaryOCPComparator`'s own docstring, and
`docs/evidence/2026-07-27-fault-tree-capacity-expansion.md`) — this brief's
contribution is deriving the −170 V figure directly from the doubler
topology rather than citing the prior finding, and confirming there is
**no other node in this topology** where a low-side shunt sees near-zero
common mode except `power_return` itself (§2, "On D," below).

---

## 2. Options considered

| # | Option | Sensing location | Common mode there | Meets isolation barrier? | New MPN risk | <5µs? |
|---|---|---|---|---|---|---|
| A | **Second current transformer** (mirrors OCP-01) | `DC_BUS_RTN`, in series (same splice point the shunt design already used) | N/A — magnetically isolated; secondary references signal ground regardless of primary potential | **Yes**, 5000 Vrms reinforced / ≥8 mm creepage — same part already used and declared for OCP-01 | **None** — same already-verified MPN (`CST3015-100ED`) | Demonstrable for logic/driver path (528 ns worst case); analog front end plausible, unmeasured |
| B | **Isolated amplifier + shunt** (`AMC1300DWVR`) | Shunt stays at `DC_BUS_RTN`; AMC1300 crosses the isolation barrier in place of INA240 | Handled by design: AMC1300's HV-side ground floats with the shunt, only needs a local isolated bias supply | **Yes**, 5000 Vrms UL1577 / 1500 Vrms working voltage / 8.5 mm creepage — real TI datasheet, verified this session | Low — real, stocked part, but **needs a second isolated bias supply**, itself unspecified | Demonstrable but tight: 3.4 µs (AMC1300 max, datasheet) dominates the 5 µs budget |
| C | **High-common-mode amplifier** rated above ~170 V | `DC_BUS_RTN` directly, non-isolated | Would need CM rating >170 V | N/A — see below | **No real part found** | N/A |
| D | **Shunt at a genuinely low-CM node** | `power_return` (doubler midpoint) | ~0 V | Isolation moot (SELV-side node) | Reuses existing INA240/TLV3201 design | Fast (~1.4 µs by design-doc arithmetic, unmeasured) |
| — | **De-scope** | — | — | — | — | — |

**On C:** researched rather than assumed absent. TI's INA240 family tops
out at 80 V common mode; ADI's MAX49925 ("High Voltage Bidirectional
Current-Sense Amplifier," explicitly marketed for automotive high-voltage
use) is −40 V to +76 V; ON Semi's NCS7041 is 80 V. No standard
current-sense-amplifier IC found in this search reaches anywhere near
170 V. The only path to genuinely higher CM without isolation is a
discrete floating-supply/Zener-referenced front end (TI's own SBOA295
reference design for 12–400 V sensing uses exactly this technique with an
INA138) — that is a bespoke analog design exercise, not a component swap,
**and it still provides no galvanic isolation across the mains-adjacent
barrier**, so it would not clear the reinforced-insulation requirement
this crossing needs regardless of whether its common-mode range is
adequate. **C is ruled out**: no real off-the-shelf part, and the discrete
workaround doesn't solve the isolation requirement either.

**On D:** this is not a new option beyond what `OCP02_DESIGN.md` already
flagged as "shunt at the doubler midpoint" — investigated here to confirm
it, not merely repeat it. `power_return` is the only node in the current
path (tank branch, half-bridge, DC bus) that sits at ~0 V relative to
signal ground; everything else is either `dc_bus_plus`/`dc_bus_minus`
(±170 V) or the switching node (0–340 V, worse). An AC-line-current sense
point ahead of the rectifier would see low CM too, but it is filtered by
the bulk caps and far too slow to catch a <5 µs fault — not viable for
this requirement. D therefore collapses into the trade-off already on the
table: **`power_return` is the exact node OCP-01's CT already returns
through** (`ct_sense.primary_out ~ power_return`, `main.ato:807`) — placing
OCP-02's shunt there means a single failure at that physical
node/connector/trace could disable both channels, defeating the
independence that is OCP-02's whole reason to exist. Kept in the table for
completeness, not carried forward as a candidate.

I found no fifth option the circuit suggests beyond A/B/C/D — the design
space here really is "isolated sensor" vs. "isolated amplifier" vs.
"high-CM part" vs. "different node," and C and D each resolve to "not
viable" for reasons specific to this board, not by assumption.

---

## 3. Per-option analysis

### 3.1 Option A — second CT at `DC_BUS_RTN`

**Placement rationale, not assumed:** `hb.dc_bus.hv_minus ~ dc_bus_minus`
(`main.ato:778`) — the half-bridge's low-side switch returns through
`DC_BUS_RTN`. In a shoot-through fault (both IGBTs conducting), the fault
current path is `dc_bus_plus → Q_high → SW_NODE → Q_low → DC_BUS_RTN`,
i.e. it **does** flow through this conductor — the same fault class the
original shunt design targeted. This is a genuinely switched (AC-content)
waveform, not smoothed DC, so a CT — which cannot sense DC at all — works
here for the same reason it works for OCP-01's tank current.

**Isolation:** the CT primary is a two-terminal splice with no electrical
connection to its secondary; the secondary can be referenced to signal
ground regardless of the primary conductor's absolute potential, up to the
part's insulation rating. `CST3015-100ED` — the exact part already used
for OCP-01 — is rated **5000 Vrms 1 min, reinforced, ≥8 mm creepage/
clearance** (`components.ato:124-141`, from Coilcraft Document 1608-1).
This clears the board's own reinforced-barrier standard (**6.4 mm
clearance / 8.0 mm creepage** at 400 V working voltage, PD2, material
group IIIb — `scripts/check_isolation_keepout.py:53-63`) with margin, and
is **the same MPN already committed and used** for OCP-01, so there is
zero incremental part-verification risk — this is a quantity change on an
already-verified line, not a new part. It is also already declared as a
domain-manifest isolator (`elec/domain_manifest.yaml:402-409`,
`ct_sense.ct`); a second instance follows the identical declaration
pattern.

**Sensed-current headroom:** 88 A rated vs. a 55–65 A trip window gives
1.35–1.6x headroom (less than OCP-01's 1.73x margin at 50 A, but still
inside the part's rating with room; the 88 A figure is itself a 40 °C-rise
reference point per the datasheet, not a hard ceiling, per the component's
own docstring note).

**Reference-divider caveat, derived not assumed:** naively reusing OCP-01's
exact burden (4.99 Ω) at the same 1:100 ratio for a 60 A trip requires
V_ref = 60 A / 100 × 4.99 Ω = **2.994 V** — 91% of the 3.3 V rail, uncomfortably
close to VCC once the rail's own ±5% regulation tolerance (`BuckConverter3V3`,
already used as a worst-case term elsewhere in this repo) is stacked on
top. This is not a blocker, but it means OCP-02's divider cannot be a
drop-in copy of OCP-01's; either a lower burden value or (better) a
precision reference — `REF2025` is already instantiated elsewhere on this
board for the RTD window — should replace a raw-3.3V-rail divider. This is
a real, solvable design detail, not fully worked here because it is an
`elec/` change and out of this brief's scope.

**What's unresolved and stated as such:** whether a second `CST3015-100ED`
footprint (23.0 × 30.0 mm — the same body that forced a board re-layout
when it replaced OCP-01's original CT) fits the current PCB without
another routing regression is **not established in this brief**. I did not
touch `pcb/` and have no current placement/free-area data; a placement
study is a prerequisite before committing to this option, not a formality.

### 3.2 Option B — isolated amplifier (`AMC1300DWVR`) + existing shunt

Verified directly from TI's datasheet (SBAS895D, May 2018, rev. May 2022 —
fetched and read this session, not taken from a search snippet):

- Reinforced isolation: **5000 Vrms** (UL1577, 60 s qualification), **1500
  Vrms maximum working voltage** (DIN VDE V 0884-11), external clearance
  and creepage **≥8.5 mm** — clears this board's 6.4 mm/8.0 mm reinforced
  requirement.
- Gain **8.2**, ±250 mV input full-scale — at 60 A across the already-specified
  2 mΩ shunt (120 mV), this is under half of full-scale, comfortable
  headroom, no clipping.
- **AMC1300 replaces INA240 entirely** — it reads the shunt directly and
  crosses the isolation barrier in one part, rather than the original
  design's implied two-stage (local INA240 gain + separate isolator)
  chain. This simplifies the BOM relative to `OCP02_DESIGN.md`'s original
  sketch, at the cost below.
- **Confirmed real and stocked:** `AMC1300DWVR`, 8-SOIC, DigiKey lists it
  in stock at **~$6.37/unit (1-piece price, cut-tape)** per a DigiKey
  search-result snippet; I could not re-confirm this figure against the
  live product page in this session (a direct product-page fetch attempt
  by guessed URL returned an unrelated part number), so treat the price as
  approximate, not verified to the standard this repo's MPN-fabrication
  audit otherwise applies. The part's existence, package, and electrical
  specs above **are** independently verified against the TI datasheet PDF.

**The real cost is a second isolation barrier.** AMC1300 needs its own
isolated power supply on the high-voltage side (VDD1, 4.5–5.5 V for
AMC1300, referenced locally to the shunt/`DC_BUS_RTN` node, not to
`power_return`). This board's existing isolated supply (`AuxSupply`, Mean
Well IRM-10-15) is referenced to `power_return`, not `DC_BUS_RTN` — it
cannot power this directly. `simulation/models/UCC14140_behavioral.sub`
exists in this repo but **no `component UCC14140` is defined anywhere in
`elec/src/*.ato`** (confirmed by grep) — someone anticipated an isolated
bias-supply need and left a simulation model for it, but never implemented
it as an orderable part. TI's `UCC14140-Q1` (verified real this session:
>3 kVrms isolation, 12 V in / 25 V output, 1.5 W, orderable as
`UCC14140QDWNRQ1`) is a plausible real candidate, but its 25 V output is
sized for gate-driver bias, not a 5 V analog rail — using it here would
need an additional local LDO, i.e. this is a genuine new subsystem (supply
+ regulation + its own isolation-barrier verification and PCB keepout),
not "add one IC." That puts this option's true integration cost closer to
DESAT's "driver-family redesign" framing than to a value change, even
though every individual part is real and available.

### 3.3 Timing — the demonstrable/plausible distinction, and why it matters more here than for OCP-01

Per `docs/STRATEGY.md` and `docs/evidence/2026-07-27-fault-tree-capacity-
expansion.md`, OCP-01's own <1 µs budget is **not simulated** —
`TLV3201_ngspice.lib`'s header states outright it "does not claim a
timing, noise, or temperature model" (confirmed by reading the file this
session: the comparator is a zero-delay behavioral switch with a 0.5 pF
output cap, nothing else). The only real timing numbers in this repo come
from a **datasheet-derived, non-simulated, worst-case arithmetic bound**
(`docs/evidence/2026-07-27-fault-tree-capacity-expansion.md`), using TI's
published 2V-VCC worst-case propagation delays (conservative stand-in;
neither part is characterized at 3.3V) for the actual gate cascade in
`modules.ato`:

| Part | Worst-case t_PD (VCC=2V, −40–85°C) |
|---|---|
| SN74HC4075 (OR) | 125 ns |
| SN74HC00 (NAND, latch) | 115 ns |
| UCC21550 gate driver | 48 ns (existing figure, reused) |

**OCP-02's logic path is shorter than OCP-01's, which I traced explicitly**
(`modules.ato:3153-3159`): OCP-01 enters at `fault_or.A1` and cascades
`fault_or` gate1 → gate2 → `fault_any_or` gate1 → `fault_or3` gate2 → latch
(**4 OR + 2 NAND**, matching the 730 ns figure in the evidence doc).
OCP-02's reserved input, `fault_or3.B1`, enters **two gates closer to the
latch**: `fault_or3` gate1 → gate2 → latch (**2 OR + 2 NAND**):

    2×125 + 2×115 = 480 ns (logic) + 48 ns (driver) = 528 ns worst case

This portion is real, datasheet-sourced, and **demonstrable by arithmetic**
regardless of which sensing option is chosen (both A and D route through
the same reserved input; B's amplifier sits upstream of this same logic).

What differs by option is the **front-end** delay feeding into that 528 ns:

| Option | Front-end delay | Source | Status |
|---|---|---|---|
| A (2nd CT) | Sub-µs expected (CT bandwidth 0.78 kHz–>1 MHz per datasheet) + comparator | Coilcraft datasheet (bandwidth only, not a delay figure) + TLV3201 (unmeasured) | **Plausible, not demonstrated to a number** — same honesty gap OCP-01 itself still has |
| B (AMC1300) | **2.0–2.7 µs typ / up to 3.4 µs max** (50%–90%, unfiltered output, standard grade) + comparator | TI SBAS895D §7.10, read directly this session | **Demonstrated** (real datasheet max), and it **dominates** the budget |
| D (midpoint shunt) | ~0.875 µs INA240 rise time (per `OCP02_DESIGN.md`'s own arithmetic, not independently re-verified this session) + comparator | Design-doc arithmetic, unmeasured | Plausible, not independence-preserving (see §2) |

**Total worst-case budget, option A:** even a pessimistic 10x-over-datasheet
guess at the unmeasured analog front end (400 ns, purely illustrative, not
a claim) plus 528 ns logic/driver is ~930 ns — **more than 4 µs of margin**
to the 5 µs requirement.

**Total worst-case budget, option B:** 3.4 µs (AMC1300 max) + 528 ns
(logic/driver) + TLV3201's unmeasured comparator delay (its datasheet-typical
40 ns, not a guaranteed max) ≈ **3.97 µs**, leaving **~1.03 µs (~21%)**
margin — the tightest of any option here, and the only one where the
isolation stage itself, not the logic tree, is the dominant term. This
number **cannot be improved by a wiring or logic choice**; it is intrinsic
to the AMC1300's delta-sigma-modulator isolation architecture (the faster
AMC1300B grade only gets to 2.1–3.0 µs, still the dominant term).

**Verdict for requirement item 3:** <5 µs is **demonstrable** for the
logic/driver portion under any option (real datasheet numbers, computed
here, not simulated). It is **demonstrable-with-large-margin** for option
A's total budget under a deliberately pessimistic front-end assumption,
and **demonstrable-but-tight** for option B, where the dominant term is a
verified datasheet maximum rather than an assumption. What would make
either fully demonstrated rather than partially plausible: a bench or
SPICE-with-real-timing-model measurement of the TLV3201's actual
propagation delay — a gap this repo has now flagged for OCP-01 twice
(`STRATEGY.md`, this document) without closing it. No delay figure in this
brief is reported as measured when it isn't; the AMC1300 numbers above are
the one genuinely new, datasheet-verified quantity this brief adds to the
timing picture.

---

## 4. Simulation — what could and could not be done

`simulation/harness/run_ocp01_sim.py` is the working example this brief
was pointed at. I attempted to extend the same approach to a candidate
OCP-02 circuit and hit a hard environment limit, reported rather than
worked around: **`ngspice` is not installed in this sandbox, and I do not
have root to install it** (`apt-get install ngspice` fails with a
permission error; no vendored binary exists anywhere on the machine). No
ngspice-based simulation was run for this brief, for OCP-02 or as a
re-run of OCP-01.

**What I did instead, honestly bounded:**

- **Reused the existing, committed OCP-01 evidence** rather than
  re-deriving it: `docs/evidence/2026-07-27-ocp01-trip-point-sim.json`
  reports a simulated trip current of **49.971 A** (worst case 48.774–
  51.155 A), all runs `"calibrated": false`, deterministic across 5 ngspice
  runs. This is the real, current-at-HEAD number for OCP-01 — not the
  "50.12 A" figure mentioned in my task brief, which appears to be from an
  earlier run (`docs/evidence/2026-07-25-ocp01-trip-point-sim.json` is the
  other candidate on disk); I'm reporting the most recent committed
  evidence file rather than guessing which the brief meant.
- **No SPICE model exists in this repo for INA240, AMC1300, or any
  isolated amplifier** — `simulation/models/` holds 13 models (checked by
  listing the directory): CT, gate driver support parts, comparators,
  regulators, and thermal/pan-load models, but nothing for a
  current-sense or isolation amplifier. A candidate OCP-02 circuit built
  around either shunt-based option (B or D) could not be simulated even
  if ngspice were available, without first writing and validating a new
  behavioral model — itself a `calibrated: false` model, per this repo's
  own convention, until bench-checked.
- **Option A (second CT) could reuse `current_transformer.sub` and
  `TLV3201_ngspice.lib` exactly as `run_ocp01_sim.py` does**, with `N=100`
  and a re-derived burden/reference for a 60 A trip point — this is the
  one candidate that is mechanically ready to simulate the moment ngspice
  is available in an environment that has it. I did not fabricate a trip
  figure by hand-deriving one and presenting it as simulated; the
  worst-case-corner *arithmetic* (pure Python, no ngspice needed) that
  `run_ocp01_sim.py` also performs independently of the simulator is the
  same style of check that produced the 59.0–61.1 A / 58.5–61.6 A figures
  already in `SecondaryOCPComparator`'s own docstring for the INA240
  design — those are real, already computed, and I re-checked the
  arithmetic (3.74k±1%, 10k±1%, shunt 2mΩ±1%, INA240 gain ±1%, exhaustive
  16-corner sweep computed in Python: **58.54–61.59 A**, nominal 60.04 A),
  agreeing with the docstring's own re-derivation to within 0.04 A.
- Every model referenced in this brief — existing or hypothetical —
  carries `calibrated: false`. No bench measurement of any OCP-02
  candidate exists.

---

## 5. Interaction with OCP-01

**Threshold separation, checked against real committed numbers, not the
nominal-only figures:** OCP-01's worst-case band (tolerance + tempco,
`docs/evidence/2026-07-27-ocp01-trip-point-sim.json`) is **48.774–51.155 A**.
OCP-02's worst-case band, independently re-checked this session against
`SecondaryOCPComparator`'s committed values, is **58.54–61.59 A**. The gap
between the two worst-case bands is **7.4 A**, comfortably separated —
there is no tolerance stack-up under which OCP-02 could trip before or
simultaneously confuse OCP-01's window. On a monotonically rising fault
current, OCP-01 trips first in every case, which is the intended behavior
(secondary protection is a backstop, not a race).

**Both reach the latch, mechanically verified, not assumed:**
`scripts/capacity_budget_gate.py`'s BFS reachability check
(`docs/evidence/2026-07-27-fault-tree-capacity-expansion.md`) confirms
`fault_or3.B1` — OCP-02's reserved input — is a genuine `AVAILABLE`
SET-path input that reaches `latch.A1` (`SN74HC00DR`'s SET pin) through
`fault_or3` gate1 → gate2, exactly the same package already carrying
UVL-02's fault line on gate1's `A1`. OCP-01 reaches the same latch through
the separate, longer `fault_or → fault_any_or → fault_or3` path (§3.3).
Because the latch's SET input is level-sensitive (an OR-of-ORs feeding an
SR latch), both channels asserting SET at overlapping times — plausible if
a fault ramps fast enough to cross both windows within the propagation
window — is not a hazard: SET is OR'd, and RESET is a separate, qualified
path (`fault_any_or.B2`/reset-qualifier logic, untouched by either OCP
channel). No race condition exists between the two channels at the latch.

---

## 6. Should OCP-02 be de-scoped instead? (The DESAT question, asked honestly)

DESAT was de-scoped because the enabling hardware **did not exist within
the chosen gate-driver family** — TI's actual DESAT-capable parts require
a different driver architecture entirely, and the document that proposed
otherwise cited a non-existent part number. That is a "this cannot be
built without a redesign no one has scoped" situation.

OCP-02 is different in a way that matters to this decision:

1. **It is buildable.** Two of the four candidate topologies above (A, and
   B with added scope) use real, verified, available parts and clear the
   5 µs timing budget on datasheet arithmetic. This is not a case where
   the enabling part doesn't exist.
2. **It is an explicit, numbered acceptance-test line item**, not a design
   pattern borrowed from a since-discredited document. `docs/
   FUNCTIONAL_TEST_CRITERIA.md` §2.1 lists "Secondary OCP | 60A Peak |
   55–65 A | <5 µs" on equal footing with OCP-01 in the same table.
   De-scoping it is not "remove 19 uncosted BOM lines" (DESAT's actual
   footprint) — it requires editing a currently-standing, explicitly
   numbered pass/fail criterion in the acceptance-test document itself, a
   materially more visible and consequential change than DESAT's.
3. **The redundancy argument is real and specific to this board's
   topology**, not generic defense-in-depth: a shoot-through fault's
   current path physically crosses `DC_BUS_RTN` (§3.1) whether or not it
   registers proportionally on OCP-01's tank-return CT — the two sensing
   locations are not measuring the same current by construction, which is
   the actual justification for building a second channel here rather
   than just trusting OCP-01's existing 45–55 A margin under the IGBT's
   60 A pulsed SOA limit (`main.ato:610-631`).

**What OCP-02 does *not* close, regardless of which option is built** — the
same residual-risk class DESAT's brief already named for that circuit, and
unchanged by this brief:

| Uncovered fault | Why current sensing (either OCP-01 or OCP-02) misses it |
|---|---|
| Gate-drive degradation (sagging bootstrap, partial turn-on) | Device stays in linear region below the 45–65 A current window while dissipating heavily |
| Response speed vs. the fastest possible short | A hard short can, in principle, destroy a device faster than sense→amp/CT→comparator→logic→driver responds, for either channel |

These are the same gaps DESAT would have closed and remain open regardless
of this decision — recorded here for consistency with `BOM.md`'s existing
"Accepted residual risk" table (§5.4/§4.4), not newly discovered.

**Given the above, de-scoping is not the recommendation here.** Unlike
DESAT, the evidence supports building OCP-02, and a real, low-part-count,
low-timing-risk path (option A) exists.

---

## 7. Recommendation

**Build option A: a second `CST3015-100ED` current transformer in series
with `DC_BUS_RTN`, entering the fault tree at `fault_or3.B1`.**

Reasoning: zero new MPN-verification risk (same already-audited part as
OCP-01), the largest timing margin of any option by a wide margin (>4 µs
of headroom even under a pessimistic front-end assumption, against option
B's ~1 µs), the shortest logic path to the latch of any protection channel
on this board (528 ns worst case, 2 gates fewer than OCP-01's own path),
and an isolation story that is a copy of an already-declared, already-
working pattern (`elec/domain_manifest.yaml:402-409`) rather than a new
one. The reference-divider tightness noted in §3.1 (91% of VCC at nominal)
is real but solvable — swap the raw 3.3V-rail divider for the already-
instantiated `REF2025` precision reference, which is exactly the fix this
repo already applied to OVP-01 for an analogous near-rail problem
(`OVPComparator`'s "RE-REFERENCED 2026-07-27" history). **Unresolved and
flagged rather than assumed:** whether a second 23×30mm CT footprint fits
the current board without a routing regression — a placement study is a
prerequisite, not a formality, before this is committed to `elec/`.

**Runner-up: option B, `AMC1300DWVR` reading the existing 2 mΩ shunt.**
This preserves the original design's genuinely different sensing
*technology* from OCP-01 (resistive vs. magnetic — two CTs on one board
share more failure-mode DNA, e.g. core saturation or EMI susceptibility,
than a CT and a shunt do), uses smaller components with less placement
risk than a second CT body, and every part named is real and verified.
Its costs are real, not merely different in kind: the tightest timing
margin of any viable option (~21%, and intrinsic to the part, not
improvable by logic choices), and a genuinely new isolated-bias-supply
subsystem this brief did not fully specify (no `UCC14140` component exists
in `elec/src/*.ato` today, only an orphaned simulation model) — closer in
scope to a small redesign than a part swap.

**What would change this answer:**

- If a placement study shows a second `CST3015-100ED` does not fit without
  a routing regression at least as bad as the one the first one caused,
  switch to option B despite its added bias-supply scope — smaller
  components under real board-area pressure beats a component that is
  already known to force a re-layout once.
- If a bench or timing-modeled measurement of TLV3201's real propagation
  delay comes back materially worse than its 40 ns datasheet-typical
  figure, option B's thin (~21%) margin is the one most at risk; option
  A's >4 µs of headroom absorbs that same uncertainty comfortably. This
  is a reason to prefer A now, before that measurement exists, not just
  a tiebreaker.
- If independence from OCP-01's specific failure modes is weighted above
  propagation margin, board area, and part-verification risk — i.e., if
  "two different sensing physics" matters more than "fastest, cheapest,
  already-verified" — option B is the better answer despite its costs.

This is a recommendation, not a decision: a human should accept or reject
it, and either way `fault_or3.B1` should not remain a reserved-but-silently-
grounded input indefinitely once this is resolved one way or the other.
