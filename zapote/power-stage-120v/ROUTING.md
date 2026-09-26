# Four-layer routing — native-06

Status: all five routing batches are integrated and checked for prototype review. The owner approved a 240 × 160 mm
outline and four layers on 2026-09-26. Revised placement D4 is still required.
This is a prototype review artifact, not a fabrication or powered-operation release.

`native-05` is the source-generated placement. `native-06/section.kicad_pcb` is
the current routed board. All copper comes from explicit paths in `tools/routes.py`
and `tools/routes_aux.py`, serialized under `routes/` and replayed through KiCad.
There is no path-search autorouter. Replay rejects stale poses, outline, stackup,
frozen-source receipt, incorrect enabled layers, and an already-routed input.

## Copper arrangement

- In2.Cu carries BUS_P beneath the MOSFETs and local capacitors.
- In1.Cu carries HV_RET and a separate LEG_RET power region. The current path
  passes through R5 pads 1 and 4. The control returns use Kelvin pad 2; the
  opposing shunt sense uses pad 3.
- F.Cu and B.Cu carry the switch-node/tank pours, mains routes and local signals.
- The controller island has separate supply and return copper. HOT copper stays
  outside the provisional 8 mm barrier on every layer, including buried layers.
- Each gate output has a nearby source return. Leg A's high-side output now has
  an explicit F.Cu SW_A return beside it rather than relying on a remote pour.

### Shunt Kelvin connection

R5 is a four-terminal Vishay WSK2512. The source assigns its current pad 1
and sense pad 2 to LEG_RET, but their PCB copper stays separate: the resistor
provides their internal connection. Vishay's [electrical connection drawing,
page 3](https://www.vishay.com/docs/30108/wsk2512.pdf) identifies distinct current
and voltage-sense terminals. The opposite sense pad 3 is OCP_KELVIN_N; current
pad 4 is HV_RET.

KiCad consequently reports an unconnected LEG_RET item between the pad-2
control branch and pad 1. Do not clear it by bridging the pads on the board:
that would bypass the intended Kelvin pickup. This raw DRC finding remains
visible in the review packet and needs a narrowly documented disposition;
it is not permission to ignore other LEG_RET opens or power-pour splits.

The proposed 1.6 mm stackup uses 70 µm copper on all four layers, a 0.2 mm core,
two 0.55 mm dielectric layers, and 0.01 mm masks. Fabricator acceptance and
finished minimum copper/plating remain open; the owner's layer-count decision
is not a manufacturing tolerance specification.

## Current-capacity screen

The earlier 35 µm HV_RET inner plane had a roughly 5.9 mm neck. The repository's
IPC-2221 screening equation (`temper-geometry/src/trace_width_assignment.rs`),
using the inner-layer coefficient and a 20 °C rise, gives approximately 5.9 A
for that cross-section; it cannot justify the intended power current.

The revised return uses 70 µm inner copper. Auxiliary routing exposed two
additional constraints: signal clearances can disconnect filled planes, and a
connected plane can still have an undersized neck. The north Kelvin pair stays
together; the auxiliary return fence moves to B.Cu so HV_RET can pass it.
A 5.0 mm F.Cu HV_RET track and two banks of three 1.6/0.8 mm vias bypass the
remaining narrow inner section near D2. The nominal outer-track screen is
17.15 A at 20 °C rise. Finished via plating and current division remain
unqualified. BUS_P also has a stitched B.Cu path around the TVS pin.

The final filled-board power review records section widths and the assumptions
behind the current-sharing model. Adding disconnected strip widths, adding
ideal via ratings, or passing connectivity alone does not establish ampacity.

The 2.4 mm terminal escapes on paired outer/inner mains layers have a combined
nominal screen near 15 A only under ideal sharing. Terminal heating, copper
thickness and temperature rise require verification. This screen does not
establish continuous-current capability or switching overshoot.

## Spacing-rule correction

The former courtyard exemption is removed. It could exempt an entire long
track after only one part touched a courtyard, and the last-footprint parser
could assign unrelated routed nets to J5. Both are reproduced regressions.

The replacement permits only explicit component-local outward escapes, with
whole-object containment in a named F.Cu rule area and the exact two pad nets.
The permitted distance is the measured intrinsic pad gap, not a blanket
0.2 mm trace exception. Other nets retain their full board spacing. Geometry
is obtained from pcbnew and checked in Rust; altered areas or pad/net mappings
must fail before rules are written. This is a provisional layout convention;
it does not extend a component's insulation certification to PCB copper.

The source's 8 mm SELV/HOT and PE/HOT rules remain unconditional. Functional
HOT spacing is enforced as clearance because KiCad's creepage engine cannot
apply a footprint-local exception. See D5-BASIS.md for unresolved voltage,
frequency, package and laminate qualification.

## Saved-copper identity

KiCad can reassign unanchored tracks and vias to another net while saving a
board with overlapping copper. DRC can then appear clean because it sees the
reassigned nets. Each route receipt now records the requested net and UUID
before saving. `tools/check_copper_identity.py` reads the saved bytes through
the raw KiCad parser, then the Rust validator checks every authored track and
via against all five receipt batches and their source hashes. Run it after
zone filling and any operation that saves the board. A saved-via net mutation
must fail; source-to-pad parity alone cannot detect this failure.

Connectivity is independently grouped by connected **pad** UUIDs. A filled
zone UUID may contain several disconnected islands, so sharing a zone UUID
is not evidence that two pad groups connect.

## Final review evidence

The saved native-06 board has 560 tracks, 141 vias and 24 zones. Three full DRC
runs report no copper-spacing or schematic-match findings, one documented R5
internal connection, 28 library mismatches and three L1/J3 silkscreen overlaps.
Source/MPN/pad identity, saved-copper identity, stackup, pad-only connectivity,
all-layer barrier and both terminal-hardware configurations pass their stated
checks. The source audit passes 48 tests, board/tool tests 43, and the Rust
workspace 325. Exact hashes, commands and limits are in
[native-06/verification](native-06/verification/README.md).

The western BUS_P section has only about 6% nominal formula margin against
15 A. The local BUS_P sharing result and the upper two-via transfer bank remain
model-dependent. See the [filled-copper review](native-06/verification/power-review.md).
Finished copper, via plating and actual waveforms can change the disposition.

The terminal-envelope repair moves HOT5 below the surface near the negative
strap/bench lug and relocates the BUS_P stitching vias. It does not enlarge
an exemption or waive the hardware spacing floor.

Physical tests have not run: overshoot/clamp energy, protection timing and
brownout, CT injection, touch/leakage, hipot, thermal/current, and EMI. The
Coilcraft evidence, certification-lab review, RCA teardown, measured terminal
hardware, airflow and fabricator stackup remain separate qualification items.
