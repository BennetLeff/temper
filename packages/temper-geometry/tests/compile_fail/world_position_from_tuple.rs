// GUARD: no `From<(f64, f64)>` for `WorldPosition`.
//
// A raw (x, y) pair must never become a `WorldPosition` without passing
// through `from_component_pin`, which applies the full rotation kernel
// (mirror + R(-theta) + quadrant + component position).
//
// EXPECTED ERROR: E0277 (trait bound `WorldPosition: From<(f64, f64)>` not
// satisfied / the trait `Into` is not implemented).
fn main() {
    let _bad: temper_geometry::WorldPosition = (1.0, 2.0).into();
}
