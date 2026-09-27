# 06 Controller interface: CT burden check (partial result)

- Board: `native-09/section.kicad_pcb`, copper identical to SHA-256
  `ccaa385921f686d6d08859cf4e81fb2e93014c434a935996a85257a1f3594112`; source `frozen/default.net`
- Date: 2026-09-26. Operator: Claude Opus 5.5
- Scope: check 5 of [task 06](../../validation-plan/06-controller-interface.md)
  (CT secondary) only. The other 15 pins are not yet checked.
- Evidence class:
  - netlist and connectivity facts: **exact structural**
  - voltages: **simulation/model-based**, first-order
- **Verdict: FAIL, escalate to the owner.** The tank CT secondary leaves this
  board with no burden anywhere in the design, on a SELV connector.

## Summary

- T1 (CST3015-100ED, 1:100) connects its secondary **only** to J4.13/J4.14:
  - `ct_s1`: T1.3 ↔ J4.13
  - `ct_s2`: T1.4 ↔ J4.14

  There's no burden, clamp or other part on either net on this board.
- The design intends the burden to be on the current-sense board
  (`README.md` J4 table: "The burden and OCP/phase comparators are on the
  current-sense board; retune its burden for the full-bridge peak";
  `elec/src/power_stage_120v.ato` header). **That board doesn't implement
  it.** `zapote/current-sense` is a standalone CT unit: its own CST3015 takes
  the *primary* current on J1 and has its own 1.50 Ω burden. It has no input for
  another CT's secondary, and it was designed for a different operating point
  (44–50 kHz, 45–55 A trip). A repo-wide search finds no other consumer of
  `CT_S1`/`CT_S2`.
- So whenever the tank runs without a burden across J4.13/14, T1's secondary
  is effectively open-circuit. That means the cable is unplugged, the
  receiving board is absent or unpowered, or its burden is open. A
  first-order estimate puts the resulting secondary voltage at roughly
  **120–350 V peak spikes** on SELV header pins. A 1 Ω burden limits it to
  **< 1 V**.

## Method

`scripts/ct_open_secondary.py` → `outputs/ct_open_secondary.json`.

Datasheet values for the CST3015-100ED are taken from
`docs/evidence/2026-08-13-tank-fault-sizing-inputs.md`, which records their
retrieval and hash:

| Value | Datasheet figure |
| --- | --- |
| Secondary inductance | 3.2 mH |
| Turns ratio | 1:100 |
| Volt-time product | 638 V·µs |
| Terminating resistance | 1.0 Ω |
| Secondary DCR | 1.5 Ω |

With the secondary open, the referred primary current (I_p/100) must flow as
magnetizing current. The voltage follows ω·L·I_s until the core reaches its
volt-time limit, then collapses; that happens every half-cycle in every case
here. The script reports the linear value and the value at the moment of
saturation.

| Case | Primary peak | f | Open: linear | Open: at saturation | Terminated 1 Ω |
| --- | --- | --- | --- | --- | --- |
| Full power | 37 A | 35 kHz | 260 V | **231 V** | 0.37 V |
| Full power | 37 A | 33 kHz | 246 V | 218 V | 0.37 V |
| OCP nominal trip | 61 A | 35 kHz | 429 V | **317 V** | 0.61 V |
| OCP trip + 10 A spread | 71 A | 35 kHz | 500 V | **347 V** | 0.71 V |
| Light load | 10 A | 60 kHz | 121 V | 121 V | 0.10 V |

### Assumptions and limits

- The model is linear magnetizing inductance with an abrupt saturation at the
  volt-time limit, applied as the half-cycle swing.
- It ignores the real B-H curve, winding capacitance and ringing, and
  cable capacitance. Those can make spikes **higher or lower**.
- Treat the numbers as order of magnitude, not a bound. Tens of volts would
  already exceed SELV; these estimates are hundreds.
- Even a burden that goes open for one cycle (a connector intermittent)
  produces the same spikes, and the core then saturates the remaining cycles.

## Consequences

1. **Safety:** voltages far above SELV limits on SELV-domain pins J4.13/14 and
   on the cable to the controller side. They could stress or destroy whatever
   receiving input is connected, and pose a touch hazard on an unplugged
   harness.
2. **Function:** without a defined burden and receiver, the CT phase
   information and the tank over-current sense it was meant to provide don't
   exist. POWER-SECTION.md §7 item 4 already lists "CT phase inhibit" as
   unverified.
3. **Interface definition gap:** J4.13/14 have no qualified counterpart.

## Recommended fix (owner decision; not implemented)

Terminate the CT **on this board**, at T1, and send a low-impedance voltage
across J4 instead of a current-source secondary:

- **Burden:** a 1.0 Ω burden (the datasheet terminating value; `power_section.rs`
  already assumes 1.0 Ω: 0.72 V at 72 A) across T1.3–T1.4, placed at the
  transformer.
  - Use a pulse-rated resistor sized for the secondary current
    (I_s,rms ≈ 0.19 A → ~40 mW; size ≥ 0.25 W).
- **Clamp (recommended):** a bidirectional clamp across the burden, such as a
  low-voltage bidirectional TVS or antiparallel diodes. It keeps the node
  within a few volts if the burden fails open.
- **Receiver:** the receiving board becomes a high-impedance voltage input and
  must not add a second burden. The current-sense board as designed does not
  fit this role; either adapt it or define a new receiver. Record the
  contract in the J4 interface table.
- **Layout feasibility (checked, not verified):** the SELV-side area between
  T1.3 and T1.4 (about x 173–181 mm, y 64–77 mm) currently holds only the two CT
  traces. A 1206/2512 burden and a small clamp appear to fit there with short
  stubs, far (> 15 mm) from HOT copper.

A source change is required: new parts in `elec/src/power_stage_120v.ato`,
then re-freeze, a new native projection and re-route. The whole verification
pipeline follows, and the change needs renewed D4 review.

## Open items and confirming physical test

- Owner decision on the fix above.
- After the fix: a bench check with a low-energy primary current injection,
  measuring the burden voltage with the cable unplugged. It must stay
  < 1 V typical and within the clamp level on a simulated burden open.
- The remaining task-06 checks (the other 15 J4 pins and the default states)
  are not started.

## Reproduce

```sh
python3 validation-results/06-controller-interface/scripts/ct_open_secondary.py
python3 - <<'EOF'   # connectivity: every node on the CT nets
import re; net = open("frozen/default.net").read()
for n in ("ct_s1", "ct_s2"):
    m = re.search(r'\(net \(code "?\d+"?\) \(name "' + n + r'"\)(.*?)\)\s*\(net ', net, re.S)
    print(n, re.findall(r'\(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(1)))
EOF
git grep -n -i "ct_s1" -- ':!*.kicad_pcb' ':!*.net' ':!*.json'   # consumers
```
