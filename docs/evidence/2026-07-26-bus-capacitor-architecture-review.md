# Bus capacitor ripple failure: is this a part-selection problem at all?

**Provenance: commit=UNKNOWN dirty=UNKNOWN** -- backfilled prior to the provenance gate's introduction (2026-07-26); no self-declared commit exists in this file's own content and none was fabricated. See .evidence-provenance-allowlist.

**Scope and status.** `docs/evidence/2026-07-26-bus-capacitor-ripple.md`
established (not re-derived here) that `C_BUS1/1B/2/2B` (`EKMQ251VSN182MA50S`,
1800µF/250V snap-in, 2 parallel per half-bus) fail their rated ripple current
by 4.2–5.8× (central 4.8×) under actual operating current. A same-day
reselection to `ALS30A472MF250` (KEMET, 4700µF/250V screw terminal) was
implemented and then **reverted** (`elec/src/modules.ato`,
`docs/hardware/BOM.md`) once board-area math showed it doesn't fit — see §1.
Source is back on `EKMQ251VSN182MA50S`: real, fits, **still fails ripple
current**. That failure is open, not resolved, at the end of this document
too — this is an analysis with a recommended next step, not a fix.

**Analysis only. No topology change is implemented here** — `elec/src/*.ato`
is untouched by this document (the bus-cap revert described above was a
separate, already-committed correction of a wrong reselection, not new
design work). The required-rating derivation in
`docs/evidence/2026-07-26-bus-capacitor-ripple.md` is unchanged and not
redone.

---

## 1. Area-infeasibility correction (screw-terminal reselection)

`docs/evidence/2026-07-26-bus-capacitor-reselection.md` originally
characterized fitting 6× `ALS30A472MF250` (66mm-diameter screw-terminal
cans) as "relocating roughly a dozen neighboring components." That
materially understated the problem. Board outline is `(20,20)-(172,254)` mm
in `pcb/temper.kicad_pcb` = 152×234mm = **35,568 mm²** (confirmed against
the file's Edge.Cuts and against the four existing bus-cap footprint
positions, unchanged since that doc was written).

| Packing assumption | Area for 6× 66mm cans | % of board |
|---|---|---|
| Raw circles (π×33², no clearance) | 20,527 mm² | **57.7%** |
| Square grid, 70mm pitch (diameter + clamp clearance) | 29,400 mm² | **82.7%** |
| Hex packing, 70mm pitch | 25,461 mm² | 71.6% |
| Literal grid-fit inside the 152×234mm rectangle at 70mm pitch | 2×3 = 6 positions, zero margin, zero room for anything else | — |

**Corrected statement: this bank alone consumes 58–83% of the entire board.**
That is not a layout adjustment to a dozen nearby parts — it is "there is no
room left for the half-bridge, gate drive, MCU, sensing, or resonant tank."
The literal grid-fit line is the sharpest way to see it: at a pitch that
provides reasonable clamp/wiring clearance, the *entire* board rectangle
holds exactly 6 cans with nothing left over — which happens to be exactly
the count needed, meaning zero slack for board edge margin, mounting holes,
connectors, or any other component. This is why the reselection was
reverted rather than carried forward with a promised future layout change.

---

## 2. Does "more, smaller D35mm cans" do better per unit of board area?

**Checked, not assumed.** Ripple-current capability in a 2-pin snap-in scales
with can volume/surface area, so the intuition that many small cans beat few
large ones (more total surface area for the same footprint category) is
reasonable to check. Using the best real same-footprint 250V part found
in the original reselection search — Rubycon VXH 2200µF/250V, 35×60mm,
**3.37 Arms @105°C/120Hz** (Mouser datasheet `e_VXH-1600617.pdf`) — against
the ripple doc's own already-120Hz-normalized combined per-cap figures
(§5 of that doc: best 11.39A / central 13.02A / worst 15.57A, at the
existing N=2-per-half basis), scaling by `2/N`:

