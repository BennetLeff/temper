# F2 shutdown circuit — U1 source handback

This directory records the U1 source and its connectivity contract. The
Atopile module is an isolated experiment and is not instantiated by the
production `Top` module. The source is
`elec/src/power_entry_f2_shutdown.ato:PowerEntryF2Shutdown`.

## Topology

Each HOT-referenced bus (`vd` and `vb`) feeds a 987 kOhm / 200 Ohm / 5.62 kOhm
tapped divider with a 100 pF high-node filter. The 2.5 V LM4040 reference feeds
the absolute-overvoltage channels. Two TLV3202 dual comparators provide four
independent push-pull health outputs:

* `cmp_vd` channel 1: `ref25 > vd_div.high` (VD absolute health).
* `cmp_vd` channel 2: `vd_div.high > vb_div.low` (one mismatch polarity).
* `cmp_vb` channel 1: `ref25 > vb_div.high` (VB absolute health).
* `cmp_vb` channel 2: `vb_div.high > vd_div.low` (the reverse mismatch).

The first SN74HCS21 4-input AND produces `health_ok`. Its second gate produces
`ready = health_ok & rails_ok & permit & logic5`. The SN74HCS74 uses `ready` as
both D and active-low asynchronous-clear release, with raw `arm` on CLK. Thus a
fault, permit loss or external `rails_ok` loss clears `run`; health/rail return
cannot create a clock edge while ARM is held high. A fresh ARM rising edge is
required after the clear.

`run` drives UCC27624 ENA. Its external 2.2 kOhm pulldown supplies a default-low
condition against the driver's internal EN pull-up. PWM drives INA, while INB
and ENB are explicitly tied low. OUTA drives the retained 10 Ohm gate resistor
and 10 kOhm gate-source pulldown. The 1 uF and 100 nF driver bypasses and local
100 nF logic bypasses are explicit.

## Exact package pin identities

The source pin declarations are transcribed from the retained official PDFs in
`f2-timing-02/sources/`:

| Part | Pins used |
| --- | --- |
| TLV3202 D/DGK | 1 OUT1, 2 IN1−, 3 IN1+, 4 GND, 5 IN2+, 6 IN2−, 7 OUT2, 8 VCC |
| SN74HCS21 D/PW | 1 1A, 2 1B, 3 NC, 4 1C, 5 1D, 6 1Y, 7 GND, 8 2Y, 9 2A, 10 2B, 11 NC, 12 2C, 13 2D, 14 VCC |
| SN74HCS74 D/PW | 1 1CLR, 2 1D, 3 1CLK, 4 1PRE, 5 1Q, 6 1Q̅, 7 GND, 8 2Q̅, 9 2Q, 10 2PRE, 11 2CLK, 12 2D, 13 2CLR, 14 VCC |
| UCC27624 D/DGN | 1 ENA, 2 INA, 3 GND, 4 INB, 5 OUTB, 6 VDD, 7 OUTA, 8 ENB |

The ERC test intentionally checks these physical pin numbers in the compiled
bridge, rather than only looking for strings in the authored source.

## Count and evidence boundary

The expected compiled source count is 32 physical components: 16 divider
resistors/capacitors, 2 comparators, reference and bias resistor, one HCS21,
one HCS74, one gate driver, three gate/enable resistors, and six supply bypass
capacitors. This is an estimate until the parent source-build adapter emits
`source-01/resolved-components.json` and `compiled-bridge.json`; the test binds
the final count and source hash to those artifacts.

No pre-change characterization or compiled shutdown graph existed in this
worktree before U1. An initial Atopile build could not be run here because the
requested `atopile==0.2.69` tool was not cached and network access was disabled;
this is an environment limitation, not compile evidence. The parent task owns
the source build and must preserve its receipt and exact graph.

## Unresolved interface limits

`logic5`, `aux`, and `rails_ok` are external interfaces. The circuit does not
implement the supply sequencer, isolation, precharge, or a guaranteed brownout
reset. `rails_ok` must remain low through supply return when ARM is held high.
The UCC27624 EN internal pull-up, comparator input protection, and divider
back-power paths have not been bounded across unpowered/partially powered
states. The source therefore does not claim rail-off safety or an end-to-end
2 us shutdown deadline. The transient simulation must model these limits or
retain them as indeterminate.

