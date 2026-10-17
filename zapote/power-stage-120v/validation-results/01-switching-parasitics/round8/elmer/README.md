# Round 8 D1: Elmer direct-solver and plate air-box checks

Evidence class: **simulation/model-based**. This packet tests the fixture
solver and finite air-box setup in the [D1 FEM procedure](../../../../validation-plan/D1-FEM.md).
It does not measure the board inductance. The mutual fixture, board extraction,
and D2/C1/C2 remain held until all three fixtures qualify.

## Solver identity and the 64-bit check

The pinned Elmer source is `a19504ac53ec222e3355e182b08f2ff280c2203a`.
The installed `ElmerSolver` SHA-256 is
`b12d9ea79bc83345c7458e9d991447f53186b0d814d4a54692a93f89e8747355`;
`MagnetoDynamics.dylib` is
`92bd4e1420ab93898dbea57240109816593ad0a6e0c9ba13419fe8df9f27e096`,
and `libelmersolver.dylib` is
`3713aea3c83682b636ee17d56f179f0d37029e93d4b6c3873e6a32c416501e58`.
No solver binary or source was rebuilt or modified in this round.

`DirectSolve.F90` selects the `umf4_l_*` calls for the exact SIF value
`Linear System Direct Method = Big Umfpack`. The pinned CMake build defines
`HAVE_UMFPACK` and `UMFPACK_LONG_FORTRAN_TYPE C_LONG`; its link command uses
Elmer's bundled `libumfpack.a`, which exports both `umfpack_di_numeric` and
`umfpack_dl_numeric`. The bundled `umf_realloc.c` returns null when an
allocation size exceeds `Int_MAX / size_of_object`. `HAVE_MUMPS` is absent;
MUMPS is unavailable in this installed runtime.

The two unchanged round-7 coax meshes passed the complete sampled-current
2% criterion with Big Umfpack. See [coax-evaluation.json](coax-evaluation.json):
13.794154–13.836063 nH on 130,430 tetrahedra and
13.794132–13.814638 nH on 229,668 tetrahedra, versus 13.862944 nH exact.
These intervals cover four sampled current cuts, not every possible cut.
The coarse Elmer solver log printed `ALL DONE` and the expected final energy,
but its `/usr/bin/time -l` wrapper returned 1 because sandboxed `sysctl` was
denied; this run has no peak-memory figure. The finer solve used scoped
resource-metric permission and exited 0. No model or mesh was changed for that
instrumentation issue.

The [input-identity check](input-identity.json) hashes all five core Elmer
mesh files for each coax rerun and the failed plate rerun; all match round 7
byte for byte. It also verifies that each SIF changes only the backend name
and output mesh path.

The **same** 165,394-tetrahedron plate mesh that returned `umf4num: -1` with
ordinary UMFPACK in round 7 solved with Big Umfpack. The Elmer mesh element
and node files are byte-identical to the round-7 failed case. The new solve
printed final equal field energy and coenergy `1.397491e-9 J`, `ALL DONE`, and
exit 0, or 2.794982 nH. Peak RSS was 3.20 GB; peak memory footprint was
4.59 GB. This strongly supports an integer-sized allocation/index limit as
the cause of that particular `-1`; the solver log does not reveal which
allocator branch returned null. It does **not** establish that a larger board
model fits on this machine.

## Full plate air-box study

The geometry remains two 10 × 50 mm ideal conducting sheets 0.5 mm apart,
with the 1 A port source and outer magnetic-insulation boundary from round 7.
The **full domain** is used; the rejected half-domain symmetry shortcut is
not used. All three meshes have the same 0.25 mm plate/gap target, 0.2 mm
near-field padding, 0.5 mm transition, and 12 mm far-field maximum size.
Only the outer air margin changes. Actual plate triangle sizes, the 500 mm²
area of each sheet, positive tetrahedra, source geometry, and 1 A at three
port cuts were audited before each solve. The local plate triangles were
identical across all three margins by the independent mesh audit (median
0.25 mm, 99th percentile 0.281616 mm). The 20 mm mesh is byte-identical
to round 7 (SHA-256
`c5e6b4208a648e197697fbe8964f9cae917f507219a1ec783d533af178ffe24d`).

| Air margin | Tetrahedra | Full-domain inductance | Peak RSS | Peak footprint | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| 20 mm | 226,819 | 2.802628 nH | 3.69 GB | 4.03 GB | Outside 2.85–3.14 nH |
| 40 mm | 264,195 | 2.816182 nH | 4.28 GB | 6.03 GB | Outside band |
| 80 mm | 417,956 | 2.828260 nH | 6.75 GB | 17.28 GB | Outside band |