| N per half (total) | Best | Central | Worst | Verdict |
|---|---|---|---|---|
| 8 (16) | 1.18x margin | 1.04x margin | **0.87x — FAILS** | No |
| 10 (20) | 1.48x | 1.29x | **1.08x — thin PASS** | Marginal |
| **12 (24)** | **1.78x** | **1.55x** | **1.30x — PASS** | Comfortable margin |

**This confirms the ~20–24-can estimate: N=10–12 per half (20–24 total) is
needed**, matching the rough figure almost exactly rather than just being in
the right ballpark.

Board-area check for D35×60mm cans (17.5mm radius):

| Packing assumption | N=20 (thin margin) | N=24 (comfortable margin) |
|---|---|---|
| Raw circles | 19,242 mm² (54.1%) | 23,091 mm² (**64.9%**, matches the ~65% estimate) |
| Square grid, 40mm pitch | 32,000 mm² (**90.0%**) | 38,400 mm² (**108.0% — exceeds the board**) |
| Hex packing, 40mm pitch | 27,713 mm² (77.9%) | 33,255 mm² (93.5%) |
| Literal grid-fit at 40mm pitch | 3×5 = **15 positions max**, zero margin | (same ceiling: 15) |

**Verdict: refuted, and more decisively than the raw-circle number suggests.**
The raw-circle estimate (65%) undersells it exactly the same way the
screw-terminal doc's original characterization did — once realistic mounting
pitch is applied, the *margin-adequate* case (24 cans) requires **more area
than the entire board contains**, and even the *thin-margin, no-safety-factor*
case (20 cans) requires 90% of it. A literal grid-fit check caps out at 15
positions on the whole bare board — fewer than even the thin-margin
requirement, with nothing left for the rest of the circuit. Small-cans-in-
parallel is not a way around the area problem on this board; it fails for
the same reason as the big-can route, and the failure is quantitatively
worse once packing realism is applied instead of raw circle area.

**Conclusion of §1+§2: neither route — fewer big electrolytics nor more
small ones — fits this board.** This is the signal the coordinator predicted:
the problem is upstream of part selection.

---

## 3. The film DC-link question

### 3.1 Is `c_dc_hf` even in the right current loop?

`c_dc_hf` (470nF, PP, 630V, `elec/src/modules.ato` `HalfBridge` module,
currently ~line 345-352) is wired `dc_bus.hv_plus ~ c_dc_hf.p1`,
`c_dc_hf.p2 ~ dc_bus.hv_minus` — straight across the full bus.

Tracing the actual 35kHz tank-current loop from `elec/src/main.ato` and
`HalfBridge`'s own internal wiring:

- **Upper half-cycle** (`Q_high` conducting): `C_BUS1(+)=hv_plus → Q_high →
  switch_node → tank.in → tank → tank.out → ct_sense.primary →
  power_return(=gnd_ref) → C_BUS1(−)=gnd_ref`. (`main.ato:351-352`:
  `tank.out ~ ct_sense.primary_in`, `ct_sense.primary_out ~ power_return`;
  `main.ato:263`: `power_return ~ power_in.dc_bus.gnd_ref`.)
- **Lower half-cycle** (`Q_low` conducting): the mirror loop, entirely within
  `gnd_ref ↔ hv_minus`.

**Neither loop ever involves both `hv_plus` and `hv_minus` together** — each
half's tank current returns to `gnd_ref` (the doubler midpoint), not to the
opposite rail. `c_dc_hf`, bypassing `hv_plus↔hv_minus`, sits across a node
pair that is not in the nominal ripple current's own path for either half.
It would help with true common-mode `hv+`/`hv-` transients (e.g.
shoot-through spikes across the totem pole), which is a legitimate and
different function, but **it cannot divert the steady 35kHz tank ripple
current away from the electrolytics no matter how large it is made**, as
currently placed. A correct placement would need two separate film banks:
one `hv_plus ↔ gnd_ref` (parallel with the upper electrolytic bank) and one
`gnd_ref ↔ hv_minus` (parallel with the lower bank) — this is a topology
detail, not drawn or implemented here, only identified.

