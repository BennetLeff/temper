<!-- provenance: commit=d9d455d29073aa1b184abc39b3bbf5879b8412b2 dirty=UNKNOWN -->
# The board is out of sync with the schematic — U6/U7 designators are swapped

**Date:** 2026-08-13
**Status:** finding; one contributing defect fixed here, the desync itself is NOT fixed
**Blocks:** `Invariant tests (io, deterministic, physics, fields, validation, cp_sat)` on `main`

## Summary

`pcb/temper.kicad_pcb` no longer matches `elec/src`. Three independent
symptoms, one cause:

1. **`U6` and `U7` refer to different physical parts in the two sources.**
2. **Four components exist in the schematic but not on the board:** `C41`,
   `J2`, `T2`, `TP4` — all on classified (safety-relevant) nets.
3. **`TP3` carries a different net in each source.**

The board's last substantive change was `7e3608bc2` (2026-08-06); the
schematic changed on 2026-08-07 (`c617e0d08`, OCP-02) and 2026-08-08
(`044114459`, J_RTD1). The board was never re-synced.

## 1. U6/U7 are swapped

Read directly from `pcb/temper.kicad_pcb` and `elec/build/default.net`:

| Ref | On the board | In the schematic |
|-----|--------------|------------------|
| `U6` | `Package_TO_SOT_THT:TO-247-3_Vertical` — **3** thru-hole pads; pad nets `DC_BUS_RTN`, `GATE_LS`, `SW_NODE` | **13** nets: `+15V_LS`, `+3V3`, `GATE_HS`, `gnd`, `hb.gate_hs.driver-p1`, `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`, `hb-gnd`, `ina`, `inb`, `input`, `nc_7`, `SHUTDOWN` |
| `U7` | `lib:SOIC16W_Isolated` — **16** SMD pads; pad nets include `DC_BUS_RTN`, `GATE_HS`, `SHUTDOWN`, `gnd`, `+3V3` | **2** nets: `+15V_LS`, `hb.gate_hs.driver-p1-1` |

A 3-pad TO-247 cannot carry 13 nets. The board's `U7` (16-pin isolated
SOIC) is the UCC21550 gate driver; the schematic calls that part `U6`.

**Consequence:** an assembly built from this board + this BOM would place
the wrong part in both positions — an IGBT where the gate driver belongs
and vice versa. This is a build-blocking defect, not a bookkeeping one.

## 2. Four schematic components are absent from the board

Refs on classified nets in `elec/build/default.net` but with no footprint
in `pcb/temper.kicad_pcb`:

```
C41, J2, T2, TP4
```

`pcb_components = 169`, `netlist_components = 168`,
`netlist_refs_on_classified_nets = 158`,
`matched_components_in_placement = 153`.

## 3. TP3 carries a different net in each source

`c617e0d08` (2026-08-07) instantiated OCP-02 and, in the same change,
moved the UVLO-02 fault line from `TP3` to a new `TP4`, putting the new
`safety.ocp2-line` on `TP3`.

| Source | TP3's net |
|--------|-----------|
| Board (`pcb/temper.kicad_pcb`, net 142) | `safety.uvlo_logic-line` |
| Schematic (`elec/build/default.net`, net 116) | `safety.ocp2-line` |

`TP4` — which now carries `safety.uvlo_logic-line` — is one of the four
components missing from the board entirely.

## What this PR fixes: the undeclared net

`elec/domain_manifest.yaml` gained OCP-02's *instance* path
(`safety.ocp2.ct`) in `c617e0d08` but never gained its *net*
(`safety.ocp2-line`). `TP3` therefore became unclassified, and
`generate_domain_clearance_constraints()` emitted **zero** constraints for
every pair touching it.

This is the same defect the manifest's own 2026-07-27 note records
("`TP3` became unclassified, so the domain-clearance generator emitted zero
constraints for every pair touching it ... The two `TestRealBoardTP3Coverage`
tests exist to catch exactly that and did"), recurred through a different
door. **Declaring the instance is not declaring the net.**

`safety.ocp2-line` is genuinely SELV despite OCP-02 sensing a `DC_BUS_RTN`
conductor: it senses through CT2, whose *"secondary has no galvanic
connection to the primary, so it can be referenced to signal ground
regardless of common-mode voltage"* (`modules.ato`,
`SecondaryOCPComparator` docstring) — the same construction that already
makes OCP-01's `ct_sense.ct` safe. The comparator is a TLV3201 powered
from `power_3v3`.

Measured effect of declaring it:

| Metric | Before | After |
|--------|--------|-------|
| Unclassified components | 16 | 15 |
| Coverage ratio | 0.9053 | 0.9112 |
| Domain-clearance constraints | 10,848 | 11,001 |
| Constraints touching `TP3` | 0 | 153 |
| `TP3`↔`U7` @ 8.0mm | absent | exactly 1 |

Both `TestRealBoardTP3Coverage` tests pass again.

## What is deliberately NOT fixed

Two tests still fail, and they are **correct to fail**:

- `test_production_board_constraint_count_11571` — expects 11,343, measures
  11,001. The residual gap is the four missing board components.
- `test_real_board_finds_known_isolators` — expects the component-level
  intra-footprint check to flag `{C6, K1, K2, K3, T1, U3, U7}`; it flags
  `{C6, K1, K2, K3, PS1, T1, U6}`. `U6`/`U7` differ **because the two
  sources disagree about which part those designators name.** The
  component-level check reads the schematic's `nets`; the REQ-SAFE-01
  validator reads the board's pads.

Re-pinning either baseline would record a board that does not match its
schematic as the new normal, and would retire the only two gates currently
detecting that. They should be re-derived **after** the board is
regenerated, not before.

## Why this surfaced today and not on 2026-08-08

CI caches the compiled netlist under
`hashFiles('elec/src/**', 'elec/ato.yaml', 'Makefile')`. `5939be89e`
(2026-08-12) changed the `Makefile`, invalidating that key and forcing a
rebuild of the netlist from current `elec/src` — which exposed a desync
that had been masked by a stale cached artifact since 2026-08-07.

The same trap exists locally: a stale `elec/build/default.net` makes these
tests pass. The four failing tests **skip** entirely when the netlist is
absent, so "no failures locally" can mean "never ran". Run `make netlist`
first, in the working tree you are testing from.

## Recommendation

Regenerate `pcb/temper.kicad_pcb` from the current schematic before any
further DRC, clearance or routing measurement is taken against it. Every
such measurement made since 2026-08-07 was taken against a board that does
not match its own netlist.
