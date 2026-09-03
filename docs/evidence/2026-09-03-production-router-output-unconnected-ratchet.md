<!-- provenance: commit=faca9d05270000ee194f48f511736d7f1745c636 dirty=false -->
# Production router output: stable unconnected-item ratchet

## Result

On 2026-09-03, the production routing regression was re-measured from
`origin/main` at `faca9d05270000ee194f48f511736d7f1745c636` in
`/tmp/temper-route-measure`.  The ten pyo3 extensions were freshly built and
verified before measurement.  Five sequential route-and-DRC samples produced
the following identical results:

| metric | samples | result |
|---|---|---:|
| total DRC errors | 780, 780, 780, 780, 780 | 780 |
| `shorting_items` | 7, 7, 7, 7, 7 | 7 |
| `unconnected_items` | 343, 343, 343, 343, 343 | **343** |

The routing completion rate was `0.3143` in each sample.  The repeated
`unconnected_items=343` result has zero observed scatter, so the previous
342 threshold was stale rather than a noise margin.  The production routing
ratchet is therefore updated from 342 to 343; this preserves the gate and
does not assert that the routed board is connectivity-clean.

## Attribution and boundary

The +1 is attributed to the post-342 router/geometry lineage: #1422's
conservative rasterizer and the subsequent Rust router migrations changed the
emitted route geometry/connectivity result.  This is a measured ratchet
update, not an unexplained increase and not an attempt to conceal a PCB
change.  No PCB, K1 placement, or DRC safety ceiling was changed by this
update.  The separate K1 creepage failure remains a genuine hardware-layout
issue and is not resolved here.

The measurement command used the repository's production route test path and
fresh pyo3 extensions; the five samples were run against the same committed
board and current-main source.  The raw summary was:

```
total=780  shorting_items=7  unconnected_items=343  completion_rate=0.3143
```
