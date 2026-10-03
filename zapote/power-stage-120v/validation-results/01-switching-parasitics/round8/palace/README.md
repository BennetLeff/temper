# Round 8 D1 FEM: Palace attempt 4

Status: **Palace build passed; first coax solve failed numerically.** The
second coax mesh and matched 20/80 mm plate configurations are prepared but
**unrun**. Mutual, board extraction and D2/C1/C2 remain held. This is
simulation and toolchain evidence, not a physical board measurement.

Input revision: `8b1615c8a622c05ee979014b1059b57cbc9e604f`; Palace source
`ca04eddeaa1d8f5345b8a51b5ce5cc578da3a8c7`. Operator: Codex / gpt-6-sol.
The native-17 board input remains the round-7 pinned SHA-256
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`;
no board mesh was built in this packet.

The sole authorized build change from round 7 was disabling GSLIB. The
round-7 final Palace link had selected `/opt/homebrew/lib/libgs.dylib`
(Ghostscript) instead of the required GSLIB archive. Attempt 4 ran from
21:56:00 to 22:37:02 UTC on 2026-09-28. The previous 2.8 GB build was copied
with clone-on-write into `/tmp/ps-r8-palace-build4`, and 3,527 generated text
files were relocated to the private prefix. The historical build tree was
never written. The private copy preserved the default CPU dependency choices
(ARPACK, SLEPc, SuperLU, LibXSMM, Sundials ON; GPU OFF), while both the Palace
superbuild and rebuilt MFEM set GSLIB OFF. MFEM kept LAPACK YES.

The inner CMake cache binds MFEM to
`/tmp/ps-r8-palace-build4/lib/libmfem.a` and compilation explicitly includes
`/tmp/ps-r8-palace-build4/include`. The rebuilt MFEM archive has no unresolved
`gslib_` symbol. Its SHA-256 is
`e1ca4466c01eed3a52f12db1e1e2760daf2a5bd07f13a7eac1556f4bb9e57656`.
During MFEM's completed install, the orchestration script was edited. The
running `zsh build_attempt4.sh mfem` process exited **1** with the tool-visible
message `build_attempt4.sh:88: unmatched '\n'`, after the archive and undefined
symbol record were written. That exact stderr was not captured to a raw file;
the script's pre-edit bytes are not recoverable. The source and compiler
output did not fail. The final script is a corrected replay recipe, not an
exact copy of the bytes that ran for the MFEM stage, and passes `zsh -n`.
The installed MFEM cache, archive hash, symbol record, Palace link and binary
were checked separately. No second MFEM build or extra Palace attempt was run
to erase the wrapper failure.
The generated final link was inspected **before** execution: it contains
exactly that MFEM archive and no `/opt/homebrew/lib/libgs`. A positive
prelink control passed; copied link commands with injected Ghostscript,
Homebrew MFEM, or historical MFEM were rejected.
The Palace binary linked and reports version `ca04edd`, SHA-256
`d581869906ca59b2f9fa479f41155df6ceca5a4b11bfe941b4aae360e4a30cfd`.
`otool -L` on the binary and copied `libceed`/`libxsmm` dependency chain
shows no Ghostscript or old build prefix. The copied dylibs' two install
names and one linked dependency were corrected; before/after output and
hashes are retained.

The round-7 prepared coax Palace JSON could not pass Palace's dry-run:
`CoordinateSystem` is forbidden with string `Direction: "+R"`; the source
parser says that string already implies cylindrical coordinates. The round-8
coax configs remove only that redundant key. The original failing JSON and
error log and a clean round-8 dry-run are retained in `raw/fixtures/`.
Palace's source sets excitation current to **1 in its internal units** for
each surface-current index. Its coaxial source is normalized by `2πr`.
`units.hpp` defines the physical current scale as
`Hc × Lc_m = 1/sqrt(Z0)`, so `terminal-I.csv` reports 0.051521 A for that
internal unit source. The plate source is likewise internally normalized by
its port width. These are input normalization facts, not independent solved
current-contour checks. The two accepted round-7 coax meshes have SHA-256
`4fca7a2431cdf2032fbc40f141fc3a423af2efcbe8dc6fbc039f9620eb3f4e39`
and `0bfac7659ce47553e083c1f21b4bcafbe96856a3c790305af90147937c52e947`.

The first Palace solve loaded 130,430 tetrahedra and ran PCG to its existing
`MaxIts=1000` limit. It explicitly reported **nonconvergence** with
`norm(Ax-b)/norm(b)=8.808e+06`; the final printed preconditioned residual
was `4.039164e+05` against `4.585844e-02` initially. Palace nevertheless
wrote finite terminal CSVs: `terminal-M.csv` says `6.860406900803e+07 H`
and `domain-E.csv` says `9.105196285730e+04 J`. Those numbers are **rejected**;
`verify_palace_coax.sh` rejects this actual log even though the CSV exists.
The source current in `terminal-I.csv` is the expected dimensionalized
0.051521 A and is not a failed-current diagnostic. Palace's own resource
report gives 2.3 GB estimated peak memory and 492.128 s elapsed. The
launch wrapper's recorded exit code is 1 because `/usr/bin/time -l` could
not read `kern.clockrate` in this sandbox; Palace's native exit code was not
separately captured. The explicit solver warning rejects the result
independently of that wrapper error. No additional Palace solve was started.

Replay from this directory requires the **existing local** 2.8 GB round-7
build tree at `/tmp/ps-r6-fem-build1`, and the pinned Palace source at
`/tmp/ps-r6-fem-palace`. The round-7 raw archive contains the fixture
meshes, but **does not** contain that build tree; this packet is not a
portable clean-machine bootstrap. Git revisions of external dependencies
and SHA-256 of the 40 copied local libraries are in
`build-source-revisions.tsv` and `build-local-libraries.sha256`. The MFEM,
ARPACK and SuperLU source trees carry the superbuild's patches; exact diffs
and hashes are in ignored `raw/build-records/`. GSLIB source was present in
the clone but was excluded from attempt 4.

With those local prerequisites and the two round-7 accepted mesh files
copied into `raw/fixtures/`, the recorded invocation sequence was:

```sh
zsh prepare_build_copy.sh
zsh build_attempt4.sh configure
zsh build_attempt4.sh mfem
zsh relocate_copied_dylibs.sh
zsh build_attempt4.sh palace-configure
zsh verify_prelink_guard.sh
zsh build_attempt4.sh palace-build
zsh run_palace_coax.sh coax-port0p10-vol0p30
zsh verify_palace_coax.sh coax-port0p10-vol0p30  # expected rejection
```

Build caches, logs, link command, dependency checks, dry-runs and rejected
fixture output are under ignored `raw/` and indexed by `raw-manifest.sha256`.
The manifest contains 67 local files (about 52 MB); `shasum -a 256 -c`
verified all 67 after the run. The vendor-model `.lib` and `.ibs` extensions
are banned by `make_raw_manifest.sh` and none are present.
No additional Palace build attempt or fixture run is authorized by this packet.
