# External insulation answer — review and follow-up

Initial review, 2026-09-25. The owner's pasted answer proposed a functional earth
bond, the >125–250 V band for most crossings, a different ISO7710 land pattern,
and CT relocation. **D5 remains open:** the claimed rectifier voltage clamp
is not established by this circuit. At that initial review no bond or CT
source change had been made; the CT relocation was implemented later.
The pasted answer contains damaged text; this document records the legible
proposals and their assessment, not a verbatim reconstruction.

## Follow-up answer and source integration

[ORACLE-ANSWER.md](ORACLE-ANSWER.md) corrects the rectifier direction, the
CT land-pattern gap and the unsupported IRM capacitance estimate. The owner
subsequently made five source changes: T1 moved to SW_A, the nominal shunt
trip fell to about 61 A, a roughly 280 V bus comparator was ANDed into the
isolated fault line, resonant-bank bleeders were added, and U9 received TI's
8.1 mm high-voltage land pattern. These are risk reductions with audited
connectivity. They do not establish a safe maximum bus voltage.

The answer's 468 V and 511 V figures are **heuristic energy estimates**, not
conservative bounds. Its expression transfers only inductor energy to the
bus; resonant-capacitor energy can also return. As a check of that mathematical
claim, the supplied `ringdown()` model at 198 V initial bus, 100 µH, zero
pan resistance and 250 V initial capacitor magnitude gives 474.1 V from
90.1 A, above the claimed 468.6 V estimate for a 61 A trip. At 100.1 A it
gives 513.8 V, above the 511.7 V estimate for 71 A. These are model states,
not proof that a particular controller sequence reaches them; they show why
the expression is not an energy upper bound.

The ≈280 V restart inhibit can allow a bus above the 198 V line crest. Even
the same incomplete expression rises to about 556 V at 61 A and 597 V at
71 A if it starts at 279 V. `trip_state()` detects absolute tank current,
whereas the implemented comparator reads a 1 mΩ DC-return shunt through a
10 kΩ / 10 kΩ, 100 pF sense node (about 0.5 µs RC time constant), followed
by comparator, isolation, interlock and gate delays. The supplied script
runs one 0.3 Ω, 300 ns trip trajectory per listed case; it does not contain
the damping and 100–800 ns sweep asserted in the answer. A source-consistent
fault sequence and measured turn-off/overshoot are needed before deciding
whether a bus clamp is required.

**D5 remains open.** The proposed single-point SELV_GND–PE bond and uniform
≥8.0 mm reinforced PCB barrier remain a review basis, pending owner sign-off,
working-voltage analysis, Coilcraft package evidence and applicable lab
interpretation. T1 now faces SW_A rather than the resonant junction, but
SW_A still has periodic high-frequency stress. PCB spacing and source parity
do not establish package insulation or certification.

## Controller fault-interface blocker

The standalone interlock's [interface contract](../interlock/INTERFACES.md)
requires active-high fault inputs (healthy low, with local pullups).
Power-stage J4.10 instead provides BUS_OCP_OK (healthy high, fault or HOT-side
power loss low). A direct connection inverts the intended protection.
The off-board path therefore needs a fail-safe polarity adapter or a compatible
latch input, followed by checks of fault assertion, loss of either supply,
broken signal/return conductors and reset behavior. This adapter is not present
in the 102-part source. The OVP comparator currently establishes only a local
threshold/fault indication; an integrated restart inhibit is not yet proved.
This is an additional blocker alongside D5 and physical timing qualification.

## Findings that carry forward

- Reinforced isolation must not depend on continuity of a functional PE bond.
  The proposed single-point removable 0 Ω connection from controller return
  to PE is an architecture option for review. Its location, external USB/probe
  paths, open-PE behavior and electrical classification remain to be resolved.
- Creepage requires the applicable working-voltage convention, not substitution
  of the old half-bridge peak voltage into an RMS band. PCB and package paths
  need separate material and environmental evidence. The live repository
  lookup values are in [RULES-PREFLIGHT.md](RULES-PREFLIGHT.md).
- The former ISO7710 land pattern had a 7.25 mm pad gap. The implemented
  high-voltage pattern measures 8.1 mm. Slots do not increase the package
  surface distance.
