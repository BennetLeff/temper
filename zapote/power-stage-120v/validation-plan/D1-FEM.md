# D1 by finite elements: board loop inductance from the real 3-D copper

Part of the [master plan](00-MASTER-PLAN.md). Read its ground rules (§2)
first. This document **replaces the FastHenry method** in ROUND-5.md R5-D1.
The goal is the same: the board's commutation-loop and gate-loop
inductances, so the switching model (D2, then C1/C2) can run on native-17's
real copper instead of guesses. When this is done, design changes (gate
resistor, snubber, gate bias, copper) can be tried in simulation in minutes
rather than on a fabricated board.

Written 2026-09-28 against PR #1615. Owner decision: simulate this rather
than defer it to the bench.

## Amendments after round 6 (2026-09-28)

Round 6 (`validation-results/01-switching-parasitics/round6/d1-fem/`)
stopped before any board solve. These amendments supersede the sections
they name.

1. **Palace: one more build is authorized (a third attempt), done
   deliberately.** Both failures were configuration choices: attempt 1
   switched off both eigen backends, one of which Palace requires; attempt 2
   linked Homebrew's MFEM instead of the superbuild's. For attempt 3:
   - keep Palace's default dependency set, with ARPACK (and SLEPc if it
     builds) on; switch off only GPU items (MAGMA);
   - bind MFEM explicitly to the superbuild (`MFEM_DIR` **and**
     `MFEM_LIBRARY` and its include path), and prove the binding from the
     final CMake cache and `otool -L` on the Palace binary before running;
   - time-box it to one working session. If it fails, record the log and
     move to item 2; don't try a fourth time.
2. **Elmer direct is an accepted fallback for fixtures.** Round 6's
   direct (UMFPACK, tree-gauge) coax solve gave 13.745 nH against
   13.863 nH exact (−0.85 % at 0.25 mm), inside §5A's 2 %. The iterative
   Hypre/AMS path is **not** accepted: it stagnated (residual 9.7 against
   1e-9) while reporting success, and round 6's verifier rightly rejects it.
   With whichever solver runs, finish §5A (plate pair, then mutual) before
   the board. For the board, check that a direct solve fits in memory. If
   it doesn't, an iterative solver is acceptable only after it reproduces
   the direct coax and plate results within 1 %.
3. **Current conservation is part of the fixture error.** Round 6's
   current-sheet source carried 0.9997–1.0111 A across sampled cuts. Report
   the cut spread with every fixture, and fold it into the error bar (the
   2 % criterion applies to the whole range, not a chosen normalization).
