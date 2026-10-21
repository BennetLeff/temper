# Printed parts (CadQuery)

Code-generated 3D-printed parts for the Rev C probe's HV leads (option B,
[`../docs/hv-leads.md`](../docs/hv-leads.md)). Every dimension comes from
`../validation/leads/geometry.json`, which `tools/leads.rs` writes after its gates
pass (`make leads`); the scripts only add print details (snap mouths, wall
fillets, fastener clearances), named at the top of each script. Each script
writes STEP (for the owner's enclosure CAD), STL (for printing) and a JSON record
(resin, volume, print orientation) to `out/`; `render.py` draws `renders/`.

Environment, isolated from the main workspace (CadQuery's OCP kernel is about 1.3 GB):

```sh
cd instruments/differential-probe/mech3d
uv sync --no-cache        # Python 3.12, cadquery from uv.lock
cd .. && make mech3d      # every part, then the renders (about 1 minute)
```

| Part (out/) | Script | Resin | Volume | Per two probes | What it does |
|---|---|---|---|---|---|
| `wall-insert` | `wall_insert.py` | Flame Retardant | 16.1 cm³ | 2 | Reference tip-end wall (Hammond 1455N2201 outline) for the owner's enclosure: two PG7 gland bosses, the spine socket boss outside, the ledge for the lead bridge inside, TIP+/TIP− legends readable from outside (TIP− on the right). |
| `lead-bridge` | `lead_bridge.py` | Flame Retardant | 13.5 cm³ | 2 | Carries both internal leads from the glands to W_HV1/W_HV2, three ties per lead, clamped by the H3/H4 nylon screws. |
| `spine-coil` | `spine.py` | Flame Retardant | 10.0 cm³ | 1 | Probe 2's external spine: rod plus three snap saddles; the pair turns half a twist about the rod while closing from the 29 mm gland pitch to 15 mm. |
| `spine-bank` | `spine.py` | Flame Retardant | 3.8 cm³ | 1 | Probe 1's spine: rod plus one saddle. |
| `dock-coil` | `dock_coil.py` | Flame Retardant | 23.4 cm³ | 1 | On stage 53 at H6/H7: half-depth grooves for both S-bends, the ring-sleeve channels that stop either ring turning, a guard plate over the J5/J2 stud stacks, the spine seat. |
| `dock-bank` | `dock_bank.py` | Flame Retardant | 39.2 cm³ | 1 | On stage 53 at H10/H8, arm 3.5 mm over the bank caps: guide-plate grooves, risers either side of C22, riser snap clips, the TIP− strain-relief clamp above C22's hole, the spine seat. |
| `trim-guide-ct` | `trim_tools.py` | Tough 2000 | 0.8 cm³ | 4 | Snap-in lid sleeve over CT1/CT2, stops 2 mm above the trimmer. |
| `trim-guide-rv` | `trim_tools.py` | Tough 2000 | 1.0 cm³ | 4 | Same over RV1/RV2, with a 5.03 mm collar so one tool depth serves all four. |
| `trim-handle` | `trim_tools.py` | Tough 2000 | 7.5 cm³ | 1 | Handle for a Vessel CA-18 zirconia blade, shoulder-to-tip set by the guides. |
| `cal-cm-jig` | `cal_jigs.py` | Tough 2000 | 77.4 cm³ | 1 | Stage-53 replica plate (dock holes, J5/J2/C22 contacts), contacts bused: common-mode trim. |
| `cal-dc-jig` | `cal_jigs.py` | Tough 2000 | 76.7 cm³ | 1 | Same plate, HI = J5, LO = J2 + C22: DC ratio. |

Volumes are the JSON records' (`out/*.json`); `procurement/cost.py` prices them
from `procurement/printed-parts.csv`.

Frames: the stage-53 parts are modelled in place (X = KiCad x, Y = −KiCad y,
Z above the board top), the box parts in the probe-board frame (X along the
board from the tip edge, Z above the enclosure floor). Import the STEP files
without moving them and they land where `tools/leads.rs` gates them.

**Fasteners.** All stage-53 fixings are nylon (H6–H10 are "M3 NYLON ONLY"):
M3 × 10 mm M-F hex standoffs in H6, H7, H8, H10; M3 × 35 screws down the H6,
H8 and H10 posts, M3 × 10 into H7; M3 × 16 screws with trapped nuts at each
spine end (insert socket and dock seat). Ties: 2.5 mm nylon, 100 mm.

**Resin.** Printed resin carries no insulation credit: Formlabs publishes no
dielectric strength or tracking index for these resins, so the rated wire
insulation and the air clearances remain the HV design. The parts fix geometry
only. Flame Retardant (UL 94 V-0 at 3 mm per Formlabs) is used for everything
that stays on stage 53 or in the probe box; Tough 2000 for tools and bench jigs.
Every part near the leads is mirror-symmetric about the leg axis except the
items `tools/leads.rs` lists and gates (posts, TIP− clamp: ≤ 0.021 pF).

**Checks before printing a new revision.** `make check` (leads gates), then
`make mech3d`, then look at `renders/assembly-closeup.png`. The scripts assert
on invalid solids; OCCT is fragile where a groove axis lies exactly on a face,
so `dock_bank.py` makes all its cuts in one boolean and lifts the guide-plate
groove 0.02 mm off the plate top.
