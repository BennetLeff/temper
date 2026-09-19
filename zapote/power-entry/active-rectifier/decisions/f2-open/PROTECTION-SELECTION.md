# F2-open protection selection (Package 2)

Date: 2026-09-19. Status: **SELECTION with illustrative model support;
no protection qualification promoted.** No fabrication, procurement, powered
testing, or external correspondence is authorized by this record. Part
classes and quantitative selection criteria are specified; no MPN is
selected. The retained `DECISION.md` in this directory is superseded review
input (bank-side worker draft) and is not amended by this file.

Retained inputs: authored `elec/src/power_entry_active_unit.ato` (diode-side
ECO: U20.1 on `BOOST_DIODE_POSITIVE`); controller primary source
`zapote/power-entry/shunt-repair/sources/TI-UCC28180.pdf` Rev D
(SHA-256 `e1e1588c…1b00be`); timed model + corners
(`../experiments/f2-open/MODEL.md`, `raw/timed-sweep.csv`,
`raw/startup-bursts.csv`); ngspice second path
(`../evidence/f2-open-timed-02/`). All peaks below are illustrative model
results; all ceilings are authored values, not qualifications.

## 1. Allowable-voltage budget from actual affected parts

| Part / structure | Limit used | Kind | Basis |
|---|---|---|---|
| U40 `B32672P6474K000` film, `BOOST_DIODE_POSITIVE`–`CONTROL_GND` | 630 VDC | authored maximum, illustrative ceiling | authored `.ato` value/mm; pulse current, dv/dt, ESR **NULL** (no retained manufacturer curve) |
| U9 `STW65N65DM2AG` silicon | 650 V | authored rating, no avalanche credit | authored `voltage_rating`; no retained datasheet basis for avalanche energy |
| U10 `C3D20065D` silicon | 650 V | authored rating, no avalanche credit | authored `voltage_rating`; same NULL |
| VSENSE divider 5×200 kΩ (`CRCW2512200KFKEG`) + 13 kΩ | **NULL** | no rating credited | No retained part doc. Per-resistor stress at the ceiling: ≈124 V each at 630 V node (≈173 V at 877 V worst model row); bottom resistor ≈1.3% of node. Reported, not bounded. |
| PCB spacing on the diode-side node | **no new claim** | — | TEA construction screens remain open with three failures (see `../review/`); no creepage/clearance credit taken here. |

Governing illustrative ceiling: **630 V** (U40). Every "closes / exceeds"
verdict below is against 630 V as an *illustrative* ceiling, and every row
above it is simultaneously above both silicon ratings.

## 2. Response-time budget (healthy U9; illustrative, from `timed-sweep.csv`)

Post-trip delay T_resp is detection + comparator + latch + FET + gate-fall
time, swept 0–20 µs and never zero-by-default. Slope near trip: ≈15 V/µs at
470 nF (≈4–5 V/µs at 1.5 µF) — each microsecond of delay costs about that.

| Configuration (crest unless noted) | T_resp | Vpeak | vs 630 |
|---|---|---|---|
| 470 nF, typ OVP (424.7 V) | 0 µs | 751 V | exceeds — budget does not close at any achievable delay |
| 470 nF | 2 / 5 / 10 / 20 µs | 779 / 822 / 854 / 947 V | exceeds |
| 470 nF, OVP-latest (454 V) / detector-latest (510 V), 5 µs | — | 825 / 877 V | exceeds |
| 470 nF, phase 45° (I0=17.0 A) | 5 µs | 660 V | exceeds |
| 470 nF, phase 30° (I0=12.6 A) | 5 µs | 576 V | closes — closure ends near I0 ≈ 14 A |
| 1.0 µF, crest | 5 µs | 646 V | exceeds |
| **1.5 µF, crest, typ OVP** | **0 / 5 / 10 µs** | **576 / 598 / 613 V** | **closes; ≈14 µs interpolated limit** |
| 1.5 µF, crest | 20 µs | 658 V | exceeds |
| 1.5 µF + L216 / C−10% / I0+10% / Vpk+10% / OVP-latest, 5 µs | — | 598–617 V | closes, margin 13–32 V (nominal row 598.0, five corner rows 604.0–616.8; thin — noted, not padded) |
| 1.5 µF, detector-latest (510 V) | 10 µs | 677 V | exceeds |

Conclusions: (a) at 470 nF the shutdown-only budget **never closes** at
nominal crest current — even T_resp = 0 peaks 751 V, because the filtered
sense trips only after the node has already passed ~460 V while pumping;
(b) at 1.5 µF it closes across the swept corners iff post-trip gate-off
lands within ≈14 µs (interpolated 630 V crossing; illustrative); (c) the 510 V independent detector is
*not* the first-peak limiter — its latest corner + 10 µs still peaks 677 V
at 1.5 µF. Its functions are backup trip, latch source, and clamp
coordination. A shunt clamp is therefore required in all closable
configurations, sized below.