- The [IEC 60664-4:2005 scope](https://webstore.iec.ch/en/publication/2804)
  includes periodic voltage stress above 30 kHz through 10 MHz, used with
  Part 1 or Part 5. The applicable high-frequency requirements remain open;
  reading the public scope is not a normative-table compliance determination.

## Why the mains-crest bound is not proven

In `elec/src/power_stage_120v.ato:233–252`, BR1 feeds BUS_P/HV_RET and
C5/C6 hold the 5 µF DC link. With an idealized forward drop Vf, diode
conduction prevents approximately:

- BUS_P falling below `max(L_FILT, N_FILT) − Vf`;
- HV_RET rising above `min(L_FILT, N_FILT) + Vf`.

These are the opposite directions from the upper/lower limits needed to
prove that both rails stay within the line crest of earth. An elevated
DC-link voltage reverse-biases the bridge. Tank energy returned through
MOSFET body diodes can charge that link; the rectifier cannot send that
energy back to the mains. The body diodes limit switch nodes relative to
the **instantaneous DC rails**, subject to drops and transients, not directly
to earth. This is a circuit inference from diode polarity, independently
reviewed by a Sol agent. TI describes the analogous energy-return mechanism
in its [supply pumping discussion](https://www.ti.com/document-viewer/lit/html/SSZTBS1/GUID-4E20E0C2-9D92-42A8-B86E-D05394FAD546);
that reference is not a quantitative model of this cooker.

At the initial review, the source provided no demonstrated replacement bound:

- R3/R4 total 440 kΩ across 5 µF: about 2.2 s discharge time constant,
  not a bus clamp (`elec/src/power_stage_120v.ato:245–252`).
- RV1 is across AC upstream of the choke and rectifier, not across the DC
  bus or to PE (`:204–206`).
- The 1 nF MOSFET snubbers are capacitors, not voltage clamps.
- U4 measured bus voltage and the sole hardware comparator checked shunt
  current, not bus overvoltage (`:338–433` in the earlier source). The later
  revision adds a bus comparator and restart inhibit, though its shutdown
  energy envelope remains unproven.

Therefore the >125–250 V band is **not rejected as an eventual result**;
its proposed proof is insufficient. Rail differential voltage, common-mode
voltage to PE, controller-reference behavior and overshoot must be bounded.
An intact bond and an open PE are different conditions; they cannot silently
share the same earth-reference assumption. Exact oracle RMS/peak numbers
have not been reproduced and are not adopted as design limits.

## CT correction and relocation proposal (subsequently implemented)

The oracle's 9.1 mm PCB gap came from the old, incorrect donor footprint.
Coilcraft's recommended land pattern specifies **18.5 mm copper edge gap**;
its primary pads are 4.8 × 9.0 mm. The unit footprint is now corrected and
regenerated, with independent source parity and DRC checks. See
[FOOTPRINTS.md, F7](FOOTPRINTS.md) and [NATIVE-01.md](NATIVE-01.md).
The manufacturer's package guarantee remains ≥8 mm; the larger PCB gap
cannot substitute for package-surface evidence.

The series path before the source change was:

`SW_A → J2/coil → COIL_RET → T1 → RES_A → capacitor bank → SW_B`.

The implemented relocation is:

`SW_A → T1 → new coil-feed net → J2/coil → capacitor bank → SW_B`.

This preserves series-current measurement in principle and moves the CT
primary away from the resonant junction. The source was re-audited and
re-frozen; the CT now faces switch-node common-mode transitions.
Filter/blanking behavior must be demonstrated.
It does not repair the missing DC-link or earth-reference voltage bounds.
The relocation is implemented; a final CT insulation verdict is not approved.

## Other unverified claims

A maximum leakage-current rating is not a measurement of input-to-output
capacitance. Converting 0.25 mA at 277 V into about 2.4 nF assumes sinusoidal
60 Hz current entirely through that particular capacitance. Its test path,
frequency and other leakage contributions must be established first. No
actual capacitance, touch-current result or EMI improvement is claimed.
The optional Y2 capacitor/resistor earth network is also only a proposal;
its ratings, population options and applicable touch-current tests need review.

## Focused question for the oracle

Please revise the analysis using the actual diode directions and source:

1. Derive a bounded DC-link voltage and each rail's potential to PE over
   the applicable normal/abnormal conditions, including returned tank energy,
   shutdown, line phase and implemented protection. Identify missing controls
   explicitly. A nominal rectified-line waveform is not a bound.
2. Derive differential RMS and relevant peak voltage at every HOT/controller
   crossing for the proposed bond, open PE and external earthed connections.
   Separate PS1's mains input from the DC rails and resonant nodes.
3. Explain the applicable standard/edition's working-voltage convention and
   high-frequency treatment; retain conditional band results until justified.
4. Evaluate the CT relocation above using the corrected PCB land pattern and
   separate ≥8 mm package guarantee. State what manufacturer or lab evidence
   is still required.

Reading packet: [original question](ORACLE-INSULATION-QUESTION.md),
[preflight](RULES-PREFLIGHT.md), [decisions](DECISIONS.md), unit source and
`docs/hardware/power-section-120v/POWER-SECTION.md`.

Physical touch-current, overshoot, CT injection, hipot and emissions tests:
**NOT RUN**. No fabrication or certification approval is implied.
