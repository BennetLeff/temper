# Native19 field matrices — round 4

**Both native19 reduced-mesh four-port matrices are actually solved.** The
independent native coupling check, selected horizontal refinement and local
C6 bulk matrix also pass. Two finer-mesh workflows reached linear convergence
but were stopped for system paging during field postprocessing. Neither
produced an accepted fine matrix. No field solver remains running.

These are numerical results on generated, source-matched geometry, not hardware
measurements or a current/power release. The board SHA-256 is
`3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.
The authoritative compact handoff is [results.json](results.json), with
[consumer limits](interface.json), [geometry identity](geometry.json),
[signed pad/net modes](port-map.json) and [runtime identity](environment.json).
Protected round2 and native19 files were not changed.

## Accepted matrices

All values below are nH. Preserve the port order and signed surface-current
vectors in the JSON; do not substitute one leg's matrix for the other.

**Leg A: C38, C39, gate-high, gate-low** — [pinned matrix](evidence/A-e4-h1-matrix.json).

```text
27.818028  16.999075   3.579547   5.186767
16.999075  27.247229   3.433299   5.233520
 3.579547   3.433299  24.475894  -0.290383
 5.186767   5.233520  -0.290383  34.174180
```

**Leg B: C40, C41, gate-high, gate-low** — [pinned matrix](evidence/B-e4-f4-h1-matrix.json).

```text
28.762329  19.933409   3.980617   3.290712
19.933409  31.015143   4.133970   3.380299
 3.980617   4.133970  26.859983  -0.224055
 3.290712   3.380299  -0.224055  28.977149
```

| Check | Leg A | Leg B |
|---|---:|---:|
| Actual tetrahedra | 990,341 | 1,361,532 |
| Near / far edge, mm | 4 / 6 | 4 / 4 |
| Maximum z step, mm | 1 | 1 |
| Minimum eigenvalue, nH | 10.530511 | 9.923061 |
| Maximum field-integral versus solver-energy difference | 3.22e-7 relative | 3.04e-7 relative |
| Largest sampled RSS among accepted four-column runs | 7.086 GiB | 7.974 GiB |

Every column is a converged, signed 1 A solve on that leg's exact recorded mesh.
`compose.py` rejects wrong mesh/port/SIF identity, unconverged receipts, incorrect
units, non-elemental field output, energy mismatch or nonpositive matrices.
Symmetry comes from the field inner product; it is not by itself an independent
reciprocity measurement.

An **independent simultaneous C38/gate-high excitation** on native A gives
M = 3.579609 nH versus 3.579547 nH from separate fields: absolute difference
6.2e-5 nH, relative 1.73e-5. It passes the pinned pair checker. A separately
solved reversed-current analytic control fails as intended.

The same-mesh A serial/restart100 result is 27.817975 nH, versus 27.818028 nH
with four ranks/restart200: a 1.91 ppm numerical repeat. Both rank count and
restart changed; their runtime effects cannot be separated from that pair.
This is not a mesh-convergence test.

## Selected refinement and bulk current

The selected A C38 horizontal refinement reduces near edge 4 to 2 mm while
keeping far edge 6 mm, z step 1 mm, closure, crop and air extent fixed. It gives
**28.145563 nH, +1.17742%** relative to the primary A diagonal. Energy agreement
is 1.20e-7 relative; peak observed RSS is 7.098 GiB with no newly recorded
Swapouts. This is one diagonal's observed sensitivity, not a certified global
error bound. [Result](evidence/A-selected-refinement-matrix.json).

The local C6 extension solves both C38 and C6 again on the **same extended
mesh**, producing `[C38,C6]`:

```text
27.772455  16.942696
16.942696  38.038505
```

It is positive definite (minimum eigenvalue 15.202291 nH) and agrees with
energy within 1.63e-7 relative. [Result](evidence/A5-selected-bulk-matrix.json).
The new port uses actual C6.1 BUS_P and C6.3 HV_RET pads. This is not the full
C5/C6 network. Its crop and far mesh differ from A4: do not splice it into
A4 or label its C38 difference as pure outer-boundary convergence.

## Geometry and interpretation

- **Finite closures remain included:** 1 mm artificial closure height, with
  2 mm gate-source bridges. These are not zero-height board-only matrices.
- Device/resistor PEC bridges close an extraction current basis; they are
  not an operating switch state or a complete nonlinear circuit. Preserve
  their topology when deciding where circuit parasitics belong.
- The R5 current closure uses actual pads `(127.135,10.120)` to
  `(125.865,15.080)` mm. Old 9.615/15.585 mm Y endpoints are not used.
- Closure endpoints use KiCad board coordinates. Surface-current vectors
  use FEM X=board X, Y=−board Y. Geometry is scaled from mm to m by 0.001;
  recorded K is already A/m and must not be scaled again.
- Copper defeaturing remains 0.05 mm simplification, 0.1 mm opening radius,
  0.05 mm² minimum islands, 0.02 mm thin-face merging and 0.01 mm grid.
  Via barrels are included. Every accepted mesh passes numeric port-current,
  closed-loop, PEC-column and nondegeneracy checks.
- Two initial B meshes had 2 and 1 zero-volume air tetrahedra. They were
  rejected; refining the far mesh removed them. No elements were deleted
  to make a failing geometry pass.

**Do not concatenate A and B into a block-diagonal eight-port model.** Missing
cross-leg mutuals are not zero, and the shared R5 return must not become two
independent shunt inductors. Kelvin copper is passive and cropped; it is not
a loaded Kelvin/reference impedance extraction. The air-domain PEC model
also excludes conductor resistance/loss, package parasitics, capacitor ESL,
trace ampacity, installed catch wiring, enclosure/heatsink coupling and the
electrostatic/common-mode network. Manufacturing tolerances and hardware
correlation remain unqualified. No 45 A limit is established.

## Fine-workflow resource evidence

The retained fine A mesh has **3,542,432 tetrahedra**, near/far edges 1/2 mm
and z step 0.25 mm. The retained fine B mesh has **4,207,066 tetrahedra** and
passes fresh topology checks, but its field solve was not launched. Changing
near edge, far edge and z step together would only establish combined
sensitivity; separate vertical, horizontal, boundary, crop and closure-height
convergence remains open.

| Actual fine A attempt | Default output | Elemental-B-only output |
|---|---:|---:|
| Linear iterations | 4,315 | 4,315 |
| Last linear residual | 9.96e-8 | 9.96e-8 |
| Elapsed to resource stop | 1,178.7 s | 1,198.7 s |
| Peak sampled process-tree RSS | 10.639 GiB | 12.894 GiB |
| Newly observed system Swapouts | 504,954,880 B | 921,108,480 B |
| Accepted field matrix | **No** | **No** |

Both stopped at CalcFields before a complete field result. The watcher samples
every two seconds; transient allocation/compression and system-wide paging
cannot be bounded by sampled RSS alone. Paging is observed at this phase but
cannot be uniquely attributed from a system-wide counter. Existing swap was
already substantial before these runs. The old approximately 47 GiB estimate
is not presented as a measured requirement. Failure evidence is retained under
`evidence/rejected/fine-A-default-postprocess/` and
`evidence/rejected/fine-A-elemental-postprocess/`.

The lean profile is nevertheless **numerically qualified for its tested
scope**. `run-elemental.py` delegates the unchanged pinned runner and solver,
using Elmer's supported Skip Nodal Fields option and omitting unused H/A
output. Analytic and nonuniform fixtures pass. On the native coarse reference,
it reproduces 27.818028 nH and every exported B vector exactly across all four
partitions (maximum difference 0 T, identical coordinates/tet indices).
See [qualification](elemental-qualification.json). This does not qualify its
fine-workflow memory use; the actual retry failed that resource condition.

## Reproduction and controls

Use the existing qualified FEM Python environment and local Elmer installation.
Runtime/package identities are in environment.json. Upstream tools reside in
the separate read-only ps-oracle checkout at advisory commit
`fda5ab9ece24ef1ee6f2317604c5ca73367d5201`; content hashes in
`round2/d17/upstream-inputs.json` are authoritative. No remote compute, uploads
or solver builds were used.

```bash
# src=this fields directory; mesh=a retained registered mesh; work=a new path.
FEM_PYTHON=/path/to/qualified/python bash "$src/solve-one.sh" \
  "$oracle" "$elmer" "$mesh" 10 4 "$work"
