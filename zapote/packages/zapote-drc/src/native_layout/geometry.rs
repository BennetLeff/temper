use super::{finite, require, Polygon, Result};
use geo::{Area, LineString, MultiPolygon};

pub(super) fn distance(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}
fn ring(points: &[[f64; 2]]) -> Result<LineString<f64>> {
    require(
        points.len() >= 3,
        "native polygon has fewer than three vertices",
    )?;
    for p in points {
        for &v in p {
            finite(v)?;
        }
    }
    Ok(LineString::from(
        points.iter().map(|p| (p[0], p[1])).collect::<Vec<_>>(),
    ))
}
pub(super) fn shape(polygons: &[Polygon]) -> Result<MultiPolygon<f64>> {
    require(!polygons.is_empty(), "missing native polygon")?;
    let shapes = polygons
        .iter()
        .map(|p| {
            let value = geo::Polygon::new(
                ring(&p.shell)?,
                p.holes.iter().map(|h| ring(h)).collect::<Result<_>>()?,
            );
            require(
                finite(value.unsigned_area())? > 0.0,
                "native polygon has no positive area",
            )?;
            Ok(value)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(MultiPolygon(shapes))
}
