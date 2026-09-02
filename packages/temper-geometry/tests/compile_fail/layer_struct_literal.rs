// GUARD: `Layer` has private fields and no public constructor.
//
// A hardcoded stale copy of a copper layer -- `Layer { name: "F.Cu".into(),
// role: LayerRole::Signal, .. }` -- written anywhere outside `layer_identity`
// must not compile. The only ways to build one are `Stackup::parse` /
// `Stackup::from_path` (reading a real board's own declaration) or the
// explicit `Stackup::test_only` escape hatch.
//
// EXPECTED ERROR: E0451 (field of struct is private).
use temper_geometry::layer_identity::{Layer, LayerPosition, LayerRole};

fn main() {
    let _bad = Layer {
        name: "F.Cu".to_string(),
        role: LayerRole::Signal,
        position: LayerPosition::Outer,
        copper_thickness_mm: 0.070,
    };
}
