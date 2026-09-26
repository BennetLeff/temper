//! Deterministic rectangular shelf poses for the first native projection.
//!
//! This is an artifact staging tool, not an electrical placement algorithm.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Copy, Deserialize)]
pub struct Bounds {
    pub min_x: f64,
    pub min_y: f64,
    pub max_x: f64,
    pub max_y: f64,
}

#[derive(Debug, Deserialize)]
pub struct Part {
    pub path: String,
    pub bounds: Bounds,
    #[serde(default)]
    pub fallback_from_pads: bool,
}

#[derive(Debug, Deserialize)]
pub struct ShelfInput {
    pub outline_mm: [f64; 4],
    pub parts: Vec<Part>,
}

#[derive(Debug, Serialize)]
pub struct ShelfResult {
    pub poses: BTreeMap<String, [f64; 3]>,
    pub required_height_mm: f64,
}

#[derive(Debug, Clone, Copy)]
struct MicrometerBounds {
    min_x: i64,
    min_y: i64,
    max_x: i64,
    max_y: i64,
}

impl MicrometerBounds {
    fn from_mm(bounds: Bounds) -> Result<Self, String> {
        for coordinate in [bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y] {
            if !coordinate.is_finite() || coordinate.abs() > 1_000_000.0 {
                return Err("footprint bounds must be finite and within 1000 m".into());
            }
        }
        if bounds.max_x <= bounds.min_x || bounds.max_y <= bounds.min_y {
            return Err("footprint bounds must have positive width and height".into());
        }
        // Outward rounding makes the emitted three-decimal poses conservative.
        Ok(Self {
            min_x: (bounds.min_x * 1000.0).floor() as i64,
            min_y: (bounds.min_y * 1000.0).floor() as i64,
            max_x: (bounds.max_x * 1000.0).ceil() as i64,
            max_y: (bounds.max_y * 1000.0).ceil() as i64,
        })
    }

    fn width(self) -> i64 {
        self.max_x - self.min_x
    }

    fn height(self) -> i64 {
        self.max_y - self.min_y
    }
}

