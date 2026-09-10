# Buck Rev A — connectivity verification

Frozen board: `buck-reva.kicad_pcb` (revision A). This file records the
source-to-schematic comparison required by the board plan, Step 1.4, and the
schematic-to-board comparison required by Step 5.1.

## 1. Source authority

The nine-device electrical core is owned by
`elec/src/modules.ato::BuckConverter3V3`. The retained source-build evidence is
`harness-lab/audits/buck-final-20260910/source-build/collection.json`
(Atopile 0.2.69), with the reviewed contract in
`harness-lab/engineering/circuit-contract.json` and the fixture obligations in
`harness-lab/fixtures/buck-v2/buck-v2-contract.json`.

The standalone schematic `buck-reva.kicad_sch` is the manufacturing
representation and the authority for prototype-only I/O (J1, J2, TP1–TP4).

## 2. Core pin map check

Explicit checklist from the board plan, rechecked against the exported
schematic netlist (`verification/buck-reva.net`).

| Net | Required core pins | Present on board net | Result |
|---|---|---|---|
| +15V (VIN) | C9.1, U3.3, U3.5 | C9.1, J1.1, TP1.1, U3.3, U3.5 | PASS — EN (U3.5) tied to VIN |
| gnd (GND) | C9.2, U3.1, C11.2, C12.2, C13.2, R17.2 | C9.2, C11.2, C12.2, C13.2, R17.2, U3.1, J1.2, J2.2, TP2.1, TP4.1 | PASS |
| sw (SW) | U3.2, C10.2, L2.1 | C10.2, L2.1, U3.2 | PASS |
| boot (BOOT) | U3.6, C10.1 | C10.1, U3.6 | PASS |
| +3V3 (VOUT) | L2.2, C11.1, C12.1, C13.1, R16.1 | C11.1, C12.1, C13.1, J2.1, L2.2, R16.1, TP3.1 | PASS |
| fb (FB) | U3.4, R16.2, R17.1 | R16.2, R17.1, U3.4 | PASS |

The prototype additions (J1, J2, TP1–TP4) extend the core nets; they add no
new net and remove no core node. The three synthetic fixture terminals
J1/J2/J3 (each with two pins on one net) were removed.

## 3. Deliberate alias translation

Net names are preserved from the fixture so the comparison is direct; the
silkscreen and documentation use the prototype names. Aliases are recorded
rather than assumed:

| PCB net name | Silkscreen / documentation name |
|---|---|
| `+15V` | `VIN` (13.5–16.5 V) |
| `gnd` | `GND` |
| `+3V3` | `VOUT` / `3V3` |
| `sw` | `SW` |
| `boot` | `BOOT` |
| `fb` | `FB` |

## 4. Schematic ↔ board comparison

Run with KiCad CLI 10.0.6. Source:
`verification/buck-reva.net` (schematic export) and the board's pad nets
(extracted with pcbnew 10.0.6).

| Net | Schematic `(ref.pin)` set | Board pad set | Result |
|---|---|---|---|
| +15V | C9.1, J1.1, TP1.1, U3.3, U3.5 | identical | MATCH |
| +3V3 | C11.1, C12.1, C13.1, J2.1, L2.2, R16.1, TP3.1 | identical | MATCH |
| boot | C10.1, U3.6 | identical | MATCH |
| fb | R16.2, R17.1, U3.4 | identical | MATCH |
| gnd | C11.2, C12.2, C13.2, C9.2, J1.2, J2.2, R17.2, TP2.1, TP4.1, U3.1 | identical | MATCH |
| sw | C10.2, L2.1, U3.2 | identical | MATCH |

Native DRC's schematic-parity check (`verification/buck-reva-drc.json`,
`schematic_parity`) reports 0 mismatches on the same files.

## 5. Component census

- Nine core references: U3, L2, C9, C10, C11, C12, C13, R16, R17 — no missing,
  duplicate or extra core component. Core footprint UUIDs, positions and pad
  nets are carried over from the reviewed witness board.
- Two prototype terminals: J1, J2.
- Four bare probe pads: TP1–TP4.
- Four non-plated mounting holes: H1–H4 (mechanical; excluded from the
  netlist/BOM).

## 6. EN tied to VIN

`U3.5` (EN) resolves on the `+15V` net together with `C9.1` and `U3.3` (VIN),
so the standalone circuit enables the regulator with VIN as intended. This is
an explicit translation from the module's separately exposed `enable` port.
