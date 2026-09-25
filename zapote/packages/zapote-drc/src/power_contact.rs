//! Native copper entry cross-sections. No component/body-size proxy is used.
//! Inside-approximated pad polygons and outside-approximated drill polygons
//! make observed chords conservative. A sampled chord is a lower bound on
//! available attachment width, not a global pad/plane minimum-cut calculation.
use crate::manufacturing::Polygon;

#[derive(Debug, Clone, serde::Serialize)]
pub struct Entry {
    pub certified_chord_mm: f64,
    pub trace_width_mm: f64,
    pub full_width_chord_observed: bool,
    pub sections_examined: usize,
    pub witness_centerline_mm: Option<[f64; 2]>,
}

fn valid(p: &Polygon) -> bool {
    p.vertices_mm.len() >= 3 && p.vertices_mm.iter().flatten().all(|x| x.is_finite())
}

fn union(mut intervals: Vec<(f64, f64)>) -> Vec<(f64, f64)> {
    intervals.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut result: Vec<(f64, f64)> = vec![];
    for (a, b) in intervals {
        if let Some(last) = result.last_mut() {
            if a <= last.1 {
                last.1 = last.1.max(b);
                continue;
            }
        }
        result.push((a, b));
    }
    result
}

fn intervals(poly: &Polygon, x: f64) -> Vec<(f64, f64)> {
    let mut crossings = vec![];
    for (a, b) in poly
        .vertices_mm
        .iter()
        .zip(poly.vertices_mm.iter().cycle().skip(1))
        .take(poly.vertices_mm.len())
    {
        if (a[0] > x) != (b[0] > x) {
            crossings.push(a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0]));
        }
    }
    crossings.sort_by(f64::total_cmp);
    crossings.chunks_exact(2).map(|p| (p[0], p[1])).collect()
}

/// Certificate along the straight portion of a trace, excluding its end caps.
/// Rounded-cap-only/grazing contacts may exist without a certificate. Callers
/// must report those as incomplete rather than declare a disconnected board.
pub fn entry(
    pads: &[Polygon],
    drill: Option<&Polygon>,
    start: [f64; 2],
    end: [f64; 2],
    width: f64,
) -> Result<Entry, String> {
    if pads.is_empty()
        || pads.iter().any(|p| !valid(p))
        || drill.is_some_and(|p| !valid(p))
        || !width.is_finite()
        || width <= 0.0
        || start.iter().chain(end.iter()).any(|v| !v.is_finite())
    {
        return Err("malformed native entry geometry".into());
    }
    let dx = end[0] - start[0];
    let dy = end[1] - start[1];
    let length = dx.hypot(dy);
    if !length.is_finite() || length <= 0.0 {
        return Err("zero or invalid trace length".into());
    }
    let transform = |p: &Polygon| Polygon {
        vertices_mm: p
            .vertices_mm
            .iter()
            .map(|q| {
                let x = q[0] - start[0];
                let y = q[1] - start[1];
                [(x * dx + y * dy) / length, (-x * dy + y * dx) / length]
            })
            .collect(),
    };
    let pads: Vec<_> = pads.iter().map(transform).collect();
    let hole = drill.map(transform);
    let mut cuts = vec![0.0, length];
    for p in pads.iter().chain(hole.iter()) {
        cuts.extend(
            p.vertices_mm
                .iter()
                .map(|p| p[0])
                .filter(|x| *x > 0.0 && *x < length),
        );
    }
    cuts.sort_by(f64::total_cmp);
    cuts.dedup_by(|a, b| (*a - *b).abs() < 1e-10);
    let mut best = 0.0_f64;
    let mut examined = 0;
    let mut witness = None;
    // Midpoints avoid polygon-vertex degeneracies. Additional interior probes
    // can improve the lower bound; none can turn an unsampled gap into a pass.
    for pair in cuts.windows(2) {
        for fraction in [0.25, 0.5, 0.75] {
            let x = pair[0] + fraction * (pair[1] - pair[0]);
            let mut copper = union(pads.iter().flat_map(|p| intervals(p, x)).collect());
            for (h0, h1) in hole.as_ref().map(|p| intervals(p, x)).unwrap_or_default() {
                copper = copper
                    .into_iter()
                    .flat_map(|(a, b)| {
                        let mut pieces = vec![];
                        if h0 > a {
                            pieces.push((a, b.min(h0)));
                        }
                        if h1 < b {
                            pieces.push((a.max(h1), b));
                        }
                        pieces.into_iter().filter(|(a, b)| b > a)
                    })
                    .collect();
            }
            for (a, b) in copper {
                let chord = (b.min(width / 2.0) - a.max(-width / 2.0)).max(0.0);
                if chord > best {
                    best = chord;
                    witness = Some([start[0] + x * dx / length, start[1] + x * dy / length]);
                }
            }
            examined += 1;
        }
    }
    Ok(Entry {
        certified_chord_mm: best,
        trace_width_mm: width,
        full_width_chord_observed: best >= width - 1e-9,
        sections_examined: examined,
        witness_centerline_mm: witness,
    })
}

/// Same copied IPC scalar as the existing power checks: external copper,
/// assumed 20 C rise. This is not a fabrication-qualified current rating.
pub fn capacity_a(width_mm: f64, copper_um: f64) -> Result<f64, String> {
    if !width_mm.is_finite() || width_mm <= 0.0 || !copper_um.is_finite() || copper_um <= 0.0 {
        return Err("invalid copper dimensions".into());
    }
    Ok(crate::ipc::external_capacity_a(width_mm, copper_um))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rect(a: f64, b: f64, c: f64, d: f64) -> Polygon {
        Polygon {
            vertices_mm: vec![[a, b], [c, b], [c, d], [a, d]],
        }
    }
    #[test]
    fn large_pad_never_hides_a_narrow_trace() {
        let r = entry(&[rect(-5., -5., 5., 5.)], None, [-10., 0.], [0., 0.], 0.2).unwrap();
        assert!((r.certified_chord_mm - 0.2).abs() < 1e-9);
        assert!(r.full_width_chord_observed);
        assert!(capacity_a(r.certified_chord_mm, 70.).unwrap() < 15.);
    }
    #[test]
    fn drill_void_and_tangent_do_not_create_a_chord() {
        let pad = rect(-2., -2., 2., 2.);
        let hole = rect(-1., -1., 1., 1.);
        assert_eq!(
            entry(
                std::slice::from_ref(&pad),
                Some(&hole),
                [-0.5, 0.],
                [0.5, 0.],
                0.2
            )
            .unwrap()
            .certified_chord_mm,
            0.
        );
        assert_eq!(
            entry(std::slice::from_ref(&pad), None, [-3., 2.1], [3., 2.1], 0.2)
                .unwrap()
                .certified_chord_mm,
            0.
        );
        assert!(
            entry(&[pad], Some(&hole), [-3., 1.5], [0., 1.5], 0.2)
                .unwrap()
                .full_width_chord_observed
        );
    }
    #[test]
    fn side_overlap_is_measured_and_direction_invariant() {
        let pad = rect(-2., -2., 2., 2.);
        let a = entry(std::slice::from_ref(&pad), None, [-3., 2.1], [3., 2.1], 0.4).unwrap();
        let b = entry(&[pad], None, [3., 2.1], [-3., 2.1], 0.4).unwrap();
        assert!((a.certified_chord_mm - 0.1).abs() < 1e-9);
        assert!((a.certified_chord_mm - b.certified_chord_mm).abs() < 1e-9);
        assert!(!a.full_width_chord_observed);
    }
}
