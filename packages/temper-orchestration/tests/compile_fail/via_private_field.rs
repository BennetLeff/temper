// GUARD: every `Via` field is private, so `Via::emit_s_expr` is the only
// sexpr-producing path.
//
// The pre-fix router formatted raw `(via (at ...))` strings itself, with no
// type token -- and KiCad's parser defaults a tokenless via to THROUGH. A
// blind/buried via silently became a through via, drilling copper it must not
// touch. `emit_s_expr` ALWAYS computes the token from the layer pair first; if
// a caller could read `from_layer`/`to_layer` they could format the sexpr
// themselves and reintroduce exactly that bug.
//
// EXPECTED ERROR: E0616 (field `from_layer` of struct `Via` is private).
fn main() {
    let via = temper_orchestration::Via::new(0.3, 0.3, "F.Cu", "In3.Cu", 0.6, 0.3);
    let _ = via.from_layer;
}
