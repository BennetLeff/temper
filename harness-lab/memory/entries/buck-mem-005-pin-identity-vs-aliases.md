# buck-mem-005 — Verify raw pin/part identity independently of aliases

- **Claim / procedure:** When importing source connectivity (netlist →
  downstream artifact), verify raw `(ref, pin)` identity independently
  of pin aliases, symbol pin names, or display ordering. Known trap:
  KiCad numbers symbol pins bottom-to-top regardless of the `number`
  attribute, so a label placed for source "pin 1" lands on KiCad's
  "pin 2" without Y-index compensation — on both left and right sides.
  Verify with a connectivity-partition oracle comparing `(ref, pin)`
  groups (ignoring net names) between source and generated output.
- **Applicability:**
  source-import guidance; transfers as a procedure, but its exact
  check must be re-verified against P1's current bridge before MCU use.
  Required capabilities: source import, pin-identity verification
  against the current bridge (`harness-lab/circuit_native.py`, pinned
  atopile `0.2.69`, `BuckCircuitCandidate` from `elec/src` with
  `resolved-components.json` export — read 2026-09-10; P1-owned, not
  modified by this entry). A bare `grep` found no alias-handling code in
  the bridge yet, so the oracle pattern from the evidence doc is the
  standing procedure until P1's bridge is checked. No buck part/pin
  values transfer (R3: exact facts only on matching source identity).
- **Evidence:**
  `docs/solutions/tooling-decisions/generated-schematics-from-atopile-netlist-2026-07-15.md`
  (`sha256:15231830…e2e0090`) — §3 pin-numbering gotcha with compensation
  code, §4 connectivity-partition oracle, Temper result (346 pins,
  73 nets isomorphic).
- **Provenance class:** expert-curated (manual curation 2026-09-10; not
  automatic learning — the full-buck pilot has not run).
- **Validation state:** source-reviewed against the evidence doc;
  bridge cross-check outstanding (recorded above, not assumed).
