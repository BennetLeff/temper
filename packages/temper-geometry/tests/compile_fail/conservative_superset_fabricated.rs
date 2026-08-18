// GUARD: the `ConservativeSuperset` ZST marker cannot be minted externally.
//
// The marker is the proof-carrying token that the containment check actually
// ran and passed. Its only field and only constructor are private, so external
// code can NAME the type but cannot fabricate the guarantee -- which is what
// stops someone assembling a `ClearanceHalo` that never verified its witnesses.
//
// This guard previously had NO compile_fail doctest at all.
//
// EXPECTED ERROR: E0451 (field `_private` of struct is private).
use temper_geometry::clearance_halo::ConservativeSuperset;

fn main() {
    let _forged = ConservativeSuperset { _private: () };
}
