# Passive power-entry working baseline

**Milestone NOT MET.** This is the retained routed passive board and a reviewed
protection/cooling checkpoint. It is not a new protected or thermally qualified
PCB. F2, its external holder, and the larger film reservoir are **not installed
in this CAD or BOM**. Active-bridge construction remains paused.

The user-directed objective and completion criteria are in [MILESTONE.md](MILESTONE.md).

## What is concrete

- The separate authored entry is
  `elec/src/power_entry_passive_reva.ato:PowerEntryPassiveReva`. Its Atopile
  0.2.69 compile/export is retained in [source-build-01](source-build-01/).
- [candidate/section.kicad_pcb](candidate/section.kicad_pcb) is the routed
  54-component, 230 × 210 mm, two-copper-layer GBJ2510-F baseline. Its SHA-256
  is `34e6fba9e6d323d795bba5bfe7ddfbcb5d158630cd2eb8cf95253b8e0263b2b9`,
  identical to `../shunt-repair/candidate/section.kicad_pcb`. This work changes
  no copper and installs no protection components.
- [Native verification](native-01/README.md) retains fresh KiCad 10.0.4 ERC
  and DRC reports and an invocation with `--schematic-parity`. The reports
  contain zero reported ERC/DRC violations and zero unconnected pads. Their
  existing ignored-check lists remain visible; zero findings is not a claim
  that every possible KiCad check was enabled.
- The existing Rust `Circuit::parse` / `bind_native` check binds the compiled
  source pin graph to retained native evidence. The scoped integration test
  also checks that evidence's complete PCB text against the candidate bytes.
  No new validation rule or comparator was introduced.
- [Protection](protection/DISPOSITION.md) now names the Mersen A70QS50-14F
  candidate and a sourced US141/Z331153 DIN-rail holder. Its UL DC rating,
  general rating and installation limits are kept distinct. The holder does
  not establish that the fuse will clear this bank discharge.
- [Cooling](cooling/thermal-budget.json) is bound to the actual GBJ model and
  exact catalog sources. With the retained forced-flow assumptions, a 60 °C
  sink at 40 °C inlet supports about 112.63 W of total modeled heat. The
  existing 110.6 W allowance nearly consumes it. Neither is a measured limit.

## What the calculations changed

The retained STW switch-plus-gate model gives 112.9–157.4 W at its assumed
9–11 V gate points at 120 V line. This is an unqualified sensitivity, not a
measured loss or a worst-case bound. Nevertheless, it prevents accepting the
old 65 W other-PFC allowance as established. Adding the 40 W bridge and 5.6 W
fan allowances gives 158.5–203.0 W before the remaining losses; the same
cooling formula then gives approximately 68.1–76.1 °C at the sink. The retained
bridge FEM results prescribe a 60 °C sink and cannot be promoted to predictions
for that hotter assembly without resolving the actual loss and boundaries.

The [film-reservoir screen](protection/FILM-RESERVOIR-SCREEN.md) shows why a
larger diode-side capacitor deserves one bounded design evaluation: at the
stated 424.68 V / 40 A immediate-switch-off example, 22 µF gives about 449.2 V.
This example does not establish detection, turn-off latency, restart, capacitor
tolerance/pulse rating, or failed-short protection. It also adds 2.75 J at
500 V outside the bulk-bank fuse. It is a design lead, not an accepted ECO.

## Minimum remaining path

1. **Close the actual drive/loss basis.** Establish the STW gate-drive operating
   point and switching loss on the retained circuit, or obtain independent
   exact-circuit evidence that resolves the model discrepancy. Retain the
   whole-assembly loss terms; do not substitute a different MOSFET's result.
2. **Finish one passive protection ECO.** Define the F2 holder/interconnect,
   diode-side feedback and post-opening energy response together. Evaluate the
   larger film reservoir against a real controller timing/restart model before
   selecting it. Coordinate F1 and F2 against their different fault paths using
   applicable clearing and withstand evidence. Drawing a candidate is allowed
   before qualification; calling it protected is not.
3. **Bind the mechanical assembly and qualify it.** Select the actual mounting,
   interface and duct; establish installed flow, temperatures and fault
   response. The [qualification protocol](cooling/qualification-protocol.md)
   specifies the evidence to retain. Hardware qualification is NOT PERFORMED.

These are engineering/physical-evidence dependencies, not requests for another
generic harness campaign. The general harness remains frozen. The existing
passive section is the integration reference while this work continues; it is
not released for powered use by this checkpoint.

## Reproduction boundary

`tools/build_source.py` delegates to the existing source exporter. Its receipt
retains the exporter's historical `zapote.current-sense.*` schema name and
whole-source inventory; the explicit `entry`, not that schema label, identifies
this unit. `tools/build_native.py` is the existing generic native projector;
its initial staging board is not a reroute of the retained candidate. See
[native-01/README.md](native-01/README.md) for the explicit routed-board copy.

The common runner continues to use the maintained `shunt-repair/units.json`
manifest. Its power-entry board is byte-identical to this candidate. The new
entry name is checked by the scoped Rust binding test, not silently substituted
into the maintained runner's source-entry contract.

Run from the repository root:

```sh
cargo test --locked --offline --manifest-path zapote/Cargo.toml -p zapote-erc --test passive_reva
rustc --edition=2021 --test zapote/power-entry/passive-reva/cooling/budget_calc.rs -o /tmp/passive-cooling-tests
/tmp/passive-cooling-tests
rustc --edition=2021 --test zapote/power-entry/passive-reva/protection/film_reservoir_screen.rs -o /tmp/passive-film-tests
/tmp/passive-film-tests
```

See [validation](validation/README.md) for exact common-suite commands, outcomes,
aborted attempts and source-hash verification.