4. **Closures must not cross other copper (replaces the bridge and port
   geometry in §3 step 3).** On a TO-247 the pins run G–D–S in a line, so a
   straight G–S bridge passes through the drain pad (round 6's negative
   control shows this on Q2, Q3, Q5 and Q6). A capacitor's 15 mm port sheet
   laid flat would cross top-layer copper between its pads. So:
   - build every closure (bridge or port sheet) that would cross other
     copper as a **raised arch**: vertical legs from the two pads to height
     h above the top copper, and a span at h, contacting exactly its two pads;
   - solve each loop at **h = 1, 2 and 3 mm** and extrapolate the loop
     inductance linearly to h = 0. This removes the arch's own contribution;
     the component's real lead and body inductance stays in its SPICE model.
     Report all three values and the fit; if the fit isn't linear within 5 %,
     say so;
   - closures between adjacent pads that cross nothing (D–S of each MOSFET,
     the driver's adjacent SMD pins, R5 pads 1–4, the gate resistors) stay
     flat, as specified;
   - geometry audit: every closure touches exactly its two pads at every h.

## 0. Why the method changed

Rounds 4 and 5 turned the copper into FastHenry wire segments on a pixel
grid, then required every segment to lie inside real copper. Fine grids
fail that by construction: hundreds to thousands of edge links leave the
copper, and removing them breaks real connections. Both rounds stopped
before any board solve.

This method never rasterizes. KiCad exports the actual copper as 3-D solids;
gmsh meshes the space *around* those solids with tetrahedra that follow
their true surfaces; a finite-element solver computes the magnetic field and
the inductance between terminals. That is how commercial extractors (Ansys
Q3D and similar) work.

**Feasibility already shown** (scratch probe, 2026-09-28, not committed):
- `kicad-cli pcb export step` exported native-17's copper in 9 s (17 MB),
  as 84 solid volumes, effectively one per connected conductor.
- gmsh cropped leg A's region (25 conductors) and meshed 17 of them to their
  true shape in about 3 minutes (64,632 nodes). The other 8 failed with
  surface self-intersections at thin features ("PLC Error: a segment and a
  facet intersect"). A healing retry with `OCCSewFaces` destroyed the
  volumes, so the crop produced nothing. **Don't use `OCCSewFaces`.** Step 3
  below meshes the air instead of the copper, which removes most of this
  difficulty.

## 1. The physics and what "inductance" means here

- **Frequency.** Switching edges are 20–30 ns, with content at 10–30 MHz.
  Copper skin depth is 21 µm at 10 MHz and 12 µm at 30 MHz, less than the
  61–70 µm copper. So current flows on conductor surfaces, and the relevant
  quantity is the high-frequency ("external") inductance.
- **Model.** Treat copper as a **perfect conductor**: the solve domain is
  the non-conducting space (air, and FR-4, which is non-magnetic, µr = 1),
  with conductor surfaces as perfect-conductor boundaries. Current is
  injected through **terminal sheets** that bridge the gap where an external
  component sits. This gives the loop inductance matrix directly. It is
  valid above about 3 MHz (at 1 MHz the skin depth, 66 µm, equals the copper
  thickness). Resistance is not produced; see §6.
- **What's excluded.** The MOSFET package inductance is inside the Infineon
  model; capacitor ESL and the shunt's own inductance are component
  parameters in SPICE. The copper model ends at component pads.

## 2. Ports: where the external components are

A port is a small conducting sheet across the two pads of **one** external
component. Exciting it with a unit current drives current around the copper
loop that component closes. Every other component in that loop is replaced
by a **bridge**: a thin perfect-conductor strip joining its pads at the
board surface, adding as little extra inductance as possible (its real lead
or package inductance is already in its SPICE model). Components not in a
loop (snubbers C12/C13, hold-offs R11/R13, bootstrap parts) are left open.
Unexcited ports are open (no current).

Per leg, **four ports**, which give four loops. Pads are native-17 (board
coordinates, mm, Y downward):

| Port | Component (sheet across) | Loop it closes | Bridges in that loop |
| --- | --- | --- | --- |
| P1 | C38 (leg A) / C41 (leg B) | local cap → high-side drain → switch node → low-side source → R5 → cap return | Q-high D–S, Q-low D–S, R5 pads 1–4 |
| P2 | C39 (A) / C40 (B) | the same loop through the second local cap | same |
| P3 | driver high output: U1.15–U1.14 (A) / U2.15–U2.14 (B) | driver → R10/R18 → Q-high gate; Q-high source → driver | R10/R18, Q-high G–S |
| P4 | driver low output: U1.10–U1.9 (A) / U2.10–U2.9 (B) | driver → R12/R20 → Q-low gate; Q-low source → driver | R12/R20, Q-low G–S |

Pad positions:

| Leg A | Leg B |
| --- | --- |
| C38.1 bus_p (144.000, 22.000), C38.2 hv_ret (129.000, 22.000) | C41.1 bus_p (88.400, 22.000), C41.2 hv_ret (103.400, 22.000) |
| C39.1 bus_p (164.600, 22.000), C39.2 hv_ret (149.600, 22.000) | C40.1 bus_p (109.000, 22.000), C40.2 hv_ret (124.000, 22.000) |
| Q2 high: G (150.550, 4.215), D bus_p (156.000, 4.215), S sw_a (161.450, 4.215) | Q5 high: G (92.550, 4.215), D (98.000, 4.215), S sw_b (103.450, 4.215) |
| Q3 low: G (132.550, 4.215), D sw_a (138.000, 4.215), S leg_ret (143.450, 4.215) | Q6 low: G (110.550, 4.215), D sw_b (116.000, 4.215), S leg_ret (121.450, 4.215) |
| R10: out_h (150.550, 14.062) → gate_h (150.550, 11.137) | R18: (92.550, 14.062) → (92.550, 11.137) |
| R12: out_l (132.550, 14.062) → gate_l (132.550, 11.137) | R20: (110.550, 14.062) → (110.550, 11.137) |
| U1.15 out_h (144.825, 41.125), U1.14 sw_a (146.095, 41.125) | U2.15 (100.825, 41.125), U2.14 sw_b (102.095, 41.125) |
| U1.10 out_l (151.175, 41.125), U1.9 leg_ret (152.445, 41.125) | U2.10 (107.175, 41.125), U2.9 leg_ret (108.445, 41.125) |
| R5 (shared): 1 leg_ret (127.135, 9.615), 4 hv_ret (125.865, 15.585); 2 leg_ret, 3 ocp_kelvin_n are the Kelvin pair | same R5 |

Notes:
- MOSFET bridges D–S and G–S both land on the source pad; that is correct.
  The shared source copper is what couples the power loop into the gate loop
  (common-source inductance). It appears as the mutual M(P1,P4) for the low
  side and M(P1,P3) for the high side.
- Bridge R5 from pad 1 to pad 4 only. Leave the Kelvin pads (2, 3) and their
  sense traces open; they carry no current.
- **Optional fifth port (P5):** bulk capacitor C6 (leg A side; pads 1/2 bus_p,
  3/4 hv_ret) closing the same loop, for the bulk/local sharing. Do it after
  the four-port result is accepted.

Read every pad position from the board with KiCad Python rather than
copying this table, and fail if any differs; the table is for orientation.

## 3. Geometry and mesh

1. **Export** (unit root; KiCad 10.0.4):
   ```sh
   kicad-cli pcb export step --no-components --no-board-body \
     --include-tracks --include-pads --include-zones --include-inner-copper \
     --fuse-shapes --no-extra-pad-thickness \
     --output copper.step native-17/section.kicad_pcb
   ```
   In the STEP, X equals board X, **Y = −board Y**, and Z runs from about
   −0.07 (B.Cu bottom) to 1.563 mm (F.Cu top). Record the STEP's SHA-256 and
   the board hash. If thin features give trouble, try `--min-distance`
   (merges near-coincident points) and record the value.
2. **Crop** with gmsh's OpenCASCADE kernel: intersect the copper with a box
   around the leg's ports' pads plus margin M (§5). Leg A's pad bounding box
   is about x 125.9–164.6, board y 4.2–41.1 mm. Healing that's allowed:
   `Geometry.OCCFixDegenerated`, `OCCFixSmallEdges`, `OCCFixSmallFaces`.
   **Not** `OCCSewFaces`.
3. **Add bridges and port sheets** as OpenCASCADE geometry:
   - bridge: a box 0.5 mm wide, 35 µm thick, lying on the top copper
     surface (z from 1.563 up), from pad centre to pad centre, fused with
     the copper;
   - port sheet: a rectangle 0.5 mm wide in the same position, standing
     between the two pads, *not* fused, tagged as the port surface.

   Check that each bridge touches exactly its two pads' copper and nothing
   else.
4. **Build the air domain:** a box extending at least 20 mm beyond the crop
   on every side (and 20 mm above and below), minus the cropped copper. The
   copper surfaces become boundary surfaces of the air volume. **Mesh the
   air, not the copper.** This avoids the thin-solid tetrahedra that failed
   in the probe.
5. **Tag** physical groups: `air` (volume), one group per conductor surface
   set as `pec`, one group per port sheet (`P1`…`P4`), and `outer` for the
   air box boundary.
6. **Mesh:** start with `Mesh.MeshSizeMin = 0.05`, `MeshSizeMax = 2`,
   curvature-based sizing, `Algorithm3D = 1` (Delaunay; the more robust
   choice), then `Mesh.Optimize = 1`. Refine near port sheets and across the
   dielectric gaps between facing planes (0.5 mm and 0.436 mm): at least
   three elements across each gap. Save as MSH 2.2 or whatever the solver
   version requires.
7. **Geometry audit before any solve** (fail closed): every port sheet
   touches both of its pads; no bridge touches a third conductor; the number
   of conductor surfaces equals the number of cropped volumes; the mesh has
   no inverted or zero-volume elements. Report crop cuts: which net and
   layer the box boundary cuts, and the cut length.

## 4. Solver

**Primary: Palace** (AWS open-source, <https://github.com/awslabs/palace>).
Its magnetostatic problem type computes the inductance matrix for a set of
terminals with surface-current excitation, which is exactly §2.
- Build from source with CMake per its docs (it pulls MFEM, hypre and other
  dependencies; allow about an hour on this Mac with Homebrew's compilers and
  Open MPI). Record the commit hash, compiler versions and the binary's
  SHA-256.
- Configure: problem type magnetostatic; mesh length unit 1 mm; one
  material (µr = 1) for `air`; `pec` as perfect-conductor boundaries; `P1`…`P4`
  as the terminal (surface-current) boundaries with a direction across each
  sheet from the first pad to the second; `outer` as a far-field condition
  appropriate to magnetostatics (per the docs). **Check each config key
  against the documentation for the commit you build**; key names change
  between releases. Commit the config JSON.
- Output: the terminal inductance matrix (Palace writes it to its postpro
  directory). Keep the raw output.

**Fallback: Elmer FEM** (magnetodynamics with the Whitney solver), if Palace
fails to build after two documented attempts. Same geometry, same ports.
Record why you switched. If neither builds, stop and report blocked with
both build logs. Don't return to FastHenry rasterization.

## 5. Validation, then convergence (in this order)

**A. Solver fixtures, before the board.** Build each with the same
gmsh-to-solver pipeline and the same port method:
1. **Coaxial line**, 50 mm long, inner radius 0.5 mm, outer 2.0 mm, shorted
   at one end, port at the other. Exact: L = (µ0/2π)·ln(b/a)·ℓ = 13.863 nH.
   Require within 2 %.
2. **Parallel-plate pair**, 10 × 50 mm, 0.5 mm spacing, shorted at one end.
   Ideal (no fringing) is 3.142 nH; fringing lowers it. The corrected
   FastHenry fixtures gave 2.751/2.948/3.080 nH at 20/40/80 subdivisions.
   Require the result between 2.85 and 3.14 nH, and state it.
3. **A two-port check of mutual inductance**: two coaxial loops, or two
   adjacent rectangular loops with a known analytic mutual (Neumann
   formula, computed numerically in a committed script). Require within 3 %.

Commit each fixture's geometry script, config and result.

**B. Board convergence**, leg A first:
1. **Crop margin:** M = 5, 10, 20, 40 mm. Accept when every self term and
   every mutual larger than 10 % of the smaller self changes by ≤ 5 %
   between the last two margins. Report the cut planes at the accepted M.
2. **Mesh:** at the accepted M, solve two mesh densities (MeshSizeMin and
   the gap refinement at least 1.5× finer) and element orders 1 and 2 (or
   the solver's equivalent). Same 5 % rule.
3. **Bridge sensitivity:** repeat with bridges 0.25 mm and 1.0 mm wide.
   Report the change. It should be small next to the loop values; if not,
   say so, since it means the bridges add meaningful inductance.
4. **Matrix checks:** symmetric within 1 %, positive definite, and every
   coupling coefficient |k| < 1.

**C. Heatsink sensitivity.** The PE-bonded aluminium heatsink sits along the
top edge with the TO-247 tabs on it, and eddy currents in it lower the loop
inductance at high frequency. Add a perfect-conductor plate at the heatsink
position (the D2 heatsink span, board x 12–165 mm, top edge) and report the
change as a bracket. The real value lies between the two.

## 6. Deliverables and how D2 uses them

In `validation-results/01-switching-parasitics/round6/d1-fem/`:
- `README.md` (master plan §4 template) with board, STEP, solver and mesh
  identities;
- `scripts/`: export, crop/bridge/port geometry, mesh, config generation,
  run, parse, audit, fixtures;
- `fixtures/results.json`, `convergence.json`, `heatsink-bracket.json`;
- **`loop_matrix_legA.json` and `loop_matrix_legB.json`**: the 4×4 L matrix
  (nH), port definitions (component, pads, direction), crop, mesh and
  solver identities;
- **`spice_loops_legA.inc` / `_legB.inc`**: the matrix as SPICE coupled
  inductors, one per port, each placed in series with the component that
  defines its port:
  - `LP1` in series with the C38 branch; `LP2` with C39;
  - `LP3` in series with the high-side gate resistor; `LP4` with the
    low-side gate resistor;
  - `K` statements for every pair, from the matrix.

  This loop representation is exact for the loop inductances, including
  the common-source coupling (it enters through `K` between `LP1`/`LP2` and
  `LP3`/`LP4`).
- Raw meshes, solver output and logs go under an ignored `raw/` directory
  with a hash manifest (they can be large).

**Resistance.** The perfect-conductor model gives no R. For damping, take
each loop's DC resistance from the sheet solver on native-17
(`round4/reextract` in task 04 has most paths) and scale it by
thickness/(2 × skin depth) at 10 MHz as an estimate, labelled as such. If
the Palace build supports a finite-conductivity (surface-impedance) driven
solve, a Z-matrix at 1/10/30 MHz is a better source; optional.

**D2 deck change.** In `complementary_leg.cir` (round-4 D2 copy), remove the
scalar board inductances (LD_HS, LS_HS, LD_LS, LS_LS, LCAP, LCS, LG) and
insert the include. Split the local capacitor into its two physical branches
(C38 and C39, each 100 nF with its own ESL, kept at the 5–20 nH ASSUMED
bracket). Keep the Infineon package inductances. Then run ROUND-5 R5-D2
(the 724 V diagnosis with both device currents saved, then the grid), C1
and C2 as written there.

## 7. Once the matrix exists: design what-ifs

These are the point of doing this in simulation. Each is cheap once the
pipeline runs. Report each against the S1–S4 criteria:
- gate resistors R10/R12: 2.2, 3.9 (fitted), 6.8, 10 Ω;
- snubbers C12/C13: 0, 1 nF (fitted), 2.2 nF;
- a split turn-on/turn-off gate path (a resistor plus diode), modelled
  only: it's a circuit change;
- a negative off-state gate bias (−3 to −5 V), modelled only: it needs a
  driver-supply change;
- for any copper change D2 points to, move the copper in KiCad on a scratch
  copy, rerun §3–§5 for that leg only, and compare.

Nothing here changes the board or source. Findings go to the owner as
recommendations.

## 8. Rules that carry over

- Every number traces to a committed script and output (master plan §2).
- **Say "bound" only when it bounds.** The heatsink plate gives a bracket;
  narrower bridges don't bound anything.
- Stop and report on a contradiction between the board, the export and the
  netlist.
- One worker, one worktree. The Palace build and meshes are local; don't
  run a full workspace build in the worktree.
- Hand back uncommitted; the coordinator commits with the co-author line
  it is given.
