# Task 04, round 3: kit solver raster and drill fixes

Responds to round 2 (`../round2/README.md`), which found two defects in
`validation-plan/sim-kit/04-current/sheet_solver.py`:

1. **False connections.** The grid joined neighbour cells whenever both
   centres were on copper, so a gap narrower than the pitch conducted
   (0.20 mm between the BUS_P vias at (68.5, 54.8)/(68.5, 56.6)).
2. **Drilled contacts.** Pad and via centres are drill voids, so injection
   and barrels had no proper contact.

## Changes to the kit

- A grid edge is kept only when the segment between the two cell centres is
  covered by copper (`shapely.covers`); `dropped_edges` reports how many
  were removed per layer.
- Every barrel's drill is subtracted from each layer it passes.
- **Empty vias** (`filled=False`, the default) are split into 8 azimuthal
  columns. Each column touches only the annulus cells in its angle, and
  the columns are joined around the ring by the plating wall's own
  conductance. With one node per layer, the barrel had shorted the plane
  across the hole: a 1 mm drill in a 2 mm strip *lowered* R. A point inside
  an empty drill is refused.
- **Filled barrels** (`filled=True`, through-hole pads with soldered
  leads) are one node per layer; a point inside the drill attaches there.
  Vertical resistance is the plating only (conservative).

## Evidence (rerunnable)

| Check | Command | Result |
| --- | --- | --- |
| Kit self-test, 9 cases | `sheet_solver.py --selftest` | PASS (`outputs/kit_selftest.txt`) |
| Sim-kit smoke | `sim-kit/smoke_test.py` | PASS (`outputs/smoke_test.txt`) |
| native-13 topology, 0.25 mm | `scripts/kit_topology_native13.py ../round2/inputs/power_copper.json.gz outputs/kit_topology_native13.json` | 0 grid components span two physical components; leg_ret, sw_b, hv_ret/In1 split necks narrower than the pitch |
| native-13 topology, 0.125 mm | same, pitch `0.125` → `outputs/kit_topology_native13_p0125.json` | 0 spanning; grid components = physical components on every net and layer |

New self-tests:

- 0.2 mm gap at 0.5 mm pitch: must not conduct.
- 1 mm empty via in a 2 mm strip: drill centre is void and R rises
  (2.7042 → 2.7693 mΩ); a point in the empty drill is refused.
- Filled lead: an injection inside the drill is carried 1 A by its barrel.

Existing cases: the four-layer barrel is still exact (0.5811 mΩ, now as a
filled barrel), and the two-layer case is within 0.36 %.

## Consequence for the board run

Use **0.125 mm** pitch on native-13 (the runbook is updated). The topology
check must be rerun if the pitch or board changes.
