// GUARD: `ClearanceHalo`'s polygon field is private.
//
// A halo is only valid if it is a *conservative superset* -- a circumscribed
// polygon whose edges sit at the required separation, verified against
// boundary witnesses at construction. Reading or replacing the raw polygon
// from outside would let a caller substitute an unverified (possibly
// inscribed, i.e. clearance-violating) polygon. On a mains board this is the
// difference between a real 12.6mm PD3 barrier and a decorative one.
//
// This guard previously had NO compile_fail doctest at all despite being
// cited as one of the type-system guards.
//
// EXPECTED ERROR: E0616 (field `polygon` of struct `ClearanceHalo` is
// private).
use temper_geometry::clearance_halo::ClearanceHalo;

fn read_polygon(halo: &ClearanceHalo) {
    let _bad = &halo.polygon;
}

fn main() {}
