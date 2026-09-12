# Independent validation of the PFC checks

The PFC findings must be assessed against a verified instrument before they
justify changing copper. This work checks the nominal model and its software
implementation; it does not qualify temperatures or the physical power supply.

The [final receipt](verification.json) records **320 passing Rust tests**, six
passing live SPICE solves, and fresh native ERC/DRC plus common binding passes
for all seven boards on clean source commit `7b89ff0b4`. The same
[five nominal PFC screening findings](pfc-findings.json) remain. No product PCB
bytes changed. The complete board runs and development evidence are archived
with member hashes; the review's evidence-binding finding is resolved.

## Independent references and failure cases

| Check | Independent reference | What it establishes |
|---|---|---|
| Full-line branch RMS | Closed-form integrals of powers of absolute sine at three operating points | Agreement without reusing production phase quadrature or samples |
| Switching physics | Six actual ngspice transient solves: three frozen line phases, two maximum timesteps | Inductor, switch, diode and bus-absorbed capacitor-current RMS agree with current Rust samples within 0.05%; timestep refinement within 0.01%; average, extrema and energy checked separately |
| Graph cut currents | Brute-force edge removal for every one of the 1,024 five-node simple graphs | Exact/cyclic classification and signed-injection RMS/peak behavior, including disconnected components; additional parallel-edge/subdivision fixture |
| Native pad/drill geometry | Fresh KiCad 10.0.4 extraction of the asymmetric 30-degree oval/slotted fixture | Copper, drill and trace values exactly match the pinned fixture; Rust tests distinguish drill void and over-wide entry |
| Full saved-board pipeline | Narrow then restore a real saved segment; split/reorder unchanged copper | Specific failure appears and clears with a determined adequate branch; geometric subdivision preserves findings and current |
| Capacity scalar | Published IPC-2221 external-layer formula and exact mil dimensions | Implementation and units agree with the specified scalar; no validation of actual board temperature |

The [KiCad calculator manual](https://docs.kicad.org/5.1/en/pcb_calculator/pcb_calculator.pdf)
documents the IPC-2221 equation used by this copied scalar: external-layer
coefficient 0.048, temperature exponent 0.44 and area exponent 0.725. This is
an older screening formula, not a claim that current native KiCad DRC provides
a thermal acceptance test or that the formula accounts for this board's planes,
pad heat sinking, airflow and temperature-dependent material properties.

## Defects exposed before fixes

1. **CCM validity depended on sample density.** A deliberately low-current
   case entered discontinuous conduction close to a line zero crossing, yet
   32 phase samples accepted it. The analytic minimum valley coefficient now
   rejects this case without relying on hitting the short interval in a sample.
2. **Copper segmentation changed the verdict.** Splitting an unchanged 6 mm
   trace caused two unrelated same-net findings to become indeterminate. The
   side-contact diagnostic now coalesces touching, collinear, equal-width spans
   before assessment. Original native UUIDs remain in the current graph.
   Different widths, layers, nets, real gaps and turns remain separate; real
   parallel side contacts remain indeterminate.
3. **Physical thickness was converted through approximate ounce constants.**
   The copied scalar was approximately 0.0041% low. Direct exact mil conversion
   fixes this. The original donor hash remains recorded in `ports.toml`.

## SPICE independence and limits

The [Rust live runner](../../../packages/zapote-erc/examples/verify_pfc_spice.rs)
constructs a voltage-source/inductor/switch/diode-path circuit and lets ngspice
integrate it. Rust waveform samples are never fed into circuit sources.
Independent closed-form math supplies a nominal inductor initial condition;
the simulator must recover slopes, branch currents and moments from that state.
Zero-volt sources measure branch currents. The stiff bus source absorbs the
diode-minus-load current represented as aggregate capacitor current in the
nominal model; it is not a finite-capacitance bus-ripple simulation.

Each accepted measurement window spans exactly ten PWM cycles. One-picosecond
edges and corrected pulse width avoid changing duty through finite edge time.
The retained [result](spice/result.json) and six decks/logs identify the exact
conditions. Rejected exploratory runs used startup currents, rounded duty or
non-integer windows; those are retained as development evidence, not acceptance.

The validation supports **ideal, initialized CCM switching physics** and the
closed-form full-line integration. It does not establish a real UCC28180 control
loop, saturation, device losses, EMI currents, fault/inrush behavior, local zone
current sharing, full pad minimum cuts or thermal ampacity. Those remain explicit
model gaps. Independent reference tests also do not prove every custom ERC/DRC
rule in Zapote; this receipt is scoped to the new PFC current/copper checks.

## Reproduce

Ordinary `cargo test --manifest-path zapote/Cargo.toml --locked --workspace`
includes closed-form, cut-graph, saved-board metamorphic and pinned-SPICE replay
tests. The replay compares fresh production samples with measured ngspice values,
parsed directly from retained raw logs, not with the saved Rust values alongside
them. A SHA-256 pin covers all six decks/logs, the summary and solver version.
Changing a retained inductor value by 1,000x originally left replay green;
the strengthened replay rejects that same mutation. Updating this pin requires
a reviewed new external run, never copying production outputs into the summary.

Run the external solver again on a host with ngspice:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check-pfc-oracle \
  NGSPICE=/opt/homebrew/bin/ngspice \
  ORACLE_RUN_DIR=/private/tmp/zapote-new-pfc-oracle
```

The output directory must be new. A missing solver, failed solve, missing
measurement or comparison outside tolerance fails the command. It never
overwrites the committed oracle evidence or product boards.
