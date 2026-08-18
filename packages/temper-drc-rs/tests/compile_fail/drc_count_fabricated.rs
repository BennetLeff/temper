// GUARD: `DrcCount`'s fields are private, so `is_capped` can never disagree
// with the count it classifies.
//
// KiCad's DRC reporter saturates at a per-category cap. A count equal to the
// cap is a FLOOR, not the truth. `from_kicad` is the only constructor and it
// derives `is_capped` from the category's own cap table -- hand-building
// `DrcCount { count: 199, is_capped: false }` would launder a saturated count
// into an "honest" zero-violations claim on a mains board.
//
// This guard previously had NO compile_fail doctest at all despite being cited
// as one of the type-system guards.
//
// EXPECTED ERROR: E0451 (field of struct is private).
use temper_drc_rs::drc_count::DrcCount;

fn main() {
    let _laundered = DrcCount {
        count: 199,
        is_capped: false,
    };
}
