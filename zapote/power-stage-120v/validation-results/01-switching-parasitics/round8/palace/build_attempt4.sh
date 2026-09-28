#!/bin/zsh
set -euo pipefail

# Palace attempt 4: the approved Ghostscript/GSLIB collision fix only.
# The caller must first clone and relocate the round-7 build tree into BUILD.
ROOT=/tmp/ps-r6-fem-palace
BUILD=/tmp/ps-r8-palace-build4
RECORD=${0:A:h}/raw/build-records
PREFLIGHT=${0:A:h}/check_prelink.sh
mkdir -p "$RECORD"

case ${1:-} in
  configure)
    date -u '+%Y-%m-%d %H:%M:%S UTC' > "$RECORD/attempt4-start.txt"
    git -C "$ROOT" rev-parse HEAD > "$RECORD/palace-source-commit.txt"
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
      -DPALACE_WITH_GSLIB=OFF \
      -DPALACE_WITH_SUNDIALS=ON \
      -DPALACE_WITH_MAGMA=OFF \
      -DMFEM_DIR="$BUILD" \
      > "$RECORD/attempt4-superbuild-configure.log" 2>&1
    cp "$BUILD/CMakeCache.txt" "$RECORD/attempt4-superbuild-cache.txt"
    rg '^(PALACE_WITH_|MFEM_DIR|CMAKE_INSTALL_PREFIX)' "$BUILD/CMakeCache.txt" \
      > "$RECORD/attempt4-effective-options.txt"
    ;;
  mfem)
    cmake -S "$BUILD/extern/mfem" -B "$BUILD/extern/mfem-build" \
      -DCMAKE_INSTALL_PREFIX="$BUILD" -DMFEM_USE_GSLIB=NO \
      > "$RECORD/attempt4-mfem-configure.log" 2>&1
    cp "$BUILD/extern/mfem-build/CMakeCache.txt" "$RECORD/attempt4-mfem-cache.txt"
    rg -q '^MFEM_USE_GSLIB:BOOL=NO$' "$BUILD/extern/mfem-build/CMakeCache.txt"
    rg -q '^MFEM_USE_LAPACK:BOOL=YES$' "$BUILD/extern/mfem-build/CMakeCache.txt"
    cmake --build "$BUILD/extern/mfem-build" -j 2 --target install \
      > "$RECORD/attempt4-mfem-build.log" 2>&1
    shasum -a 256 "$BUILD/lib/libmfem.a" > "$RECORD/attempt4-mfem-archive.sha256"
    nm -u "$BUILD/lib/libmfem.a" > "$RECORD/attempt4-mfem-undefined.txt" 2>&1
    if rg -qi 'gslib_' "$RECORD/attempt4-mfem-undefined.txt"; then
      print -u2 'MFEM still references GSLIB; stop before Palace configure'
      exit 1
    fi
    ;;
  palace-configure)
    cmake -S "$ROOT/palace" -B "$BUILD/palace-build" \
      -DCMAKE_INSTALL_PREFIX="$BUILD" \
      -DPALACE_WITH_GSLIB=OFF -DPALACE_WITH_ARPACK=ON \
      -DCMAKE_CXX_FLAGS="-I$BUILD/include" \
      -DMFEM_DIR="$BUILD" -DMFEM_LIBRARY="$BUILD/lib/libmfem.a" \
      > "$RECORD/attempt4-palace-configure.log" 2>&1
    cp "$BUILD/palace-build/CMakeCache.txt" "$RECORD/attempt4-palace-cache.txt"
    cp "$BUILD/palace-build/CMakeFiles/palace.dir/link.txt" "$RECORD/attempt4-palace-link.txt"
    rg -q "^MFEM_LIBRARY:FILEPATH=$BUILD/lib/libmfem.a$" "$BUILD/palace-build/CMakeCache.txt"
    rg -q '^PALACE_WITH_GSLIB:BOOL=OFF$' "$BUILD/palace-build/CMakeCache.txt"
    rg -q -- "-I$BUILD/include" "$BUILD/palace-build/CMakeFiles/libpalace.dir/flags.make"
    zsh "$PREFLIGHT" "$BUILD/palace-build/CMakeFiles/palace.dir/link.txt" \
      > "$RECORD/attempt4-prelink.txt" 2>&1
    ;;
  palace-build)
    cmp "$RECORD/attempt4-palace-link.txt" "$BUILD/palace-build/CMakeFiles/palace.dir/link.txt"
    zsh "$PREFLIGHT" "$BUILD/palace-build/CMakeFiles/palace.dir/link.txt" \
      >> "$RECORD/attempt4-prelink.txt" 2>&1
    cmake --build "$BUILD/palace-build" -j 2 --target palace \
      > "$RECORD/attempt4-palace-build.log" 2>&1
    otool -L "$BUILD/palace-build/palace-arm64.bin" > "$RECORD/attempt4-otool.txt"
    date -u '+%Y-%m-%d %H:%M:%S UTC' > "$RECORD/attempt4-end.txt"
    ;;
  *)
    print -u2 'Usage: build_attempt4.sh {configure|mfem|palace-configure|palace-build}'
    exit 2
    ;;
esac
