// GUARD: `RotationQuadrant` has no `Div` impl.
//
// Treating the 0-3 quarter-turn index as if it were already degrees is the
// exact defect class this type exists to prevent. Without the newtype it is a
// silent wrong answer; with it, it is a compile error.
//
// EXPECTED ERROR: E0369 (cannot divide `RotationQuadrant` by `{integer}`).
use temper_geometry::rotation_quadrant::RotationQuadrant;

fn main() {
    let q = RotationQuadrant::from_raw(1);
    let _bad_degrees = q / 90;
}
