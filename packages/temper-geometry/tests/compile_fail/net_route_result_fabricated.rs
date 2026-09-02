// GUARD: `NetRouteResult::Connected` cannot be fabricated.
//
// `VerifiedRoute`'s fields are private to `net_route_result`, so the A* engine
// (or any caller) cannot hand-build a "connected" verdict. `Connected` is
// reachable ONLY through `NetRouteResult::verify_continuity`, which checks the
// claimed route against the real copper geometry. A fake completion on a mains
// board means an unrouted net reported as done.
//
// EXPECTED ERROR: E0451 (field of struct is private).
use temper_geometry::net_route_result::{NetRouteResult, VerifiedRoute};

fn main() {
    let _fake = NetRouteResult::Connected(VerifiedRoute {
        pad_ids: vec![0, 1],
        segment_ids: vec![],
        via_ids: vec![],
    });
}
