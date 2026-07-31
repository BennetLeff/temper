<!-- provenance: commit=8d1884031462fb2f5d41811c4165469067057f13 dirty=false -->

# PD3 (12.6mm) isolation *mechanisms* for U7 and U3 — not part substitution, a different barrier technology

Base commit `8d188403` (`origin/main`). Branch `explore/pd3-isolation-mechanisms`,
worktree created fresh from `origin/main` per this task's hard rule. **Analysis
only** — no design file, footprint, netclass, or constant touched anywhere in
this worktree; `git status --short` clean apart from this document.

This document picks up where `docs/evidence/2026-07-29-pd3-part-selection-survey.md`
and its verification pass (`docs/evidence/2026-07-29-pd3-part-selection-verification.md`)
left off — both currently live only on unmerged sibling worktrees/branches, not
on `origin/main` at this base commit; read directly from those worktrees this
session, not reconstructed from memory. Their finding, reproduced and not
contradicted here: **U7 (UCC21550BDWK, isolated gate driver, 8.100mm today)
and U3 (H11L1TVM, ZCD optocoupler, 8.560mm today) cannot reach 12.6mm by
substituting a same-class part.** Every reinforced gate-driver IC and every
optocoupler family surveyed, across TI, Vishay, Broadcom, and one disqualified
Chinese entrant (Chipanalog CA-IS3211, certifications "Pending"), plateaus in
the 7–8.5mm band, independent of function or isolation-voltage rating — the
limit is IC lead-frame/package geometry, not die performance.

**This document's question is different: not "is there a wider chip," but
"is there a different barrier technology that isn't built on an IC lead
frame at all."** Two such technologies exist and were evaluated with real,
manufacturer-primary sources fetched this session: **magnetic (transformer)
isolation** and **a certified logic-only isolator IC in a package family
the prior survey did not check (extra-wide automotive-grade digital
isolators)**. One of them clears 12.6mm today, with real orderable parts.

## 0. Verdict up front

| Ref | Mechanism | Achievable spacing (manufacturer-verified) | Real & orderable today? | Verdict |
|---|---|---:|---|---|
| U7 | **Discrete: certified digital isolator (logic only) + local secondary-side driver IC, one stage per switch** | **>14.5mm** (TI ISO7741-Q1/ISO7740-Q1, DWW-16 package) | **Yes** — `ISO7741FQDWWRQ1`, DigiKey Active, 6,968 units, $5.09 | **PASS — this is the recommendation** |
| U7 | Gate-drive transformer (off-the-shelf catalog part) | 9–12.5mm across every real, orderable, reinforced-insulation GDT family checked (Pulse/YAGEO, TDK InsuGate, ICE Components) | Yes, but none clears 12.6mm | **FAIL — real parts exist, all fall 0.1–3.6mm short** |
| U7 | Gate-drive transformer (custom-wound to spec) | Not package-limited in principle (winding separation is a layout choice, not a lead-frame constraint) | No — not a purchased part; same "specification + incoming acceptance test" status as this repo's own tank coil | **UNRESOLVED — plausible, not demonstrated with a real part** |
| U7 | Two cascaded isolation stages (two ICs in series) | Bounded by the same IC package ceiling per stage (7–8.5mm each) | N/A | **Not evaluated further — does not change the governing constraint (see §4)** |
| U3 | Widen: single channel of the same TI DWW-package isolator family, plus an added primary-side comparator stage | **>14.5mm** | **Yes**, same part family as U7's fix | **Real mechanism exists — but see verdict below: recommend DELETE, not widen** |

**U7: a real mechanism exists and clears 12.6mm with margin (1.9mm), using
real, orderable, agency-certified parts available today.** PD3 is *not*
unreachable for U7 — the prior survey's "no mechanism reaches this" question
was answered "no part reaches this," which is correct but narrower than "no
mechanism reaches this." A mechanism does.

**U3: recommend deletion**, not widening — despite a real ≥12.6mm mechanism
existing for it too (§6). The signal has no firmware consumer, no safety
role, and no architectural necessity in this DC-bus resonant topology (§6.1).
The widening mechanism is reported because the task asked for it to be
checked, and because it means a future re-introduction is not a dead end.

---

## 1. What "mechanism, not part" means here, established before evaluating candidates

