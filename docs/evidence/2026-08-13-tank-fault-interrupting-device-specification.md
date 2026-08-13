<!-- provenance: commit=1cf94ec58bd906fd38159ce1197673876b31abb9 dirty=false (own worktree `tank-fault-interrupter`, branch `analysis/tank-fault-interrupting-device`, branched from PR #1120's `analysis/tank-fault-interruption` at this same commit). `git status --porcelain` clean, `git grep -l "^<<<<<<< "` empty, checked immediately before this document was written. No file under `elec/src/**` or `pcb/temper.kicad_pcb` was opened for writing at any point in this session. `which ngspice` -> exit 1, re-confirmed fresh this session, consistent with every prior evidence document cited below; nothing here is a SPICE result. This is a specification document: it recommends what a human should buy, not a value in the source tree. -->

# Interrupting-device specification for the tank-coil/CT1/bus-cap fault loop — what closes, what does not, and why

**Scope.** This document turns `docs/evidence/2026-08-13-tank-fault-interruption.md` and
`docs/evidence/2026-08-13-tank-fault-sizing-inputs.md` (PR #1120, `analysis/tank-fault-interruption`)
into a buyable specification for the series interrupting device (fuse or breaker) those documents
recommend adding in series with each half-bus capacitor bank. It re-verifies every load-bearing
number it depends on rather than trusting the prior documents' prose, closes the two blockers named
for this task where the data permits, and states precisely what remains open where it does not.

**Bottom line, up front:**

- **Interrupting rating, voltage rating, physical form/location, and coordination with existing
  protection are fully specifiable and justified below** — every number carries a source or a
  derivation from a sourced number.
- **CT1's insulation-class ambiguity (Blocker A) is closed.** Not because CT1's true class was
  found, but because CT1 is proven — with a new, conservative, sourced calculation (§3) — to never
  approach either candidate class's ceiling regardless of which one applies. It does not gate the
  specification.
- **The I²t withstand / let-through ceiling (Blocker B) is closed for two of the four loop elements
  (CT1, PCB copper) and stays open for the other two (the tank coil, the bus capacitors) — which,
  by the loop's own resistance breakdown, absorb 97–99% of the fault energy between them.** Neither
  has a sourced mass, turn count, or manufacturer surge/pulse-current rating in this repository, and
  no defensible bound can be built from what is published (§4). This is the one number in this
  specification that is not provable today. §4.4 states exactly what would close it and who would
  supply it.
- **The practical consequence**: this document can specify *how big* and *how fast* the device must
  be to survive and interrupt the fault (a real part can be bought against that), but it cannot yet
  state the *maximum* let-through I²t the coil and capacitors can tolerate — so it recommends the
  fastest-clearing device class available in the required current/voltage range as the only
  currently-defensible position, rather than a specific let-through number.
- **Correction folded in below (§5)**: an earlier pass of this document reconstructed IEC 60335-1
  Table 8's numeric values from an OCR text layer that a prior evidence document had already judged
  unsafe to reassign — inference on data a predecessor deliberately declined to touch, not
  independent confirmation of it. This session pulled the archive.org page-image scan directly
  (leaf `0029`, printed page 25) and confirmed the reconstruction was numerically correct — but the
  methodology gap was real, and §5 records it rather than silently fixing it. **Table 8 was never
  load-bearing for either blocker's closure and remains so now**; this correction changes how a
  number was obtained, not what this specification concludes.
- **The interrupting-rating bracket (619–710 A, §2.1) itself carries a caveat that belongs next to
  the number, not buried**: it assumes the tank coil's inductance stays linear through the fault, but
  the coil's own spec only guarantees that up to 40 A — 15–18× below the fault bracket. The true peak
  current more likely exceeds 710 A than falls short of it.

---

## 1. The loop and the numbers this document inherits, re-verified

Carried forward from the two source documents, each independently re-checked this session before
being relied on:

| Quantity | Value | Re-verification performed this session |
|---|---|---|
| Fault loop | `+170V_BUS → short → tank coil (88µH) → CT1 primary → PWR_RTN → c_bus1‖c_bus1b (3600µF) → +170V_BUS` | Read `elec/src/main.ato:897`, `elec/src/modules.ato:422` directly: single shared `UCC21550` `DIS` pin, `OUTB ~ gate_ls.input` — confirms gate shutdown cannot open this loop. |
| CT1 primary DCR | 0.0001 Ω | Re-fetched the primary Coilcraft datasheet (Document 1608-1, not the product web page) directly, §2 below — matches. |
| Bus-cap ESR (3600µF, 283 Hz) | 41.1 mΩ/half-bus | Re-derived from the same Chemi-Con KMQ catalog (re-fetched, sha256 `1e6c0c241393f983aca540278536bd6ea5c9ab95d17ab19c6425f53538f7480a` — identical to the cited hash) — no surge/peak-current rating anywhere in that document (grepped fresh, §4.2). |
| Loop pour resistance | ≤1.8 mΩ | Not independently re-measured (would require re-parsing `pcb/temper.kicad_pcb`, out of scope since this document must not open that file); taken as previously sourced. |
| R_total, damped peak current, I²t(t) | 143.0 mΩ; 619 A at 694 µs; 147/255 A²·s at t_peak/1ms | **Independently re-derived from scratch** with a fresh numeric RLC integration (§1.1) — matches the prior document to the number. |
| Table 8 (winding temperature) numeric values | confirmed | **Read directly off the archive.org page-image scan this session** (leaf `0029`, printed page 25 — §5), after an initial OCR-text reconstruction from the same source the prior document found unreadable was cross-checked against it and matched exactly. **Not load-bearing in this document's conclusions either way** — see §5's closing paragraph. |
| Tank coil insulation class | ≥180 °C (Class H) | Re-read `docs/hardware/TANK_COIL_SPECIFICATION.md:47` directly: requirement #11, "Insulation and former rated ≥ 180 °C continuous." Class H is defined at 180 °C (IEC 60085) — this is a direct match, not an inference. |

### 1.1 Independent re-derivation of the fault-current/I²t model

Re-implemented the series-RLC source-free model from the sourced inputs (V₀=170V, L=88µH,
C=3600µF, R_total=143.0mΩ) as a fresh numerical integration (2×10⁷-point grid), not copied from the
prior document's output:

```
f0 = 282.77 Hz   Z0 = 0.1563 Ω   ζ = 0.4573   fd = 251.47 Hz
t_peak = 693.6 µs   i_peak = 618.91 A      (closed-form and numeric grid agree to the printed digits)
Energy dissipated, full ring-down = 52.020 J   vs ½CV₀² = 52.020 J   — energy-conservation check passes
I²t(100µs)=1.10, I²t(250µs)=13.95, I²t(500µs)=76.26, I²t(t_peak)=147.32, I²t(1000µs)=254.94  [A²·s]
```

Every figure matches `docs/evidence/2026-08-13-tank-fault-sizing-inputs.md` §6 to the digit. This is
an independent re-derivation, not a copy — it gives this document its own basis for §4's per-element
energy breakdown rather than inheriting an unverified number.

**Defensible peak-current bracket carried forward: 619–710 A**, DC, per the prior document's
sensitivity bracket on the derived (upper-bound) cap-ESR figure — see §1.2 for why the true figure
could plausibly exceed even this.

### 1.2 A new caveat this session found: the model assumes linear coil inductance, and the coil's own spec says that assumption is only guaranteed to 40 A

`docs/hardware/TANK_COIL_SPECIFICATION.md` requirement #7: **"Peak current, non-repetitive: ≥ 40 A
peak without saturation or measurable L shift."** The fault's own modeled peak (619–710 A) is
**15–18× this guarantee**. Ferrite-cored inductors lose effective inductance as they saturate; the
RLC model above holds L fixed at 88 µH throughout the entire event. A lower effective L raises the
characteristic impedance's denominator (Z₀=√(L/C) falls), which raises the peak current bound
(I_pk≈V/Z₀) and shortens the time to peak — both in the unsafe direction. **This repository does not
publish a B-H curve or a large-signal inductance-vs-current curve for this coil**, so the size of
this effect cannot be quantified here. It is stated as a directional, sourced caveat: **the true
peak fault current is more likely to exceed the modeled 619–710 A bracket than to fall short of it.**
This argues for specifying interrupting capability with real margin above 710 A, not for treating
710 A as a firm ceiling (§2.1).

---

## 2. The parts of the specification that close

### 2.1 Interrupting rating

**≥ 710 A, DC, with real margin held above that figure — not treated as a firm ceiling.** 619–710 A
is the sourced, re-derived bracket for a *linear-inductance* model of the coil. **That assumption is
itself only guaranteed by the coil's own specification up to 40 A** (`docs/hardware/
TANK_COIL_SPECIFICATION.md` requirement #7: "Peak current, non-repetitive: ≥ 40 A peak without
saturation or measurable L shift") — **15–18× below the 619–710 A fault bracket.** Ferrite cores lose
effective inductance as they saturate, which raises the peak current and shortens the time to reach
it (§1.2); no B-H curve exists in this repository to quantify by how much, so **the true peak fault
current should be assumed to plausibly exceed 710 A, by an amount this document cannot bound.** A
device whose manufacturer-stated DC interrupting rating is comfortably into the multi-hundred-to-
low-thousand-amp class at the required voltage (§7 shows this is a normal, stocked class of part, not
a special order) absorbs this uncertainty without needing to quantify it precisely — but the
selection should be made with this caveat in view, not against 710 A as if it were a hard number.

### 2.2 Voltage rating

**≥ 250 V, DC-rated as a DC interrupting rating specifically — not an AC voltage rating.** 250 V
matches the bus capacitors' own rating (`EKMQ251VSN182MA50S`, 250 V, giving 47% margin over the
170 V nominal half-bus per `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` §1.1).

**Why DC-rated matters here, specifically:** AC interrupting devices rely on the source current's
natural zero-crossing (every half-cycle, e.g. every 10 ms at 50 Hz) to help extinguish the arc that
forms as contacts open or a fuse element melts — the arc voltage does not have to exceed the source
voltage on its own, because the current is already heading to zero regardless. **A DC fault has no
such zero-crossing.** Once an arc forms, it persists until something (arc elongation, arc chutes,
a fuse's own current-limiting dynamic resistance forcing di/dt negative) forces the arc voltage
above the source voltage. This is exactly the loop here: the bus capacitors are a DC source with no
periodic zero. **A device's AC voltage rating does not transfer to DC service at the same number —
manufacturers publish a separate, materially lower DC rating for the same physical part**, which is
why this specification calls out "DC-rated" as a distinct, load-bearing requirement rather than a
formality.

### 2.3 Physical form and loop position

**A series fuse or fast solid-state DC breaker, one per half-bus, in series between the half-bus
capacitor bank (`c_bus1`+`c_bus1b` for the upper half, `c_bus2`+`c_bus2b` for the lower half) and
the corresponding DC-bus rail node** (`dc_bus.hv_plus` / `dc_bus.gnd_ref` for the upper half;
`dc_bus.hv_minus` for the lower half) — this is the position the source documents already identified
as the only one that puts a device *inside* the loop clause 19.11.2(a) requires "a non-self-resetting
interruption of the supply... within the appliance" to occur in. The upper-half position is the one
this document's own re-derivation (§1.1) characterizes directly (the `PWR_RTN`-closing loop); the
lower half is structurally symmetric (same doubler topology, same component values) but was not
independently re-derived here — installing on both halves is recommended for parity, not asserted as
independently sized.

**Not a standard AC glass/ceramic fuse** — wrong class of part for a DC service voltage/current
combination this large (§2.2, §7).

### 2.4 Continuous / normal-duty rating and nuisance-trip margin

The device sits on the **DC bus path**, not the tank branch — these are two different current
loops on this board, and the distinction matters for sizing:

- **DC bus path current (this device's own continuous duty): 22 A peak / 15 A RMS**, from
  `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §3.1 ("DC Bus Path (HighVoltage Class)... Current: 22A
  peak, 15A RMS").
- **The tank branch's own separate, pre-existing, unresolved rating conflict**
  (`elec/src/constraints.ato:8` declares `HighVoltageConstraints.i_max = 25A`; `elec/src/modules.ato`
  records a 28.7–31.9 A tank peak, marked UNRESOLVED) is a **different physical current path** (the
  tank coil branch, not the DC bus path this device sits on) and does not propagate into this
  device's sizing. Noted per the task's instruction, not resolved, not touched.

**Nuisance-trip margin is generous.** The fault bracket (619–710 A) is **≥28×** the 22 A normal
bus-path peak and **≥12×** OCP-01's own 50.1 A trip window (`elec/src/main.ato:624`,
`elec/src/components.ato:138`: worst-case 48.8–51.2 A). Any device correctly rated for 22 A
peak / 15 A RMS continuous duty, with the normal fuse-selection headroom against inrush/ripple that
its own datasheet's time-current curve specifies, sits nowhere near the fault current — this
specification does not need to trade off nuisance-trip risk against fault sensitivity, because the
two regimes are separated by more than an order of magnitude.

### 2.5 Coordination with existing protection

- **OCP-01** (tank CT — the same physical `T1`/CT1 this loop runs through — 50.1 A trip,
  `elec/src/main.ato:624`) **will also see this fault and latch**, since its own sensing CT sits
  directly in the loop; its trip threshold (48.8–51.2 A worst-case) is over an order of magnitude
  below the fault current, so it latches essentially instantly. **Its only actuator is the shared
  gate-driver `DIS` pin, which — as already established — does not open this loop.** The new device
  does not need to wait for, defer to, or be gated by OCP-01: OCP-01's ineffective (for this fault)
  latch and the new device's clearing are independent events, and there is no race condition to
  design around — OCP-01 does not do anything that could interfere with the new device's operation
  or vice versa.
- **OCP-02** (`elec/src/main.ato:794`, a bus shunt on `dc_bus.hv_minus`, 60 A design trip,
  `docs/hardware/BOM.md:368`) sits on the *lower*-half-bus node (`DC_BUS_RTN`/`hv_minus`), which
  `docs/evidence/2026-08-13-tank-fault-sizing-inputs.md` §3.1 already established is a **distinct net**
  from this loop's `PWR_RTN`. It shares the same structural limitation as OCP-01 (same fault-OR into
  the same shared `DIS` pin) and the same conclusion applies: it does not interfere with, and is not
  interfered with by, the new device.
- **F1** (`0034.3129`, 16 A/250 V time-lag mains fuse, `docs/hardware/BOM.md:44`) sits upstream on
  the AC-mains side of the doubler and, per the prior determination's own loop trace, **never carries
  current from this DC-side fault at all** — "no rectifier diode, no CMC winding, no inrush NTC, no
  bypass relay, and no F1 sits in this loop." Adding the new device changes nothing about F1's
  exposure; no re-coordination of F1's rating is required. (F1's own pre-existing, separately-tracked
  headroom concern — `docs/hardware/BOM.md:597`, "~7% headroom over the 15A continuous branch load" —
  is unrelated to this fault and is not touched here.)
