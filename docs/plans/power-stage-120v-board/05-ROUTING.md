# Part 5: routing

**Goal:** route every net of the owner-approved placement, so that:
- DRC with the Part 4 rules has **0 unconnected items** and **0 clearance, creepage,
  courtyard and short violations**
- schematic parity is 0
- the audit and the stackup gate still pass

**Precondition:** the owner has approved `PLACEMENT-REVIEW.md` in writing (Part 4).
If poses change, go back to Part 4.

## Method: scripted route replay, never GUI dragging

Routes are written as JSON "instructions" and applied by
`zapote/power-stage-120v/tools/apply_routes.py`. That's a thin wrapper around
`zapote/rtd/apply_routes.py`, from Part 1. The replayer:

- resolves pad endpoints written as `"REF.PAD"` (for example `"Q2.2"`) to exact
  coordinates, and **refuses** a pad whose net differs from the instruction's net.
  So routing can never change connectivity.
- is transactional: a failed instruction leaves the board untouched.
- writes a receipt with input and output board hashes.

Instruction format (one file per routing batch, `routes-NN.json`):

```json
{
  "author": "<model name>; explicit paths, no search",
  "nets": [
    {
      "net": "leg_a-gate_h",
      "mode": "replace",
      "paths": [
        {"layer": "F.Cu", "width_mm": 0.8, "points": ["R10.2", [71.0, 40.5], "Q2.1"]}
      ],
      "vias": [{"position_mm": [70.0, 44.0], "diameter_mm": 1.2, "drill_mm": 0.6}],
      "zones": [
        {"layer": "B.Cu", "outline_mm": [[60,30],[90,30],[90,50],[60,50]],
         "clearance_mm": 0.5, "priority": 1}
      ]
    }
  ]
}
```

- `mode: "replace"` removes that net's existing copper first. `"add"` keeps it.
- Every bend is an explicit `[x, y]` point in mm. There is no autorouting.
- Net names are the board's names, for example `sw_a` or `leg_a-gate_h`. List them
  from `native-0N/section.kicad_pcb` `(net ...)` entries; never guess.

Apply and check after **every** batch:

```sh
B=native-0N/section.kicad_pcb
python3 tools/apply_routes.py $B routes-NN.json routes-NN.receipt.json
python3 tools/write_rules.py $B
kicad-cli pcb drc --severity-all --schematic-parity --refill-zones --save-board \
  --format json --output native-0N/drc-NN.json $B
```

`--refill-zones --save-board` fills the poured zones. Without it, zone
connections look unconnected.

## Copper sizing (70 µm = 2 oz external, 20 °C rise, IPC-2221 external formula)

| Current (A rms) | Minimum width (mm) |
| ---: | ---: |
| 5 | 0.9 |
| 10 | 2.4 |
| 15 | 4.1 |
| 18.7 | 5.6 |
| 23 | 7.5 |
| 26 | 8.8 |

Skin depth at 35–50 kHz is about 0.3 mm, larger than the 70 µm copper, so skin
effect doesn't reduce these at this frequency. Use **poured zones on both layers,
stitched with vias**, wherever a net needs more than about 6 mm. Record the width
you used per net in `ROUTING.md`.

