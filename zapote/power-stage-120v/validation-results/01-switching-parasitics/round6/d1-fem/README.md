# 01 round 6 D1 FEM — BLOCKED before board inductance extraction

- Board: `native-17/section.kicad_pcb`, SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`
- Date: 2026-09-28; operator/model: Codex / gpt-6-sol; source/tool identities: [tool-identity.json](tool-identity.json)
- Evidence class: exact structural for source hashes, KiCad pad positions and STEP import; simulation/model-based for fixture energies; no physical measurement
- Verdict: **BLOCKED**. No 4×4 board matrix, SPICE include, or downstream switching rerun is qualified.

## Summary

Palace did not produce a binary in the plan's two allowed build attempts. The first build failed linking MFEM's example against HYPRE/BLAS; after a local MFEM link configuration repair, the second reached Palace and failed because the reduced build had both ARPACK and SLEPc disabled. This is a specific configuration failure, not proof that Palace cannot run on this machine. No third Palace build was attempted.

The pinned Elmer fallback builds and passes three upstream magnetic CTests. On a coax current-sheet fixture, a direct tree-gauge solve at 0.25 mm gives 13.745 nH versus 13.863 nH analytic (0.85% low at nominal 1 A). The discretized source is not exactly current-conserving: four sampled circular cuts carry 0.999669–1.011119 A. The scalable Hypre/AMS solve does **not** reproduce the same 0.35-mm direct result. A verbose AMS run stagnates at relative residual 9.723 against the requested 1e-9, yet Elmer exits zero and prints `ALL DONE`. The fixture method is therefore unqualified for a board solve. The [local verifier](scripts/verify_elmer_fixture.py) rejects that false success.

## Method and assumptions

The board STEP was exported from the pinned native-17 board with KiCad 10.0.4's D1-FEM copper flags. `kicad-cli` exits 2 after OCC fuse warnings and a macOS file-attribute warning, but writes a 17 MB STEP. Independent gmsh 4.15.2 import finds 84 copper solids, 11,857 surfaces, and Z extent −0.070 to 1.563 mm. The STEP SHA-256 is `07e8a14caa1f2b1888576dbece1e4356350f593d3bef12cc5d4d928a6ac17aff`. This establishes only structural importability; it does not prove every conductor link or port closure. The exact command and checks are in [export_step.py](scripts/export_step.py).

The coax fixture uses an annular air volume (inner radius 0.5 mm, outer 2 mm, length 50 mm), PEC inner/outer walls and one end short, plus a current sheet on the other end. The analytic value is `μ0·length·ln(outer/inner)/(2π) = 13.8629436112 nH`. The [geometry script](scripts/make_coax.py) checks positive tetrahedral Jacobians. ElmerGrid scales mm to SI metres. The source is a nominal 1 A radial sheet `K_r=1/(2πr)`; Elmer's pinned `WhitneyAVSolver.F90::LocalMatrixBC` applies the `Magnetic Field Strength` vector directly as `−L·edge_basis`, without rotating it by the surface normal. An initial azimuthal-H input and later cylindrical-wall diagnostic were rejected; their SIFs and logs remain in `raw/`. The corrected direct configuration is [coax-0p25.sif](fixtures/coax-0p25.sif). Copper is treated as perfect conductor, as specified in D1-FEM for edge-frequency inductance; no resistance is inferred.

The direct solve uses UMFPACK and Elmer's default tree gauge. A second Elmer build enables MPI/Hypre and applies the pinned upstream `mgdyn_hypre_ams` solver pattern to the *same* 0.35-mm mesh and source. `AMS Singular Matrix=True` is a documented pinned-source option tested once with verbose residual logging; it does not rescue the solve. A zero process exit or `ALL DONE` is not counted as convergence. Raw SIFs, logs, caches, meshes and build receipts are hashed in [raw-manifest.sha256](raw-manifest.sha256).

## Results

| Coax mesh | Tetrahedra; min Jacobian | Direct magnetic energy | Nominal `2E/I²` | Error vs analytic |
| --- | ---: | ---: | ---: | ---: |
| 0.50 mm | 25,041; positive | 6.662585 nJ | 13.325170 nH | −3.88% (fails 2%) |
| 0.35 mm | 66,006; positive | 6.839985 nJ | 13.679970 nH | −1.32% |
| 0.25 mm | 179,590; 0.004781 mm³ | 6.872621 nJ | 13.745242 nH | −0.85% |

At 0.25 mm the sampled cuts at radii 0.6/1.0/1.5/1.9 mm carry 1.011119/0.999669/1.000460/1.001476 A. Their **sampled range** is 1.145 percentage points, not a rigorous continuity bound. The area-average current is 1.003278 A; dividing the 0.25-mm energy result by its square gives 13.655578 nH (−1.50%). It is an average, not a uniquely conserved branch current. Normalizing instead by the sampled cut extrema gives 13.445–13.754 nH, so the fixture cannot be called an unqualified 1 A port proof. At 0.35 mm, a 2 A excitation gives 4× the 1 A energy to the printed precision, and reversing 1 A leaves energy unchanged. Details and cut definitions are in [check_coax_source.py](scripts/check_coax_source.py) and `raw/coax-*-source.json`.

| Same 0.35-mm mesh/source | Magnetic energy | Relative residual evidence | Classification |
| --- | ---: | --- | --- |
| Direct tree gauge | 6.839985 nJ | Direct factorization; no iterative residual | Numerical reference only |
| Upstream-style Hypre/AMS | 1.777093 nJ | No residual printed at output level 5 | Fail: 74% energy disagreement |
| AMS plus singular-matrix option | 10,256.04 nJ | Last printed relative residual 9.723099 vs 1e-9; wrapper says zero required iterations/norm 1 | Fail despite exit 0/`ALL DONE` |

The [verifier's actual outputs](fixtures/) classify the direct log as a **nominal numerical log screen only** and reject the AMS log. Six captured-log mutations verify that a missing residual, a plausible energy with bad residual, a nonfinite tolerance, an explicit error marker, and final NaN energy/residual values after earlier valid values cannot pass; see [verifier-mutation-check.json](fixtures/verifier-mutation-check.json). The [STEP export stale-output check](fixtures/export-stale-output-check.json) proves an existing target is refused before KiCad runs. The [Gmsh binary-to-ASCII roundtrip check](fixtures/mesh-conversion-check.json) matches physical groups, node coordinates and oriented element connectivity after accounting for Gmsh's node renumbering.

The parallel-plate air mesh was generated and checked structurally (1,787,643 positive-Jacobian tetrahedra, minimum 0.000935949 mm³); no plate solve was started after the scalable coax solver failed. The upstream rings mesh was copied and hashed, but the mutual fixture was not solved. **Neither fixture has a pass result.** The board was not cropped or meshed for field solving, and no leg-A/leg-B matrix was computed.

## Sensitivity and open items

- The direct nominal coax value changes +0.065272 nH (+0.48%) from 0.35 to 0.25 mm. The source's sampled cut range remains about 1%; it must be included in any fixture uncertainty, not hidden by choosing a favorable normalization.
- The [negative geometry control](fixtures/straight-bridge-negative.json), queried from KiCad's actual native-17 pad positions, shows that a straight G–S bridge runs through the drain pad center on Q2, Q3, Q5 and Q6. Any resumed extraction needs an audited dogleg/elevated closure contacting exactly G and S at all bridge widths. A nominal 15 mm capacitor port sheet and approximately 11 mm G–S closure can contribute field energy; reference-plane and component ESL/package de-embedding remain open.
- The board crop bounds in [crop_step.py](scripts/crop_step.py) include shared R5 pad 1 at x=127.135 mm and pad 4 at x=125.865 mm. This helper was **not run or validated**; no crop acceptance, mesh refinement, outer-box convergence, bridge-width sensitivity, element-order comparison, or heatsink bracket exists. The installed heatsink geometry is unselected, so a future perfect-conductor plate study must state assumed placement, not claim a rigorous installed-board bound.
- Palace can potentially resume from the saved build tree by enabling one required eigen backend (ARPACK or SLEPc), but this would be a third build attempt beyond D1-FEM's two-attempt limit; the coordinator controls that choice. **Dependency selection must be audited first:** the inner Palace cache records `MFEM_DIR=/tmp/ps-r6-fem-build1` but `MFEM_LIBRARY=/opt/homebrew/lib/libmfem.dylib`, so attempt 2 selected Homebrew MFEM despite the isolated MFEM repair. A future approved attempt must explicitly bind and inspect the intended `MFEM_LIBRARY` and include path, not assume `MFEM_DIR` wins. See `raw/build-records/palace-inner-CMakeCache.txt` and `build2.log`. If a solver does qualify, run all three analytic fixtures with the same current-port method before any board matrix, then D1-FEM's crop/mesh/bridge/heatsink checks. D2/C1/C2 stay on hold until accepted matrices exist. The first-board double-pulse procedure remains the physical switching check.

## Reproduce and handoff

Run from this `d1-fem/` directory. The local solver and source trees are intentionally under `/tmp/ps-r6-fem-*`; their pinned identities and full effective CMake caches are in [tool-identity.json](tool-identity.json) and `raw/build-records/`. The Palace build's nondefault feature choices were `PALACE_WITH_SUPERLU=OFF`, `PALACE_WITH_SLEPC=OFF`, `PALACE_WITH_LIBXSMM=OFF`, `PALACE_WITH_MAGMA=OFF`, `PALACE_WITH_GSLIB=OFF`, `PALACE_WITH_SUNDIALS=OFF`; `PALACE_WITH_ARPACK=OFF` was also effective. This **specific pair of eigen backends both OFF** caused attempt 2's Palace configure failure. MFEM's direct reconfigure set `MFEM_USE_LAPACK=YES` after attempt 1's BLAS link failure. The raw caches are the authoritative effective flag records; neither Palace failed build was silently retried a third time.

These commands reproduce the **effective saved configurations** (the original shell invocation is not preserved; the CMake caches are the exact configuration evidence). They document the two failed Palace attempts and the successful Elmer builds, not permission to launch another Palace attempt:

```sh
cmake -S /tmp/ps-r6-fem-palace -B /tmp/ps-r6-fem-build1 -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=/usr/bin/clang -DCMAKE_CXX_COMPILER=/usr/bin/clang++ -DCMAKE_INSTALL_PREFIX=/tmp/ps-r6-fem-build1 -DPALACE_BUILD_EXTERNAL_DEPS=ON -DPALACE_WITH_SUPERLU=OFF -DPALACE_WITH_SLEPC=OFF -DPALACE_WITH_ARPACK=OFF -DPALACE_WITH_LIBXSMM=OFF -DPALACE_WITH_MAGMA=OFF -DPALACE_WITH_GSLIB=OFF -DPALACE_WITH_SUNDIALS=OFF
cmake --build /tmp/ps-r6-fem-build1 -j 6  # attempt 1: MFEM/HYPRE BLAS link failure
cmake -S /tmp/ps-r6-fem-build1/extern/mfem -B /tmp/ps-r6-fem-build1/extern/mfem-build -DMFEM_USE_LAPACK=YES
cmake --build /tmp/ps-r6-fem-build1 -j 6  # attempt 2: Palace requires ARPACK or SLEPc
cmake -S /tmp/ps-r6-fem-elmer -B /tmp/ps-r6-fem-elmer-build -DCMAKE_C_COMPILER=/opt/homebrew/bin/gcc-16 -DCMAKE_CXX_COMPILER=/opt/homebrew/bin/g++-16 -DCMAKE_Fortran_COMPILER=/opt/homebrew/bin/gfortran-16 -DCMAKE_INSTALL_PREFIX=/tmp/ps-r6-fem-elmer-install -DWITH_MPI=OFF -DWITH_Hypre=FALSE -DWITH_ELMERGUI=OFF -DBUILD_TESTING=ON -DBLAS_LIBRARIES=/opt/homebrew/opt/openblas/lib/libopenblas.dylib -DLAPACK_LIBRARIES=/opt/homebrew/opt/openblas/lib/libopenblas.dylib
cmake --build /tmp/ps-r6-fem-elmer-build -j 6
ctest --test-dir /tmp/ps-r6-fem-elmer-build -R '^mgdyn_steady_(coils|plate|wire)$' --output-on-failure  # 3/3 pass
cmake --install /tmp/ps-r6-fem-elmer-build
cmake -S /tmp/ps-r6-fem-elmer -B /tmp/ps-r6-fem-elmer-hypre-make -DCMAKE_C_COMPILER=/opt/homebrew/bin/gcc-16 -DCMAKE_CXX_COMPILER=/opt/homebrew/bin/g++-16 -DCMAKE_Fortran_COMPILER=/opt/homebrew/bin/gfortran-16 -DCMAKE_INSTALL_PREFIX=/tmp/ps-r6-fem-elmer-hypre-install -DWITH_MPI=ON -DWITH_Hypre=TRUE -DHYPRE_ROOT=/tmp/ps-r6-fem-build1 -DWITH_ELMERGUI=OFF -DWITH_OpenMP=OFF -DBUILD_TESTING=OFF -DBLAS_LIBRARIES=/opt/homebrew/opt/openblas/lib/libopenblas.dylib -DLAPACK_LIBRARIES=/opt/homebrew/opt/openblas/lib/libopenblas.dylib
cmake --build /tmp/ps-r6-fem-elmer-hypre-make -j 6
cmake --install /tmp/ps-r6-fem-elmer-hypre-make
```

Verify the frozen evidence before rerunning anything:

```sh
shasum -a 256 -c raw-manifest.sha256
python3 scripts/verify_elmer_fixture.py raw/coax-0p25-radial.log
python3 scripts/verify_elmer_fixture.py raw/coax-0p35-ams-singular.log --iterative  # expected exit 1
python3 scripts/check_verifier_mutations.py raw/coax-0p25-radial.log raw/coax-0p35-ams-singular.log
```

A fresh direct-coax rerun uses a separate temporary directory and verifies its **new** log. This recipe has not been executed as one block by the coordinator; the individual geometry, conversion and solver stages were exercised during fixture work.

```sh
(
  set -eu
  D1_FEM_ROOT="$PWD"
  D1_FEM_RERUN=$(mktemp -d /tmp/ps-r6-coax-rerun.XXXXXX)
  mkdir -p "$D1_FEM_RERUN/raw"
  cp fixtures/coax-0p25.sif "$D1_FEM_RERUN/coax.sif"
  PYTHONPATH=/opt/homebrew/lib /Users/bennet/Miniforge3/bin/python3 scripts/make_coax.py "$D1_FEM_RERUN/raw/coax-0p25.msh" --size 0.25
  PYTHONPATH=/opt/homebrew/lib /Users/bennet/Miniforge3/bin/python3 scripts/convert_mesh_for_elmer.py "$D1_FEM_RERUN/raw/coax-0p25.msh" "$D1_FEM_RERUN/raw/coax-0p25-ascii.msh"
  /tmp/ps-r6-fem-elmer-install/bin/ElmerGrid 14 2 "$D1_FEM_RERUN/raw/coax-0p25-ascii.msh" -out "$D1_FEM_RERUN/raw/coax-0p25-elmer" -scale 0.001 0.001 0.001
  PYTHONPATH=/opt/homebrew/lib /Users/bennet/Miniforge3/bin/python3 scripts/check_coax_source.py "$D1_FEM_RERUN/raw/coax-0p25.msh" > "$D1_FEM_RERUN/source-current.json"
  cd "$D1_FEM_RERUN"
  ELMER_HOME=/tmp/ps-r6-fem-elmer-install /tmp/ps-r6-fem-elmer-install/bin/ElmerSolver coax.sif > coax.log 2>&1
  /Users/bennet/Miniforge3/bin/python3 "$D1_FEM_ROOT/scripts/verify_elmer_fixture.py" coax.log
)
```

The subshell stops on a nonzero command status; a zero solver status still requires the numerical log check and separate source-current assessment. The frozen raw files and their manifest are not changed by this rerun. No licensed vendor device model is included. The coordinator may commit this report/scripts/summaries and archive ignored `raw/` separately; this worker did not stage or commit anything.