# Fresh primary campaign: retained primary meshes must already be in new_output.
bash "$src/solve-matrices.sh" "$oracle" "$elmer" "$new_output"
```

New work directories are required; prior evidence is never overwritten. Gmsh
is not byte-deterministic: regenerated meshes need new registration and new
solves through `FIELD_GEOMETRY`, never relabeling old results. The current
wrapper checks seven solver/grid/core/Hypre/MPI binary hashes; earlier wrapper
bytes are retained. Actual restart is recorded in case.sif and solver_lines;
the upstream display label incorrectly always says GMRES100.

`fine-matrices.sh` and `refinement-job.sh` are **unexecuted higher-RAM follow-on
profiles in their current forms**, guarded at >=64 GiB, with sampled 48 GiB RSS
limits, finite timeouts and paging guards. The former requests the two retained
fine matrices with the qualified lean output. The latter also varies closure
height, near mesh, z step, crop and outer-air extent. The watchdog is macOS-
specific; Linux needs separate monitor/runtime qualification. Neither script
promises memory/disk sufficiency or solves missing physical current modes.
The actual 32 GiB fine-campaign script is retained in evidence.

Qualification includes the exact two-port plate matrix, the nonuniform
floating-conductor fixture, independent pair energy, and rejecting controls
for wrong current sign, unconverged solver exit0, mixed-leg geometry,
degenerate meshes, time/RSS limits and insufficient host RAM. The Swapouts
controller test injects a synthetic counter increment; it is not real paging.

Complete meshes, solver logs and field outputs remain under
`output/temper-prototype-closure/round4/fields/`. Completed VTUs were losslessly
archived with decompressed SHA256 verification, then **all raw VTUs restored
byte-for-byte**, preserving original analysis paths; local gzip copies and
manifests are also retained. `archive-vtu.py --restore RUN...` reproduces that
restore. It excludes active, failed and out-of-scope runs. Compact source
receipts and compressed solver logs remain in evidence; checksums.json pins
this packet. No Git commit or push was performed by this field worker.
