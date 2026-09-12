# Native Mac installation

Verified on arm64 macOS on 2026-09-12. Gmsh is installed by Homebrew;
Elmer is installed at `/Users/bennet/.local/opt/elmer-26.2.1`.
The reference command takes explicit executable paths, so no shell profile
changes or globally shadowing wrapper scripts are needed.

## Reproduce

Install prerequisites with Homebrew (already present on this host except Gmsh):

```sh
brew install gmsh cmake gcc open-mpi
```

Use a fresh source and build directory. Pin the official annotated release tag
to its underlying commit, not a moving branch:

```sh
git clone --depth 1 --branch release-26.2.1 \
  https://github.com/ElmerCSC/elmerfem.git /tmp/zapote-elmer-src
git -C /tmp/zapote-elmer-src rev-parse HEAD
# Must be a19504ac53ec222e3355e182b08f2ff280c2203a

cmake -S /tmp/zapote-elmer-src -B /tmp/zapote-elmer-build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$HOME/.local/opt/elmer-26.2.1" \
  -DCMAKE_C_COMPILER=/opt/homebrew/bin/gcc-16 \
  -DCMAKE_CXX_COMPILER=/opt/homebrew/bin/g++-16 \
  -DCMAKE_Fortran_COMPILER=/opt/homebrew/bin/gfortran \
  -DWITH_MPI=TRUE -DWITH_OpenMP=TRUE \
  -DWITH_ELMERGUI=FALSE -DWITH_ELMERPOST=FALSE
cmake --build /tmp/zapote-elmer-build --parallel 8
cmake --install /tmp/zapote-elmer-build
```

Recorded dependencies: CMake 4.4.3, GCC/GFortran 16.2.0, Open MPI 5.0.9;
BLAS/LAPACK use Apple's Accelerate framework. Gmsh's Homebrew package is
4.15.2; the binary reports `4.15.2-git`. Elmer's release tag is 26.2.1 but
its binary reports `26.2-unknown (Rev: a19504a)`. Preserve these literal
identities; neither suffix is evidence of a different source checkout.

AppleClang configuration failed to find OpenMP for C. Reconfiguring a fresh
build directory with GNU C, C++ and Fortran succeeded. The source and build
used about 0.5 GB before tests; the installed Elmer tree is about 43 MB.

## Verification and limitations

The installed solver passed its upstream `ConstantUnknownPotStatCurrent`,
`HeatAniso` and `ThermalActuator` reference tests when invoked directly as a
single process (`TEST.PASSED` = 1 for each). Retained logs are in
[native evidence](evidence/native-2026-09-12/).

The first CTest attempt could not launch through the host's existing `mpiexec`:
PRRTE reported a PMIx runtime/build ABI mismatch (`0x60100` vs `0x50009`).
This was an MPI launcher failure, before the solver ran. The direct serial
reference succeeds. Multi-process MPI remains unverified and requires repairing
that host dependency mismatch; no parallel speedup is claimed.

OpenMP was also exercised with four threads on the 10,392-node bar mesh.
Elmer reported four threads and produced byte-identical scalar results to the
single-thread run. Observed wall times were 1.09 s and 1.12 s respectively;
one small case is not a scaling benchmark. See the retained `openmp/` evidence.

For serial reference runs set `OMP_NUM_THREADS=1` and `OMPI_MCA_btl=self`.
The latter avoids opening a TCP listener for a single-process solve in the
desktop sandbox. These settings do not establish a configuration for distributed
MPI. The Rust runner records its actual runtime settings.

Future Linux/Ryzen installation should use the same pinned Elmer source and
reference cases, with host-appropriate compiler paths. It is not installed or
benchmarked on that desktop yet.
