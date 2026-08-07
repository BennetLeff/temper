// Exact 2-D Euclidean distance transform (EDT).
//
// Spike per docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md
// (KTD8): scipy.ndimage.distance_transform_edt is a recorded BLOCKER for the
// Python-removal effort. docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md
// rejected the third-party `edt` crate (max diff 2.0–2.236 vs scipy — an
// approximate/incorrect implementation, not a rejection of "EDT in Rust" as
// an approach). This module implements the algorithm scipy itself uses:
// Felzenszwalb & Huttenlocher, "Distance Transforms of Sampled Functions"
// (2012 Theory of Computing version; originally a 2004 tech report) — an
// exact, separable, O(n) per dimension lower-envelope-of-parabolas
// algorithm over squared distances.
//
// Semantics mirror `scipy.ndimage.distance_transform_edt`: `mask[i] == 0`
// (background) is a distance-zero source; `mask[i] != 0` (foreground)
// receives the Euclidean distance, in grid-cell units, to the nearest
// background cell. See docs/evidence/2026-08-07-exact-edt-rust-spike.md for
// the parity/perf measurements against scipy that this module exists to
// produce.

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// 1-D squared Euclidean distance transform (Felzenszwalb–Huttenlocher).
///
/// `f[p]` is the squared "cost" of treating index `p` as a distance-zero
/// source; `f64::INFINITY` for indices that are not sources. `sampling` is
/// the physical spacing between adjacent grid indices along this axis
/// (1.0 for the isotropic/no-`sampling` case, which is all three current
/// Python call sites).
///
/// Returns, for each index `q`, `min_p (sampling*(q-p))^2 + f[p]` — the
/// squared distance to the nearest source, in the same units as `sampling`.
///
/// This is the textbook lower-envelope-of-parabolas construction from the
/// Felzenszwalb–Huttenlocher paper: each source `p` defines a parabola
/// `sampling^2*(q-p)^2 + f[p]` in `q`; the transform is their pointwise
/// minimum, computed in O(n) by maintaining the lower envelope's breakpoints
/// on a single left-to-right sweep (`v`/`z`), then reading it off with a
/// second sweep.
fn edt_squared_1d(f: &[f64], sampling: f64, out: &mut [f64]) {
    let n = f.len();
    debug_assert_eq!(out.len(), n);
    if n == 0 {
        return;
    }
    if n == 1 {
        out[0] = f[0];
        return;
    }

    // v[k]: index of the k-th parabola on the lower envelope (in order).
    // z[k]: x-coordinate where parabola v[k] starts dominating (z[0] = -inf).
    let mut v: Vec<usize> = vec![0; n];
    let mut z: Vec<f64> = vec![0.0; n + 1];
    let s2 = sampling * sampling;

    let mut k: usize = 0;
    v[0] = 0;
    z[0] = f64::NEG_INFINITY;
    z[1] = f64::INFINITY;

    for q in 1..n {
        loop {
            let p = v[k];
            // Intersection of parabola p and parabola q:
            //   s2*(x-p)^2 + f[p] == s2*(x-q)^2 + f[q]
            //   x = ((f[q] + s2*q^2) - (f[p] + s2*p^2)) / (2*s2*(q-p))
            let fp = f[p] + s2 * (p as f64) * (p as f64);
            let fq = f[q] + s2 * (q as f64) * (q as f64);
            let denom = 2.0 * s2 * (q as f64 - p as f64);
            // denom > 0 always holds here (q > p, s2 > 0); if f[p] and f[q]
            // are both +inf the numerator is NaN, so guard explicitly and
            // treat an all-infinite envelope entry as "never dominates"
            // (s = +inf) so the loop moves on to inserting q.
            let s = if fp.is_infinite() && fq.is_infinite() {
                f64::INFINITY
            } else {
                (fq - fp) / denom
            };
            if s <= z[k] {
                if k == 0 {
                    // Parabola q dominates from -inf; replace v[0].
                    v[0] = q;
                    z[0] = f64::NEG_INFINITY;
                    z[1] = f64::INFINITY;
                    break;
                }
                k -= 1;
                continue;
            }
            k += 1;
            v[k] = q;
            z[k] = s;
            z[k + 1] = f64::INFINITY;
            break;
        }
    }

    k = 0;
    for (q, out_q) in out.iter_mut().enumerate() {
        while z[k + 1] < q as f64 {
            k += 1;
        }
        let p = v[k];
        let d = sampling * (q as f64 - p as f64);
        *out_q = d * d + f[p];
    }
}

/// Exact 2-D Euclidean distance transform, matching
/// `scipy.ndimage.distance_transform_edt(mask)` (no `sampling` argument,
/// i.e. isotropic unit spacing) to floating-point rounding.
///
/// `mask` is row-major, shape `(height, width)`: `mask[r*width+c] == 0` is
/// a distance-zero source (background); nonzero cells receive the distance,
/// in grid-cell units, to the nearest source. Returns a row-major `f64`
/// array of the same shape, holding actual (not squared) distances.
pub fn exact_edt(mask: &[u8], height: usize, width: usize) -> Vec<f64> {
    exact_edt_sampled(mask, height, width, 1.0, 1.0)
}

