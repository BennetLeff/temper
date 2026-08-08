// Exact 8-connected connected-component labeling for 2-D boolean grids.
//
// KTD8 follow-up (routability_check.py's remaining scipy binding):
// `check_routability_cc` (packages/temper-placer/src/temper_placer/router_v6/
// routability_check.py) calls `scipy.ndimage.label(passable_mask,
// structure=np.ones((3, 3), dtype=bool))` -- an 8-connected (all 8 neighbors,
// not the 4-connected cross-shaped default) connected-component labeling.
// This is a different scipy function from `distance_transform_edt`
// (see edt.rs / docs/evidence/2026-08-07-exact-edt-rust-spike.md), explicitly
// left out of scope by that spike. See
// docs/evidence/2026-08-07-rust-connected-components-spike.md for the
// contract determination (label VALUES are not part of the consumer's
// contract, only the partition + nonzero-ness) and the differential/
// benchmark measurements against scipy.
//
// Algorithm: classic two-pass union-find raster-scan labeling. Pass 1 scans
// row-major; for each foreground cell it looks at its already-visited
// West/North/North-West/North-East neighbors (the four 8-connected neighbors
// that precede it in raster order), assigns a provisional label, and unions
// together any neighbor labels that co-occur (the "conflict" that a
// single-pass scan cannot resolve on its own -- e.g. a checkerboard-adjacent
// pair of arms merging under a later cell). Pass 2 resolves every
// provisional label to its union-find root and renumbers roots to 1..N in
// the order they are first encountered scanning the grid -- which happens to
// reproduce scipy's own "labels increase in the order first found scanning
// the array" numbering, though the consumer's contract does not require
// that (see the evidence doc).
//
// This is exact by construction (no approximation tradeoff, unlike EDT):
// union-find with path compression correctly computes connectivity for any
// finite graph.

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Disjoint-set forest with path compression and union by rank. Labels are
/// 1-indexed provisional component ids (0 is reserved for "background" and
/// never entered into the forest).
///
/// Grows lazily via `push_new` (one entry per NEW provisional label, not one
/// per grid cell) rather than being preallocated to the grid size up front.
/// This matters a lot in practice: a mostly-background grid (few foreground
/// cells) or a mostly-single-component grid (foreground cells almost always
/// find an already-labeled neighbor) both need very few provisional labels
/// even on a multi-million-cell grid -- measured to save an order of
/// magnitude of allocation+fill work on those common shapes versus
/// preallocating `n + 1` entries regardless of how many labels are ever
/// used (see docs/evidence/2026-08-07-rust-connected-components-spike.md).
struct UnionFind {
    parent: Vec<i32>,
    rank: Vec<u8>,
}

impl UnionFind {
    /// Index 0 is reserved (never assigned as a real label) and pre-seeded
    /// so it is always in bounds.
    fn new() -> Self {
        UnionFind {
            parent: vec![0],
            rank: vec![0],
        }
    }

    /// Appends a new singleton set and returns its id.
    fn push_new(&mut self) -> i32 {
        let idx = self.parent.len() as i32;
        self.parent.push(idx);
        self.rank.push(0);
        idx
    }

    /// Iterative find with path halving (each node on the path is pointed
    /// at its grandparent, not fully compressed in one pass) -- avoids
    /// recursion overhead and an extra full pass that a fully-compressing
    /// recursive `find` would otherwise incur; still amortized near-O(1)
    /// with union by rank.
    fn find(&mut self, x: i32) -> i32 {
        let mut xi = x as usize;
        while self.parent[xi] != xi as i32 {
            let grandparent = self.parent[self.parent[xi] as usize];
            self.parent[xi] = grandparent;
            xi = self.parent[xi] as usize;
        }
        xi as i32
    }

    fn union(&mut self, a: i32, b: i32) {
        let ra = self.find(a);
        let rb = self.find(b);
        if ra == rb {
            return;
        }
        let (ra_i, rb_i) = (ra as usize, rb as usize);
        match self.rank[ra_i].cmp(&self.rank[rb_i]) {
            std::cmp::Ordering::Less => self.parent[ra_i] = rb,
            std::cmp::Ordering::Greater => self.parent[rb_i] = ra,
            std::cmp::Ordering::Equal => {
                self.parent[rb_i] = ra;
                self.rank[ra_i] += 1;
            }
        }
    }
}