### 3.2 Sizing, assuming the corrected placement

The relevant comparison is impedance at 35kHz. Electrolytic bank impedance
there is `sqrt(ESR² + Xc²)`, and for these values it is **ESR-dominated**,
confirming the coordinator's framing was the right one to check against
(verified by direct calculation, not assumed):

| Bank | C | Xc(35kHz) | ESR (from datasheet) | \|Z\| | Xc as % of ESR |
|---|---|---|---|---|---|
| Current, 2×1800µF/half | 3600µF | 1.26 mΩ | 55.5 mΩ (`tanδ/(2πfC)`, established ripple doc §1) | 55.51 mΩ | 2.3% |

Xc is negligible; the bank's impedance at 35kHz is essentially its ESR.
`c_dc_hf` as sized today: `Xc(470nF, 35kHz) = 9.675 Ω` — **~174× higher
impedance than the bank's 55.5mΩ ESR**, confirming the coordinator's
"diverts essentially none of the HF term" directly (current divides
inversely with impedance in this parallel path; at a 174:1 impedance ratio,
well under 1% of the ripple current would take the film path even if it
*were* wired into the loop).

For a film bank to carry the dominant share of the HF current (target: film
impedance ≤ 1/10 of the bank's ESR, a common rule-of-thumb margin for
"dominates"):

```
target Z_film ≤ 55.5mΩ / 10 = 5.55mΩ
C_film ≥ 1 / (2π × 35000 × 0.00555) ≈ 819 µF   per half-bus
```

**≈819µF per half-bus (≈1.6mF across both halves)** — roughly **1,740×**
the existing 470nF, in addition to needing to move to the correct node pair.

### 3.3 Does such a part exist, and what does it cost/take up?

Commercial "DC-link" film capacitor families (Panasonic EZP-E, Vishay
MKP1848DC, TDK B32774/B32778, Eaton EFDKA) cover roughly **47–600µF at
450–1100VDC** in single cylindrical/box packages. 819µF/half sits at or
above the top of that typical single-unit range — this would plausibly need
**2+ units in parallel per half-bus** (e.g., 2× ~450µF) rather than one
part, and I did not find and am not naming a specific single-part MPN at
819µF/250V+ — **UNVERIFIED**: a real BOM-grade selection pass (the kind done
for the electrolytic candidates in the withdrawn reselection doc) has not
been done here; this is an order-of-magnitude feasibility check only, not a
part recommendation. These are physically substantial parts in their own
right (commonly 60–120mm box/can packages) — **this is not a free
capacitance upgrade; it trades electrolytic ripple-current stress for a
different, non-trivial volume and cost**, though film capacitors don't carry
an explicit "rated ripple current" ceiling the way electrolytics do (ESR is
low and comparatively frequency/temperature-stable), so the physics is more
forgiving even if the size is not free.

### 3.4 Necessary, not sufficient

Even a correctly-placed, correctly-sized film bank only removes the **HF
(35kHz) term**. `docs/evidence/2026-07-26-bus-capacitor-ripple.md`'s own
falsifier check found the **LF (60Hz mains-recharge) term alone already
exceeds the current part's rating by 2.8–4.2×**, independent of the HF term.
**A film HF bypass, however well engineered, does not by itself fix the
ripple-current failure** — the LF term is the larger and more fundamental
problem, and that is what §4 addresses.

---

## 4. Why is the bus 3600µF per half at all?

**Searched:** `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`,
`docs/specs/REQUIREMENTS.md`, `docs/specs/PCB_SPECIFICATION.md`,
`elec/src/main.ato`'s `v_bus_ripple_max` assertion, and a repo-wide search
for the referenced SPICE simulation.

