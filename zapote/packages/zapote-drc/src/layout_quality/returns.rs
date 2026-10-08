//! Geometric route detour plus shared-impedance pickup.
//! The direct chord is a placement reference, not an obstacle-legal route.
use super::{
    coupling::{self, SharedImpedance},
    ensure, finite, positive, Error,
};
use serde::{Deserialize, Serialize};

/// One physically continuous, ordered return path; include via z transitions.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Input {
    /// Native route identity.
    pub object: String,
    /// Ordered board-space coordinates, mm.
    pub points_mm: Vec<[f64; 3]>,
    /// Shared conductor terms from the source-bound connectivity graph.
    pub shared: Vec<SharedImpedance>,
}

/// Detour and disturbance kept as separate quantities.
#[derive(Debug, Clone, Serialize)]
pub struct ResultRow {
    /// Native route identity.
    pub object: String,
    /// Complete polyline length, mm.
    pub route_length_mm: f64,
    /// Endpoint separation, mm.
    pub direct_length_mm: f64,
    /// Route length divided by endpoint separation; at least one.
    pub detour_ratio: f64,
    /// Signed shared-return disturbance, V.
    pub shared_voltage_v: f64,
    /// Independent-sign shared-return disturbance bound, V.
    pub shared_voltage_bound_v: f64,
}

fn distance(a: [f64; 3], b: [f64; 3]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1]).hypot(a[2] - b[2])
}

/// Measure route detour and evaluate declared common-impedance terms.
///
/// # Errors
/// Rejects missing paths, repeated vertices, coincident endpoints and invalid
/// or overflowing coordinates/model values. Does not infer connectivity from
/// proximity; the caller must supply a continuous native path.
pub fn evaluate(input: &Input) -> Result<ResultRow, Error> {
    ensure(!input.object.trim().is_empty(), "return identity is blank")?;
    ensure(
        input.points_mm.len() >= 2,
        "return path needs at least two points",
    )?;
    for p in &input.points_mm {
        for &v in p {
            finite(v, "return coordinate")?;
        }
    }
    let mut length = 0.0;
    for pair in input.points_mm.windows(2) {
        length += positive(distance(pair[0], pair[1]), "segment length")?;
    }
    let direct = positive(
        distance(
            input.points_mm[0],
            input.points_mm[input.points_mm.len() - 1],
        ),
        "endpoint separation",
    )?;
    let (voltage, bound) = coupling::shared_voltage(&input.shared)?;
    Ok(ResultRow {
        object: input.object.clone(),
        route_length_mm: finite(length, "route length")?,
        direct_length_mm: direct,
        detour_ratio: finite(length / direct, "detour ratio")?.max(1.0),
        shared_voltage_v: voltage,
        shared_voltage_bound_v: bound,
    })
}
