// GUARD: `WorldPosition` has no public constructor from raw coordinates.
//
// The recurring defect (three times: zone-stitch swap shorts, zone hulls at
// wrong coordinates, the `run_collect_pad_positions` rotation omission) is a
// naive `comp_pos + pin_pos` sum with no component rotation. The structural
// fix is private fields: an unrotated pair has no way into the type.
//
// EXPECTED ERROR: E0451 (field of struct is private).
// If this ever compiles, the guard is gone. If it fails with a DIFFERENT
// error, the test is no longer exercising the guard -- the .stderr diff
// catches both.
fn main() {
    let _bad = temper_geometry::WorldPosition { x: 1.0, y: 2.0 };
}
