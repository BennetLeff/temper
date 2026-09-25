# Revision 12: command-protocol counterexamples and AUX budget

Two Luna assignments produced a proposed two-wire start protocol and a refined
AUX cutoff budget. The parent implemented the protocol as an executable Rust
model and found a single-wire false-start counterexample. A third Luna review
confirmed the model and counterexample. **The proposed protocol is rejected;
no replacement command circuit was adopted.** The compiled candidate remains
revision 11 with 136 instances.

## Command result

My earlier proposed one-bit fix—observe ARM low before accepting a new high—
does not distinguish an intentional low from an open wire's pulldown. The
two worlds in `one_bit_indistinguishability.tsv` deliver identical observations
to the receiver. This is an observation-level proof, not an analog simulation.

Luna proposed two command wires, A/B, carried over the fourth available forward
isolator channel:

| Received code | Intended meaning |
|---|---|
| 01 | Idle; qualify READY while health/PERMIT are valid |
| 11 | PREPARE, accepted only after READY |
| 10 | START, accepted only after PREPARE |
| 00 | Invalid; reset the receiver |

Health/PERMIT loss resets the receiver. The logical model uses two healthy idle
samples for qualification and a bounded PREPARE hold. Sample durations are
abstract; no physical clock, debounce or isolator timing is claimed.

The parent counterexample is shorter than the initial worker's reconnect
caveat:

1. The producer sends valid 01 long enough to qualify READY.
2. It sends 11, entering PREPARE.
3. The producer **remains at 11**, but the B conductor opens and is read low.
4. The receiver sees 10 and starts RUN, although START was never transmitted.

See [b_open_during_prepare.tsv](b_open_during_prepare.tsv). Qualification delay
does not remove this ambiguity: the valid idle and prepare stages can be held
for any required duration before the wire opens. A minimum prepare dwell can
move the failure later but cannot distinguish the final wire fault from START.

| Executable witness | Observed result |
|---|---|
| One-bit low-first qualifier | Accepts the intentional and reconnect histories alike; reject |
| Two-bit valid sequence | Starts; positive control |
| Two-bit B opens during PREPARE | Starts without transmitted START; reject |
| Held 10 reconnects after reset | Does not start; the specific older case is blocked |
| Held 11 returns after reset | Does not start; static-state control |

The last two controls do not erase the new counterexample. This is why checking
only revision 11's one known failing case would have accepted an inadequate
replacement. The model assumes an open asserted conductor eventually becomes
a clean low; it does not establish analog thresholds, cable timing, metastability
or silicon behavior. The protocol-level failure is sufficient to reject this
proposal before schematic implementation.

The next command candidate needs explicit source/receiver confirmation and
reset/timeout semantics, with the single-wire fault scope stated first. It must
be checked for faults in every intermediate state, including partial commands.
This result does not prove all two-wire or unidirectional protocols impossible,
nor does it establish that a particular acknowledgement scheme is safe.

## AUX result

[aux-budget.md](aux-budget.md) extends the prior divider screen with input
leakage. The conditional static trip interval is about **16.066–17.485 V**.
The 120 kΩ current-limit setting is inadequate for the existing conditional
load budget. Output peak voltage remains unbounded by the available timing and
fault-waveform evidence. The old LDO output capacitor cannot automatically be
credited as downstream capacitance after inserting the cutoff.

## Reproduction and ownership

From this directory:

```sh
rustc --edition=2021 protocol_witness.rs -o protocol_witness
./protocol_witness > results.csv
rustc --edition=2021 aux_budget.rs -o aux_budget
./aux_budget > aux-budget.csv
```

The protocol program exits zero when the expected behaviors—including the
unsafe false start—are reproduced. Zero is successful reproduction, **not** a
passing circuit. Sources, CSVs and state traces are retained here.

Luna agents `gate_restart` and `supply_interfaces` owned read-only proposals;
`pfc_stage` independently reviewed the parent's logical witness. The parent
owns both Rust programs and final interpretation. All children were interrupted
after handback. Requested model: gpt-5.6-luna; served model not independently
attested. No circuit/PCB edits, full-converter simulation, hardware test,
vendor contact, commit or push occurred. Prior frozen inputs are preserved.
