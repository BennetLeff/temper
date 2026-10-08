# C2 dead-time loss comparison — reference-inductance screen

- Board: `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Frozen source revision: `829ee9debc08ce239bc2dffe0938c4fec2429545`.
- Tool: Miniforge Python/NumPy; C1 uses ngspice 45.2 and the pinned Infineon L1 model.
- Evidence class: **simulation/model-based**, reference inductances and 27 °C switching model; digitized typical datasheet curves for 25/125 °C forward diode and Eoss.
- Verdict: **conditional model comparison only; O6 remains open.** On the corrected commutation-dwell screen, 51 kΩ raises the matched-event subtotal in most cases at every modeled timing corner. Keep R9/R17 unchanged pending D1 board inductance, physical floating-dead-time and hot-loss qualification.

## Summary

Round-3 raw evidence independently verified `3327/3327 files verified`; the
simulation kit ends in `SMOKE PASS`. This run uses the **replacement frozen**
A grid after the withdrawn 42.00314 A crossing was corrected and checked at
12.5 ns. Its 270 accepted cases contain 190,336 full-bridge events across
42 and 40.45 A ceilings. The C1 catalog uses 1,226 nominal-L waveforms from
the frozen 2,118-row export; the finite-waveform and C1 charge cross-checks
passed. [Input hashes](outputs/loss-manifest.json) and the [1,226 raw-wave
hashes](outputs/waveform-raw-sha256.csv) make the calculation reproducible.

## Method and assumptions

One A switching-event row is one **full-bridge** drive sign change: one
physical leg executes C1 `DIR0`, the other `DIR1`. The event is counted once
per leg, with the same tank-current magnitude and each leg's own current
orientation. Unfavorable A current signs are excluded from the favorable
soft-commutation deck. The A deck has ideal drive with no floating dead
time; its `±500 ns` current samples and slope are diagnostic only.

The six C1 timing points are 39/51 kΩ × min/typ/max, pairing `DIR0` and
`DIR1` at the **same** driver-tolerance corner. They do not enumerate
independent U1/U2 mismatch, resistor tolerance or controller-inserted dead
time. TI's 50 kΩ characterized spread is transferred by an **assumed**
relative scaling to 39 and 51 kΩ. C1's
reference-L map covers 10–198 V. Below 10 V remains outside the map. At
10 V, use the separately named *signed positive-residual discharge*
diagnostic; it does **not** establish continuous diode clamp. The waveform
diode integral is independent of this threshold. The legacy absolute-5% metric can reject a forward-clamped
device because 5% of 10 V is only 0.5 V. No threshold interpolation blends
the 10 V signed criterion with the 30 V absolute criterion, or crosses
missing/nonmonotonic threshold rows. Intermediate bus voltages use endpoint
brackets as a model screen, never a guarantee.
The reported `hard_screen`/`zvs_screen` fractions diagnose **die-VDS before
the incoming gate command**. Residual Eoss is evaluated later, at the
gate-qualified channel-current onset. A precommand hard-screen event can
still have little residual Eoss after further commutation; those two fields
answer different timing questions and are not physical hard-switch counts.

For every normal C1 waveform, [the catalog builder](build_waveform_catalog.py)
uses **incoming body-diode current**, `-i(V_sense2)`, from the outgoing
command through actual gate-qualified channel-current onset. That is the
**commutation-dwell term used in the comparison**, integrated with typical
diagram-11 `Vf(I,T)·I dt` at 25 and 125 °C. The catalog separately integrates
the entire saved postcommand window as a **lower bound on diode heat**, because
forward diode current can remain after channel onset and even while the gate
is fully on. A finite-window current tail is flagged, but does not erase the
known commutation-dwell term. This term is not total third-quadrant conduction
loss; the gate-qualified onset is a model analysis surrogate. The outgoing diode's
last-20-ns forward history is recorded separately; external drain current
cannot stand in for either diode branch because it includes Coss/snubber
displacement. Right-censored **channel onsets** and waveforms with die VDS ≥650 V or
the C1 avalanche flag are excluded from normal interpolation. At currents
below the 0.1 A digitized Vf domain, the charge is retained as an explicit
unquantified tail, with a separate endpoint-Vf sensitivity for small tails.

[The loss join](deadtime_losses.py) combines C1's 27 °C **outgoing-device**
vendor dissipative energy with incoming-diode heat, typical diagram-15
`Eoss` at **residual die VDS at channel-current onset**, and a
`0.5 C Vdie²` sensitivity for the 1 nF incoming-device snubber. The snubber
is wired across the **external** drain/source terminals, while C1 saved die
VDS but not that external capacitor voltage; the sensitivity is explicitly
named `die_vds_proxy`, not a measured snubber dissipation. Eoss(0)=0 is
the stored-energy origin assumption documented with the curves. Using the
full bus voltage would overstate partially commutated events. Conversely,
channel-current onset is an analysis surrogate and may understate the first
overlap; the result is conditional. Terms outside the Eoss/Vf graph domain
remain missing, not zero.
In a separate 20-case exact C1 replay with external capacitor-voltage probes,
the die-VDS proxy differed by a median **0.00678 µJ** and at most **0.12264
µJ** in absolute stored-energy estimate. Relative error was large near zero
voltage; this selected-case check does not bound the full grid. The frozen
[snubber probe](../snubber-voltage-check/README.md) gives its case selection
and hashes.

For hard-classified events with outgoing diode forward current observed in
the saved precommand window, the script adds a **conditional** `Vbus·Qrr`
sensitivity using the Infineon Table 7 `2.30 µC typical / 4.60 µC maximum`
at **400 V, 58.2 A, 100 A/µs**. An all-hard-event maximum-test-charge
scenario is also shown. Neither is a guaranteed bound at this board's
current, voltage, di/dt or diode history: the single-transition C1 waveform
omits the preceding resonant half-cycle. The diode's reverse-recovery di/dt
is not measured here; A's ideal-drive tank-current slope cannot establish it.
No Qrr is assigned as an established physical loss from a missing history.
The recent-forward Qrr term is zero in
**every output row** because no hard-classified saved C1 case showed ≥0.1 A
outgoing forward-diode current in its short precommand window. That is
**not evidence of zero physical Qrr** after a
real preceding half-cycle. The 125 °C diode curve paired with a
27 °C MOSFET switching model is a hybrid sensitivity, not a complete hot
device calculation.

Every reported power is the sum of *both* leg event energies in one 60 Hz
line half-cycle, divided by `1/120 s`. The comparison uses an identical
matched event subset across all six timing corners. It records the missing
coverage separately so a smaller subtotal cannot appear to win by omitting
hard cases. C1 energy/current interpolation between sampled current and bus
points is a model assumption, especially across sharp threshold changes.
[The corner comparison](compare_corners.py) reports where the
51 kΩ screen is lower/higher under several Qrr and snubber assumptions.
Conduction loss, gate-drive loss, installed cooling, unquantified low-bus
events, and D1 board coupling are not included in the subtotal.

## Current-reversal screen

The A ideal-drive `+500 ns` current sign and local-slope zero estimate are
reported, but they do not answer what happens while both MOSFETs are off.
The script also solves a separate series-RLC trajectory from each A event
with ideal bridge drive held at each of `±(Vbus+1 V)` for the candidate dead
time. The 1 V is a typical-diode assumption and the rails omit overshoot;
cases that can reach zero under either ideal rail are flagged. A case that
does not reach zero in this bracket is still **not** a physical no-reversal
proof. A full floating-node commutation simulation or staged VGS/VDS/tank
current measurement is required before approving 51 kΩ.

## Results and sensitivity

The table compares **only events with both legs covered in all six timing
corners**, using the 27 °C reference-L turn-off model, typical 25 °C diode
curve, typical residual Eoss curve and the die-VDS snubber proxy. The median
delta is 51 kΩ minus installed 39 kΩ in watts per case, converted from the
matched event energies over one line half-cycle. A negative value favors 51
kΩ *on this subset only*.

| Current ceiling | Paired min timing | Paired typ timing | Paired max timing | Six-corner matched events |
|---|---|---|---|---|
| 40.45 A | 313.80→406.75 ns; **105/135 higher**; median +0.398 W | 348.40→451.60 ns; **110/135 higher**; median +0.225 W | 383.00→496.45 ns; **118/135 higher**; median +0.280 W | 73,152 / 95,444 (76.64%) |
| 42 A | 313.80→406.75 ns; **105/135 higher**; median +0.394 W | 348.40→451.60 ns; **110/135 higher**; median +0.235 W | 383.00→496.45 ns; **118/135 higher**; median +0.286 W | 72,997 / 94,892 (76.93%) |

All 270 cases have incomplete matched-event coverage. The worst per-case
matched fraction is **59.05%** at both ceilings. At the
42 A ceiling, typical timing, the known share of full-bridge events with at
least one hard-screened leg is 38.7% at 39 kΩ versus 11.5% at 51 kΩ. If all
unclassified events were hard, those shares could be 52.6% versus 24.3%.
The case table carries these known/possible fractions for all six corners;
they are C1 reference-map classifications, not hardware measurements. At the
39 kΩ typical corner, the uncovered leg reasons are mixed 10–30 V threshold
definitions (14,204 / 14,138 legs at 40.45 / 42 A), bus below 10 V
(6,926 / 6,894), and threshold brackets/interpolation (5,666 / 5,404).
Post-onset diode current persists to the saved end in 16,751 / 24,865
**covered** legs; their switching-commutation term is retained, while their
additional third-quadrant conduction remains a lower bound. [A representative
waveform](outputs/post-onset-diode-sharing.png) shows 5.54 A body-diode
forward current at the saved end with incoming die VGS at 9.93 V and model
channel current near 43 A. The outputs keep each reason and coverage fraction.
None of the A ideal-drive `+500 ns`, local-slope, or bounded ideal-rail RLC
screens finds a current reversal in the frozen event grid; those screens
cannot establish current persistence through a real floating dead time.

The 125 °C *diode-only* sensitivity and `Vbus·Qrr` test-point transfer are
separate columns in [the paired comparison](outputs/deadtime_comparison.csv).
The all-hard-event 4.60 µC scenario moves the comparison by watts and can
alter the modeled subtotal, but its charge is
specified at 400 V / 58.2 A / 100 A/µs and is **not** a bound here. Physical
Qrr and hot MOSFET turn-off losses remain unknown. The [case table](outputs/deadtime_losses.csv),
[comparison summary](outputs/comparison-summary.json), [hash manifest](outputs/loss-manifest.json),
and [waveform catalog](outputs/waveform_loss_catalog.csv) retain the complete
recomputable evidence.

An earlier local diagnostic required forward diode current to drop below
0.1 A by the saved waveform end. That wrongly treated fully-on third-quadrant
sharing as missing switching-dwell data, leaving only ~33% matched coverage
and producing the **withdrawn** 103/135 max-corner finding. Its files are
preserved under ignored `outputs/runs/superseded-full-saved-window-censor/`;
the table above uses the corrected, plan-defined commutation window.

## Open items and physical confirmation

Obtain D1's coupled board/gate/common-source inductance and rerun both legs.
The C1 reference result alone cannot decide O6. At bring-up, record both
legs' die-referenced VGS, VDS, switch node and tank current over low-bus,
light-load, nominal, cold and hot states. Measure actual driver output
timing and the controller's dead-time contribution. Use those waveforms and
the installed thermal path to close diode/recovery and total hot loss.

## Reproduce

From the repository root, restore the round-3 raw evidence and verify it,
then run the simulation-kit smoke test. After the A/C1 frozen handoffs are
available at their normal sibling paths, run:

```sh
UNIT=zapote/power-stage-120v
ROOT="$UNIT/validation-results"
C2="$ROOT/01-switching-parasitics/round4/c2-losses"
A="$ROOT/05-resonant-tank-envelope/round4/a-derated"
C1="$ROOT/01-switching-parasitics/round4/c1-zvs"
CURVES="$ROOT/round4-coordination"
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 "$C2/build_waveform_catalog.py" --c1-root "$C1" --curve-root "$CURVES" --output "$C2/outputs/waveform_loss_catalog.csv"
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 "$C2/deadtime_losses.py" --a-root "$A" --c1-root "$C1" --curve-root "$CURVES" --wave-catalog "$C2/outputs/waveform_loss_catalog.csv" --output-dir "$C2/outputs"
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 "$C2/compare_corners.py" --losses "$C2/outputs/deadtime_losses.csv" --output-dir "$C2/outputs"
```

**Master-plan status line:** 01 / round 4 C2 — reference-L conditional loss
screen complete on frozen A/C1 inputs; O6 remains open. The 51 kΩ candidate
raises the matched-event subtotal in **105/135 minimum, 110/135 typical and
118/135 maximum** timing cases at each current ceiling, with ~77% aggregate
matched coverage. This is a conditional reference-L subtotal, not a total
hot-loss verdict. Board L, physical diode history/recovery and floating-current
reversal remain unqualified; R9/R17 remain unchanged.

Post-review guards pin the C1 source-wave map before opening catalog output, pin the resulting catalog/manifest at the loss join, and require the exact frozen 810 case/corner pairs before comparison. Reprocessing all 1,226 waves and 190,336 events leaves the catalog, loss CSV and paired numerical outputs byte-identical. Only provenance manifests gain the explicit source-wave binding. Original scripts/manifests remain under ignored `outputs/runs/source-before-review/`.