/// Exact 8-connected component labeling, matching the partition
/// `scipy.ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))`
/// computes: `mask[i] == 0` cells stay unlabeled (label `0`, "background");
/// every maximal set of nonzero cells connected via any of the 8 neighbor
/// directions (including diagonals) shares one positive label.
///
/// `mask` is row-major, shape `(height, width)`, nonzero = foreground.
/// Returns `(labels, num_features)`: `labels` is row-major `i32`, same
/// shape, `0` for background and `1..=num_features` for foreground
/// components; `num_features` is the number of distinct components (`0` for
/// an all-background or empty grid).
///
/// Label *values* are assigned in raster-scan first-encounter order (this
/// happens to match scipy's own numbering) but this is not a documented
/// contract of this function -- callers that only test partition membership
/// (`labels[a] == labels[b] && labels[a] != 0`) do not depend on it; see the
/// evidence doc for why the one real caller in this repo is exactly such a
/// caller.
pub fn label_components_8(mask: &[u8], height: usize, width: usize) -> (Vec<i32>, i32) {
    debug_assert_eq!(mask.len(), height * width);
    let n = height * width;
    let mut labels = vec![0i32; n];
    if n == 0 {
        return (labels, 0);
    }

    // Grows lazily -- see UnionFind's doc comment for why this matters.
    let mut uf = UnionFind::new();

    for r in 0..height {
        let row = r * width;
        for c in 0..width {
            let idx = row + c;
            if mask[idx] == 0 {
                continue;
            }
            // Inline (not a closure) the four preceding-in-raster-order
            // 8-neighbors: West, North-West, North, North-East. `best` is
            // the first nonzero neighbor label seen; any other *distinct*
            // nonzero neighbor label is a same-cell "conflict" that gets
            // unioned with `best` immediately (no deferred merge list
            // needed -- union-find handles repeat unions of the same pair
            // as a cheap no-op).
            let mut best: i32 = 0;
            macro_rules! consider {
                ($lbl:expr) => {
                    let lbl = $lbl;
                    if lbl != 0 {
                        if best == 0 {
                            best = lbl;
                        } else if lbl != best {
                            uf.union(best, lbl);
                        }
                    }
                };
            }
            if c > 0 {
                consider!(labels[idx - 1]);
            }
            if r > 0 {
                if c > 0 {
                    consider!(labels[idx - width - 1]);
                }
                consider!(labels[idx - width]);
                if c + 1 < width {
                    consider!(labels[idx - width + 1]);
                }
            }

            if best == 0 {
                labels[idx] = uf.push_new();
            } else {
                labels[idx] = best;
            }
        }
    }

    // Pass 2: resolve each provisional label to its union-find root, and
    // renumber roots to 1..=num_features in first-encounter (raster) order.
    // `root_to_final` is indexed directly by root id (bounded by the number
    // of provisional labels actually allocated, `uf.parent.len()`) -- a
    // plain array lookup, not a hash lookup, since every possible root
    // value is already a small dense integer.
    let mut root_to_final: Vec<i32> = vec![0i32; uf.parent.len()];
    let mut num_features: i32 = 0;
    for lbl in labels.iter_mut() {
        if *lbl == 0 {
            continue;
        }
        let root = uf.find(*lbl);
        let slot = &mut root_to_final[root as usize];
        if *slot == 0 {
            num_features += 1;
            *slot = num_features;
        }
        *lbl = *slot;
    }

    (labels, num_features)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (mask_bytes, height, width))]
/// Pyo3 boundary: mask as raw bytes (one byte per cell, row-major,
/// `numpy.ascontiguousarray(mask, dtype=np.uint8).tobytes()` on the Python
/// side), dims as plain ints. Returns `(label_bytes, num_features)`:
/// `label_bytes` is the label grid as raw little-endian `i32` bytes
/// (row-major) -- mirrors `exact_edt_transform`'s bytes-in/bytes-out
/// convention in `edt.rs`.
pub fn connected_components_8_transform(
    mask_bytes: Vec<u8>,
    height: usize,
    width: usize,
) -> (Vec<u8>, i64) {
    debug_assert_eq!(mask_bytes.len(), height * width);
    let (labels, num_features) = label_components_8(&mask_bytes, height, width);
    (i32_vec_to_le_bytes(labels), num_features as i64)
}