The prior survey's own finding, reproduced by this session's independent
checks (§3, §5), is that **IC package creepage plateaus in a narrow band
(7–8.5mm) across every function** — gate driver, digital isolator,
optocoupler — because the limit is the molded package's lead-frame pitch,
not the die's isolation performance. TI's UCC21732 (>8mm), UCC5350 (8.5mm),
Vishay's widest optocoupler option (">8mm"), and ISO7741's own *standard*
DW-16 package (>8mm, verified §3.2) all land in the same band. **A barrier
technology only escapes this ceiling if its board-level pin spacing is not
set by an IC molding process.** Two candidates fit that description:

1. **A transformer**, where primary and secondary winding *termination
   points* (pins on a bobbin, or a PCB planar winding's own copper) are a
   layout/winding choice, not a lead-frame constraint.
2. **A digital isolator in a package family specifically built wider than
   the standard SOIC/DIP body** — TI's automotive DWW ("extra-wide SOIC")
   package is exactly this: the same die/technology as the standard-width
   part, deliberately re-packaged for automotive high-voltage isolation
   requirements that the industrial-grade package family was never
   pressured to meet. This is a real, distinct package option the prior
   survey did not check (it checked TI's *gate-driver* catalog and general
   digital-isolator search results, not the automotive-qualified DWW
   package specifically).

---

## 2. U7 — Gate-drive transformer, evaluated honestly

### 2.1 Real, orderable, reinforced-insulation GDT families checked this session

All figures below are **MEASURED from manufacturer datasheets fetched this
session** (PDFs saved under this worktree's scratchpad `pdfs/`), using the
same "external clearance/creepage" definition (shortest terminal-to-terminal
distance through air / across package surface) the prior survey's IC
figures and this repo's own SOIC16W_Isolated footprint use — directly
comparable.

| Family | Part(s) | Creepage | Insulation class / standard | Working voltage | Orderable? |
|---|---|---:|---|---|---|
| Pulse/YAGEO P774, `PH9400.XXXANL` | e.g. `PH9400.111ANLT` | **12.0mm** ("the 12mm package creepage & clearance distance satisfies IEC 61558 requirements") | Reinforced; IEC 60950-1, IEC 61558-1/-2-16, IEC 61010, IEC 60601 | up to 600Vrms | **Yes** — DigiKey, `PH9400.111ANLT`, $4.36, real listing |
| ICE Components GT06-U series | e.g. `GT06-111-049-U` | **12.5mm** (creepage AND clearance both stated as 12.5mm) | Reinforced; IEC 61558-1, IEC 62368-1 | up to 867Vrms | **Yes** — DigiKey/Mouser, AEC-Q200 qualified, 17 variants listed |
| ICE Components GT07-U / GT04-U series | — | 9.2mm | Reinforced; IEC 61558-1, IEC 62368-1 | — | Yes, but far short |
| TDK EPCOS InsuGate `B78541A` | e.g. `B78541A2467A003` | **9.0mm** | — | — | Yes — DigiKey sample-kit listing found |
| YAGEO/Pulse `PGT7604NL` (announced July 2025) | — | **≥16mm creepage, ≥9.6mm clearance** — clears 12.6mm comfortably | "Compliance with IEC 61558-1 and IEC 60664-1" (self-declared in a white paper; **no agency certificate number found**) | up to 1250Vpk (EV/ESS-class) | **No** — no dedicated datasheet found (only a July-2025 white-paper announcement), no DigiKey/Mouser listing, no distributor stock found this session |

**Every real, orderable, currently-shipping catalog GDT found this session
tops out at 12.5mm** (ICE GT06-U) — **0.1mm short of 12.6mm**, an amount
smaller than typical PCB fab pad-position/soldermask-registration tolerance,
but per this task's own hard rule ("no published creepage figure... 12.6mm
never proposed downward") a 0.1mm shortfall is a fail, not a rounding
error to wave through. The one part that clears the bar with real margin
(`PGT7604NL`, ≥16mm) is real (manufacturer-published, dated document, on
YAGEO's own domain) but **not established as a currently orderable part** —
reported as market evidence that ≥12.6mm-creepage GDTs are being brought to
market, not adopted as a solution, on the same "real figure, unconfirmed
orderability/certification" basis this project already applies to the
Chipanalog CA-IS3211 case.

**Why off-the-shelf GDTs cluster at 9–12.5mm and not further:** every family
checked targets IEC 62368-1/61558-1 "reinforced up to ~600–870Vrms working
voltage, pollution degree 2" — the same commercial pressure that caps IC
isolators at 7–8.5mm (minimize footprint against the *minimum* the standard
they're built to requires) applies here too. The GDT plateau is higher than
the IC plateau because a wound bobbin has more room than a molded lead
frame, but it is still optimized toward a target, not built with headroom to
spare.

### 2.2 Custom-wound GDT: a real path in principle, not demonstrated with a real part

**This repo already has a working precedent for exactly this move.**
`elec/src/modules.ato`'s `ResonantTank.inductor_conn` (the resonant tank
coil) is declared with `mpn = "CUSTOM_LITZ_COIL"` and its own docstring
states plainly: *"no orderable coil in this class publishes an inductance
... What replaces the placeholder is a SPECIFICATION plus an incoming
acceptance test."* A custom-wound GDT built to an explicit ≥12.6mm
creepage/clearance requirement under IEC 61558-2-16 (which gives a direct
creepage/clearance-vs-working-voltage/pollution-degree/material-group
table a magnetics house designs to) is the same move, for the same
underlying reason: **transformer winding separation is a mechanical design
choice, not a die-package limit**, so there is no structural reason 12.6mm
is unreachable the way it is for an IC. This is reported as **plausible,
not demonstrated** — no specific magnetics house was contacted, no specific
part number exists, and per this task's own hard rule this is explicitly
**not** an MPN to be fabricated or pattern-guessed. It would carry the same
honesty burden the tank coil already carries in this repo: a specification
document, not a BOM line, until a supplier confirms it.

### 2.3 GDT functional risk, assessed against this design's actual switching scheme

The task asks this to be assessed honestly against the design's real
control scheme, not a generic hard-switched-PWM assumption. Checked this
session, directly from firmware:

- **This is frequency-modulated, not duty-modulated, control.** `firmware/components/hal/include/hal_pwm.h` exposes `set_frequency` for "PLL tracking for ZVS" as the live control axis; `set_duty` exists but the only call sites found repo-wide (`firmware/main/state_handlers.c:120,539`, `state_machine.c:67`) are `pwm_set_duty_cycle(0)` — a hard shutdown, not a modulation path. Normal operation runs at a duty cycle held near 50% complementary, power control done entirely by frequency, per the resonant ZVS half-bridge topology `elec/src/modules.ato`'s `HalfBridge`/`ResonantTank` implement.
- **This is exactly the case a GDT handles best, and the task's own framing anticipates this correctly.** A GDT's core limitation — accumulated volt-seconds and the need for a reset window — is a hard-switched-PWM problem (wide, asymmetric duty ratios from near-0% to near-100%). A near-fixed-50%-duty resonant converter is the textbook GDT-friendly case (this is why GDTs are common in LLC/resonant converters industry-wide): each half-cycle is self-resetting by symmetry, so no dedicated reset winding/clamp is needed beyond ordinary core-loss margin.
- **DC transmission loss is real and would require a scheme change.** A literal (AC-coupled) GDT cannot hold a DC gate-on level indefinitely the way UCC21550 (or a digital isolator) does — it needs edge-triggered secondary-side latching (e.g., a set/reset flip-flop or self-oscillating half-bridge driver IC fed by transformer pulses) to reconstruct a static gate command between transformer pulses. This is a genuine, non-trivial redesign of the drive electronics on both sides of the barrier, not a footprint swap — it is the concrete cost that the discrete-isolator approach (§4) avoids entirely, because a digital isolator is DC-coupled by internal design (refresh/watchdog circuitry sustains a static logic level through its own capacitive/magnetic microtransformer barrier — this is the isolator's job, already solved, not something this design has to re-solve).
- **Power delivery is a second, separate problem a GDT does not solve for free.** A signal-only GDT still needs its own isolated bias supply for the secondary-side driver stage — the same problem this design already solves today via `power_15v_ls` (floating on `hv_minus`) and the bootstrap diode/cap network (`D5`/`C17`) documented in `HalfBridge`'s "High Side Power (Bootstrap)" section. A GDT-based redesign would have to either reuse that existing bootstrap architecture (workable, since it is independent of *how* the logic command reaches the secondary side) or build a second isolated supply — an added, not avoided, cost relative to keeping the existing bootstrap network and only replacing the *signal* barrier (§4).

**Conclusion on GDT for U7: real, honestly evaluated, and rejected as the
primary recommendation** — not because the physics fails, but because (a)
no real, orderable, ≥12.6mm catalog part was found (closest is 12.5mm,
0.1mm short), (b) the one part that clears the bar is unconfirmed-orderable,
(c) a custom-wound part is plausible but undemonstrated, and (d) even if a
part existed, it would force a real redesign of the drive electronics (DC
transmission loss) that the discrete-isolator approach (§4) does not
require.

---

## 3. U7 — "Discrete isolated driver": checked and independently ruled out for one specific reading, ruled in for another

The task names this candidate as: *"a certified isolator plus a local
secondary-side driver, where the isolator's own package can be chosen for
spacing because it only carries logic."* Two different real parts answer
two different readings of that sentence, and they give opposite verdicts —
both are reported, because conflating them would be exactly the kind of
error this repo's own evidence standard exists to catch.

### 3.1 Reading 1 — "any digital isolator, since it doesn't need to be a gate driver": REFUTED

Checked this session, TI ISO772x/ISO674x-class **standard-width** digital
isolators (not automotive DWW), i.e., exactly the "just use a plain
isolator IC instead of a gate-driver IC" reading:

- `ISO7741` (industrial, non-automotive): DW-16 package only, **>8mm**
  CLR/CPG (SLLSEU0G datasheet, §5.6 Insulation Specifications, fetched and
  read directly this session) — reproduces the prior survey's own finding
  that plain digital isolators sit in the identical 7–8.5mm band as gate
  drivers and optocouplers. `ISO7721` (dual-channel, reinforced): DW-16
  package only, same band.
- **This confirms the governing constraint is package geometry, not
  function** — a "logic-only" isolator built in the industry-standard
  SOIC/DIP body is exactly as creepage-limited as a gate-driver IC in the
  same body. Choosing a plain digital isolator over a gate-driver IC, by
  itself, buys nothing.

### 3.2 Reading 2 — "a digital isolator in a package family the gate-driver survey didn't check": CONFIRMED, real, orderable, clears 12.6mm

TI publishes a **third, extra-wide package** for one specific family — the
automotive-qualified `ISO774x-Q1` line — that the prior survey never
checked (it searched TI's gate-driver catalog and general digital-isolator
web results, not the automotive isolator line specifically):

**`ISO7741-Q1` / `ISO7740-Q1`, DWW-16 package** (`SLLSEU0G`, TI, fetched
and read directly this session, `www.ti.com/lit/ds/symlink/iso7741-q1.pdf`):

| Package | Body size | External CLR/CPG | Insulation |
|---|---|---:|---|
| DWW-16 (extra-wide SOIC) | 10.30mm × 14.0mm | **>14.5mm** | Reinforced |
| DW-16 (standard-wide SOIC) | 10.30mm × 7.50mm | >8mm | Reinforced |
| DBQ-16 (SSOP) | 4.90mm × 3.90mm | >3.7mm | Basic |

**This is >14.5mm — clears 12.6mm with 1.9mm of real margin, not a
knife-edge.** Real agency certifications, all with actual certificate
numbers (not "Pending"), read directly from the datasheet's Insulation
Specifications and Safety-Related Certifications tables:

- **DIN EN IEC 60747-17 (VDE 0884-17)** — reinforced insulation per CSA
  62368-1 and IEC 62368-1, **1450Vrms max working voltage (DWW-16)**.
- **UL 1577 Component Recognition Program** — DWW-16: Single Protection,
  5700Vrms.
- **CQC** (China Compulsory Certification) — DWW-16: Reinforced Insulation,
  altitude ≤5000m, 1450Vrms max working voltage; **certificate number
  `CQC15001121716`** — a real, populated number, the exact thing the
  Chipanalog part in the prior survey failed to have.
- **EN 61010-1 and EN 62368-1** — reinforced insulation up to 1450Vrms
  working voltage (DWW-16).
- Isolation rating: 5700VRMS / 8000VPK reinforced, 12800VPK max surge
  isolation voltage.

This design's actual working voltage across the U7 barrier
(`elec/src/constraints.ato:7`, `HighVoltageConstraints.v_max = 400V`) sits
at roughly 3.6x margin under the DWW-16's 1450Vrms reinforced working-voltage
rating and 14x under its 5700Vrms isolation rating — the electrical rating
is not close to being the limiting factor; creepage was always the binder,
and this package solves that specifically.

**Orderability, confirmed this session, not assumed:** `ISO7741FQDWWRQ1` —
DigiKey product page fetched directly: **Status Active, 6,968 units in
stock, $5.09/unit (cut tape, qty 1)**, package listed as "16-SOIC (0.551",
14.00mm Width)" matching the datasheet's DWW dimensions exactly. This is a
real, currently-orderable, in-stock part, not a paper part.

### 3.3 The architecture this actually requires

`ISO7741-Q1` is a **quad-channel, unidirectional** isolator (4 forward
channels, per the datasheet's own channel-direction table) with **one**
isolation barrier and **one** secondary ground. `HalfBridge`'s high-side and
low-side gate commands need **two separate floating secondary references**
(`switch_node` for the high side, `dc_bus.hv_minus` for the low side) — the
same reason UCC21550 internally needs its own "channel-A-to-channel-B
isolation" spec (`|VSSA-VSSB| = 1850V`, already documented in this repo's
`SOIC16W_Isolated.kicad_mod` footprint description). **One `ISO7741-Q1`
cannot serve both channels; the architecture requires two separate
packages, one per switch**, each carrying only its own switch's command
signal (1 of 4 channels used; 3 spare per package) — each package's own
primary-to-secondary barrier is independently >14.5mm, so no channel-to-
channel governing pair is introduced.

Each secondary side additionally needs a **local, non-isolated gate driver
IC** (the digital isolator's output is logic-level, not gate-drive current)
between the isolator and the existing `GateDriveHS`/`GateDriveLS` resistor
stages. A real, checked candidate: **TI `UCC27517`** — single-channel,
4A/4A source/sink peak drive (same peak-current class as the incumbent
UCC21550), 13ns typical propagation delay, non-isolated, SOT-23-5. This is
reported as a plausible, real part in the right performance class, **not a
final selection** — a full BOM decision would need its own sourcing pass.

**Power architecture is largely unaffected.** The existing floating
auxiliary supply (`power_15v_ls`, referenced to `hv_minus`) and its
bootstrap diode/capacitor network (`D5`/`C17`, feeding the high-side driver
stage per `HalfBridge`'s already-documented "High Side Power (Bootstrap)"
section) are independent of *how* the logic command reaches each secondary
side — they can be reused essentially unchanged. This is the concrete
advantage this approach has over the GDT approach (§2.3): the GDT approach
would have to either reinvent isolated power delivery or lean on the same
bootstrap network anyway, while this approach needs no power-architecture
change at all, only a signal-path change.

### 3.4 Dead-time margin: checked quantitatively, not asserted

`elec/src/main.ato:664-672` records the live budget this repo actually
enforces: `t_dt_sw (300ns) > t_igbt_off (245ns) + 50ns` — i.e., the design's
software dead-time exceeds IGBT turn-off by exactly 55ns nominal, with a
hard-asserted 50ns minimum. (The build log's own assertion output, `300ns >
295ns`, is this same inequality evaluated at its 50ns-margin boundary —
confirmed by reading `main.ato` directly, not inferred from the task's
framing.) This budget is why channel-to-channel timing skew matters here
specifically, and it is the concrete question this section had to answer,
not skip.

- **UCC21550's own published channel matching** (`SLUSEU0/current TI
  datasheet`, `www.ti.com/lit/ds/symlink/ucc21550.pdf`, fetched and read
  directly): propagation delay 26/33/45ns (min/typ/max); **Propagation
  Delay Matching for Dual Channel Driver (tDM): 0–5ns max** (−10°C to
  +150°C), 0–6.5ns max (−40°C to −10°C) — this tight, single-package,
  factory-matched figure is what currently underwrites the 55ns nominal /
  50ns minimum margin.
- **`ISO7741-Q1`'s own published part-to-part skew** (same datasheet,
  §5.15 Switching Characteristics): propagation delay 6/10.7/17ns
  (min/typ/max, 5V supply); **`tsk(pp)` part-to-part skew time: 4.4ns max**
  (5V supply) — TI explicitly defines and publishes this as "the magnitude
  of the difference in propagation delay times between any terminals of
  *different devices* switching in the same direction... at identical
  supply voltages, temperature, input signals and loads." **This is the
  correct figure for this architecture** (two separate physical ISO7741-Q1
  packages, one per switch) and it is comparably tight to UCC21550's own
  internal matching spec (4.4ns vs 5–6.5ns) — genuinely reassuring, and
  not an assumption: TI qualifies and publishes exactly this cross-device
  number.
- **What is NOT bounded by a published spec, and is the real open risk of
  this approach:** the local secondary-side driver IC (§3.3, e.g.
  `UCC27517`) is a *second*, independent source of HS/LS mismatch once two
  separate driver ICs are used (one per switch). TI's `UCC27517` datasheet
  publishes only a population-wide min/typ/max propagation delay, not a
  cross-device matching spec the way `ISO7741-Q1` does. **Until a specific
  driver IC with either a published device-to-device matching spec, or a
  min/max spread narrow enough that its worst case (stacked with the
  isolator's 4.4ns) still clears the 50ns minimum margin, is selected and
  checked, this architecture's total skew budget is not fully closed.**
  This is flagged as the one concrete, unresolved engineering task standing
  between this recommendation and a build-ready design — not hand-waved,
  and not fatal: the isolator half of the budget (the part actually
  driving the creepage requirement) is solidly closed; the driver-IC half
  needs one more sourcing/verification pass.

### 3.5 Two cascaded isolation stages — evaluated, does not change the governing constraint

The task also names "two cascaded isolation stages, each individually
clearing the bar" as a candidate. This is subsumed by, not separate from,
§3.1's finding: **any individual IC-packaged stage in the standard-width
family is still capped at 7–8.5mm**, so cascading two standard-width stages
still requires each stage's own package to clear 12.6mm on its own — which
none of the standard-width parts checked in the prior survey or this
session do. Cascading does not relax the per-stage requirement; it only
matters once a single stage already clears the bar (as `ISO7741-Q1`'s DWW
package does), at which point cascading is unnecessary rather than helpful.
Not evaluated further because §3.2–3.4 already give a one-stage-per-switch
answer that clears 12.6mm without needing a second stage.

---

## 4. U7 — Recommendation

**Two `ISO7741FQDWWRQ1` (or `ISO7740`-family equivalent), one per switch,
each paired with a local non-isolated secondary-side gate-driver IC,
replacing the single `UCC21550BDWK`.**

Why this over the GDT path: it is the only mechanism checked this session
with (a) a real, currently-orderable, in-stock part, (b) real agency
certifications with actual certificate numbers, (c) creepage clearing
12.6mm with genuine margin (1.9mm) rather than a knife-edge, (d) no DC-
transmission redesign (digital isolators are DC-coupled by internal
design — no reset scheme, no duty-cycle limitation, no core-saturation
risk, unlike a literal GDT), and (e) no change to the existing, already-
solved bootstrap power architecture.

**What it costs:** 1 IC → 4 ICs (2 isolators + 2 local drivers), more board
area, and — the one item not yet closed — a local driver IC selection that
demonstrably preserves the 50ns dead-time margin against the isolator's own
already-tight 4.4ns part-to-part skew.

**What survives unchanged:** the dead-time *target* (300ns programmed vs
245ns IGBT turn-off) is a property of the drive resistor/IGBT choice, not
of the isolation barrier, and is untouched by this proposal. The bootstrap
network, the `power_15v_ls` floating supply, and the existing
`GateDriveHS`/`GateDriveLS` resistor stages are all reusable without
modification. Shoot-through protection (the dead-time itself) is preserved
in principle pending the §3.4 driver-IC verification; it is not weakened by
design, only left with one open numeric check.

---

## 5. U3 — what mains-voltage ZCD is for, and whether this design needs it

Traced directly from `elec/src/modules.ato`'s `PowerInput` module and
firmware, this session:

```
ac_l -> 220k -> 220k -> zcd (HV tap, ~3.78V pk)
zcd -> 10k -> dc_bus.gnd_ref   (divider bottom -- referenced to AC NEUTRAL via the CMC, not PE)
zcd -> zener clamp -> dc_bus.gnd_ref
zcd -> 430R -> H11L1 LED anode; LED cathode -> dc_bus.gnd_ref
--- barrier (U3) ---
H11L1 output -> pullup to vcc_3v3 (SELV) -> mcu.zcd_in (GPIO13, PIN_ZCD_INPUT)
```

- **`grep -rn PIN_ZCD_INPUT firmware/` returns exactly one hit — its own
  `#define`.** No consumer anywhere in firmware. Not wired into
  `SafetyInterlock`, OCP, OVP, or WDT in `elec/src/main.ato`/`modules.ato`.
- **`pll_control.c`'s "ZCD" is a different signal** — the resonant-tank
  *current* zero-crossing, sourced from the CT (`ct_sense.ct`), already
  SELV-side by construction (current-transformer isolation), used for
  PLL/ZVS phase tracking. Confirmed by reading `pll_control.c` directly:
  its capture channel is documented as "Connected to Current Transformer ->
  Comparator (ZCD)," unrelated to U3's mains-line signal.
- **`hal_timer.h`'s "Capture/compare for ZCD edge timing"** is generic HAL
  infrastructure, not a U3-specific forward plan: the one concrete consumer
  of MCPWM capture-channel ZCD timing found in firmware is `pan_detect.h`'s
  `cap_chan` (the same CT-based resonant-current ZCD `pll_control.c` uses).
  This weakens, not strengthens, the "planned not abandoned" reading — the
  capture facility already has a real consumer, and it is not this signal.
- **What mains ZCD is conventionally for, in this appliance class:**
  synchronizing phase-angle/burst-fire power control or TRIAC/relay
  switching to the AC line zero-crossing (inrush/EMI reduction), or
  mains-frequency/brownout validation. **None of these apply structurally
  to this design as built:** the resonant half-bridge is driven from a
  rectified/doubled DC bus, not phase-controlled directly off the AC line,
  so zero-cross-synchronized switching of the power stage itself is not
  applicable the way it would be for a TRIAC dimmer. The one plausible use
  — zero-cross-synchronized *relay* closure to reduce contact arcing at
  K2/K3 or the main mains relay — is not how this design's soft-start
  actually works today: `main.ato`'s `t_soft_start_delay = 500ms` is a
  fixed time delay, not ZCD-synchronized. No control loop, thermal model,
  or state machine references a mains-frequency quantity anywhere in
  `firmware/`.

## 6. U3 — a real ≥12.6mm mechanism does exist, if ever needed

Checked directly per the task's suggestion ("reinforced digital isolators
in wide packages are the obvious candidate, so check real ones"): **the
same `ISO7741-Q1`/`ISO7740-Q1` DWW-16 family found for U7 (§3.2) applies
here too** — U3 only needs *one* isolation domain (a single SELV output),
which is structurally simpler than U7's two-floating-domain requirement.
One channel of one `ISO7741FQDWWRQ1` (>14.5mm, reinforced, real,
orderable — same part, same certificates, same DigiKey stock as §3.2)
would clear 12.6mm with the same 1.9mm margin.

**This is not a drop-in part swap, and that matters for the verdict.** A
digital isolator's primary-side input must already be a clean digital
logic level — it has no analog LED front end the way H11L1's optocoupler
does. Today's circuit relies on the optocoupler doing signal conditioning
as a side effect of being an opto (the divided/clamped analog sine
crossing the LED's forward-conduction threshold *is* the signal
shaping). Widening to a digital isolator would require adding a primary-
side comparator/Schmitt-trigger stage (referenced to `dc_bus.gnd_ref`,
still on the HV side — no new barrier, a same-domain addition) ahead of
the isolator input. Small, bounded, real — but not free, and this is the
same signal-conditioning cost the rejected protective-impedance analysis
(`docs/evidence/2026-07-30-zcd-protective-impedance-viability.md` §5)
already flagged for its own proposal.

## 7. U3 — verdict: DELETE (with a verified re-introduction path, not a dead end)

**Recommend deletion of U3 and its associated divider/clamp network**
(`r_zcd_top1`, `r_zcd_top2`, `r_zcd_bot`, `d_zcd_clamp`, `r_zcd_opto`, `U3`
itself), on the following reasoning:

- No firmware consumer exists today (§5, confirmed by direct grep, not
  inferred).
- No safety or control function depends on it (§5, confirmed by tracing
  `SafetyInterlock`/OCP/OVP/WDT wiring).
- The conventional uses of mains ZCD in this appliance class do not apply
  to this design's actual architecture (DC-bus resonant converter, not
  phase-controlled; time-delay soft-start, not zero-cross-synchronized) —
  this was checked against the real control scheme, not assumed from the
  device category.
- Deletion removes real BOM/board-area cost (one optocoupler + five
  passives) for a signal with no current consumer.

**This is not a dead end if requirements change.** Unlike the rejected
protective-impedance route (which fails on signal-class physics — an
edge detector referenced to the wrong node — independent of any part
search), U3's deletion is reversible with a known, real, ≥12.6mm mechanism
already verified in this document (§6): if a future feature genuinely
needs mains-referenced ZCD (e.g., a deliberate zero-cross relay-switching
redesign, or line-frequency validation), `ISO7741FQDWWRQ1` plus a small
added comparator stage is a checked, orderable, agency-certified path back
in — not a research problem to redo from scratch.

**What deletion entails beyond removing the part**, stated plainly since
the task asks for this explicitly: remove `zcd`/`zcd_out` net declarations
and the divider/clamp/opto instances from `PowerInput` in
`elec/src/modules.ato`; remove `power_in.zcd_out.line ~ mcu.zcd_in.line`
and the `PIN_ZCD_INPUT` `#define` in `temper_pins.h` (or leave the pin
defined-but-unrouted if a future header revision might reuse the GPIO —
a call for whoever owns the pin map, not resolved here); no firmware
logic to remove, since none exists; re-run
`scripts/check_isolation_keepout.py` and the domain-partition checker to
confirm no orphaned SELV/HV crossing remains flagged for a deleted node.
None of this was performed in this pass — analysis only, per the task's
hard constraint.

---

## 8. UNVERIFIED (stated plainly, not guessed past)

- **The local secondary-side driver IC for U7's discrete-isolator
  architecture is not finally selected.** `UCC27517` is reported as a
  real, plausible, right-performance-class candidate (§3.3), not a
  verified final choice. Its device-to-device propagation-delay matching
  (as opposed to population min/typ/max) was not found published anywhere
  this session — this is the one open item standing between this
  recommendation and full closure of the dead-time margin (§3.4).
- **`PGT7604NL`'s (§2.1) real-world orderability and agency certification**
  were not established — no dedicated datasheet, no distributor listing,
  no certificate number found. Reported as market evidence only, not
  adopted.
- **A custom-wound GDT to a ≥12.6mm specification (§2.2)** was not
  quoted, designed, or confirmed acceptable to any magnetics house this
  session — reported as structurally plausible by analogy to this repo's
  own tank-coil precedent, not demonstrated.
- **Whether `ISO7741-Q1`'s automotive (`-Q1`) qualification carries any
  practical sourcing friction** (price premium, minimum order quantity,
  design-in restrictions) for a non-automotive household appliance was not
  checked beyond confirming DigiKey stock and per-unit price. Automotive-
  grade parts are routinely used in non-automotive designs industry-wide,
  but this specific sourcing question was not separately verified.
- **Whether a wide-body (DWW-class) TI digital isolator exists in a
  smaller/cheaper channel-count part than the quad-channel `ISO7740`/
  `ISO7741` family** (which would be a better cost/board-area fit for
  U3's single-channel need) was not found this session — only the
  quad-channel automotive family was confirmed to ship in the DWW
  package; a search for narrower/cheaper DWW-class parts came back empty
  (§3.1 found only standard-width DW packages for TI's non-automotive
  and lower-channel-count isolator lines).
- **The board-level rework this recommendation implies for U7** (new
  footprints for two `ISO7741-Q1` DWW packages plus two driver ICs,
  routing two separate floating secondary domains, updated bootstrap
  network verification) was not performed or estimated in area/cost terms
  — this document is a mechanism feasibility analysis, not a layout study,
  per the task's explicit scope.
- **IEC 60335-1's exact clause treatment of a digital-isolator-based
  reinforced barrier for a gate-drive function** was not independently
  verified against primary standard text (paywalled) — the same
  UNVERIFIED-at-primary caveat this repo's other evidence documents
  already carry for IEC 60335-1 clause interpretation applies here
  unchanged.

## 9. Hard-constraint compliance

- **No design file, footprint, netclass, or constant modified.** Only
  this document was written; `git status --short` clean apart from it
  (verified before writing, at base commit `8d188403`).
- **12.6mm never proposed downward; no pollution-degree or domain
  reclassification proposed anywhere in this document.**
- **No part adopted on a "probably certified" basis.** `PGT7604NL`'s real
  but unconfirmed-orderable/uncertified status is reported and explicitly
  not adopted (§2.1, §8) — the same treatment this repo already gives the
  Chipanalog CA-IS3211 case. `ISO7741FQDWWRQ1`, by contrast, is adopted
  only after confirming Active DigiKey stock, a real per-unit price, and
  agency certificate numbers that are populated, not "Pending"
  (`CQC15001121716` read directly from the datasheet).
- **Manufacturer-primary sources for every spacing and rating figure**
  cited above: TI datasheets (`iso7741-q1.pdf`, `iso7741.pdf`,
  `ucc21550.pdf`, all fetched and saved this session), Pulse/YAGEO's own
  `P774.J` datasheet and gate-drive-transformer white paper, ICE
  Components' own GT06/GT07/GT04 product pages, TDK's own InsuGate press
  materials. DigiKey used only for stock/price/orderability, never for a
  spacing or certification figure.
- **No fabricated or pattern-guessed MPN.** Every part number above was
  read from a fetched manufacturer datasheet or a live distributor product
  page this session; the custom-GDT path (§2.2) is explicitly flagged as
  not-yet-a-part, following this repo's own tank-coil precedent's honesty
  convention rather than inventing an MPN for it.
- **Own git worktree**, branched fresh from `origin/main`, not one of the
  many pre-existing worktrees/branches for this repo. `make venv-isolate`
  run before any tool invocation. `uv run --no-sync` used for the
  provenance check below. No `git stash` used. **No sub-agents spawned**
  — all research, fetching, and writing in this document was performed
  directly in this session.
- **Not pushed, no PR opened.**