## 3. Selected arrangement (one concrete design)

**Select: independent diode-side OV detector + SR latch + dedicated inhibit
FET (alternative gate-disable path) + diode-side shunt clamp + local-C
complement 470 nF → 1.5 µF film, with a separately specified bank-status
function.** No credit is taken for an unspecified "fast shutdown", for the
existing `HOT_PERMIT_EXTERNAL` path (no supervisor contract: source,
polarity, default, latency, fault behavior all NULL), or for shutdown alone
at 470 nF (§2a).

### 3.1 Topology (nets: `BOOST_DIODE_POSITIVE`, `CONTROL_GND`, `pfc.VSENSE`, `AUX_15V_IN`)

1. **Detector divider D_det**: independent string from
   `BOOST_DIODE_POSITIVE` to `CONTROL_GND`, sized for the §3.3 thresholds.
   Selection criteria: per-resistor rated working voltage ≥ 250 V with
   pulse rating covering a 700 V single event; placement creepage-reviewed
   (QR-DIV). Not shared with the regulation divider (common-cause).
2. **OV comparator + SR latch** (part class: industrial open-drain
   comparator + discrete SR latch or supervisor with latched output;
   criteria in §3.4). The latch sets on OV **or** on detector-bias fault
   and drives the inhibit FET. Reset input: AUX removal only (§3.6).
3. **Dedicated inhibit FET q_inhibit2**: N-channel, D→`pfc.VSENSE`,
   S→`CONTROL_GND`, in parallel with the existing q_inhibit (wired-OR at
   the node — either FET pulls `VSENSE` below OLP). Asserted HIGH =
   inhibit. Gate driven directly by the latch; no software, no
   HOT_PERMIT dependence.
4. **Shunt clamp**: across `BOOST_DIODE_POSITIVE`–`CONTROL_GND`, first
   conduction below the detector's latest trip, clamping below the ceiling
   (§3.4 criteria). Absorbs the first-peak energy the delay budget cannot.
5. **Local-C complement**: U40 470 nF → 1.5 µF film (same B32672 series
   class or equivalent meeting QR-CAP). Unfused stored energy at 400 V:
   0.0376 J → 0.120 J (stated consequence). Footprint/mechanical delta is
   QR-CONSTR. This is a *complement*, not the solution: 1.5 µF without
   clamp/latch still peaks 677 V in the det-latest/10 µs corner.

### 3.2 Bias supply and loss-of-bias safe state

Detector, latch, and UCC28180 all bias from `AUX_15V_IN` referred to
`CONTROL_GND` (same rail by construction). Bias loss ⇒ VCC falls through
UVLO (off 9.1–10.3 V, §8.3.3) ⇒ **GATE held off** (§8.3.15) independent of
any detector output. The unpowered detector output is high-Z and asserts
nothing; safety under bias loss comes from controller UVLO on the common
rail, not from detector assertion. AUX source behavior and hold-up timing
remain NULL (QR-DET input). The existing q_inhibit default (released on AUX
loss) is covered by the same UVLO argument — stated, not changed.

### 3.3 Thresholds with tolerance stack (volts at the power node)

- Regulation (existing, nominal divider): setpoint 389.6 V; max normal
  ≈ 401 V (over-temp VREF 5.15 V; switching ripple NULL on top).
- Detector OV trip: **500 V nominal**; corners 490.2 / 500.0 / 510.0 V
  (same assumed ±1% divider tolerance as the OVP corners). Nuisance margin:
  ≈89 V above max normal (ripple NULL noted). Headroom: 120 V from latest
  trip to the 630 V ceiling for clamp + delay action.
- Controller OVP_H (first-peak limiter): 403.0 / 424.7 / 454.3 V corners
  (modeled); reset 102% typ 397.4 V (burst analysis).
- Clamp standoff window (selection criterion): min standoff > 430 V
  (above max normal + margin, never conducts in normal operation) and max
  standoff < 490 V (below earliest detector trip, so absorption precedes
  backup-trip tolerance spread).

### 3.4 Detection-delay and clamp criteria (requirements, not measurements)

- Trip-to-inhibit (detector output → q_inhibit2 Miller plateau → VSENSE <
  OLP) **≤ 5 µs**, verified by QR-DET measurement. Rationale: §2 closes at
  1.5 µF within ≈14 µs; 5 µs holds the 13–32 V corner margins with allowance
  for the NULL τ tolerance and unmodeled EDR/VCOMP dynamics.