**Finding: no analytical derivation exists anywhere in this repository.**

- `docs/specs/REQUIREMENTS.md` REQ-PWR-01 states "DC Bus Ripple: <10% —
  3300µF capacitance" as if the capacitance value were self-justifying. No
  formula (`ΔV = I×t/C`, charge balance, or otherwise) connects the two
  anywhere in that document.
- `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md` is the actual origin of the
  3300µF value (later parallelled to 3600µF = 2×1800µF once the original
  3300µF/250V part turned out not to exist — see `BOM.md`'s own correction
  note). Its stated basis is **a SPICE simulation**, `sim_33_voltage_doubler.cir`,
  cited by name (`"Simulation Results (sim_33_voltage_doubler.cir)"`) and by
  exact path twice more at the bottom of the document: `Simulation:
  simulation/testbenches/sim_33_voltage_doubler.cir` and `Results:
  simulation/results/sim_33_voltage_doubler_results.txt`. **Neither file, nor
  either directory path, exists anywhere in the repository** — `find . -iname
  "*sim_33*"` and `find . -iname "*.cir"` return no match under that name (the
  `.cir` files that do exist are unrelated RTD/OVP/OCP/ZVS/gate-drive test
  harnesses under `elec/`, `simulation/harness/`, `components/`, and
  `packages/temper-placer/`); `simulation/testbenches/` and
  `simulation/results/` are not present as directories at all. The
  simulation's inputs, assumptions, and conduction-angle model are
  **unreproducible** from this repo — the 3300/3600µF value's sole cited
  justification cannot be checked, by name or by either of its two cited
  paths.
- The same document's capacitor spec table says **"Ripple Current ≥5A RMS
  at 120Hz."** Twelve lines later, in the thermal-loss section, it states
  **"Average current: ~5A per diode"** — the same number, derived from
  `P_out/V_bus` (1800W/340V ≈ 5.3A, split across two rectifier diodes). This
  is strong circumstantial evidence the "≥5A ripple current" spec is the
  **average DC diode current relabeled as an RMS ripple-current
  requirement**, not a real charge-balance/conduction-angle calculation —
  exactly the class of error `docs/evidence/2026-07-26-bus-capacitor-ripple.md`
  corrected (that doc's own conduction-angle model gives 4.2–5.8× higher
  ripple current than a naive average-current read would suggest). The same
  document's capacitor-loss estimate ("1-2W per capacitor" from ESR heating)
  is consistent with that flawed ~5A assumption and is **an order of
  magnitude low** against the real ripple current: at the ripple doc's
  central 13.02A combined and the part's ~0.111Ω ESR, `I²R ≈ 18.8W`, not
  1-2W. Had the original design used its own correct ripple current, its own
  thermal-loss logic would have already flagged the problem.
- Even by this flawed, self-inflicted 5A spec, the part actually specified
  and installed (`EKMQ251VSN182MA50S`, 2.70A) **undershoots it by nearly
  2×** — a second, independent breakdown on top of the spec itself being
  wrong.