- **Net effect**: the new device is a pure addition. It does not require re-tuning OCP-01, OCP-02, or
  F1, and none of them requires re-tuning to accommodate it, because the current regimes involved
  (normal duty, OCP trip windows, and the fault bracket) are separated by more than an order of
  magnitude at every boundary that matters.

---

## 3. Blocker A — closed: CT1's insulation-class ambiguity does not gate the specification

**The ambiguity, restated.** Coilcraft's own datasheet (Document 1608-1, re-fetched this session —
see §3.1) gives CT1's maximum part temperature as 165 °C but does not print an IEC 60085/60335
insulation-class letter. 165 °C falls between Class F (155 °C) and Class H (180 °C). The task's
instruction was to attack this conservatively — using Class F, the lower/stricter candidate — and to
determine whether that bound closes the requirement.

**It does, but not by arithmetic against Class F's number directly — by showing CT1 never gets
close to *either* candidate's ceiling.**

### 3.1 CT1's own datasheet, re-fetched from the primary PDF (not the bot-blocked product page)

The Coilcraft product web page 403s (Cloudflare), as it did in the prior session. This session
located and fetched the actual datasheet PDF instead (`https://www.coilcraft.com/getmedia/df31d5fe-
b3af-4586-82a7-7b773ac9f838/cst3015.pdf`, Document 1608-1/1608-2, "Revised 09/08/25", 2 pages,
275,571 bytes) and read it with `pdftotext`/`pdftoppm` (rendering page 2's dimensional drawing to an
image and reading it directly, since the dimension figures are embedded as vector-drawing labels
that `pdftotext` does not extract as text). Confirmed, verbatim from the document:

- **Weight: 16.6–16.9 g** (whole part: ferrite core, bobbin, both windings, leads).
- **Maximum part temperature: +165 °C (ambient + temp rise)** — matches the prior document's figure.
- **Package: 23.0mm × 30.0mm max footprint, 15.2mm max height.**
- **Land pattern: pins 1–2 (the primary, per the pin-1-dot/pinout diagram on the same sheet) are
  6.36mm apart, pad-to-pad** ("0.250 / 6.36" dimension on the recommended land pattern).
- **Primary DCR: 0.0001 Ω** (Specifications table, matches the prior document).

### 3.2 A conservative lower bound on CT1's primary copper mass, from these dimensions

CT1's primary is a single turn (N=1). Using the standard DC-resistance relation `DCR = ρL/A` with
copper resistivity ρ = 1.68×10⁻⁸ Ω·m (the value this repository already uses elsewhere,
`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §6) and the **land-pattern pin-1-to-pin-2 spacing as a
deliberately-small lower bound on the primary conductor's true length** (the real conductor must
also thread through the ferrite core's window, so its true length is longer than a straight
pin-to-pin span — using the shorter, sourced dimension keeps this bound conservative in the correct
direction: it *understates* mass, which *overstates* the resulting temperature rise):

```
L_min = 6.36 mm (sourced: land-pattern pin spacing, Coilcraft Doc 1608-2)
A = L_min × ρ / DCR = 0.00636 m × 1.68e-8 Ω·m / 0.0001 Ω = 1.0685 mm²
m_min = ρ_Cu(density) × L_min × A = 8960 kg/m³ × 0.00636 m × 1.0685e-6 m² ≈ 60.9 mg
```

(Copper density 8960 kg/m³ and specific heat 385 J/(kg·K) are standard tabulated material constants,
used the same way this repository already uses copper resistivity — not a datasheet or standards
figure being invented.)

### 3.3 Adiabatic temperature rise at this conservative mass bound

Using the per-element energy actually deposited in CT1 (§4.1's breakdown, itself re-derived
independently in §1.1/§1.2 of the accompanying calculation and matching the prior document's
0.015–0.026 J range exactly):

| Scenario | E in CT1 | ΔT = E/(m·cₚ) at m=60.9mg |
|---|---|---|
| 3600 µF (installed), through t_peak (694 µs) | 0.01473 J | **0.63 K** |
| 3600 µF (installed), through 1 ms | 0.02549 J | **1.09 K** |
| 3000 µF (recommended), through t_peak (639 µs) | 0.01172 J | **0.50 K** |
| 3000 µF (recommended), through 1 ms | 0.02215 J | **0.95 K** |

**Even at this deliberately pessimistic mass bound, CT1's primary winding rises at most ~1.1 K.**
Against a starting point anywhere in its −40 °C to +125 °C rated ambient range, this leaves CT1
nowhere near either Class F's 155 °C or Class H's 180 °C ceiling — and nowhere near its own
165 °C maximum-part-temperature figure either. **The F-vs-H ambiguity is moot: CT1 does not
approach a damaging temperature under this fault regardless of which class actually applies.**
Blocker A is closed.

(A secondary, non-thermal note: the fault's 619–710 A peak is 7–8× CT1's own 88 A sensed-current
rating — the ferrite core will very likely saturate during the fault, meaning CT1 stops accurately
reporting the fault current partway through. This does not create a fire/thermal hazard — the
primary is still a low-impedance, low-heat conductor regardless of core saturation — but it is worth
recording as a reason not to lean on CT1/OCP-01's *reading* of this event for anything beyond the
initial trip.)

---

## 4. Blocker B — closed for CT1 and PCB copper, open for the coil and the bus capacitors

### 4.1 Which elements actually bind — the per-element energy breakdown

Since all four resistive elements sit in one series loop, they all carry the *identical* current and
I²t; what differs is how much of that current's heating lands in each one, which is exactly
proportional to each element's share of R_total (independently re-derived this session, §1.1):

| Element | R (installed, 3600µF) | Share of R_total | Energy absorbed, through t_peak (694µs) | Energy absorbed, through 1ms |
|---|---|---|---|---|
| Tank coil | 100.0 mΩ | 69.93% | **14.73 J** | **25.49 J** |
| Bus-cap ESR | 41.1 mΩ | 28.74% | **6.05 J** | **10.48 J** |
| PCB pour | 1.8 mΩ | 1.26% | 0.27 J | 0.46 J |
| CT1 primary | 0.1 mΩ | 0.07% | 0.015 J | 0.025 J |

**The coil and the bus capacitors together absorb 97–99% of the fault's dissipated energy at every
horizon.** CT1 (§3) and the PCB pour (§4.2) are cleanly ruled out as the binding elements. The
question this document cannot answer is whether the coil or the caps reach a damaging condition
before a realistic interrupting device clears — because neither has a sourced I²t withstand figure.

### 4.2 PCB copper — closed, not binding within the relevant timescale

`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` gives only a continuous-current-carrying formula
(IPC-2221B), not a transient fusing-current figure — but a **standard, physics-based adiabatic
fusing-time formula (Onderdonk's equation)** can be applied to the repository's own sourced minimum
design width, using only material constants (copper's melting point, 1083 °C — a standard physical
constant, not an invented figure) and the document's own stated worst-case ambient (60 °C, "worst-
case kitchen environment," §1 Design Parameters table):

```
Minimum designed DC-bus trace/pour width: 5.0mm / 200mil, 2oz (70µm) copper (TRACE_WIDTH_CALCULATIONS.md §3.1)
A = 697.7 circular mils

Onderdonk: I = A × sqrt( log10((Tm − Ta)/(234 + Ta) + 1) / (33t) )
Solved for t at I = 619 A:  t ≈ 25.1 ms
Solved for t at I = 710 A:  t ≈ 19.1 ms
```

**A minimum-width trace at this fault current would take 19–25 ms to fuse** — an order of magnitude
longer than the fault's own dominant energy-transfer window (peak at 694 µs; most of the available
I²t accumulates within the first 1–2 ms). The board's *actual* copper here is not this narrow
minimum-width trace at all — it is a wide copper-pour zone independently measured elsewhere in this
repository at ~17,546 mm² (`docs/evidence/2026-07-28-pour-strategy-audit.md:115`, cited in the prior
sizing document), i.e. far more copper than the conservative minimum assumed here. **PCB copper is
not the binding element, with margin, using the repo's own worst-case design parameters.**

### 4.3 The coil and the bus capacitors — genuinely open, and why the two available attack paths both fail

**Attack path 1 (identify the binding element and spec against it) does not fully close.** It
narrows the field from four candidates to two (§4.1), but does not distinguish which of the coil or
the caps binds first, or whether either survives at all — because withstand data exists for neither.

**Attack path 2 (bound copper/thermal mass from physical data) succeeds for CT1 (§3.2, because a
sourced land-pattern dimension gives a real minimum conductor length) and fails for both remaining
candidates, for two different reasons:**

- **The tank coil.** `docs/hardware/TANK_COIL_SPECIFICATION.md` — read in full this session — gives
  an outer-diameter *ceiling* (≤200mm, a mechanical maximum from `docs/COIL_BRACKET_DESIGN.md`, not a
  measured or minimum size), a DC resistance figure (≤0.12Ω, target 0.10Ω), and a strand-size
  constraint (≤0.2mm/≥AWG32) — but **no turn count, no coil height/thickness, no inner diameter, and
  no strand count.** Unlike CT1 (§3.2), where a single sourced pin-spacing dimension pinned down a
  usable lower bound on conductor length, the coil has no analogous minimum-geometry dimension
  anywhere in this repository: DCR alone fixes only the *ratio* `L_conductor/A_conductor`, not either
  quantity independently, and mass grows with the *square* of whichever one is assumed — there is no
  second independent geometric constraint to solve with. §6–§8 of the same document confirm this is a
  known, named gap, not an oversight: the coil has no MPN, no vendor, and no bench sample yet: **"No
  orderable coil in this class publishes an inductance... the deliverable is the spec and the test,
  not a purchase order line."** A conservative mass bound genuinely cannot be built from what is
  published.
- **The bus capacitors.** Physical case dimensions *are* published (D35×L50mm snap-in, confirmed
  directly against the Chemi-Con catalog's own part-specific row this session, §4.2's fetch). But
  **grepping the full, re-fetched catalog text for `surge`, `peak curr`, `non-repet`, `fault`,
  `short-circuit`, and `shock` returns nothing** — no manufacturer pulse/surge-current withstand
  figure exists for this part in the document this repository already cites as its source. Unlike a
  solid copper conductor, a can-and-thermal-mass bound would not actually answer the relevant
  question here: aluminum electrolytic capacitor damage under an abusive current pulse is driven by
  **localized I²·ESR heating inside the electrolyte/foil roll and the resulting internal vapor
  pressure**, not by the bulk average temperature of the can — a lumped adiabatic ΔT=E/(m·cₚ) model
  against the can's total mass would not represent the actual failure mechanism even if a mass figure
  were available. This is a physics mismatch, not just a missing number, and it means bounding the
  can's mass would not have closed this gap even if the data existed.

**Neither route closes.** This matches the task's own framing that this could be the honest
outcome, and it is: 97–99% of the fault's energy lands in two components this repository cannot
currently bound.

### 4.4 What would close this, and who would supply it

- **Tank coil**: a turn count (or total conductor length), or a directly measured/reported copper
  mass. Since `TANK_COIL_SPECIFICATION.md` §1 already specifies what a certificate of conformance
  must report (L_unloaded, L_loaded, ratio, R_dc, R_ac) but not mass or turn count, the cleanest path
  is to **add copper mass or turn count + strand count to that CoC requirement** before or when a
  real coil is sourced — the coil winder/vendor supplies it, once one exists (this document does not
  select or invent one; per §6 of that document, none is sourced yet). Absent that, a bench
  measurement (weigh a sample coil, or count turns on a production sample) would also close it.
- **Bus capacitors**: a manufacturer-supplied pulse/surge-current withstand curve or non-repetitive
  peak-current rating for this specific fault profile (peak current, pulse duration, expected
  repetition rate — a single-fault-then-replace event, not a repetitive duty cycle). This is not in
  United Chemi-Con's public KMQ catalog; it would have to come from **United Chemi-Con's applications
  engineering**, on request, referencing the derived fault profile in §1.1 above.

---

## 5. Table 8 (IEC 60335-1, "Maximum Winding Temperature") — confirmed this session by direct page-image read; not load-bearing

**Correction to this document's own first-draft methodology, recorded here rather than silently
fixed.** An earlier pass of this document reconstructed Table 8's numeric values from the OCR text
layer alone (`is.302.1.2008_djvu.txt`), using clause 19.9's inline prose limits to fix the
column ordering of a run of 40 undifferentiated digits, and a same-source internal-consistency check
(two independent decompositions of the digit run landing on the same two rows twice) as corroboration.
That reconstruction was performed on **exactly the data `docs/evidence/2026-08-13-tank-fault-
sizing-inputs.md` §4.4 had already looked at and explicitly declined to reassign**, on the stated
grounds that doing so risked "the kind of fabricated-looking-real number the task prohibits." An
OCR-text reconstruction, however internally cross-checked, is inference from the same ambiguous
source that prior pass judged unsafe — not independent confirmation of it. That was a real
methodological gap in this document, flagged externally before being caught here.

**Resolved this session by pulling the actual page-image scan, not the OCR text layer, from the same
archive.org item** (`gov.in.is.302.1.2008`, sha256 of the underlying djvu text `2695a4bc1b2c87dd24a6
126d984d01ad30be53c8d905ff196b73241b73f99251` — unchanged, same source). Used the item's own
full-text search-inside index (`fulltext/inside.php`) to locate the exact leaf containing "Table 8
Maximum Winding Temperature," then fetched that leaf directly out of `is.302.1.2008_jp2.zip` via
`BookReaderImages.php` (no OCR involved — a rendered page image, read visually) — **leaf `0029`,
printed page 25 of IS 302-1:2008.**

**The image is fully legible and matches the OCR-text reconstruction exactly, digit for digit, across
all 5 rows × 8 classes:**

| Row (clause 19.11 context) | A | E | B | F | H | 200 | 220 | 250 |
|---|---|---|---|---|---|---|---|---|
| i) Not operated to steady state | 200 | 215 | 225 | 240 | 260 | 280 | 300 | 330 |
| ii-a) Impedance protected, steady state | 150 | 165 | 175 | 190 | 210 | 230 | 250 | 280 |
| ii-b-1) Protective-device protected, during first hour, max | 200 | 215 | 225 | 240 | 260 | 280 | 300 | 330 |
| ii-b-2) Protective-device protected, after first hour, max | 175 | 190 | 200 | 215 | 235 | 255 | 275 | 305 |
| ii-b-3) Protective-device protected, after first hour, average | 150 | 165 | 175 | 190 | 210 | 230 | 250 | 280 |

**One correction the image surfaces that the OCR-based citation got wrong**: the table's own printed
caption reads **"(Clauses 17, 19.7 and 19.11)"**, not "(Clauses 11, 19.1, and 19.11)" as the
OCR-derived citation in the prior sizing document stated — a small numeral-garbling in the OCR text
layer, caught only by reading the image directly. The table's *content* was right; one clause
citation attached to it was not. This is itself evidence for the coordinator's underlying point: OCR
reconstruction, even when it lands on the right numbers, is not a substitute for the image where the
image is obtainable, and it can be right about the load-bearing content while still wrong about
adjacent details.

**What this means for the fault here:** clause 19.11 ties Table 8 directly to the electronic-circuit
fault-condition test this document is about. The relevant row for a fault that clears in well under an
hour (the event, even fully unimpeded, rings down within tens of milliseconds) is **row (i)/(ii-b-1):
240 °C for Class F, 260 °C for Class H** — confirmed, not reconstructed, values.

**This is not load-bearing in this document's conclusions, and that remains true regardless of the
methodology correction above.** Blocker A (§3) closes on CT1's own conservative copper-mass bound
without reference to Table 8 at all — the comparison there is against the base insulation-class
temperatures (155 °C / 180 °C), not Table 8's fault-condition allowances, and the margin (≤1.1 K rise)
is large enough that it would survive either comparison. Blocker B (§4) states plainly that converting
any winding-temperature ceiling — Table 8's or otherwise — into an I²t withstand still requires the
coil's copper mass, which is the missing input, not the temperature figure. **Table 8's confirmation
closes a real, separate gap (this primary-source table is now genuinely read, not guessed at) but it
does not, and was never going to, close Blocker B.** The two open data requests in §4.4 — coil copper
mass/turn count, and a Chemi-Con pulse-current withstand curve — stand exactly as before.

---

## 6. Interaction with the bus-capacitance recommendation (3600µF vs 3000µF/half)

`docs/hardware/BUS_CAPACITANCE_DERIVATION.md` recommends ~3000µF/half for an unrelated reason
(`BusDischarge` hold-up-time tolerance margin, not this fault) and flags it as provisional/unsourced
for a specific replacement part. Independently re-derived this session (§1.1's method, same code,
re-run at C=3000µF, R_total=149.8mΩ per the prior document's own higher-ESR-for-smaller-cans figure):

| | Installed (3600µF/half) | Recommended (3000µF/half, UNVERIFIED part) |
|---|---|---|
| Stored energy | 52.02 J | 43.35 J (−17%) |
| Peak fault current | 618.9 A | 576.3 A (−7%) |
| Time to peak | 693.6 µs | 638.9 µs |
| I²t through t_peak | 147.3 A²·s | 117.2 A²·s |
| I²t through 1 ms | 254.9 A²·s | 221.5 A²·s |
| Coil energy through 1ms (69.9%/66.8% share) | 25.49 J | 22.15 J |
| Cap-ESR energy through 1ms (28.7%/32.0% share, higher ESR) | 10.48 J | 10.61 J |

**Both re-derived and internally cross-checked** (energy-conservation self-check: 43.350 J dissipated
vs ½×3000µF×170² = 43.350 J, exact). **The specification in §2 does not change at either
capacitance value** — the interrupting-rating bracket (§2.1), voltage rating (§2.2), physical
position (§2.3), and coordination requirements (§2.5) are all set by the higher (installed, 3600µF)
figures, which remain the correct sizing basis regardless of whether the 3000µF change is ever
implemented; if it is, the device specified here is not oversized, only carries slightly more margin.
The one number that *would* shift is the (still-open) coil/cap I²t withstand comparison in §4 — at
3000µF the coil absorbs ~13% less energy by 1ms, a real but not qualitative difference; it does not
change the finding that no withstand figure exists to compare against either way.

---

## 7. Existence proof — unverified, not selected

Per the task's explicit instruction, **no part is selected or recommended here.** The following are
named only to demonstrate that a real, stocked class of device exists that could plausibly satisfy
§2's requirements — **none has been checked against this specification's exact voltage, current, or
(open) let-through requirement, and none is endorsed:**

- Littelfuse POWR-GARD semiconductor fuse families — published ranges spanning 1–4500 A at 250 VDC
  and 1–2000 A at 600 VDC (per manufacturer marketing copy retrieved via web search this session, not
  independently verified against a primary datasheet).
- Mersen A50QS series bolt-on semiconductor fuses (250 A class, 500 VAC — DC rating not checked here).
- Bussmann semiconductor fuse families, general class.

A human selecting a real part must independently verify: (a) the manufacturer's stated **DC**
interrupting rating (not AC) at the actual bus voltage, (b) a total-clearing-time / let-through curve
checked against §1.1's I²t-vs-time table once §4.4's missing coil/cap data closes the withstand side,
and (c) mechanical/footprint fit, which is entirely outside this document's scope (`pcb/**` was not
opened for writing at any point in this session).

---

## 8. What this document does not do

- It does not modify `elec/src/**` or `pcb/temper.kicad_pcb`. Verified clean (`git status
  --porcelain`) before and after this session.
- It does not select or name a part to buy. §7's names are existence proof only, explicitly labeled
  unverified.
- It does not run `ngspice` — confirmed absent machine-wide, fresh, this session.
- It does not resolve the pre-existing tank `i_max=25A` vs 28.7–31.9A peak conflict
  (`elec/src/constraints.ato:8`) — noted in §2.4 as a different current path from the one this device
  sits on, not touched.
- It does not close the coil/bus-capacitor I²t withstand gap (§4.3–4.4). This is the one number in
  this specification that remains genuinely unprovable with data currently in this repository, and it
  is the reason this document recommends "fastest available clearing class" rather than a specific
  let-through target.
- It does not survey the lower half-bus (`c_bus2`/`c_bus2b`, `DC_BUS_RTN`) loop independently — §2.3
  recommends symmetric installation there but the fault-current/I²t figures in this document were
  derived only for the upper-half (`PWR_RTN`) loop the prior documents characterized.
