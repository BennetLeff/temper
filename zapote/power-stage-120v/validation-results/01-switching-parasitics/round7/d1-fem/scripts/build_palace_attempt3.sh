#!/bin/zsh
set -euo pipefail

# Owner-authorized third and final Palace build campaign, 2026-09-28.
# Run from this d1-fem directory; all build output stays under /tmp.
ROOT=/tmp/ps-r6-fem-palace
BUILD=/tmp/ps-r6-fem-build1
RECORD="$PWD/raw/build-records"
mkdir -p "$RECORD"
date -u '+%Y-%m-%d %H:%M:%S UTC' > "$RECORD/attempt3-start.txt"
git -C "$ROOT" rev-parse HEAD > "$RECORD/palace-source-commit.txt"

if ! rg -q '^MFEM_USE_LAPACK:BOOL=YES$' "$BUILD/extern/mfem-build/CMakeCache.txt"; then
  print -u2 'Repaired MFEM cache lacks MFEM_USE_LAPACK=YES'
  exit 1
fi
if ! test -s "$BUILD/lib/libmfem.a"; then
  print -u2 'Local static MFEM archive is missing'
  exit 1
fi

# CMake's inner find_library cached Homebrew MFEM despite MFEM_DIR. Preseed
# the exact local archive; ExternalProject passes MFEM_DIR without -U, so this
# value survives its configure step. The generated link command must confirm.
/usr/bin/python3 - "$BUILD/palace-build/CMakeCache.txt" "$BUILD/lib/libmfem.a" <<'PY'
import pathlib
import sys

cache = pathlib.Path(sys.argv[1])
library = sys.argv[2]
lines = cache.read_text().splitlines()
matches = [i for i, line in enumerate(lines) if line.startswith('MFEM_LIBRARY:FILEPATH=')]
if len(matches) != 1:
    raise SystemExit(f'Expected one MFEM_LIBRARY cache entry, got {len(matches)}')
lines[matches[0]] = 'MFEM_LIBRARY:FILEPATH=' + library
cache.write_text('\n'.join(lines) + '\n')
PY

cmake -S "$ROOT" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
  -DCMAKE_Fortran_COMPILER=/opt/homebrew/bin/gfortran-16 \
  -DCMAKE_INSTALL_PREFIX="$BUILD" \
  -DCMAKE_PREFIX_PATH='/opt/homebrew;/opt/homebrew/opt/openblas' \
  -DBLAS_LAPACK_LIBRARIES='/opt/homebrew/opt/openblas/lib/libopenblas.dylib$<SEMICOLON>-lm' \
  -DPALACE_BUILD_EXTERNAL_DEPS=ON \
  -DPALACE_WITH_ARPACK=ON \
  -DPALACE_WITH_SLEPC=ON \
  -DPALACE_WITH_SUPERLU=ON \
  -DPALACE_WITH_LIBXSMM=ON \
  -DPALACE_WITH_GSLIB=ON \
  -DPALACE_WITH_SUNDIALS=ON \
  -DPALACE_WITH_MAGMA=OFF \
  -DMFEM_DIR="$BUILD" \
  > "$RECORD/attempt3-configure.log" 2>&1

cp "$BUILD/CMakeCache.txt" "$RECORD/palace-superbuild-configured-CMakeCache.txt"
rg '^(PALACE_WITH_|MFEM_DIR|CMAKE_Fortran_COMPILER)' "$BUILD/CMakeCache.txt" \
  > "$RECORD/attempt3-effective-flags.txt"

cmake --build "$BUILD" -j 4 \
  > "$RECORD/attempt3-build.log" 2>&1

cp "$BUILD/palace-build/CMakeCache.txt" "$RECORD/palace-inner-final-CMakeCache.txt"
cp "$BUILD/extern/mfem-build/CMakeCache.txt" "$RECORD/mfem-final-CMakeCache.txt"
shasum -a 256 "$BUILD/lib/libmfem.a" "$BUILD/extern/mfem-build/libmfem.a" \
  > "$RECORD/mfem-final-sha256.txt"
date -u '+%Y-%m-%d %H:%M:%S UTC' > "$RECORD/attempt3-end.txt"
