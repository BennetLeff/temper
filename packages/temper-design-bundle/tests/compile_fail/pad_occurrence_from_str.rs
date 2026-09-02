// GUARD: no `From<&str>` for `PadOccurrence`.
//
// A bare pad number must not silently stand in for "the" pad. K2's two
// physical pad-"3" holes sit 7.5mm apart; `get_pin`'s first-match shortcut
// applied to a footprint with duplicate pad numbers silently picks the wrong
// hole. The occurrence index must always be written explicitly.
//
// EXPECTED ERROR: E0277 (the trait bound `PadOccurrence: From<&str>` is not
// satisfied).
use temper_design_bundle::pad_occurrence::PadOccurrence;

fn main() {
    let _bad: PadOccurrence = "3".into();
}