/// Pack measured footprint rectangles at angle zero with 3 mm gaps and a 5 mm edge margin.
/// Returns an error without poses if the supplied outline is too small.
pub fn pack(input: ShelfInput) -> Result<ShelfResult, String> {
    let [x1, y1, x2, y2] = input.outline_mm;
    for coordinate in input.outline_mm {
        if !coordinate.is_finite() || coordinate.abs() > 1_000_000.0 {
            return Err("outline must be finite and within 1000 m".into());
        }
    }
    if x2 <= x1 || y2 <= y1 {
        return Err("outline must have positive width and height".into());
    }
    let left = (x1 * 1000.0).ceil() as i64 + 5000;
    let top = (y1 * 1000.0).ceil() as i64 + 5000;
    let right = (x2 * 1000.0).floor() as i64 - 5000;
    let bottom = (y2 * 1000.0).floor() as i64 - 5000;
    if right <= left || bottom <= top {
        return Err("outline has no room after the 5 mm margin".into());
    }

    let mut seen = BTreeSet::new();
    let mut parts = Vec::with_capacity(input.parts.len());
    for part in input.parts {
        if part.path.is_empty() || !seen.insert(part.path.clone()) {
            return Err(format!("empty or duplicate instance path: {:?}", part.path));
        }
        let mut bounds = MicrometerBounds::from_mm(part.bounds)?;
        if part.fallback_from_pads {
            bounds.min_x -= 1000;
            bounds.min_y -= 1000;
            bounds.max_x += 1000;
            bounds.max_y += 1000;
        }
        if bounds.width() > right - left {
            return Err(format!(
                "{} needs {:.3} mm usable width, outline has {:.3} mm",
                part.path,
                bounds.width() as f64 / 1000.0,
                (right - left) as f64 / 1000.0
            ));
        }
        parts.push((part.path, bounds));
    }
    // Tall parts first keep later rows from inheriting a much taller part's
    // height after their width is already committed.
    parts.sort_by(|a, b| {
        b.1.height()
            .cmp(&a.1.height())
            .then_with(|| b.1.width().cmp(&a.1.width()))
            .then_with(|| a.0.cmp(&b.0))
    });

    let mut poses = BTreeMap::new();
    let mut cursor_x = left;
    let mut cursor_y = top;
    let mut row_height = 0;
    let mut required_bottom = top;
    for (path, bounds) in parts {
        if cursor_x != left && cursor_x + bounds.width() > right {
            cursor_y += row_height + 3000;
            cursor_x = left;
            row_height = 0;
        }
        poses.insert(
            path,
            [
                (cursor_x - bounds.min_x) as f64 / 1000.0,
                (cursor_y - bounds.min_y) as f64 / 1000.0,
                0.0,
            ],
        );
        required_bottom = required_bottom.max(cursor_y + bounds.height());
        cursor_x += bounds.width() + 3000;
        row_height = row_height.max(bounds.height());
    }
    let required_height_mm =
        (required_bottom + 5000 - (y1 * 1000.0).floor() as i64) as f64 / 1000.0;
    if required_bottom > bottom {
        return Err(format!(
            "shelf needs {:.3} mm total height including margins; outline provides {:.3} mm",
            required_height_mm,
            y2 - y1
        ));
    }
    Ok(ShelfResult {
        poses,
        required_height_mm,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn part(path: &str, bounds: [f64; 4]) -> Part {
        Part {
            path: path.into(),
            bounds: Bounds {
                min_x: bounds[0],
                min_y: bounds[1],
                max_x: bounds[2],
                max_y: bounds[3],
            },
            fallback_from_pads: false,
        }
    }

    #[test]
    fn origin_offsets_and_gap_are_preserved() {
        let result = pack(ShelfInput {
            outline_mm: [0.0, 0.0, 40.0, 30.0],
            parts: vec![
                part("b", [-4.0, -2.0, 6.0, 2.0]),
                part("a", [0.0, 0.0, 10.0, 4.0]),
            ],
        })
        .unwrap();
        assert_eq!(result.poses["a"], [5.0, 5.0, 0.0]);
        assert_eq!(result.poses["b"], [22.0, 7.0, 0.0]);
    }

    #[test]
    fn overflow_rejects_entire_output_and_reports_height() {
        let err = pack(ShelfInput {
            outline_mm: [0.0, 0.0, 20.0, 17.0],
            parts: vec![
                part("a", [0.0, 0.0, 10.0, 4.0]),
                part("b", [0.0, 0.0, 10.0, 4.0]),
            ],
        })
        .unwrap_err();
        assert!(err.contains("needs 21.000 mm total height"), "{err}");
    }

    #[test]
    fn path_tiebreak_is_input_order_independent() {
        let make = |paths: &[&str]| ShelfInput {
            outline_mm: [0.0, 0.0, 40.0, 30.0],
            parts: paths
                .iter()
                .map(|path| part(path, [0.0, 0.0, 10.0, 4.0]))
                .collect(),
        };
        assert_eq!(
            pack(make(&["b", "a"])).unwrap().poses,
            pack(make(&["a", "b"])).unwrap().poses
        );
    }

    #[test]
    fn larger_part_leads_and_fractional_bounds_round_outward() {
        let result = pack(ShelfInput {
            outline_mm: [0.0, 0.0, 50.0, 30.0],
            parts: vec![
                part("small", [0.0, 0.0, 2.0, 2.0]),
                part("large", [-0.0001, 0.0, 10.0001, 8.0]),
            ],
        })
        .unwrap();
        assert_eq!(result.poses["large"], [5.001, 5.0, 0.0]);
        assert_eq!(result.poses["small"], [18.002, 5.0, 0.0]);
    }

    #[test]
    fn pad_fallback_expands_one_mm_per_side_in_rust() {
        let mut fallback = part("fallback", [0.0, 0.0, 2.0, 2.0]);
        fallback.fallback_from_pads = true;
        let result = pack(ShelfInput {
            outline_mm: [0.0, 0.0, 30.0, 20.0],
            parts: vec![fallback, part("neighbor", [0.0, 0.0, 2.0, 2.0])],
        })
        .unwrap();
        assert_eq!(result.poses["fallback"], [6.0, 6.0, 0.0]);
        assert_eq!(result.poses["neighbor"], [12.0, 5.0, 0.0]);
    }

    #[test]
    fn height_order_packs_mixed_parts_inside_outline_without_overlap() {
        let parts = [
            part("low_wide", [-2.0, -1.0, 31.0, 14.0]),
            part("tall", [0.0, 0.0, 19.0, 24.0]),
            part("mid", [-1.0, -2.0, 15.0, 10.0]),
            part("small_1", [0.0, 0.0, 4.0, 3.0]),
            part("small_2", [0.0, 0.0, 4.0, 3.0]),
            part("small_3", [0.0, 0.0, 4.0, 3.0]),
        ];
        let outline = [0.0, 0.0, 50.0, 80.0];
        let result = pack(ShelfInput {
            outline_mm: outline,
            parts: parts
                .iter()
                .map(|p| {
                    part(
                        &p.path,
                        [
                            p.bounds.min_x,
                            p.bounds.min_y,
                            p.bounds.max_x,
                            p.bounds.max_y,
                        ],
                    )
                })
                .collect(),
        })
        .unwrap();
        let reversed = pack(ShelfInput {
            outline_mm: outline,
            parts: parts
                .iter()
                .rev()
                .map(|p| {
                    part(
                        &p.path,
                        [
                            p.bounds.min_x,
                            p.bounds.min_y,
                            p.bounds.max_x,
                            p.bounds.max_y,
                        ],
                    )
                })
                .collect(),
        })
        .unwrap();
        assert_eq!(result.poses, reversed.poses);
        assert_eq!(result.poses.len(), parts.len());
        let boxes: Vec<[f64; 4]> = parts
            .iter()
            .map(|part| {
                let [x, y, angle] = result.poses[&part.path];
                assert_eq!(angle, 0.0);
                let b = part.bounds;
                let rect = [x + b.min_x, y + b.min_y, x + b.max_x, y + b.max_y];
                assert!(rect[0] >= outline[0] + 5.0 && rect[1] >= outline[1] + 5.0);
                assert!(rect[2] <= outline[2] - 5.0 && rect[3] <= outline[3] - 5.0);
                rect
            })
            .collect();
        for (i, a) in boxes.iter().enumerate() {
            for b in boxes.iter().skip(i + 1) {
                assert!(
                    a[2] + 3.0 <= b[0]
                        || b[2] + 3.0 <= a[0]
                        || a[3] + 3.0 <= b[1]
                        || b[3] + 3.0 <= a[1],
                    "footprints lack a 3 mm separation: {a:?}, {b:?}"
                );
            }
        }
        assert_eq!(result.poses["tall"], [5.0, 5.0, 0.0]);
    }
}
