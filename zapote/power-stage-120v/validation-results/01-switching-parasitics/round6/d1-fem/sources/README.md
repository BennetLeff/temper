# Solver and board sources

- Board: `zapote/power-stage-120v/native-17/section.kicad_pcb`, SHA-256
  `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
- [Palace source](https://github.com/awslabs/palace), pinned commit
  `ca04eddeaa1d8f5345b8a51b5ce5cc578da3a8c7`. The official
  [magnetostatic problem guide](https://awslabs.github.io/palace/dev/guide/problem/)
  and [rings example](https://awslabs.github.io/palace/stable/examples/rings/)
  define SurfaceCurrent ports, inactive-port behavior and the upstream
  `rings.msh` fixture. Its copied mesh is in ignored `raw/`, SHA-256
  `2291c903231832cf5c69c9aff03ac78c931c94f2058da36931307c72b71888a5`.
- [Elmer source](https://github.com/ElmerCSC/elmerfem), release 26.2.1 pinned
  commit `a19504ac53ec222e3355e182b08f2ff280c2203a`. Source SHA-256:
  `fem/src/modules/MagnetoDynamics/WhitneyAVSolver.F90`
  `ba6e08584bcf2f8d7baed616ea932cbfcc7272889584571e5437e204a6fcf9e8`;
  `fem/src/SParIterSolver.F90`
  `7765cdad2306b1510f05e6a2ec6c24251e0903454632ecbc52222f21dc73579a`.
  The official [Elmer Models Manual](https://www.nic.funet.fi/index/elmer/doc/ElmerModelsManual.pdf)
  §18 describes the Whitney magnetic solver. The pinned source's
  `LocalMatrixBC` applies the vector under `Magnetic Field Strength`
  directly as `-L·WBasis`, so this extraction's radial end sheet passes
  a radial current-load vector, rather than an azimuthal H vector.
- Elmer's own `mgdyn_steady_coils`, `mgdyn_steady_plate`, and
  `mgdyn_steady_wire` CTests passed on the serial build. This validates
  the binary on those upstream cases, not the four-port board method.

No licensed vendor MOSFET model is present in this handback.
