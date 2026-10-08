#!/bin/bash
# Round 18: build a patched copy of the Elmer install without touching the live one.
#   ~/temper-fem/elmer-install   live chain's install: read only (copied)
#   ~/temper-fem/build           live build tree: read only (objects, modules, link line)
#   ~/temper-fem/speedup/elmer-r18  new prefix: copy of the install with a relinked libelmersolver.so
# Only SParIterSolver.F90 is recompiled (patch_elmer_ams.py), into speedup/obj;
# the shared library is relinked from the build tree's other objects into the
# new prefix. ElmerSolver_mpi's RUNPATH is $ORIGIN/../lib/elmersolver, so the
# copy loads its own library. One CPU (taskset 23).
set -eu
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
S=$HOME/temper-fem/speedup B=$HOME/temper-fem/build E=$HOME/temper-fem/elmerfem
mkdir -p "$S/src" "$S/obj" "$S/mod"
[ -d "$S/elmer-r18" ] || cp -a "$HOME/temper-fem/elmer-install" "$S/elmer-r18"
python3 "$S/scripts/patch_elmer_ams.py" "$E/fem/src/SParIterSolver.F90" "$S/src/SParIterSolver.F90"
F=$B/fem/src/CMakeFiles/elmersolver.dir/flags.make
DEF=$(sed -n 's/^Fortran_DEFINES = //p' "$F")
INC=$(sed -n 's/^Fortran_INCLUDES = //p' "$F")
FLG=$(sed -n 's/^Fortran_FLAGS = //p' "$F" | sed 's|-J../../fmodules||')
cd "$B/fem/src"     # include paths are absolute; nothing is written here
# eval: the flags carry make-style quoting (-DCONTIG="") that must go through the shell once
eval taskset -c 23 nice -n 5 /usr/bin/f95 $DEF $INC -I"$B/fmodules" $FLG -J"$S/mod" \
  -c "$S/src/SParIterSolver.F90" -o "$S/obj/SParIterSolver.F90.o"
LINK=$(cat CMakeFiles/elmersolver.dir/link.txt)
LINK=${LINK//CMakeFiles\/elmersolver.dir\/SParIterSolver.F90.o/$S\/obj\/SParIterSolver.F90.o}
LINK=${LINK//-o libelmersolver.so/-o $S\/elmer-r18\/lib\/elmersolver\/libelmersolver.so}
LINK=${LINK//-Wl,--dependency-file=CMakeFiles\/elmersolver.dir\/link.d/}
case "$LINK" in *"$S/obj/SParIterSolver.F90.o"*"$S/elmer-r18/lib/elmersolver/libelmersolver.so"*|*"$S/elmer-r18/lib/elmersolver/libelmersolver.so"*"$S/obj/SParIterSolver.F90.o"*) ;;
  *) echo "link line substitution failed"; exit 1 ;; esac
# shellcheck disable=SC2086
taskset -c 23 nice -n 5 bash -c "$LINK"
sha256sum "$S/elmer-r18/lib/elmersolver/libelmersolver.so" "$HOME/temper-fem/elmer-install/lib/elmersolver/libelmersolver.so"
strings "$S/elmer-r18/lib/elmersolver/libelmersolver.so" | grep -c "R18: scaling"