- Clamp (all QR-CLAMP): standoff in §3.3 window; clamping voltage
  ≤ 600 V at ≤ 30 A illustrative bound; single-pulse (non-repetitive)
  energy ≥ 250 mJ (floor from worst model row: 192 mJ above 450 V standoff
  in `c15_detlate_r10`, plus margin TBD); declared fail mode:
  fail-short ⇒ line-fed fault via bridge/L/U10, cleared by F1 (QR-F1 input);
  fail-open ⇒ controller-OVP + latch path still inhibits, silicon survival
  shown illustrative 576–617 V < 650 V at 1.5 µF/OVP-path corners.
  Repetitive rating is *not* required **because** the latch (§3.6)
  guarantees a single event per F2-open — if the latch is ever removed,
  the clamp rating reopens (coupling recorded for review).

### 3.5 Gate-disable path

Latched OV ⇒ q_inhibit2 ON ⇒ `pfc.VSENSE` held below the OLP threshold
(16.5% VREF) ⇒ UCC28180 standby (PWM halted, ICC 1.8–3.47 mA per EC table).
This is a control response for a **healthy** U9 (detection + latency
budget §3.4), never an interrupter for failed-short U9 (§4).

### 3.6 Reset: latching, and why

**Latched.** The latch sets on detector OV and clears only on AUX removal
(input power cycle). Reasons: (1) automatic reset through the OVP-hysteresis
window produces 19–31 re-switching bursts/s with a 545 V-class overshoot
each (MODEL §4) — repetitive, unqualified stress on U40/U9/U10 and
repetitive clamp duty no non-repetitive rating covers; (2) F2-open is a
hardware fault requiring service — self-clearing contradicts fail-safe;
(3) the single-event guarantee is what lets the clamp carry a
non-repetitive rating (§3.4 coupling).

### 3.7 Behavior on the three cases (with arrangement)

- **(a) Startup, F2 already open**: soft-start pumps ≤42.4 mJ to first trip
  (≤5 bounding DMAX cycles; wall time NULL) → detector/controller trip →
  latch sets → q_inhibit2 holds standby → **no burst train**. Clamp absorbs
  the first overshoot (bound 545 V; ≈71 mJ above 450 V standoff at 1.5 µF,
  inside the single-pulse criterion). Bank sits ≈0 V (no charge path;
  leakages NULL) → bank-status withholds bank-ready. OVP activity is not a
  fuse-continuity proof.
- **(b) F2 opens during operation** (bank at 390 V, disconnected):
  controller OVP path trips first (typ 424.7 V filtered), detector backs up
  at 500 V nominal; clamp limits the first peak (modeled 576–617 V across
  1.5 µF corners, illustrative); latch sets; gate inhibited. Bank remains
  charged on its own bleeders (300 kΩ × 2240 µF ≈ 672 s) — discharge/access
  provisions are QR-BANK, not modeled.
- **(c) Restart**: latched ⇒ no re-switching while AUX is held. An AUX
  cycle clears the latch; if F2 is still open the next power-up delivers
  exactly one bounded burst (§a) then re-latches. Repetitive exposure is
  therefore one event per power cycle, maximum.

## 4. Failed-short switch case (SEPARATE — no gate credit)

Gate shutdown (controller OVP, detector, q_inhibit2) **cannot** interrupt a
failed-short U9: drain–source remains conductive regardless of GATE. States:

| State | Path | Interrupting device today |
|---|---|---|
| U9 healthy/on/off | line-fed boost loop; diode-side cap | q_inhibit2 + clamp + latch (control response, §3; detection+latency QR-DET) |
| U9 failed-short, U10 healthy | line-fed through rectifier/L/U9; U10 blocks bank reverse discharge | F1 in line path only — clearing/bridge survival unestablished (QR-F1) |
| U10 failed-short, U9 healthy | internal bank loop until U9 turns off | U9 turn-off via §3 path — detection/latency/survival unestablished (QR-DET/QR-F2B) |
| U9 + U10 failed-short | bank+ → F2 → U10 → a1 → U9 → `PFC_BUS_MINUS` → bank− | **F2 candidate only** — clearing/let-through/withstand unestablished (QR-F2A/QR-F2B) |

Neither U12 nor F1 is in the internal loop. No destructive-fault
interruption is claimed; each converts to a qualification requirement (§5).

## 5. Qualification requirements (method per item, CLOSEOUT Q1/Q2 style)

