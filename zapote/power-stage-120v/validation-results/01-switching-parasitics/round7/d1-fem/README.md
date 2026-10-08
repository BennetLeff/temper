# 01 D1 finite-element continuation — round 7 result

- Board: `native-17/section.kicad_pcb`, SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`. No board mesh or board solve was run.
- Date: 2026-09-28 UTC; operator/model: Codex / gpt-6-sol. Exact source and tool identities are in [tool-identity.json](tool-identity.json).
- Evidence class: exact structural for hashes, build caches, mesh groups and serialized connectivity; simulation/model-based for fixture inductance. There is no physical measurement.
- Verdict: **BLOCKED** at the parallel-plate fixture. The coax fixture passes its amended sampled-current criterion, but the finest completed plate result is below the mandatory 2.85–3.14 nH band. The mutual fixture, board loop matrices, D2, C1 and C2 remain held.

## Summary

The owner-approved third and final Palace build reached the executable link, then failed on unresolved GSLIB symbols. The intended local static MFEM was selected, but the Palace inner cache selected Homebrew `libgs.dylib` rather than the local `libgs.a`. No Palace executable exists; the attempt is exhausted. This is a build-configuration failure, not evidence that Palace cannot work on the host.

Elmer direct/UMFPACK with tree gauge passed the coax fixture on two refined meshes. At the finer mesh, the nominal inductance is 13.813728 nH against 13.862944 nH exact; including the **four sampled** current-cut extrema gives 13.794132–13.814638 nH, all within 2%. The extrema are samples, not a global current-conservation bound.

The plate fixture with the same Elmer direct method gave 2.759946, 2.793182 and **2.802628 nH** as the plate/gap mesh went from 0.4 to 0.3 to 0.25 mm at fixed 20 mm air margin and fixed coarse exterior settings. The finest value is 0.047372 nH (1.66%) below the required lower edge. It rose 0.338% from 0.3 to 0.25 mm; air-box and exterior-mesh sensitivity have not been shown converged. No extrapolation is accepted as a pass. A z-half-domain experiment missed matched full-domain values by 5.5–5.8% and is rejected.

## Method and assumptions

- The fixture acceptance values come from [D1-FEM.md](../../../../validation-plan/D1-FEM.md) §5A: coax 13.862944 nH within 2%; plate pair 2.85–3.14 nH; analytic mutual within 3%. These are procedure criteria, not new thresholds fitted to this run.
- Elmer source commit `a19504ac53ec222e3355e182b08f2ff280c2203a` and binary SHA-256 `b12d9ea79bc83345c7458e9d991447f53186b0d814d4a54692a93f89e8747355` use perfect-conductor sheets, air, ElmerGrid scaling 0.001 mm→m, direct UMFPACK, and tree gauge. `fixtures/plates-direct.sif` and the generated raw SIFs give the exact physics. The source sheet uses constant +z `Magnetic Field Strength 3 = 100 A/m` across a 10 mm port width: 1 A at z=0.1, 0.25 and 0.4 mm by source-sheet integration. [check_plate_source.py](scripts/check_plate_source.py) audits this geometry/current, but **does not independently integrate an H-field contour**.
- [make_plates_box.py](scripts/make_plates_box.py) imposes a continuous size field over both 10×50 mm PEC plate surfaces and the 0.5 mm gap. [audit_plate_mesh.py](scripts/audit_plate_mesh.py) checks the actual triangles, area and gap tetrahedra, rather than trusting the requested size. Each plate has 500 mm² area; both together have 1,000 mm². Earlier sampled-distance meshes left most surface triangles much coarser than the requested near size and are diagnostic only.
- The far-field box is a finite PEC/magnetic-insulation boundary, not free space at infinity. Its margin and exterior mesh need their own convergence check. At 0.4 mm with far size 8 mm, increasing margin 10→20 mm changed 2.728618→2.780684 nH (+1.91%). At 20 mm margin, changing the far size from 12 to 8 mm changed 2.759946→2.780684 nH (+0.75%). These are not bounds on the true value.
- The 0.4 mm / far size 4 mm / margin 20 mm full mesh reached tree gauge but UMFPACK returned `umf4num: -1` (SuiteSparse `UMFPACK_ERROR_out_of_memory`); it produced no inductance. A finer globally sized 0.18 mm coax mesh likewise passed stack-gauge setup only after a 65,520 KB stack limit, then failed UMFPACK allocation. The localized port-refined coax meshes avoided that allocation problem. An earlier 0.18 mm coax process crash was diagnosed from the macOS crash report as tree-gauge stack exhaustion; it was not a coax accuracy verdict.
- The z=0.25 mm half-domain was a memory-reduction experiment. With the proposed `AV {e}=0` midplane, its full-equivalent inductance `4 E_half / (1 A)^2` differed from matched full-domain results by −5.84% at 0.4 mm and −5.47% at 0.3 mm; it is not used for any fixture decision. A natural-midplane negative control gave 325.638 nH equivalent and is also rejected. The difference is unresolved; a symmetry assumption cannot replace the full solve without matching validation.

## Results

The machine-readable [coax evaluation](fixtures/coax-evaluation.json) includes each current cut and the complete sampled-current interval. The [plate results](fixtures/plates-results.json) classify **every generated mesh** as solved, failed, generated-only or rejected symmetry. The classifier requires the paired 1 A source audit and SIF, finite positive final energy/coenergy, and no explicit solver-error marker before recording a solved result; every completed numerical value traces to a `.log`, `.sif`, mesh audit and source audit in ignored `raw/`, indexed by [raw-manifest.sha256](raw-manifest.sha256).

| Fixture/case | Actual mesh | Direct result | Criterion/status |
| --- | --- | ---: | --- |
| Coax port 0.10 / volume 0.30 mm | 130,430 positive tets | 13.794462 nH nominal; sampled-current interval 13.794154–13.836063 nH | Within ±2% of 13.862944 nH |
| Coax port 0.08 / volume 0.25 mm | 229,668 positive tets | 13.813728 nH nominal; sampled-current interval 13.794132–13.814638 nH | Within ±2%; nominal mesh change +0.140% |
| Plate 0.4 mm, far 12 mm, margin 20 mm | 80,041 tets; plate edge p50 0.400 mm | 2.759946 nH | Below 2.85 nH |
| Plate 0.3 mm, same exterior | 155,974 tets; edge p50 0.299 mm | 2.793182 nH | Below 2.85 nH; +1.204% |
| Plate 0.25 mm, same exterior | 226,819 tets; edge p50 0.250 mm, p99 0.282 mm | **2.802628 nH** | Below 2.85 nH; +0.338%; not accepted |
| Plate 0.4 mm, far 4 mm, margin 20 mm | 165,394 tets; 194,565 edge unknowns | No result | UMFPACK allocation failure, exit 1 |
| Half plate 0.4/0.3 mm, far 12 mm, margin 20 mm | 43,921 / 74,913 tets | 2.598858 / 2.640298 nH full-equivalent | Rejected against matched full-domain solves |

Two smoke-test events are kept distinct. Initially, the three task-01 ngspice cases failed only because this worker checkout lacked the ignored licensed `IFX_CFD7_650V.lib`; tasks 02/04/05/07 passed. The coordinator restored the local model with SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`, matching `fetch_models.sh`. Replaying only the three affected cases then passed against their reference values. The copied licensed `.lib` files were removed from round-7 `raw/`; the model is **not included** in this handback.

