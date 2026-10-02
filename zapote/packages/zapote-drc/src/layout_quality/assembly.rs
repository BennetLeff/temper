//! Worst-case assembly/access separation of axis-aligned 3D envelopes.
//!
//! Envelopes already include component orientation. Expansion represents bounded
//! position/body variation and symmetric tool access. Overlap is a conservative
//! screen finding, not proof that the actual non-box bodies collide.
use super::{ensure, finite, identities, nonnegative, Error};
use serde::{Deserialize, Serialize};

/// Board-space component, hardware, or tool envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope {
    /// Assembly object identity.
    pub object: String,
    /// Minimum [x,y,z], mm.
    pub min_mm: [f64; 3],
    /// Maximum [x,y,z], mm.
    pub max_mm: [f64; 3],
    /// Independent worst-case per-axis expansion on each face, mm.
    pub tolerance_mm: [f64; 3],
    /// Additional symmetric access envelope on each face, mm.
    pub access_mm: [f64; 3],
}

/// Separation of one pair, with tolerances and access reserved.
#[derive(Debug, Clone, Serialize)]
pub struct Pair {
    /// First object.
    pub first: String,
    /// Second object.
    pub second: String,
    /// Positive Euclidean clearance, or negative minimum axis penetration, mm.
    pub signed_gap_mm: f64,
}

fn expand(e: &Envelope) -> Result<([f64; 3], [f64; 3]), Error> {
    let mut lo = e.min_mm;
    let mut hi = e.max_mm;
    for axis in 0..3 {
        finite(lo[axis], "envelope min")?;
        finite(hi[axis], "envelope max")?;
        ensure(
            lo[axis] < hi[axis],
            "envelope must have positive extent on each axis",
        )?;
        let expansion = nonnegative(e.tolerance_mm[axis], "tolerance")?
            + nonnegative(e.access_mm[axis], "access")?;
        lo[axis] = finite(lo[axis] - expansion, "expanded min")?;
        hi[axis] = finite(hi[axis] + expansion, "expanded max")?;
    }
    Ok((lo, hi))
}

/// Return pairs within `search_distance_mm`, ordered from worst gap to best.
/// A sweep prunes x-disjoint envelopes; work is O(n log n + candidate pairs),
/// worst-case O(n²). An empty result means no pair within the search radius.
///
/// # Errors
/// Rejects fewer than two objects, duplicate identities, invalid boxes,
/// negative tolerances/search distance and numeric overflow.
pub fn nearby(envelopes: &[Envelope], search_distance_mm: f64) -> Result<Vec<Pair>, Error> {
    nonnegative(search_distance_mm, "search_distance_mm")?;
    ensure(
        envelopes.len() >= 2,
        "assembly requires at least two envelopes",
    )?;
    identities(envelopes.iter().map(|e| e.object.as_str()))?;
    let bounds = envelopes
        .iter()
        .map(expand)
        .collect::<Result<Vec<_>, _>>()?;
    let mut order: Vec<_> = (0..envelopes.len()).collect();
    order.sort_by(|&a, &b| {
        bounds[a].0[0]
            .total_cmp(&bounds[b].0[0])
            .then(envelopes[a].object.cmp(&envelopes[b].object))
    });
    let mut active: Vec<usize> = Vec::new();
    let mut pairs = Vec::new();
    for i in order {
        active.retain(|&j| bounds[i].0[0] - bounds[j].1[0] <= search_distance_mm);
        for &j in &active {
            let mut distance: f64 = 0.0;
            let mut penetration = f64::INFINITY;
            for axis in 0..3 {
                let gap = finite(
                    (bounds[i].0[axis] - bounds[j].1[axis])
                        .max(bounds[j].0[axis] - bounds[i].1[axis]),
                    "axis gap",
                )?;
                distance = distance.hypot(gap.max(0.0));
                penetration = penetration.min(-gap);
            }
            let gap = finite(
                if distance > 0.0 {
                    distance
                } else {
                    -penetration
                },
                "assembly gap",
            )?;
            if gap <= search_distance_mm {
                let (a, b) = if envelopes[i].object < envelopes[j].object {
                    (i, j)
                } else {
                    (j, i)
                };
                pairs.push(Pair {
                    first: envelopes[a].object.clone(),
                    second: envelopes[b].object.clone(),
                    signed_gap_mm: gap,
                });
            }
        }
        active.push(i);
    }
    pairs.sort_by(|a, b| {
        a.signed_gap_mm
            .total_cmp(&b.signed_gap_mm)
            .then(a.first.cmp(&b.first))
            .then(a.second.cmp(&b.second))
    });
    Ok(pairs)
}