| ID / owner role | Work and exact output | Input needed | Pass criterion |
|---|---|---|---|
| QR-F2A — component applications engineer | F2 (A70QS50-14F) capacitor-discharge coordination: time-constant definition, current limit, minimum breaking current, total clearing/let-through at bank corners (max credible C/V, temperature). Own requirement, not a model result. | Max bank C/V corners, holder DC/thermal ratings | Retained manufacturer response tied to exact part + conditions, or explicit refusal/unsupported use |
| QR-F2B — power/protection engineer + test lab | Internal-loop prospective current, let-through, arc clearing, copper/device withstand; failed-device residuals (no normal-Rds(on) substitution); high-impedance + interrupted-arc + enclosure containment; max bus energy | QR-F2A data, failed-short residuals | Reviewed coordination report + physical tests; F2 selected/replaced accordingly |
| QR-F1 — power/protection engineer | Line-fed U9-short prospective fault, F1 total clearing, bridge survival | Line fault conditions | Coordination demonstrated, or F1 replaced |
| QR-CLAMP — power electronics engineer | Clamp selection evidence at §3.4 criteria: standoff, Vc at current, single-pulse energy, fail mode, temperature | Worst-case energy/current bounds (§3.4) | Measured Vc ≤ 600 V at rated pulse; declared fail mode with QR-F1/QR-DET consequence closed |
| QR-DET — power electronics engineer | Detector threshold/delay/fault-injection: divider open/short, bias removal, output stuck, latch set/reset; trip-to-inhibit ≤ 5 µs at corners | AUX/bias contract, temperature | Measured delay bound met; safe state (inhibit) on every injected fault; latch clears only on AUX cycle |
| QR-CAP — power electronics engineer | 1.5 µF film: effective capacitance, tolerance, pulse/dv/dt, ESR, dimensions/availability, unfused-energy (0.12 J) re-assessment | Candidate datasheet | Selected part meets §3.4 energy context + ratings, or alternative re-runs §2 |
| QR-U40 — component applications engineer | U40 pulse/dv/dt/ESR data or derating decision for the measured repetitive/single-pulse duty | Burst/single-event waveforms | Retained manufacturer data or explicit derate; NULL closed |
| QR-DIV — power electronics engineer | Detector + regulation divider working/pulse voltage ratings, temperature drift, creepage review | Part docs, layout | Ratings bound the §1 stresses with margin |
| QR-BANK — system/power engineer | Bank-status function: HOT-domain producer, isolated channel if required, sequencing, loss-of-bias state, downstream permit behavior; bank discharge/access provisions | Assembly + enclosure definition | Bank-ready withheld in all three §3.7 cases by test; discharge provisions verified |
| QR-SURGE — EMC engineer + lab | Diode-side clamp + detector under the adopted differential/common-mode contract, installed assembly | Surge contract, assembly | Applied/loaded waveforms, pin stresses, post-test function per criterion |
| QR-CONSTR — CAD owner | ECO implementation (`f2-protection-eco.patch` proposal): parity, ERC/DRC, spacing checks, BOM/manifest | Selected parts from QR-CLAMP/QR-DET/QR-CAP | Source/native parity + clean ERC/DRC on saved bytes; CAD completion closes no QR above |

## 6. Proposed source patch + ECO description (NOT applied)

`f2-protection-eco.patch` (this directory) is a **proposed, uncompiled,
unapplied** unified diff against `elec/src/power_entry_active_unit.ato`. It
adds: detector divider (2× 2512 resistors, criteria-valued), dual-comparator
+ latch block (generic SOIC-8 placeholders with the §3.1 netlist intent),
q_inhibit2 + gate drive (SOT-23, criteria-valued), shunt clamp (two-lead
power package placeholder, criteria-valued), and the U40 470 nF → 1.5 µF
value change. Reference designators, footprints, and MPNs are
intentionally criteria-valued (e.g. `TBD-QR-DET`): exact selection is
QR-DET/QR-CLAMP/QR-CAP output, and the patch must be recompiled through
Atopile → native → parity → ERC/DRC by QR-CONSTR before any CAD exists.
Someone else applies it; general harness expansion stays frozen.

## 7. What remains open (non-claims)

No claim is made that F2 clears, that shutdown meets the budget in
hardware, or that the arrangement is qualified. Open: every QR row above;
inductor saturation curve; capacitor/filter tolerances; AUX/HOT_PERMIT
producer contracts; VCOMP/EDR large-signal response; actual delays;
fuse-opening arcing; anything beyond mains inflow in surge. The evidence
ledger (`../evidence/f2-open-claims-03/claims.json`) carries these as
illustrative derivations and explicit NULL assumptions, machine-checked by
`zapote-claims`; the fault-loop models by `zapote-fault-loop`.
