# Round 8: local solver recovery, fixture qualification still blocked

**Status: BLOCKED at fixture qualification. SSH is not required to resolve the
failures observed in this round.** Palace attempt 4 built successfully on the
Mac. Elmer's 64-bit direct solver recovered the exact mesh that had failed,
and completed the plate air-box study. The plate value remains below its
acceptance band; Palace's first coax calibration failed to converge.

| Check | Result | Consequence |
| --- | --- | --- |
| Palace attempt 4 | Build and final link passed; GSLIB disabled | Mac build obstacle resolved; numerical qualification remains separate |
| Big Umfpack coax | Both original meshes pass the sampled-current 2% criterion | 64-bit direct backend qualified for these coax fixtures |
| Previously failing plate mesh | Same 165,394-tetrahedron mesh now solves; 2.794982 nH | Strong evidence for the prior 32-bit allocation/index limit, not a measured 32 GiB RAM ceiling |
| Plate air margins 20 / 40 / 80 mm | 2.802628 / 2.816182 / 2.828260 nH | Last change 0.4289% passes; final value fails 2.85–3.14 nH |
| Palace first coax | 1,000 iterations; relative residual 8.808e6 | Rejected despite written energy/matrix files; remaining Palace fixtures not run |

Mutual inductance, native-17 board extraction and D2/C1/C2 remain held. No
board matrices, circuit recommendations or fabrication release follow from
these results. The board, firmware and circuit sources were not changed.

## Evidence and authority

- [Elmer packet and reproduction commands](../01-switching-parasitics/round8/elmer/README.md)
- [Palace packet and reproduction commands](../01-switching-parasitics/round8/palace/README.md)
- [D1-FEM authority](../../validation-plan/D1-FEM.md), commit `8b1615c8a622c05ee979014b1059b57cbc9e604f` on PR #1615
- [Round-7 history](../round7-coordination/README.md)

Two fresh Codex workers using `gpt-6-sol` ran in isolated worktrees
`ps-r8-elmer` and `ps-r8-palace`; the coordinator owns verification and Git
writes. Evidence class: source/build provenance and simulation/model-based
results, not physical measurements. The native-17 PCB SHA-256 remains
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
Raw logs, meshes and rejected outputs stay local and ignored, with full
SHA-256 manifests in each packet. No licensed vendor model is included.

## What the memory test establishes

The coordinator independently compared five core Elmer mesh files for both
coax cases and the previously failing plate case: all are byte-identical to
round 7. Each SIF changes only the backend and result path. The failed mesh
now completes with equal field energy/coenergy `1.397491e-9 J`, `ALL DONE`,
and exit 0. Its peak RSS was 3.20 GB and peak memory footprint 4.59 GB.

Pinned Elmer source `a19504ac53ec222e3355e182b08f2ff280c2203a` links its
bundled UMFPACK statically. `Big Umfpack` selects the 64-bit wrappers; bundled
`umf_realloc.c` returns NULL if an allocation exceeds
`Int_MAX / size_of_object`. The same-mesh recovery strongly supports an
integer-sized allocation limit, but does not identify the exact failed
allocator branch. MUMPS is absent from this installed runtime.

The largest completed plate run has 417,956 tetrahedra and took 1,567 s,
with 6.75 GB peak RSS and 17.28 GB peak memory footprint. Those metrics are
different; RSS alone understates the memory burden. Host swap was already
in use before Palace's field solve. These fixture results do not establish
whether a converged multi-conductor board model fits on this Mac or on a
64 GB desktop.

## Palace build and runtime are separate outcomes

The authorized build ran 21:56:00–22:37:02 UTC on 2026-09-28. The old build
was cloned to a private directory; default CPU dependencies and ARPACK were
preserved, and MFEM was rebuilt with GSLIB off. Cache, explicit header path,
archive hash and pre-link checks bind the intended MFEM. The guard rejects
Ghostscript and extra MFEM libraries. The coordinator independently checked
the final binary's dependencies and SHA-256:
`d581869906ca59b2f9fa479f41155df6ceca5a4b11bfe941b4aae360e4a30cfd`.
The historical MFEM archive and Elmer binary still match their round-7 hashes.

One build-wrapper invocation ended with a shell parse error after MFEM had
installed because the worker edited the script while it was running. Its
exit was not clean; the executed script bytes were not captured. Independent
archive, configuration and final-link evidence establishes the completed
build. The final replay script is distinguished from that invocation in the
Palace packet. No additional build was run to conceal the wrapper failure.

The prepared round-7 Palace JSON also had an invalid `CoordinateSystem` key
alongside string `Direction`. Removing that redundant key in the round-8
copy passed the pinned binary's dry-run. The subsequent coax field solve
nevertheless failed its unchanged tolerance. Its finite energy and matrix
outputs are retained as rejected evidence, not inductance results. The
`time -l` wrapper separately returned 1 after a denied resource query; native
Palace exit status was not separately captured. Explicit nonconvergence is
the decisive failure, independent of the timing-wrapper status.

Palace's source current of 1 is in internal units. Its CURRENT conversion is
`Hc * Lc = 1 / sqrt(Z0)`, giving 0.051521 A here. The terminal current CSV is
therefore not evidence of lost source current. Earlier physical-1-A wording
is superseded. Any future energy-to-inductance calculation must use consistent
physical current and energy units, or the solver's dimensionalized matrix.

## Next decision and monitoring handoff

The two open questions are numerical qualification: why the Palace coax
solve diverges, and why the plate result remains below the fixed band after
passing the specified domain-change check. Enlarging the air box helped but
did not close that gap. Do not lower the band, accept rejected solver outputs,
or advance the board work on this evidence.

A next diagnostic plan should check Palace's fixture/source discretization
and null-space treatment against a known working example, and assess the
plate's remaining mesh and finite-length/reference assumptions. These are
proposed investigations, not runs completed here. No new build, parameter
sweep, board solve or SSH transfer is authorized by this handoff itself.
The desktop becomes relevant only when a measured resource requirement or
a specific cross-platform comparison calls for it; its OS, SSH details,
Docker availability and permitted working directory are still unknown.

## Review and validation

The coordinator verified all 163 raw-file hashes and the exact inventories,
reproduced both Elmer summaries, checked unchanged mesh inputs and restricted
SIF differences, and exercised link/input rejection controls. Python and shell
syntax, scoped Ruff, local document links, import boundaries, `make regen`
and `make regen-check` pass. Generated tracked files did not change.

Three Sol simplification passes found no warranted changes. The completed
[code-review receipt](review/review.json) found one broken procedure link;
the coordinator corrected it and verified the target. No findings remain
unresolved. The receipt preserves the original finding and coverage limits.
See [validation.json](validation.json) for checks and dispositions.

No additional operational monitoring is required: this packet changes
validation scripts and reports, not product runtime behavior.