## Palace build record

The third campaign ran 20:13:27–20:21:34 UTC. [build_palace_attempt3.sh](scripts/build_palace_attempt3.sh) is a **historical execution record only; it must not be rerun without new owner authorization**. The first `cmake --build` stopped at sandboxed DNS download. An unchanged build resumed with permitted network access, compiled dependencies and Palace, and failed at final link. The separate logs are `raw/build-records/attempt3-build.log` and `attempt3-build-network.log`.

The effective superbuild cache has ARPACK, SLEPc, SuperLU, LibXSMM, GSLIB and Sundials ON; MAGMA/CUDA/HIP OFF. The final inner cache and generated link line prove MFEM selected `/tmp/ps-r6-fem-build1/lib/libmfem.a`, but GSLIB selected `/opt/homebrew/lib/libgs.dylib` while the repaired MFEM used `/tmp/ps-r6-fem-build1/lib/libgs.a`. The unresolved symbols include `_gslib_tensor_mxm` and `_gslib_sarray_transfer_ext_`. The installed MFEM archive's SHA differs from the build archive's SHA only in archive metadata: a read-only comparison found all 270 ordered member payloads identical. `otool -L` could not validate a final binary because **no binary was linked**; the saved `palace-otool.txt` contains that failure, not a success claim. There was no fourth Palace attempt.

## Open items and physical test

The plate fixture does not meet §5A and its air-domain sensitivity remains open, so the analytic mutual check was not run and no board extraction, coupled loop matrix, SPICE include or switching run was produced. D2/C1/C2 remain held. The existing [double-pulse bench procedure](../../../../validation-plan/BENCH-SWITCHING.md) is the eventual physical switching check; it does not replace the missing board inductance matrix for simulation.

## Verification

Run `python3 scripts/check_plate_summary_mutations.py` with the retained raw packet to check the summary guards against missing or changed sources, stale SIFs, misleading completion markers and invalid final energies. The 22 checks use scratch copies and preserve original evidence.

## Reproduce

First verify the **retained original raw packet**, from this `round7/d1-fem/` directory:

```sh
shasum -a 256 -c raw-manifest.sha256
```

The original raw packet remains locally in the coordinator and worker checkouts. It is not in Git or a published release. A checkout without that packet cannot perform this hash check.

Separately, the commands below run from this `round7/d1-fem/` directory in a **clean scratch copy with an empty raw directory**, with R6's pinned local solver/source trees restored under `/tmp/ps-r6-fem-*`. They show the completed direct fixtures; `solve_plates_mesh.sh` deliberately refuses to overwrite an existing solved label. The `raw/` manifest preserves the original outputs. They do **not** authorize another Palace build.

```sh
export PYTHONPATH=/opt/homebrew/lib
PY=/Users/bennet/Miniforge3/bin/python3
zsh scripts/run_elmer_coax_refined.sh coax-port0p10-vol0p30 0.10 0.30
zsh scripts/run_elmer_coax_refined.sh coax-port0p08-vol0p25 0.08 0.25
$PY scripts/evaluate_coax.py > fixtures/coax-evaluation.json

for size in 0.4 0.3 0.25; do
  label="plates-box${size/./p}-far12-m20"
  $PY scripts/make_plates_box.py "raw/fixtures/$label.msh" \
    --gap-size "$size" --far-size 12 --air-margin 20 \
    --transition 0.5 --padding 0.2 > "raw/fixtures/$label-mesh.json"
  $PY scripts/audit_plate_mesh.py "raw/fixtures/$label.msh" \
    > "raw/fixtures/$label-audit.json"
  zsh scripts/solve_plates_mesh.sh "$label"
done
$PY scripts/summarize_plates.py > fixtures/plates-results.json
```

The scratch replay produces new numerical evidence and is not expected to reproduce the frozen 358-file manifest bytes. Compare numerical results and mesh/source audits; keep any new manifest separate from the original evidence. The original `raw/` remains ignored locally. No board or production source files were edited.