/// Anisotropic variant: `row_sampling`/`col_sampling` are the physical
/// spacing between adjacent rows/columns, matching scipy's
/// `sampling=(row_spacing, col_spacing)`. None of the three current Python
/// call sites pass `sampling` (all use the isotropic default), but the
/// separable algorithm supports it for free, so it is exposed rather than
/// hardcoded away.
pub fn exact_edt_sampled(
    mask: &[u8],
    height: usize,
    width: usize,
    row_sampling: f64,
    col_sampling: f64,
) -> Vec<f64> {
    debug_assert_eq!(mask.len(), height * width);
    if height == 0 || width == 0 {
        return Vec::new();
    }

    // Pass 1: transform along columns (axis 0 / rows), independently per
    // column. f(r) = 0 if mask[r,c] == 0 (source), else +inf.
    let mut sq = vec![0.0f64; height * width];
    {
        let mut col_in = vec![0.0f64; height];
        let mut col_out = vec![0.0f64; height];
        for c in 0..width {
            for r in 0..height {
                col_in[r] = if mask[r * width + c] == 0 {
                    0.0
                } else {
                    f64::INFINITY
                };
            }
            edt_squared_1d(&col_in, row_sampling, &mut col_out);
            for r in 0..height {
                sq[r * width + c] = col_out[r];
            }
        }
    }

    // Pass 2: transform along rows (axis 1 / columns), using pass 1's
    // squared distances as the source cost function.
    let mut out = vec![0.0f64; height * width];
    {
        let mut row_out = vec![0.0f64; width];
        for r in 0..height {
            let row = &sq[r * width..(r + 1) * width];
            edt_squared_1d(row, col_sampling, &mut row_out);
            for c in 0..width {
                out[r * width + c] = row_out[c].sqrt();
            }
        }
    }

    out
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (mask_bytes, height, width))]
/// Pyo3 boundary: mask as raw bytes (one byte per cell, row-major,
/// `numpy.ascontiguousarray(mask, dtype=np.uint8).tobytes()` on the Python
/// side), dims as plain ints. Returns the distance grid as raw little-endian
/// f64 bytes (row-major) — mirrors `edt_width_lookup_batch`'s bytes-in
/// convention in `channel_widths.rs`, and lets the benchmark harness measure
/// the same boundary-crossing shape a real call site would pay (one array
/// in, one array out, no per-element Python overhead).
pub fn exact_edt_transform(mask_bytes: Vec<u8>, height: usize, width: usize) -> Vec<u8> {
    debug_assert_eq!(mask_bytes.len(), height * width);
    let out = exact_edt(&mask_bytes, height, width);
    let mut bytes = Vec::with_capacity(out.len() * 8);
    for v in out {
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    /// Brute-force O(h*w*sources) reference: for every foreground cell,
    /// scan every background cell and keep the minimum Euclidean distance.
    /// Independent of the FH sweep — used to check the sweep implementation
    /// itself, before ever comparing against scipy (that comparison is a
    /// separate Python-side harness, see docs/evidence/2026-08-07-exact-edt-rust-spike.md).
    fn brute_force_edt(mask: &[u8], height: usize, width: usize) -> Vec<f64> {
        let mut sources: Vec<(usize, usize)> = Vec::new();
        for r in 0..height {
            for c in 0..width {
                if mask[r * width + c] == 0 {
                    sources.push((r, c));
                }
            }
        }
        let mut out = vec![0.0f64; height * width];
        for r in 0..height {
            for c in 0..width {
                if mask[r * width + c] == 0 {
                    out[r * width + c] = 0.0;
                    continue;
                }
                if sources.is_empty() {
                    out[r * width + c] = f64::INFINITY;
                    continue;
                }
                let mut best = f64::INFINITY;
                for &(sr, sc) in &sources {
                    let dr = r as f64 - sr as f64;
                    let dc = c as f64 - sc as f64;
                    let d = (dr * dr + dc * dc).sqrt();
                    if d < best {
                        best = d;
                    }
                }
                out[r * width + c] = best;
            }
        }
        out
    }

    fn assert_close(a: &[f64], b: &[f64], tol: f64) {
        assert_eq!(a.len(), b.len());
        for (i, (x, y)) in a.iter().zip(b.iter()).enumerate() {
            if x.is_infinite() && y.is_infinite() {
                assert_eq!(x.is_sign_positive(), y.is_sign_positive(), "index {i}");
                continue;
            }
            assert!((x - y).abs() <= tol, "index {i}: {x} vs {y}");
        }
    }

    #[test]
    fn test_empty_grid_all_background() {
        let mask = vec![0u8; 5 * 7];
        let out = exact_edt(&mask, 5, 7);
        assert!(out.iter().all(|&d| d == 0.0));
    }

    #[test]
    fn test_full_grid_all_foreground_is_infinite() {
        // No background cell exists anywhere: every cell's distance to the
        // nearest source is well-defined as +inf. Documented behavior, not
        // scipy's (checked separately against real scipy output, since
        // scipy's own handling of the no-background case is itself part of
        // what the parity harness must establish).
        let mask = vec![1u8; 4 * 4];
        let out = exact_edt(&mask, 4, 4);
        assert!(out.iter().all(|&d| d.is_infinite()));
    }

    #[test]
    fn test_single_seed_matches_brute_force() {
        let h = 15;
        let w = 20;
        let mut mask = vec![1u8; h * w];
        mask[7 * w + 10] = 0;
        let got = exact_edt(&mask, h, w);
        let want = brute_force_edt(&mask, h, w);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_sparse_seeds_matches_brute_force() {
        let h = 25;
        let w = 30;
        let mut mask = vec![1u8; h * w];
        for &(r, c) in &[(0, 0), (24, 29), (10, 15), (3, 27), (20, 2)] {
            mask[r * w + c] = 0;
        }
        let got = exact_edt(&mask, h, w);
        let want = brute_force_edt(&mask, h, w);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_dense_random_matches_brute_force() {
        // Small xorshift PRNG so this test has no external dependency.
        let mut state: u64 = 0x9E3779B97F4A7C15;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        };
        let h = 22;
        let w = 18;
        let mask: Vec<u8> = (0..h * w)
            .map(|_| if next() % 2 == 0 { 1 } else { 0 })
            .collect();
        let got = exact_edt(&mask, h, w);
        let want = brute_force_edt(&mask, h, w);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_thin_diagonal_feature_matches_brute_force() {
        let h = 20;
        let w = 20;
        let mut mask = vec![1u8; h * w];
        for i in 0..h.min(w) {
            mask[i * w + i] = 0;
        }
        let got = exact_edt(&mask, h, w);
        let want = brute_force_edt(&mask, h, w);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_all_background_row_and_column_matches_brute_force() {
        let h = 12;
        let w = 16;
        let mut mask = vec![1u8; h * w];
        for c in 0..w {
            mask[3 * w + c] = 0; // background row
        }
        for r in 0..h {
            mask[r * w + 9] = 0; // background column
        }
        let got = exact_edt(&mask, h, w);
        let want = brute_force_edt(&mask, h, w);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_non_square_aspect_ratio_matches_brute_force() {
        let h = 4;
        let w = 60;
        let mut mask = vec![1u8; h * w];
        mask[0] = 0;
        mask[h * w - 1] = 0;
        let got = exact_edt(&mask, h, w);
        let want = brute_force_edt(&mask, h, w);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_single_row_and_single_column() {
        let mut row_mask = vec![1u8; 9];
        row_mask[4] = 0;
        let got = exact_edt(&row_mask, 1, 9);
        let want = brute_force_edt(&row_mask, 1, 9);
        assert_close(&got, &want, 1e-9);

        let mut col_mask = vec![1u8; 9];
        col_mask[4] = 0;
        let got = exact_edt(&col_mask, 9, 1);
        let want = brute_force_edt(&col_mask, 9, 1);
        assert_close(&got, &want, 1e-9);
    }

    #[test]
    fn test_symmetry_row_major_vs_transposed() {
        // Transposing a rectangular mask and swapping height/width must
        // give the transposed distance field -- catches row/col axis bugs.
        let h = 6;
        let w = 9;
        let mut mask = vec![1u8; h * w];
        mask[2 * w + 5] = 0;
        mask[4 * w + 1] = 0;
        let d = exact_edt(&mask, h, w);

        let mut mask_t = vec![1u8; w * h];
        for r in 0..h {
            for c in 0..w {
                mask_t[c * h + r] = mask[r * w + c];
            }
        }
        let d_t = exact_edt(&mask_t, w, h);

        for r in 0..h {
            for c in 0..w {
                assert!(
                    (d[r * w + c] - d_t[c * h + r]).abs() < 1e-9,
                    "mismatch at ({r},{c})"
                );
            }
        }
    }

    #[test]
    fn test_anisotropic_sampling_matches_scaled_isotropic() {
        // Scaling both axes by the same factor k should scale every
        // distance by k, exactly (this is the standard cross-check for the
        // `sampling` generalization even though no current caller uses it).
        let h = 10;
        let w = 10;
        let mut mask = vec![1u8; h * w];
        mask[3 * w + 4] = 0;
        let unit = exact_edt_sampled(&mask, h, w, 1.0, 1.0);
        let scaled = exact_edt_sampled(&mask, h, w, 2.5, 2.5);
        for i in 0..unit.len() {
            assert!((scaled[i] - 2.5 * unit[i]).abs() < 1e-9, "index {i}");
        }
    }
}