// `connected_components_8_transform` (and `exact_edt_transform` in edt.rs,
// via a per-element `to_le_bytes()`/`extend_from_slice` loop) assume a
// little-endian target. Every build target for this crate is little-endian
// (x86_64, wasm32); fail the build outright, loudly, rather than silently
// mis-serialize, if that ever stops being true.
#[cfg(target_endian = "big")]
compile_error!(
    "connected_components_8_transform's bulk byte copy assumes a little-endian target"
);

/// Bulk-copies `Vec<i32>` to its raw little-endian bytes, rather than a
/// per-element `to_le_bytes()`/`extend_from_slice` loop -- measured to
/// matter at real grid sizes (millions of cells): the per-element loop
/// costs several ms on its own at 4M+ elements (see
/// docs/evidence/2026-08-07-rust-connected-components-spike.md).
///
/// Safety: `labels: Vec<i32>` is a contiguous, properly-aligned in-memory
/// buffer; reinterpreting it as `4 * labels.len()` bytes is valid for any
/// `i32` bit pattern (there is no such thing as an invalid `i32`, unlike
/// e.g. `bool` or an enum discriminant), and the target is guaranteed
/// little-endian by the `compile_error!` guard above, so the native byte
/// order this copy produces is bit-identical to an explicit
/// little-endian encode.
fn i32_vec_to_le_bytes(labels: Vec<i32>) -> Vec<u8> {
    let byte_len = labels.len() * 4;
    // `Vec::with_capacity` + `copy_nonoverlapping` + `set_len`, not
    // `vec![0u8; byte_len]` + copy: the latter zero-fills the buffer and
    // then immediately overwrites every byte, paying for two full passes
    // over multi-megabyte buffers at real grid sizes instead of one.
    let mut bytes: Vec<u8> = Vec::with_capacity(byte_len);
    unsafe {
        std::ptr::copy_nonoverlapping(labels.as_ptr().cast::<u8>(), bytes.as_mut_ptr(), byte_len);
        // Safe: `copy_nonoverlapping` above just initialized exactly
        // `byte_len` bytes of `bytes`'s spare capacity (`byte_len ==
        // labels.len() * 4 <= bytes.capacity()` by construction).
        bytes.set_len(byte_len);
    }
    bytes
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    /// Independent reference implementation: iterative (explicit-stack, no
    /// recursion) flood fill, structurally unrelated to the union-find sweep
    /// above (no shared helper code) -- used to cross-check the primary
    /// implementation before ever comparing against scipy (that comparison
    /// is a separate Python-side differential harness, see
    /// docs/evidence/2026-08-07-rust-connected-components-spike.md).
    fn flood_fill_reference(mask: &[u8], height: usize, width: usize) -> (Vec<i32>, i32) {
        let n = height * width;
        let mut labels = vec![0i32; n];
        let mut next_label = 0i32;
        let mut stack: Vec<usize> = Vec::new();

        for start in 0..n {
            if mask[start] == 0 || labels[start] != 0 {
                continue;
            }
            next_label += 1;
            labels[start] = next_label;
            stack.push(start);
            while let Some(idx) = stack.pop() {
                let r = idx / width;
                let c = idx % width;
                for dr in -1i64..=1 {
                    for dc in -1i64..=1 {
                        if dr == 0 && dc == 0 {
                            continue;
                        }
                        let nr = r as i64 + dr;
                        let nc = c as i64 + dc;
                        if nr < 0 || nc < 0 || nr >= height as i64 || nc >= width as i64 {
                            continue;
                        }
                        let nidx = nr as usize * width + nc as usize;
                        if mask[nidx] != 0 && labels[nidx] == 0 {
                            labels[nidx] = next_label;
                            stack.push(nidx);
                        }
                    }
                }
            }
        }
        (labels, next_label)
    }

    /// Two label grids describe the same partition iff, for every pair of
    /// cells, "same label" agrees -- independent of the actual numeric
    /// values used (renumbering-invariant comparison, as the evidence doc's
    /// contract determination requires).
    fn assert_same_partition(a: &[i32], b: &[i32]) {
        assert_eq!(a.len(), b.len());
        // Background (0) must match exactly -- 0 is not a component id.
        for i in 0..a.len() {
            assert_eq!(a[i] == 0, b[i] == 0, "background mismatch at {i}");
        }
        // For every pair of foreground cells, "same label" must agree.
        // O(n^2) -- fine for the small grids these unit tests use; the
        // Python differential harness uses a faster canonical-form
        // comparison at scale.
        for i in 0..a.len() {
            if a[i] == 0 {
                continue;
            }
            for j in (i + 1)..a.len() {
                if b[j] == 0 {
                    continue;
                }
                assert_eq!(
                    a[i] == a[j],
                    b[i] == b[j],
                    "partition mismatch at ({i},{j})"
                );
            }
        }
    }

    #[test]
    fn test_empty_grid() {
        let (labels, n) = label_components_8(&[], 0, 0);
        assert!(labels.is_empty());
        assert_eq!(n, 0);
    }

    #[test]
    fn test_all_background() {
        let mask = vec![0u8; 5 * 7];
        let (labels, n) = label_components_8(&mask, 5, 7);
        assert!(labels.iter().all(|&l| l == 0));
        assert_eq!(n, 0);
    }

    #[test]
    fn test_all_foreground_is_one_component() {
        let mask = vec![1u8; 6 * 5];
        let (labels, n) = label_components_8(&mask, 6, 5);
        assert_eq!(n, 1);
        assert!(labels.iter().all(|&l| l == 1));
    }

    #[test]
    fn test_single_isolated_cell() {
        let mut mask = vec![0u8; 9];
        mask[4] = 1;
        let (labels, n) = label_components_8(&mask, 3, 3);
        assert_eq!(n, 1);
        assert_eq!(labels[4], 1);
    }

    #[test]
    fn test_diagonal_touch_is_connected_8way() {
        // Two cells touching only at a corner are ONE component under
        // 8-connectivity (the consumer's actual structure=ones((3,3))) but
        // would be TWO under 4-connectivity -- this is the sharpest
        // discriminator between the two conventions.
        let mut mask = vec![0u8; 4];
        mask[0] = 1; // (0,0)
        mask[3] = 1; // (1,1) -- diagonal neighbor of (0,0)
        let (labels, n) = label_components_8(&mask, 2, 2);
        assert_eq!(
            n, 1,
            "diagonal-touching cells must be one 8-connected component"
        );
        assert_eq!(labels[0], labels[3]);
    }

    #[test]
    fn test_checkerboard_is_all_one_component_under_8_conn() {
        // A pure checkerboard: every foreground cell touches every other
        // foreground cell diagonally, so under 8-connectivity the WHOLE
        // checkerboard is one component -- the sharpest discriminator
        // named in the task brief. This also stresses the union-find
        // "conflict" path: a checkerboard forces many merges that a naive
        // single-pass-without-union labeling would get wrong.
        let h = 6;
        let w = 6;
        let mask: Vec<u8> = (0..h * w).map(|i| ((i / w + i % w) % 2) as u8).collect();
        let (labels, n) = label_components_8(&mask, h, w);
        assert_eq!(n, 1, "a full checkerboard is one 8-connected component");
        let first_fg = labels.iter().position(|&l| l != 0).unwrap();
        for (i, &l) in labels.iter().enumerate() {
            if mask[i] != 0 {
                assert_eq!(l, labels[first_fg]);
            } else {
                assert_eq!(l, 0);
            }
        }
    }

    #[test]
    fn test_spiral_matches_flood_fill_reference() {
        // A spiral/snake shape is exactly the case where a naive scan
        // (without the union-find "conflict" resolution) mislabels: the
        // arm can touch itself again several rows later.
        let h = 11;
        let w = 11;
        let mut mask = vec![0u8; h * w];
        // Carve a rectangular spiral by hand.
        let mut top = 0i64;
        let mut bottom = h as i64 - 1;
        let mut left = 0i64;
        let mut right = w as i64 - 1;
        let mut turn = 0;
        while top <= bottom && left <= right {
            match turn % 4 {
                0 => {
                    for c in left..=right {
                        mask[top as usize * w + c as usize] = 1;
                    }
                    top += 2; // leave a gap row so the spiral doesn't fill solid
                }
                1 => {
                    for r in top..=bottom {
                        mask[r as usize * w + right as usize] = 1;
                    }
                    right -= 2;
                }
                2 => {
                    if top <= bottom {
                        for c in (left..=right).rev() {
                            mask[bottom as usize * w + c as usize] = 1;
                        }
                    }
                    bottom -= 2;
                }
                _ => {
                    if left <= right {
                        for r in (top..=bottom).rev() {
                            mask[r as usize * w + left as usize] = 1;
                        }
                    }
                    left += 2;
                }
            }
            turn += 1;
        }
        let (got, _) = label_components_8(&mask, h, w);
        let (want, _) = flood_fill_reference(&mask, h, w);
        assert_same_partition(&got, &want);
    }

    #[test]
    fn test_many_small_components_matches_flood_fill_reference() {
        let h = 15;
        let w = 15;
        let mut mask = vec![0u8; h * w];
        // Isolated single cells on a grid, spaced 2 apart so they cannot
        // touch (4- or 8-connectivity), giving a known component count.
        let mut expected = 0;
        for r in (0..h).step_by(2) {
            for c in (0..w).step_by(2) {
                mask[r * w + c] = 1;
                expected += 1;
            }
        }
        let (got, n) = label_components_8(&mask, h, w);
        assert_eq!(n, expected);
        let (want, want_n) = flood_fill_reference(&mask, h, w);
        assert_eq!(n, want_n);
        assert_same_partition(&got, &want);
    }

    #[test]
    fn test_dense_random_matches_flood_fill_reference() {
        let mut state: u64 = 0x2545F4914F6CDD1D;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        };
        for trial in 0..10 {
            let h = 12 + trial;
            let w = 17 + trial;
            let mask: Vec<u8> = (0..h * w).map(|_| (next() % 2) as u8).collect();
            let (got, got_n) = label_components_8(&mask, h, w);
            let (want, want_n) = flood_fill_reference(&mask, h, w);
            assert_eq!(got_n, want_n, "trial {trial}: component count mismatch");
            assert_same_partition(&got, &want);
        }
    }

    #[test]
    fn test_non_square_grids() {
        for (h, w) in [(1, 9), (9, 1), (4, 60), (60, 4), (1, 1)] {
            let mask = vec![1u8; h * w];
            let (labels, n) = label_components_8(&mask, h, w);
            assert_eq!(n, 1, "{h}x{w} all-foreground should be one component");
            assert!(labels.iter().all(|&l| l == 1));
        }
    }

    #[test]
    fn test_border_touching_components() {
        // Two components, each hugging opposite borders, not connected.
        let h = 5;
        let w = 5;
        let mut mask = vec![0u8; h * w];
        for r in 0..h {
            mask[r * w] = 1; // left column
        }
        for r in 0..h {
            mask[r * w + w - 1] = 1; // right column
        }
        let (labels, n) = label_components_8(&mask, h, w);
        assert_eq!(n, 2);
        assert_ne!(labels[0], labels[w - 1]);
    }

    #[test]
    fn test_labels_are_first_encounter_raster_order() {
        // Not a hard contract (see module doc / evidence doc), but this
        // implementation's chosen numbering should be deterministic and
        // match raster first-encounter order, which this test pins.
        let mut mask = vec![0u8; 10];
        mask[2] = 1; // (r=0,c=2): encountered first in raster order
        mask[9] = 1; // (r=1,c=4): column distance 2 from (0,2) -- not an
                     // 8-neighbor of it (only column-adjacent cells qualify), so this is
                     // a genuinely separate second component.
        let (labels, n) = label_components_8(&mask, 2, 5);
        assert_eq!(n, 2);
        assert_eq!(
            labels[2], 1,
            "first foreground cell in raster order gets label 1"
        );
        assert_eq!(labels[9], 2, "second gets label 2");
    }
}
