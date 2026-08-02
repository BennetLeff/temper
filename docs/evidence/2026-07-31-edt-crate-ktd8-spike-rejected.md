# KTD8 spike: `edt` crate vs scipy EDT parity (2026-07-31)

<!-- provenance: commit=58b74bb0f0c1a0ed4f59ad937376bb33e4511e12 dirty=UNKNOWN (backfilled 2026-08-02: this file landed on main via commit 58b74bb0f ("perf(placer): migrate Wave 1 hot paths to Rust"); content byte-identical to that commit. Measurement-time dirty state not recorded, hence UNKNOWN.) -->

**Verdict: REJECT the `edt` crate (v0.2.2) as a
`scipy.ndimage.distance_transform_edt` replacement.** Recorded per the
repo's measurement-provenance convention so the verdict is re-verifiable.

## Reproduction

```python
import numpy as np, temper_geometry as _tg  # temper_geometry built 2026-07-31
from scipy.ndimage import distance_transform_edt
rng = np.random.default_rng(7)
for _ in range(50):
    h, w = rng.integers(3, 40), rng.integers(3, 40)
    mask = rng.random((h, w)) < 0.5
    scipy_out = distance_transform_edt(mask.astype(np.uint8))
    padded = np.pad(mask, 1, constant_values=False)
    raw = _tg.edt_transform(padded.T.astype(np.uint8).tobytes(), w + 2, h + 2, False)
    crate_out = np.frombuffer(raw, dtype=np.float64).reshape(w + 2, h + 2).T[1:-1, 1:-1]
    max_diff = max(max_diff, float(np.abs(crate_out - scipy_out).max()))
# max_diff = 2.0
```

(An earlier variant without the False-border padding and transpose
handling measured 2.236; a 3×3 single-source hand case diverges at
(1,2): scipy 2.236 vs crate 1.0.)

## Cause

`edt::edt_sq` hardcodes a grid-edge clamp —
`min((y)², ((shape.1 - y))²)` — treating the top/bottom grid edges as
distance-zero sources regardless of the mask, and its first-axis-fastest
storage/scan semantics differ from numpy's row-major layout. Padding the
mask with a False border (making the clamp equivalent to a real source
ring) and transposing the layout still leaves a 2.0 max diff, so the
crate's distance field is not scipy's Euclidean transform in general.

## Consequence

`_build_edt` keeps `scipy.ndimage.distance_transform_edt` (C-speed; it
was never the hot loop). The U4 perf win is the batched width lookup
(`edt_width_lookup_batch`), which is pinned bit-exact against the
per-point reference. A Rust-native exact EDT (Felzenszwalb–Huttenlocher
or Saito) remains the recorded fallback for a follow-up.

## Test state

The spike harness was removed with the crate; this document plus the
KTD8 resolution in `docs/plans/2026-07-23-003-perf-rust-migration-roadmap-plan.md`
and the note in `packages/temper-geometry/VERIFICATION.md` carry the
verdict.