The 20→40 mm change is +0.4836%; 40→80 mm is **+0.4289%**, within the
required 0.5% domain-change criterion. But the final result is
**0.021740 nH (0.763%) below 2.85 nH**. The plate fixture therefore
**does not pass** §5A. See [plate-margins.json](plate-margins.json) for
the paired source, mesh, log, and final-energy screens. The mutual fixture,
board extraction, and switching-model follow-ons remain held. The 80 mm
solve finished with final equal field energy and coenergy, `ALL DONE`, and
exit 0; the larger box did not close the value gap to the required band.

`raw/` retains the exact meshes, conversion and geometry audits, SIFs,
solver logs, exit codes, and macOS timing records. It is ignored by Git and
indexed by `raw-manifest.sha256`; no licensed vendor model is present.
The committed scripts prepare the studied meshes from the unchanged round-7
fixture tools and solve them with Big Umfpack. `OPENBLAS_NUM_THREADS=1`,
`OMP_NUM_THREADS=1`, and `VECLIB_MAXIMUM_THREADS=1` were explicit for the
20/40/80 mm series; the preliminary same-mesh index check did not set those
variables. Stack limit was 65,520 KB. `time -l` reports peak RSS and peak
memory footprint separately; its elapsed and CPU times differ substantially
on the larger cases, so neither is used to infer a speed benefit or exact
RAM needed by a board solve. The 80 mm run took 1,567 s elapsed and 1,354 s
user CPU, with 17.28 GB peak footprint; this does not establish the memory
cost of native-17's multi-conductor board model.

## Reproduction and retained evidence

Restore round 7's raw packet beside its committed scripts, export `R7_D1_ROOT`
to that `round7/d1-fem` directory, and run the following from this round-8
Elmer directory in a fresh checkout with an empty `raw/`:

```sh
zsh scripts/run_big_umfpack_existing.sh coax-port0p10-vol0p30
zsh scripts/run_big_umfpack_existing.sh coax-port0p08-vol0p25
zsh scripts/run_big_umfpack_existing.sh plates-box0p4-far4-m20
for label in coax-port0p10-vol0p30 coax-port0p08-vol0p25; do
  /Users/bennet/Miniforge3/bin/python3 \
    "$R7_D1_ROOT/../../round6/d1-fem/scripts/verify_elmer_fixture.py" \
    "raw/fixtures/$label-big.log" \
    > "raw/fixtures/$label-big-nominal-verification.json"
done

cp "$R7_D1_ROOT/raw/fixtures/plates-box0p25-far12-m20.msh" \
  raw/fixtures/plates-box0p25-far12-m20.msh
cp "$R7_D1_ROOT/raw/fixtures/plates-box0p25-far12-m20-mesh.json" \
  raw/fixtures/plates-box0p25-far12-m20-mesh.json
for margin in 40 80; do
  label="plates-box0p25-far12-m$margin"
  PYTHONPATH=/opt/homebrew/lib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    /Users/bennet/Miniforge3/bin/python3 "$R7_D1_ROOT/scripts/make_plates_box.py" \
    "raw/fixtures/$label.msh" --gap-size 0.25 --air-margin "$margin" \
    --far-size 12 --padding 0.2 --transition 0.5 \
    > "raw/fixtures/$label-mesh.json"
done
for margin in 20 40 80; do
  label="plates-box0p25-far12-m$margin"
  zsh scripts/prepare_plate.sh "$label"
  zsh scripts/solve_prepared_plate.sh "$label"
done
/Users/bennet/Miniforge3/bin/python3 scripts/check_round7_input_identity.py \
  "$R7_D1_ROOT" . > input-identity.json
/Users/bennet/Miniforge3/bin/python3 scripts/evaluate_results.py \
  "$R7_D1_ROOT" .
/Users/bennet/Miniforge3/bin/python3 scripts/make_raw_manifest.py \
  > raw-manifest.sha256
shasum -a 256 -c raw-manifest.sha256
```

The local manifest contains **96 files** and passed a full SHA-256 check.
The raw packet remains local for the coordinator's evidence storage decision.
The 20 mm mesh came from round 7 unchanged; the 40 and 80 mm mesh SHA-256
values are `16fb16a80d17ff78dc52502ed49d10ef2853bd7028807f866f162cb2f9ad524b`
and `1213abda76e8ba17807b65056d6688b3ea6d6431e284b856f9d09e69cb351f4a`.
