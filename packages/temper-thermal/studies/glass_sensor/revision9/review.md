> Historical review checkpoint: this records an earlier 144-case/46-test snapshot and the then-open source-identity finding. The runner was corrected and the final 168-case/47-test snapshot was reviewed in [final-review.md](final-review.md). Read that disposition for the delivered state.

# Independent R9 review

Scope: scratch thermal adapter/runner/negative tests/results and their pinned R5/R6/R7 sources, plus `process-decision.md`. Mechanical resolution and the root report were not yet complete at this review checkpoint. Read-only review; no implementation, canonical file, hardware or supplier message was changed. Physical status remains **NOT_RUN**.

## Actionable finding

**P2 — verify the inherited source snapshots actually consumed by the runner.** `thermal/run.sh` checks inherited `inputs.sha256` against the source tree, then later copies `model.rs`/R5 geometry and concatenates R5/R6/R7 source directly from that tree. Only the copied R7 geometry gets a post-copy digest check. The end-of-run check covers local unit files, while the success receipt repeats inherited expected hashes. A concurrent edit after the initial check can therefore make a successful receipt attribute output to different inherited bytes than the compiler consumed. Copy all pinned source inputs to an isolated snapshot, verify that snapshot against the pins, and compile/read only it. Alternatively capture and verify every consumed byte as it is staged. Keep stale-receipt invalidation before all input resolution. This concerns reproducible source identity; no mismatch was observed in the current recorded inputs.

## Thermal mathematics and result checks

The equivalent thickness is `t_equiv = t_actual × k_reference/k_requested`. Tracing `r7_candidate → candidate → build` shows the changed thickness affects the two intended half-bond series resistances; other geometry scalars, contact weights, paths, film distance and cover attachment properties remain unchanged. Restoring the bond node to `bond_footprint_mm2 × t_actual_mm × 0.002` correctly removes the equivalent-length artifact from capacity. This is 2 MJ/(m³·K), an inherited fixed proxy. It is not a property measured for 569 or any other alternate adhesive.

The four new tests address exact R7 parity for all three variants, analytical half-bond resistance/capacity for M222 at a non-reference conductivity, invalid inputs and equilibrium conservation. Source inspection supports their assertions. A full-matrix unchanged-outside-bond comparison at a non-reference k for both M222 and IST would make the intended isolation contract more explicit, but I found no present unintended matrix change requiring a fix. Extreme arbitrary finite floating-point inputs are outside the closed sweep; no public free-form parameter API is introduced.

Independent read-only checks of the existing result files found:

| Check | Observed evidence |
|---|---|
| Inherited source pins | All five current source hashes match `inputs.sha256` |
| Sweep census | 144 finite rows: 2 source geometries × 6 thicknesses × 4 conductivities × 3 contact cases |
| Status labels | Every row is `PARAMETRIC_NOT_CAD_OR_PROCESS_APPROVED`, physical `NOT_RUN` |
| R7 control parity | M222 control: 2.910000 s / 2.474231°C; thin M222: 2.780000 s / 2.440587°C; IST: 2.050000 s / 2.576544°C |
| Lowest steady error, M222 | 1.360294°C at 0.075 mm, assumed k=4, uniform href=4000; pan-step t90 1.700000 s |
| Lowest steady error, IST | 1.463540°C under the same virtual bond/contact choices; pan-step t90 1.200000 s |
| Boundary contributions | Glass + body reproduces underread within 0.000001°C after CSV rounding |
| Recorded test run | 46 passed, 0 failed; I inspected this receipt, not a separate rerun |
| Recorded runner negatives | Bad source pin and geometry pin exit 1; injected unit failure exits 101; each reports no new physics CSV and removed stale success receipt |

The refined extreme cases change pan-step t90 by up to 0.110 s and steady underread by up to 0.034461°C in the supplied convergence table. Report these as observed resolution sensitivity rather than rounding every row to a precision implying exact convergence. The best virtual steady error plus the inherited proposed 1°C nonthermal reserve still exceeds 2°C; no complete-system target pass follows.

The runner flushes results before publication, propagates test failure, runs warning-denied production/test builds and uses an atomic final receipt rename. Negative checks discriminate the intended pin/test failures. Existing old CSV files can remain after a failed real rerun, but the absent success receipt is the authority; consumers must preserve that contract. Source-snapshot verification above is the remaining runner correction.

## Process decision review

The public-source distinction is sound: the [Cotronics 903HP/908 sheet](https://www.cotronics.com/catalog/26%20%20%20903HP%20%20908.pdf) places the elevated complete-cure instruction with 903HP, so R8's generic high-temperature schedule cannot be promoted into a mandatory 908 recipe. The unknown exact thin-layer/lot process still prevents releasing the R7 bond as fabrication-ready.

The [Aremco catalog](https://www.aremco.com/wp-content/uploads/2025/08/A0-Catalog-25F.pdf), pp.8–11, supports selecting standard 569 for an accessible dry process witness: the product cure and generic thin-gap guidance are distinguished from the higher-temperature moisture/chemical characterization. It also warns that dehydration can continue at substantially higher exposure temperatures. The packet already requires observing later cure evolution and does not claim wet qualification. The [current EP126 page](https://www.masterbond.com/tds/ep126) and [continuous-service guide](https://www.masterbond.com/properties/heat-cure-adhesives-sealants-and-coatings) support its conditional backup status; the lower current Tg is not replaced by an older promotional value.

The full-native-lead open witness is correctly defined as a different article, with exact face/process disposition still conditional. The numerical sweep retains R7 covers, short leads and other inherited boundaries. It must not be presented as the response of P9-569-OPEN or a named alternate adhesive. No qualified alternate k/cp/density, sensor compatibility, installed insulation, cure completion or actual new CAD clearance is established. The present sweep varies thickness and k only; heat capacity is an explicitly fixed proxy, not a completed independent heat-capacity sweep.

## Pending review / irreducible gaps

Mechanical resolution evidence and root README/report were not yet available in final form. The mechanical script was inspected provisionally; its nominal axial checks explicitly exclude strength, hot tolerances, lateral escape, seal qualification and continuous swept-volume proof. Its results must be reviewed when complete before claiming geometric closure.

R9 can close source interpretation, nominated witness geometry and numerical sensitivity questions. Actual process/lot data, hot installed material properties, load/tolerance/strength requirements, seal/contact observability, metrology and physical endurance remain open. No experimental result is supplied by a simulator or a catalog selection.