| Net group | Nets | Design current | Route as |
| --- | --- | --- | --- |
| Mains in | `ac_l_in`, `l_f`, `l_filt`, `ac_n_in`, `n_filt` | 15 A rms | ≥ 4.1 mm, better 6 mm, or a zone |
| Bus + legs | `bus_p`, `hv_ret`, `leg_ret`, `sw_a`, `sw_b` | ~19 A rms line-average (HF, bidirectional) | zones on both layers, via-stitched |
| Tank | `coil_ret`, `res_a` | 18.7 A rms average, 26 A rms at line crest | zones, or ≥ 8.8 mm |
| PE | `pe` | fault current until F1 clears | ≥ 4.1 mm, direct from J1 PE to the Y capacitors and the heatsink bond point |
| Gate drive | `leg_*-out_h/out_l/gate_h/gate_l`, and the source/Kelvin returns | 4 A source / 6 A sink peak, µs pulses | 0.8–1.0 mm, gate and return on adjacent paths, same layer, shortest possible |
| 15 V gate supply, bootstrap | `v15_ls`, `leg_*-boot` | < 0.5 A | 0.5–0.8 mm |
| Shunt Kelvin | R5 pad 3 (`ocp_kelvin_n`) and R5 pad 2 (`leg_ret`, used as the sense reference) | µA | **Separate 0.3 mm traces**, routed as a tight pair from R5's pads to R29 and U6's ground. Never share the power path |
| Bus sense string | `bus_p` → R22 → … → R26 | µA | 0.3 mm; keep the string straight to spread voltage; creepage rules apply between string nodes |
| Logic HOT and SELV | everything else | < 0.1 A | 0.3 mm |

## Order of work (one batch per step, applied and checked before the next)

1. **Barrier first.** Confirm the Part 4 rules make DRC flag any copper within the
   reinforced distance of the other domain. Deliberately draw one test track
   across the barrier, see DRC fail, then remove it. Record this in `ROUTING.md`
   as proof the rule works.
2. **Commutation loop:** `bus_p`, `hv_ret`, `leg_ret`, `sw_a`, `sw_b` as zones.
   Keep the C5/C6 → high-side → low-side → R5 → C5/C6 loop tight, with top and bottom
   copper overlapping (opposite current) where possible.
3. **Tank:** `sw_a` → J2 → T1 → `res_a` → C21–C23 → `sw_b`.
4. **Mains entry:** J1 → F1 → RV1 → L1 → C2 → BR1, plus PE to C3, C4 and the
   heatsink bond.
5. **Gate loops**, per leg: driver OUTA/OUTB → gate resistor → gate, and each
   return to its own source pin (high side to `sw_*`, low side to `leg_ret`).
   Keep each gate loop's area minimal. The low-side return goes to the **source
   pin of that MOSFET**, not to a shared plane in the middle of the commutation current.
6. **Driver supplies and bootstrap:** `v15_ls`, the D1/D2 anodes, boot capacitors
   right at U1/U2's VDDA/VSSA pins (16/14).
7. **HOT auxiliary:** PS2 → U3 → `hot5` to U4, U6 and U7 side 1; the OCP network; the Kelvin pair.
8. **SELV:** J4 to the SELV pins of U1, U2, U4, U7 and T1's secondary, plus the SELV
   bypass capacitors (C7, C14, C29, C34).

After each step, the unconnected count must fall and the violation count must
stay 0. If it doesn't, fix it before the next step.

## Rules you must not break

- **Never add or rename a net** to make routing easier. Connectivity comes only
  from the source (`00-INDEX.md`, rule 4).
- **Never route copper through the SELV/HOT barrier** other than inside the
  barrier parts' own footprints.
- **No vias under the isolator bodies** (U1, U2, U4, U7, T1) in the barrier region.
- **Don't place a zone of one domain over the other domain's area on either
  layer.** Only a board edge or the barrier gap may separate the domains.
- **Thermal relief:** for power zones to TO-247 and GBJ pads, prefer solid
  connection unless assembly needs relief. Record the choice.

## Deliverables

- `routes-01.json` … `routes-NN.json` and their receipts
- `native-0N/section.kicad_pcb` routed
- `ROUTING.md` with:
  - per-net widths or zones and the stitching-via count
  - loop-area bounding boxes (commutation, each gate loop)
  - the barrier self-test from step 1
  - final DRC numbers: unconnected 0, violations 0, parity 0
- PR titled `feat(power): route power-stage-120v`

## Stop and ask if

- a net can't be routed without crossing the barrier or breaking a rule. That's a placement problem: go back to Part 4 and report it.
- a required width doesn't fit between pads (for example at TO-247 pins). Report the pad pitch and the width needed.
- DRC reports a violation class you don't understand
