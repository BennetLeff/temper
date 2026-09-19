# F2-open protection — corrected construction decision

Status: **INCOMPLETE DESIGN; NOT READY FOR ROUTING/FREEZE.** Package 2 is
not complete. Package 1 has a conditional bootstrap component selection,
not a qualified startup supply. General harness development remains frozen.

This supersedes the selection at checkpoint `3eecc61de`. Its exact prior text
and unapplied patch are preserved in `../../evidence/protection-review-04/prior/`.
Old ledgers/receipts describe historical inputs, not acceptance of this revision.
Native construction, numerical screening and hardware qualification remain
separate. No powered test or protection qualification has occurred.

## 1. Circuit and states

F2 separates `BOOST_DIODE_POSITIVE` from the bulk bank. Feedback remains
diode-side. U40 is a candidate 1.5 uF film capacitor, not an accepted means
of limiting the opening transient. Its nominal energy at 400 V is 0.120 J.

The authored construction has an independent divider, LM393ADR comparator,
LM4040 5 V reference, CD4013BM permission latch, CD40106BM startup logic,
and two parallel VSENSE inhibit FETs. The nominal independent trip is
**505 V** (5 V reference, 1 Mohm/10 kohm divider). Threshold corners must
include reference, comparator offset/bias and resistor tolerances; no 500 V
model margin transfers without recalculation.

The latch stores run permission:

- D1 high, SET1 low, CLOCK1 driven by delayed startup-ready.
- Persistent comparator fault asynchronously drives RESET1; QN1 drives
  q_inhibit2. A fault already present at ready inhibits. Clearing that fault
  does not create a new arming edge.
- Separate q_startup pulls VSENSE low while startup-ready is false, covering
  either initial flip-flop state in the modeled logic sequence.
- CD4013 second-half pin map corrected: SET2=8, D2=9, RESET2=10.

`../../experiments/f2-open/protection_logic.rs` tests these sequences and
explicit authored connections. It is not a transistor or rail simulation.
The RC ready circuit does not establish minimum ready delay, reset-recovery
margin, behavior below logic operating voltage or full-power-cycle-only reset.
Rail ramps, partial dropouts, comparator/reference startup, simultaneous
clock/reset transitions and gate charging remain QR-DET work. The existing
external HOT_PERMIT contract is still required, not supplied by this latch.

## 2. Removed clamp and withdrawn guarantees

**TVR14561 is rejected and removed from the authored circuit.** The retained
table gives 450 V continuous DC, V1mA 504–616 V and maximum clamp 930 V at
50 A. These are different quantities; they do not establish 600 V clamping
at the required current. No replacement footprint/MPN is selected merely to
make the board routable. Old generated artifacts with that MOV are historical.

The clamp target remains an engineering question. The old 250 mJ/30 A
criteria came from an unclamped screen, not a validated clamp duty envelope.
A clamp changes current, time and energy and must be modeled with the detector
and controller, using its actual V-I curve and pulse conditions.

The **one event per F2-open** claim is withdrawn. A controller OVP event
below the independent detector threshold does not set the external latch.
A clamp may also prevent that threshold from being reached. No non-repetitive
rating may be justified by the mere presence of a latch. Repeated bursts and
partial-AUX reset must be evaluated explicitly.

## 3. Complete timing budget

Required endpoint: actual U9 turn-off, starting when the power node crosses
the applicable detector threshold. The independent path includes:

1. Divider/filter and comparator propagation.
2. Fault logic propagation.
3. q_inhibit2 gate charging (currently 100k/100k, not instantaneous).
4. VSENSE discharge to the OLP threshold.
5. UCC28180 standby detection/internal propagation.
6. Power gate discharge and U9 current cessation.

Missing segments remain null. VSENSE low alone cannot close this budget.
The former <=5 us trip-to-VSENSE requirement and interpolated ~14 us allowance
are not a demonstrated end-to-end response.

The controller OVP path has different thresholds and delay. The retained
576–617 V screen used controller OVP; it does not qualify the independent
505 V path, combined circuit, startup or clamp. The known 1.5 uF/510 V/10 us
screen already exceeds the illustrative 630 V ceiling. Component ratings
are stress limits, not operating margins.

## 4. Startup calculation corrected

At 424.68 V, 1.5 uF stores **135.2648268 mJ**, not 42.4 mJ (the old 470 nF
value). This is capacitor inventory, not source energy or time-to-trip.

The former <=5-cycle claim divided energy by a maximum assumed per-cycle
transfer. Even a valid maximum gives a minimum cycle count under its
assumptions, never a maximum. The per-cycle envelope itself was unestablished,
so no cycle bound is retained. The 545 V startup bound used an unestablished
residual current and is withdrawn too.

Corrected outputs leave startup current at detection, time-to-trip and peak
bound null. Ideal divider decay is not a restart period: it omits source
recharge, other loads and controller state. Historical `raw/startup-bursts.csv`
is superseded; corrected results are in `../../evidence/protection-review-04/`.

## 5. Fault scope and remaining acceptance work

| Scenario | Supported statement | Open requirement |
|---|---|---|
| F2 open, U9 healthy | Corrected permission logic commands standby on detected OV | Actual startup, complete delay, first peak, repeated bursts, energy handling |
| U9 short, U10 intact | U10 blocks bank reverse path; line-fed loop includes F1 | F1 clearing/bridge survival; no gate credit |
| U10 short, U9 healthy | Bank discharge may flow while U9 is on | Separate detection/turn-off: do not credit an OV detector for a collapsing bus |
| U9 and U10 short | Internal loop includes candidate F2, bypasses F1/U12 | Clearing, let-through, withstand/enclosure; no gate credit |

Before Package 3 routing: QR-DET must establish complete timing and analog
startup/reset; QR-CLAMP must select supported energy handling or demonstrate
an alternative; QR-CAP must bind effective capacitance/pulse ratings. Then
simulate those exact selections together over startup, line/PWM phases and
restart, with energy balance, timestep refinement and an independent comparison.

QR-F1/F2A/F2B coordination, QR-DIV ratings, QR-BANK status/discharge,
QR-SURGE and installed thermal/physical qualification remain open. CAD/ERC
completion closes none of them. No general validator is added or protection
status promoted by this correction.
