# Review-only integrated control source

Entry: `elec/src/power_entry_pfc_control_candidate.ato:PowerEntryPfcControlCandidate`.
The pinned Atopile 0.2.69 build and resolved-component export completed.
This is a compiled source experiment, not a PCB, schematic layout, complete
power stage or qualified protection design.

## Deliberate changes

- Reuse the previously compiled BAV23C clamp candidate: pin 1/A to HOT ground,
  pin 3/K to controller ISENSE after 220 Ω; pin 2 is unconnected.
- Split diode-side `local_vd` from bank-side `hv_plus`. Move regulation
  feedback to `local_vd`, consistent with revision 08's isolated OVP test.
- Instantiate the unchanged 79-component `PowerEntryF2ShutdownRevB` module.
  Its two voltage detectors observe the separate VD/VB nodes.
- Feed the module PWM input from the controller GATE pin; drive the MOSFET
  gate through the module's split driver outputs. Remove the two redundant
  baseline gate resistor/pulldown instances.
- Drive the retained two-FET standby release from local `enable_good`.
  External HOT permit now qualifies the latch; it cannot directly release
  standby. HOT ARM is a separate fresh-edge input.

## Count and external boundaries

The exported graph contains **131 component instances: 54 + 79 − 2**.
This does not solve the earlier complexity concern. It exposes the actual
cost of integrating the currently tested blocks, and is retained for review
before selecting a simpler implementation.

The source has no installed F2, local film reservoir, its discharge network,
new ARM/5 V headers, HOT 5 V or AUX_15V supply producers, or isolated
ARM/PERMIT and relay-control producers.
Those remain named external requirements. `local_vd` and `hv_plus` intentionally
are not shorted together. A real external F2 assembly would connect them;
the local reservoir belongs between `local_vd` and HOT ground.

Do not compare this count to a complete assembled appliance, or use this graph
as proof that the power-stage SPICE and physical circuit are identical. The
SPICE includes an ideal F2 and modeled local capacitance that are not installed
here. Supply, semiconductor and clamp models remain conditional.

## Build record

The first launch could not access the default tool cache, and the permitted
offline attempt found no cached compiler. A new temporary cache installed the
pinned compiler. The first actual compilation exposed an Atopile declaration-
ordering error; `attempt-ordering.ato.txt` and its failed receipt preserve it.
Moving two connections below their component declarations corrected that error.
`build-final-receipt.json` records the successful offline build and
`export-receipt.json` records the resolved export. No installed board or prior
experiment was changed.

Reproduction uses `UV_CACHE_DIR=/private/tmp/temper09-uv-cache` and
`UV_TOOL_DIR=/private/tmp/temper09-uv-tools`, the command guard, and the exact
commands in those receipts. A fresh run must use a new receipt/output directory.
The final parent record binds source, export, checker and earlier evidence.

## Export limitation

Atopile shares library MPN/pin descriptions by footprint. This netlist is used
for selected connectivity checks only; its library metadata is not suitable
for manufacturing. See [the diagnosis](../export-metadata-limit.md).
