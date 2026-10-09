# Native-21 D5 insulation audit (2026-10-08)

What the routed board shows against D5-BASIS.md's provisional 8.0 mm floor, and what only the
laboratory, vendors or the enclosure can close. Board: native-21 stage 9, rebuild
`e9d1cc4f…` (`d5_audit.py <copper-dump.json> <board pads.json>`, the board's own pads so the fixings
are measured). Tool: `d5_audit.py` → `d5-audit.json`; `mounting_candidates.py` → `mounting-candidates.json`.

## Board measurements (all PASS)

| Check | Result | Floor |
| --- | --- | --- |
| HOT ↔ SELV copper, plan view, all layers | **8.047 mm** (zone n_ha / via leg_a-dis at [67.46, 42.32]) | 8.0 mm |
| HOT ↔ PE copper | **8.507 mm** (pad n_filt C4 / pad pe C4; C3's l_filt side is the same) | 8.0 mm |
| Rust plan-view barrier gate (independent) | 0 violations | 8.0 mm |

Plan view over all layers bounds surface creepage on a solid board from below: any surface path is
at least as long as the straight line between its ends. There are no slots. Board slots would not
extend package creepage anyway (D5-BASIS).

## Barrier-crossing parts

| Ref | Part | Land gap on this board | Package (datasheet) | Source |
| --- | --- | ---: | --- | --- |
| C3 | DE1E3RA222MA4BP01F | 8.507 mm | — | NOT IN TABLE: add the datasheet distances |
| C4 | DE1E3RA222MA4BP01F | 8.507 mm | — | NOT IN TABLE: add the datasheet distances |
| PS1 | IRM-20-15 | 42.009 mm | module approval; PCB pin span checked here | Mean Well IRM-20 (input/output pin span only) |
| T1 | CST3015-100ED | 18.5 mm | CLR/CPG 8.0 / 8.0 mm, no CTI/PD certificate | Coilcraft CST3015 datasheet (≥8 mm spacing, 5 kVrms test) |
| U1 | UCC21550BDWKR | 8.1 mm | CLR/CPG 8.0 / 8.0 mm, reinforced | TI UCC21550 datasheet, DWK insulation table |
| U2 | UCC21550BDWKR | 8.1 mm | CLR/CPG 8.0 / 8.0 mm, reinforced | TI UCC21550 datasheet, DWK insulation table |
| U32 | ISO7710DWR | 8.1 mm | CLR/CPG 8.0 / 8.0 mm, reinforced (VDE 0884-17) | TI SLLSER9E p.8 (DW-16) |
| U33 | ISO7710DWR | 8.1 mm | CLR/CPG 8.0 / 8.0 mm, reinforced (VDE 0884-17) | TI SLLSER9E p.8 (DW-16) |
| U34 | ISO7710DWR | 8.1 mm | CLR/CPG 8.0 / 8.0 mm, reinforced (VDE 0884-17) | TI SLLSER9E p.8 (DW-16) |
| U36 | VOL628A-3X001T | 8.2 mm | CLR/CPG 8.0 / 8.0 mm, option 1 (VDE) | Vishay doc 82401 rev 1.9 p.4 |
| U4 | AMC1311BDWVR | 8.85 mm | CLR/CPG 8.5 / 8.5 mm, reinforced | TI AMC1311 datasheet, DWV insulation table |
| U9 | ISO7710DWR | 8.1 mm | CLR/CPG 8.0 / 8.0 mm, reinforced (VDE 0884-17) | TI SLLSER9E p.8 (DW-16) |

C3/C4 (Y-capacitors, L_FILT to PE) are the barrier's Y-cap path. Their land gap is 8.507 mm, the
8.5 mm nominal of D5-BASIS's 1.5 mm-pad footprint; the finished-board tolerance and the component
surface path are still to be checked, as D5-BASIS says.

Non-plated holes: the HOT power terminals' own holes (J2/J5/J7–J10 studs, part of their own
conductor), J4's (SELV, ≥ 64 mm from HOT), and the seven M3 fixings below.

## Open, not closable on the PCB

- **Board fixings (stage 8, re-planned for review M4):**
  - **H1** takes metal hardware. It is 22.0 mm from HOT at the hole centre, 20.4 mm at the hole edge and 18.5 mm at the 7 mm washer's edge. Those three references are the review's m8 "inconsistency".
  - **H2–H7** take nylon hardware only (silk and F.Fab NYLON). Their 7 mm washer face is copper-free on both outer layers.
  - H2 and H3 are at the SELV tongue's corners, where only the SELV inner planes give way to the hole.
  - **H4–H6 sit in the power core**, with HOT copper 0.55 mm (H4), 1.9 mm (H6) and 7.26 mm (H5) from the hole wall (H7: 15.4 mm). The HOT→chassis path then runs along the nylon standoff and screw: **nylon standoffs ≥ 10 mm long** at H4–H6 give the 8.0 mm floor with margin. That is an enclosure/assembly requirement, not a PCB one (BRINGUP-PROBES.md table).
  - Any metal screw, washer or standoff is
  chassis/PE: it must be ≥ 8.0 mm from HOT and off SELV copper, or it adds a second controller-ground–PE
  bond beyond R38. `mounting-candidates.json` lists the legal M3 centres for metal hardware: 173 on a
  2 mm grid, all in the right and rear band (x 150–290, e.g. (285, 135) at 18.5 mm from HOT). The
  power core and the SELV tongue have none, so fixings there need nylon hardware or cut-outs in the
  SELV planes. **The enclosure's bosses must match H1–H7, or the holes move with them.**
- Laminate CTI ≥ 175 V (group IIIa) confirmed on the order: the JLC question is open (FAB-JLCPCB.md).
- PD3 / material-group qualification of the package distances (TI tables state group I, PD2).
- IEC 60664-4 high-frequency distances (switching 33–40 kHz is above 30 kHz). Expected well below
  8 mm at these peak voltages, but the laboratory confirms the governing table.
- CST3015's CTI/PD certificate; IRM-20's internal insulation scope; heatsink insulators of the TO-247
  tabs (HOT drain to the chassis/PE heatsink) and BR1's body.
- Hipot and partial discharge on the assembled board.

**Verdict:** every board-level distance meets the 8.0 mm floor. Insulation is **not qualified**;
the items above, plus the fixings decision, stand between this board and a D5 release.