- `main.ato`'s `v_bus_ripple_max: voltage = 20V` / `assert v_bus_ripple_max <
  v_bus_nominal * 0.1` is a bare declared-and-asserted pair with no formula
  computing ripple voltage from the actual capacitance anywhere in the
  `.ato` sources — it restates a target, it does not derive or check one.

**This is the finding the coordinator predicted: no derivation exists.** The
ripple-current requirement this project has been fighting since the original
ripple doc is, at least in significant part, **self-inflicted by an
unjustified capacitance choice**, not an unavoidable consequence of hitting
1800W from a 120VAC/15A circuit.

### 4.1 Is a smaller, "softer" bus actually viable for this topology class?

**Checked against outside literature, not just asserted.** This is a
half-bridge series-resonant induction cooker — exactly the topology studied
in Hsieh, "Study of half-bridge series-resonant induction cooker powered by
line rectified DC with less filtering," *IET Power Electronics* (2023),
which reports 0.95–0.995 power factor across 300W–3kW specifically *because*
of reduced DC-bus filtering, and states the general design principle
directly: **"a low value of filter capacitor is chosen to get a high power
factor, and as a consequence, a high-ripple DC bus is obtained."** This is a
recognized, published design point for this exact topology family, not a
novel or risky proposal.

Structurally, Temper's own design is already consistent with a bus that
doesn't need to be voltage-stiff: firmware regulates output via **PLL
frequency tracking** (`firmware/main/main.c`: "PLL for ZVS frequency
tracking"), not via bus-voltage regulation — the resonant tank's power
delivery is a function of switching frequency relative to resonance, which
is the standard mechanism this literature relies on to tolerate bus ripple.

**Mechanism connecting less capacitance to less ripple *current*:** the
established ripple doc modeled the LF term via a rectangular recharge pulse
of conduction angle θ, with `I_ripple,rms = I_dc × sqrt((1−δ)/δ)` — smaller
θ (narrower recharge pulse, driven by a stiffer/larger bus capacitor)
produces a higher crest factor and higher RMS ripple current for the same
delivered DC current. A smaller bulk capacitance widens θ (the sagging cap
voltage takes longer to be caught by the rising line voltage, so conduction
starts earlier and lasts longer each cycle), which **directly reduces RMS
ripple current per amp delivered** — the same lever that increases bus
voltage ripple. This is the mechanism, not a full quantitative answer: this
repo has **no validated model connecting a specific capacitance value to a
specific conduction angle** (the ripple doc treated θ as an assumed
"industry-typical" range, not something derived from C for this circuit's
actual source impedance), so I cannot state what a *specific* smaller
capacitance would do to the ripple-current numbers without a circuit model
(SPICE or bench) that does not currently exist in verifiable form in this
repo — the one that supposedly justified the current value is itself
missing.

**A real risk, not assumed away:** `docs/STRATEGY.md` ("ZVS margin — the
coil inductance is undefined," 2026-07-26) already found the design's ZVS
margin is tight — measured collapse between 32–33kHz against a 35kHz
operating point, itself based on an unverified 80µH coil assumption. A
softer, more-rippled bus voltage could interact with that already-thin
margin (bus voltage swings affecting resonant operating point or switch
timing headroom). This is a real coupling to check, not a reason to dismiss
the soft-bus direction, but it means "reduce C" is not a free move either.

---

## 5. The coupling (bulk capacitance is one knob, three consequences)

The same design variable — bulk capacitance per half-bus — simultaneously
governs three things this project has now measured going in **opposite
directions** for "more capacitance":

| Effect of increasing C | Direction |
|---|---|
| DC bus voltage ripple | **Better** (smaller %, the effect the original 3300/3600µF choice was aimed at) |
| Per-capacitor RMS ripple *current* stress | **Worse** (narrower conduction angle, higher crest factor — this is the failure mode currently open) |
| `BusDischarge` active fail-safe timing | **Worse** (τ=R×C scales linearly; the withdrawn KEMET reselection's 3.9× capacitance increase alone pushed discharge time from ~54s to ~213s against a documented <60s safety spec) |

**Reducing C moves all three in the opposite pattern**: worse voltage
ripple (which the resonant/frequency-regulated tank may tolerate, per §4.1),
but **better** ripple-current stress on the capacitors *and* **faster,
safer** bus discharge. These two already-identified problems — the ripple-
current failure and the discharge-timing regression — are not independent:
**a fix that changes bulk capacitance moves both at once, in the same
direction relative to each other.** Any future capacitance change (up or
down) needs to be evaluated against both requirements together, not
sequentially as this project's history shows happened here (the capacitance
value was set once for a voltage-ripple target with no ripple-current or
discharge-timing check at the time, and the two follow-on problems were only
found later, independently, by different analyses).

---

## 6. Recommendation

**Do not attempt another same-footprint or bigger-can electrolytic
reselection** — §1 and §2 both show area-infeasibility for this board, by a
wide and now double-checked margin, regardless of can count or size within
the electrolytic technology.

**Recommended next step (analysis path, not an implementation to execute
blindly):**

1. **Build or obtain a real circuit model (SPICE) of the actual doubler +
   source impedance + rectifier**, replacing the missing
   `sim_33_voltage_doubler.cir` this project has been informally relying on
   without being able to check it. Use it to find the smallest bulk
   capacitance that keeps DC bus ripple within whatever the resonant tank
   and ZVS margin (`docs/STRATEGY.md`'s ZVS finding) can actually tolerate —
   not the un-derived 3300/3600µF currently in source. This is the
   highest-leverage move: if a substantially smaller C is viable, it directly
   reduces the LF ripple-current term (the larger of the two failing terms)
   and simultaneously improves `BusDischarge` timing, addressing §5's coupling
   in one move instead of trading one problem for the other.
2. **In parallel, and only after §6.1's node-pair correction is designed
   in** (not before — see §3.1), size a correctly-placed film HF bypass
   (two half-bus banks, ~800µF+ each against whatever the final electrolytic
   ESR turns out to be) to remove the 35kHz term from the electrolytics'
   burden. This does not fix the LF term (§3.4) and should not be pursued as
   a standalone fix.
3. **Do not treat 1 and 2 as substitutes for each other.** The ripple doc's
   own falsifier already showed the LF term alone fails independently of the
   HF term — a film bypass without addressing bulk capacitance leaves the
   design failing; a smaller bulk capacitance without checking ZVS margin and
   inrush/holdup behavior risks a different, undiagnosed failure mode.

**Falsifier:** this recommendation (re-derive bulk capacitance from a real
model before any further capacitor reselection, with a correctly-placed
film HF bypass as a complementary, not substitute, measure) **fails if** a
properly parameterized circuit model shows that the maximum bulk-capacitance
reduction compatible with the tank's ZVS margin and any mains-holdup/inrush
requirement does not meaningfully widen the LF conduction angle — in which
case the ripple-current problem is not self-inflicted by an oversized
capacitor after all, and this project would be back to the two routes this
document already closed off (large-format electrolytics that don't fit, or
an active PFC / topology change ahead of the doubler, which was out of scope
for the original ripple doc and remains out of scope here).

---

## 7. UNVERIFIED

| Item | Reason |
|---|---|
| Whether a smaller bulk capacitance actually widens the conduction angle enough to bring LF ripple current into a fittable range | No validated C-to-θ model exists in this repo for this specific circuit; the missing `sim_33_voltage_doubler.cir` is the only prior attempt and cannot be checked |
| A specific real film-capacitor MPN at ~819µF/250V+ | Order-of-magnitude feasibility only (§3.3); no BOM-grade distributor search performed for this value |
| Interaction between a softer (more rippled) bus voltage and the already-marginal ZVS window (`docs/STRATEGY.md`) | Flagged as a real risk, not analyzed quantitatively here |
| Whether reducing bulk capacitance affects mains inrush/holdup behavior (NTC inrush limiter sizing, brief dropout ride-through) | Not analyzed in this document |
| Rubycon VXH's own 60Hz/10kHz frequency points (used the ripple doc's 120Hz-normalized figures directly against VXH's 120Hz rating instead, avoiding the need for this) | VXH datasheet's own frequency-multiplier table extraction was inconsistent/likely OCR-garbled in an earlier session and was not relied upon here |
| Whether `EKMQ251VSN182MA50S`'s ESR at 35kHz matches the 120Hz/20°C-derived 55.5mΩ figure used in §3.2 | No high-frequency ESR is published for this part (same gap the original ripple doc flagged in its own §9) |
