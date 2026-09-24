# R6 integration readiness receipt

Implementation base: `a599fd27fe67f82afa4ee64f9fa7d2bc0fd6c19f`; coordinator replay includes the later programming/UI candidate at `ab49fd5c3`. Scope: read-only source/native integration screen. No integrated PCB, full-board DRC, firmware, hardware, or physical test was changed or run.

Run from repository root:

```sh
rustfmt --check zapote/integration/check.rs
rustc --edition=2021 --test -D warnings zapote/integration/check.rs -o /tmp/zapote-integration-tests
/tmp/zapote-integration-tests
rustc --edition=2021 -D warnings zapote/integration/check.rs -o /tmp/zapote-integration-check
/tmp/zapote-integration-check .
```

The last command is expected to exit **2**. Its saved output is `matrix.tsv`: 39 required unit/edge/fault rows, 19 BLOCKED and 20 INDETERMINATE; overall BLOCKED. The test executable passes six tests. The source lock covers 31 byte-identical inputs. The checker reads and hashes each of them, verifies exact Atopile pin/net statements for source-bearing ports, and extracts numbered connector pad/net assignments from the saved native KiCad boards. `shasum` is the local SHA-256 tool; no cached generated receipt is treated as live native identity. The separate `units.tsv` ledger retains digital-construction, candidate and unbound statuses; the prior buck/MCU acceptance sources are not bound in this snapshot.

Decisive blockers: legacy J1.1 accepts only 0–250 V positive half-bus and J1.2 is also its host common return; a direct Rev38 VB/HOT0 hookup would expose the wrong envelope and return. The legacy OVP_FAULT therefore cannot be wired straight into SELV interlock J1.3. HOT0/SELV is forbidden as a direct join. Rev38 HOT RUN cannot drive the isolated gate-drive PERMIT. No global `SENSOR_LIVE` producer or qualified path from every fault to both stage stops exists. Fan-off mounted discharge heat, true F2 continuity, programming-reset stop, and service/restart behavior remain unproved. The gate-drive HV_RETURN/HOT0 Kelvin join, CTRL_GND/SELV policy, isolated bias and return currents remain indeterminate. The current Rev38 source has no accepted native cross-unit endpoint; the auxiliary, discharge, inverter, cooling and programming/UI units have not closed their standalone and joined physical obligations.

For every RTD, current, voltage, thermal-heatsink, thermal-coil, cooling and AUX contributor, `faults.tsv` records the interlock input and separate open-wire, unpowered, global-validity, PFC-inhibit, inverter-inhibit and timing states. The native interlock fault pullups account for a broken conductor under their stated leakage budget; they do **not** prove an unpowered remote output cannot clamp the input low. Cooling shares the heatsink fault input but adds independent blocked-flow/validity obligations. No fault row is accepted on a handwritten `PROVEN` token alone.

The separate programming/UI checker at coordinator commit `ab49fd5c3` is now bound through its source-locked receipt, pin ledger and README. The `programming.ui` port is a logical candidate without a native service connector; the service-reset edge remains blocked by unresolved pin ownership and unmeasured stop behavior. Its source identity does not confer accepted native identity.

Current result permits interface redesign and evidence capture only. It does not authorize a source/native integrated board, fabrication release, or energization.
`READY_FOR_DESIGN` is deliberately unreachable from the current evidence classes: no row says an integrated contract is accepted, and the tool cannot promote self-authored table fields into that status. Promotion needs a follow-on reviewed gate revision binding newly accepted native unit sources, an adopted 390 V sensing interface, selected rails/returns, and independently replayed joined-stop/fault evidence.
