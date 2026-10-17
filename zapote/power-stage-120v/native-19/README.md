# Native19 engineering candidate

**142 components, 89 nets; native DRC/ERC checks pass, product qualification open.**
This is the routed HOT5 and Kelvin correction candidate derived from ps-oracle
`fda5ab9ece24ef1ee6f2317604c5ca73367d5201` native18. The authoritative saved board
SHA256 is recorded in [verification/final-manifest.json](verification/final-manifest.json).
Do not regenerate it with the older native generator, which replaces routing.

Changes implemented:

- U8 is the six-pin SN74LVC1G10DBVR, correctly mapped and routed. U14/U15,
  R48–R50 and C48/C49 implement the independently powered HOT5 monitor.
- R5 is corrected to **WSK25121L000FEA**, using the T2.21mm footprint for the
  1 mΩ resistance range. **T is terminal length, not body height.**
  Vishay identifies current terminals I1/I2 and sense terminals E1/E2;
  KiCad uses pads 1/4 and 2/3 respectively.
- R5.1, bridge/driver returns, PS2.3 and C24.2 use LEG_RET. R5.2 and the
  30 specified analog/control return pads use OCP_KELVIN_P. R5.3 is
  OCP_KELVIN_N; R5.4 is HV_RET. The device supplies its internal same-end
  connection; there is no copper bridge or manufactured net-tie exception.
  The loaded analog return still needs a finite-impedance error budget.
- Both 49.9 kΩ precision dead-time parts and trip-setting resistors are retained.
  Five power-device origins, the 240 × 160 mm outline and saved stackup are retained.
- The schematic has real pin functions/electrical types, unique deterministic
  object IDs and matching PCB instance paths. Bootstrap, external-controller
  and internal-shunt return assertions are explicit and source-checked.
- Existing pads identify 19 candidate test signals. No mounting holes
  or new testpoint parts were added.

## Evidence

Three final native DRC runs have **zero errors, zero opens and zero schematic
parity findings**. All three retain the same 36 library-mismatch and three
L1/J3 silk warnings. Independent baseline comparison found exact pad-geometry
agreement for all 36 library mismatches; 22 also have changed model paths.
This is not a full library/manufacturer geometry equivalence proof or waiver.

Typed ERC has **zero errors**, with 13 singleton-label warnings and three
GND1 naming warnings (U4.4, U9.1, U9.7 intentionally reference the HOT Kelvin
return). None were hidden or retyped as generic bidirectional pins.

The compiled-source audit passes **62 tests**, including wrong shunt footprint,
Kelvin short, gate-supply recharge on the sense terminal, and analog-return
membership mutations. [Component identity](verification/component-identity.json)
checks MPN, footprint, source instance and full schematic path for all 142 parts;
the build also checks every pad net and retained copper identity.

[Retention screening](verification/edge-contact-screen.json) passes both outer
copper layers for the four 3 × 6 mm shoes and the two corner stop strips. This
is nominal geometry with zero extra margin; insulation, tolerances and loads
remain unqualified. [Probe access](verification/probe-access.json) records mask
layer membership, candidate toe/annulus coordinates, body-envelope screening,
reference nets, tip spacing and the first-unit service state. These are candidate
points only: full copper/tip containment and actual mask-aperture containment
are NOT_CHECKED. Fixture fit and probe ratings are not physically verified.

[Model inventory](verification/model-inventory.json) resolves 142/142 component
models. **24 are authored provisional envelopes.** The installed library lacks
the selected shunt STEP, so R5 uses the existing authored 6.35 × 3.18 × 0.635 mm
nominal body envelope, renamed to its correct MPN. No missing body is silently
omitted. The populated STEP is a local engineering output, not a fabrication
release or the integrated enclosure assembly.

Both leg regions are **CHANGED** under the existing FEM region comparator;
stackup and FET geometry flags are unchanged. Native18 electrical simulations
remain evidence for native18. Re-extract native19 before inheriting those
results. The loaded Kelvin return also needs an analog error bound: a 1 mV
positive reference shift corresponds to approximately 1 A at a 1 mΩ shunt.

## Reproduce

[Ordered commands](verification/reproduction-commands.json) identify the exact
compiler, adapter, DRC/ERC and export operations. `../prototype-closure/pcb/`
contains the authored ECO JSON and thin KiCad adapters. `frozen/` is byte-equal
to the top-level compiled source exports; no netlist was hand-edited.

Pass the native18 board to `build_candidate.py`; it rejects any other baseline
hash. `build_schematic.py` uses the compiled frozen netlist. Run DRC with this
project's `.kicad_pro`, `.kicad_dru`, library tables and local libraries present,
with all-track-errors, schematic parity and zone refill. Save the first final
refill, then compare violation sets on repeat runs. Model-only path changes do
not alter copper. KiCad's unsaved net-code order is nondeterministic; the
adapter canonicalizes complete track/via forms after assigning stable UUIDs.

## Remaining release gates

- Native19 switching/parasitic extraction and protection-delay/fault-survival
  validation; HOT5 logic timing and the accepted operating envelope remain open.
- Loaded Kelvin reference error, shunt pulse/thermal rating, startup and
  supply-loss behavior; the 1 W shunt selection is not a demonstrated fault rating.
- D22 filter plus upstream fuse/disconnect coordination, installed EMI,
  leakage/earthing and insulation qualification.
- Final cooling/enclosure interface, tolerances, retention materials/loads,
  exact component models and assembly/service access.
- Supplier stackup/process/assembly review and staged physical first-unit tests.

No assembled hardware or physical measurements exist for this candidate.
Primary shunt sources: [Vishay drawing](https://www.vishay.com/docs/30108/wsk2512.pdf)
and [part listing](https://www.vishay.com/en/product/30108/tab/quality/).
