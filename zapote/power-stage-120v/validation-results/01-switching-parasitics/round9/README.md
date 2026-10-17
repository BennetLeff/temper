# D1-FEM round 9: Palace qualification fixtures

- Board: unchanged native-17 (not solved in this round).
- Solver: Palace, the round-8 build (`/tmp/ps-r8-palace-build4/palace-build/palace-arm64.bin`,
  SHA-256 `d581869906ca59b2f9fa479f41155df6ceca5a4b11bfe941b4aae360e4a30cfd`),
  single process. Operator: Claude, 2026-09-28.
- Evidence class: simulation/model-based. Every number is in
  `results/palace-fixtures.json`; meshes and logs are local (regenerate with
  the scripts and `configs/`).
- **Verdict: Palace is exact when the port lies on the domain boundary, but
  not qualified for interior port sheets, which is what the board model
  needs. D1 stays blocked; D2/C1/C2 stay held.**

## Results

| Fixture | Result | Reading |
| --- | --- | --- |
| Palace's own `rings` example (field probe removed: it needs GSLIB, which the build omits) | converged; matrix equals Palace's reference to ~7 significant figures (M_aa 42.7388, M_bb 714.103, M_ab 1.96024 pH) | **the build is correct** |
| Parallel-plate section, 0.5 mm gap, magnetic side walls, port **on the boundary** | 3.141592653 nH vs exact 3.141592654 nH (−1.3×10⁻¹⁰); 16 iterations | Palace exact for a flat, constant-direction port on the boundary |
| The same section with the port **2 mm inside** (air behind it) | diverged (p1 residual ratio 0.049; p2 5.7×10⁵) | interior port fails where the exact answer is unchanged |
| Coax, interior annular port, radial `+R` | diverged (residual 5.8×10¹⁴ at 250 iterations; stopped) | radial coaxial element not usable in magnetostatics |
| Toroidal cavity, curved band port `+Z` | diverged (residual ratio 1.8×10⁴) | curved port not usable |
| Open plate pair, zero-thickness plates (round-8 Elmer meshes), interior port | converged: 3.1178 (p1, m20), 3.2657 (p2, m20), 3.2866 nH (p2, m80). Elmer on the same meshes: 2.8026 / 2.8283 nH | **Palace exceeds a rigorous upper bound** (below) |
| Open plate pair, **70 µm thick plates cut from the air** (the board's way), interior port, 40 mm margin | converged: 3.1850 (p1), 3.2710 nH (p2); 6.4 / 12.2 GB peak RSS | same excess: not a zero-thickness artefact |

**The upper bound.** The section's field, extended by zero into the
surrounding air, is an admissible field for the open plate pair (same
currents, same conductors). By the minimum-energy principle for fixed
current, the open pair's energy is no larger, so **L_open ≤ 3.14159 nH**.
Elmer (2.83 nH) and Wheeler's 2-D estimate (2.873 nH) satisfy it; Palace's
3.27 nH doesn't. With Palace also diverging on the one interior-port case
that has an exact answer, its interior-port sources aren't trustworthy yet.

A diagnostic with the air box ended at the port plane gave 0.41 nH and is
discarded: that box face became a PEC wall touching both plates and shorted
the port.

## Findings for the plan

1. Palace magnetostatic sources must be **flat, with a constant direction**
   (radial and curved ports diverged). The board's port sheets already are.
2. Palace is **not qualified for interior port sheets**. Every board port is
   one (a sheet across a component's pads, air all around).
3. Palace's `rings` self-inductances are 1–2.3 % above analytic, in the
   same direction as the plate excess; its interior port may be the reason.
   Treat the rings mutual (−0.69 % vs analytic) as unqualified too.
4. Elmer remains consistent with the bound and with Wheeler. It is first
   order, converges from below, and is memory-limited (round 8).

## Reproduce

```sh
PY=/Users/bennet/Miniforge3/bin/python3; export PYTHONPATH=/opt/homebrew/lib
$PY scripts/make_plate_section.py sect.msh --h 0.25               # boundary port
$PY scripts/make_plate_section.py secti.msh --h 0.25 --behind 2   # interior port
$PY scripts/make_thick_plates.py thick.msh                        # board-style plates, 40 mm margin
$PY scripts/make_coax_interior.py coax.msh --a 0.5 --b 2.0 --h-near 0.3
$PY scripts/make_toroid_band.py tor.msh --a 0.5 --b 2.0 --h-near 0.4
# fill @MESH@/@OUT@ in configs/*.template.json (Order 1 or 2), then:
env OMPI_MCA_btl=self OMP_NUM_THREADS=1 /tmp/ps-r8-palace-build4/palace-build/palace-arm64.bin config.json
```
