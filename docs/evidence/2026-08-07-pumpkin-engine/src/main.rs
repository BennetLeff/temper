//! Pumpkin-solver `Engine` backend for the BLOCKER-ORTOOLS equivalence harness.
//!
//! See `docs/evidence/2026-08-07-cpsat-equivalence-harness.md` Sec 5 for the
//! design this fulfils, and `docs/evidence/scripts/2026-08-07-pumpkin-equivalence-run.py`
//! for the Python-side `Engine` implementation that shells out to this binary.
//!
//! Protocol: reads one JSON `ModelSpec` object on stdin, writes one JSON
//! `SolveOutcome` object on stdout. No files, no state between invocations.
//!
//! Model encoding (mirrors `packages/temper-placer/src/temper_placer/placer/cp_sat/`
//! and the harness's own `IndependentVerifier`, transcribed independently from
//! each handler's documented geometric semantics -- not from OR-Tools variables):
//!
//! Per component: `x0,y0` (box origin), `w,h` (box size, chosen from the
//! component's two rotation-derived (w,h) orientations via an `element`
//! constraint on `rot`), and `cx,cy` (box center, tied to `x0,y0,w,h` via
//! `2*cx = 2*x0 + w`). All coordinates are integers in 0.01mm grid units,
//! matching the encoder's own `units_per_mm=100` -- this makes every
//! constraint below an exact integer relation, with no rounding tolerance
//! needed (the harness's `GRID_TOL_MM` is a post-hoc verifier allowance for
//! solver rounding, not something a from-scratch integer model needs).
//!
//! `AddNoOverlap2D` (constraint class C6) is intentionally not encoded: the
//! harness doc's Sec 1 table records it as redundant for correctness once
//! SEPARATED's auto-generated courtyard-tau pairs cover every component pair,
//! which the `constraints` list already includes (built by the harness's
//! `build_courtyard_constraints`, serialized as ordinary `separated` entries
//! by the Python side).

use std::collections::{HashMap, HashSet};
use std::io::{self, Read};
use std::ops::ControlFlow;
use std::time::{Duration, Instant};

use rand::rngs::SmallRng;
use rand::SeedableRng;
use serde::Deserialize;
use serde_json::{json, Value};

use pumpkin_solver::conflict_resolvers::resolvers::ResolutionResolver;
use pumpkin_solver::core::constraints::Constraint;
use pumpkin_solver::core::optimisation::linear_sat_unsat::LinearSatUnsat;
use pumpkin_solver::core::optimisation::OptimisationDirection;
use pumpkin_solver::core::options::SolverOptions;
use pumpkin_solver::core::proof::ConstraintTag;
use pumpkin_solver::core::results::{OptimisationResult, ProblemSolution, SatisfactionResult};
use pumpkin_solver::core::termination::TimeBudget;
use pumpkin_solver::core::variables::{DomainId, TransformableVariable};
use pumpkin_solver::Solver;

/// Grid units per mm. Matches `CpSatModel(units_per_mm=100)` in
/// `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`.
const SCALE: f64 = 100.0;

/// Round-half-even, THEN force even parity by rounding UP to the next even
/// integer (ceil-to-even), not down.
///
/// Started as a bit-exact port of `CpSatModel.mm_to_units` /
/// `temper-constraints`'s `encoder.rs::mm_to_units` (round-half-even, then
/// floor-modulo so an odd raw DECREMENTS by one). That direction is wrong
/// for this harness's purpose: decrementing shrinks the encoded quantity
/// below its true mm value, and for a component's `w0`/`h0` that means the
/// encoded box is smaller than the real footprint -- every SEPARATED
/// constraint on that component is then satisfiable at up to ~2x the
/// per-dimension shrink (both boxes in the pair can shrink) under its
/// declared minimum separation. Confirmed empirically on the real board
/// (`pcb/temper.kicad_pcb`, 169 components): exactly 6 of the 338
/// `w0`/`h0` dimensions hit the odd-raw branch, shrinking by up to
/// 0.010282mm each (e.g. `C2`'s 30.130282mm width raw-rounds to 3013,
/// odd, and used to decrement to 3012 = 30.12mm). The same sweep found
/// every OTHER `to_units` call site on that board (board bounds, edge
/// margin, SEPARATED/ADJACENT/ALIGNED distances, zone bounds) never hits
/// the odd-raw branch at all, so rounding up here has no observed effect
/// beyond the 6 component-size dimensions it exists to fix.
///
/// The even-parity requirement itself is NOT optional cosmetic parity: it
/// is REQUIRED by this program's own `2*cx = 2*x0 + w` midpoint identity
/// (the direct analogue of the real encoder's `x_start + x_end ==
/// 2*x_center`) -- an odd `w` or `h` makes that equation unsatisfiable over
/// the integers, which silently turns "component has an odd-hundredth-of-
/// a-mm footprint dimension" into a trivial, whole-model UNSAT with no
/// relation to any PCL constraint. Caught empirically: the `full-board`
/// corpus reported `infeasible` in ~30ms even with EVERY PCL constraint
/// stripped (board bounds only) until parity-forcing landed -- see
/// docs/evidence/scripts/2026-08-07-pumpkin-equivalence-run.py's git history /
/// commit message for the bisection that found it. Ceiling to the next
/// even integer preserves this exactly as well as flooring did (both
/// produce an even result); only the direction of the +/-1-unit
/// adjustment changed, so that regression is not reintroduced by this
/// function rounding up instead of down (re-verified: the full-board
/// corpus still solves, does not go infeasible).
///
/// Note this is a deliberate, bounded divergence from `CpSatModel.mm_to_units`
/// for the ~6-in-338 affected dimensions: this harness's model and
/// OR-Tools' production model are no longer bit-exact on those dimensions
/// (Pumpkin's boxes are up to 0.01mm larger). Given the measured 6mm+
/// isolation margins this operates over, and that ceiling only ever
/// *tightens* a SEPARATED constraint (never loosens one), this cannot turn
/// an OR-Tools SAT result into a spurious Pumpkin UNSAT-vs-SAT Tier-1
/// disagreement at any margin this repo has actually measured -- but it is
/// a real, intentional trade-off, not a hidden one.
fn to_units(mm: f64) -> i32 {
    let scaled = mm * SCALE;
    let raw = scaled.round_ties_even() as i64;
    let rem = raw.rem_euclid(2);
    (if rem != 0 { raw + 1 } else { raw }) as i32
}

#[cfg(test)]
mod to_units_tests {
    use super::*;

    /// The defect this function fixes: a component footprint dimension
    /// that raw-rounds to an odd hundredth-of-a-mm must never be encoded
    /// SMALLER than its nominal mm value. `C2`'s real board width
    /// (30.130282mm) is the exact real-world case that motivated this fix.
    #[test]
    fn encoded_box_is_never_smaller_than_nominal() {
        let cases = [30.130282_f64, 26.75, 33.65, 1.45, 9.49, 7.05];
        for mm in cases {
            let units = to_units(mm);
            let encoded_mm = units as f64 / SCALE;
            assert!(
                encoded_mm >= mm,
                "to_units({mm}) = {units} ({encoded_mm}mm) is smaller than nominal {mm}mm"
            );
        }
    }

    /// The parity invariant `to_units` exists to guarantee: every result
    /// is even, so `2*cx = 2*x0 + w` stays satisfiable over the integers
    /// for any `w`/`h` this function produces (see the doc comment above).
    #[test]
    fn result_is_always_even() {
        let cases = [0.0_f64, 0.01, 0.02, 1.45, 9.49, 30.130282, -1.45, -0.01];
        for mm in cases {
            let units = to_units(mm);
            assert_eq!(units.rem_euclid(2), 0, "to_units({mm}) = {units} is odd");
        }
    }

    /// Values that already round to an even raw are passed through
    /// unchanged (no unnecessary +1).
    #[test]
    fn even_raw_passes_through_unchanged() {
        assert_eq!(to_units(10.0), 1000);
        assert_eq!(to_units(0.02), 2);
    }

    /// Odd-raw values round UP (ceil) to the next even unit, not down.
    #[test]
    fn odd_raw_rounds_up_not_down() {
        // 30.130282mm -> scaled 3013.0282 -> raw 3013 (odd) -> 3014, i.e.
        // 30.14mm: at or above nominal, never 30.12mm (below nominal).
        assert_eq!(to_units(30.130282), 3014);
        // 0.01mm -> raw 1 (odd) -> 2, i.e. 0.02mm, not 0 (which would be
        // BELOW nominal and, for a component size, zero-width).
        assert_eq!(to_units(0.01), 2);
    }
}

fn to_mm(units: i32) -> f64 {
    units as f64 / SCALE
}

#[derive(Deserialize)]
struct CompSpec {
    w0_mm: f64,
    h0_mm: f64,
    rotatable: bool,
}

#[derive(Deserialize)]
struct ModelSpec {
    board_w_mm: f64,
    board_h_mm: f64,
    edge_margin_mm: f64,
    components: HashMap<String, CompSpec>,
    #[serde(default)]
    zones: HashMap<String, (f64, f64, f64, f64)>,
    #[serde(default)]
    zone_components: HashMap<String, Vec<String>>,
    #[serde(default)]
    loop_components: HashMap<String, Vec<String>>,
    constraints: Vec<Value>,
    #[serde(default)]
    minimize_displacement_to: Option<HashMap<String, (f64, f64)>>,
    // HPWL wirelength objective (2026-08-11 real-budget spike, docs/evidence/
    // 2026-08-11-pumpkin-real-budget-spike.md): net name -> member component
    // refs. For each net with >=2 members present in this model, adds
    // (max(cx) - min(cx)) + (max(cy) - min(cy)) to the minimised objective,
    // over component CENTERS (matches docs/plans/2026-08-11-002-feat-placer-
    // wirelength-and-hv-separation-plan.md R2's box-level-granularity
    // choice). Reuses the exact `pumpkin_solver::minimum`/`maximum` idiom
    // already present in this file's `loop_area` handler below -- no new
    // Pumpkin primitive needed.
    #[serde(default)]
    hpwl_nets: Option<HashMap<String, Vec<String>>>,
    seed: u64,
    timeout_ms: u64,
}

#[derive(Clone, Copy)]
struct CompVars {
    x0: DomainId,
    y0: DomainId,
    w: DomainId,
    h: DomainId,
    cx: DomainId,
    cy: DomainId,
    rot: DomainId,
}

/// Resolve a SEPARATED endpoint that may name a component OR a zone (the
/// zone expands to every component registered in it). Direct transcription
/// of the harness's own `_resolve()` in the `.py` companion.
fn resolve(name: &str, comp_refs: &HashSet<String>, zone_components: &HashMap<String, Vec<String>>) -> Vec<String> {
    if comp_refs.contains(name) {
        return vec![name.to_string()];
    }
    zone_components
        .get(name)
        .map(|refs| refs.iter().filter(|r| comp_refs.contains(*r)).cloned().collect())
        .unwrap_or_default()
}

fn f64_of(v: &Value) -> f64 {
    v.as_f64().expect("expected a number")
}

fn str_of(v: &Value) -> &str {
    v.as_str().expect("expected a string")
}

fn str_vec_of(v: &Value) -> Vec<String> {
    v.as_array()
        .expect("expected an array")
        .iter()
        .map(|x| str_of(x).to_string())
        .collect()
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let spec: ModelSpec = serde_json::from_str(&input).expect("parse ModelSpec JSON");

    let t0 = Instant::now();

    let rng = SmallRng::seed_from_u64(spec.seed);
    let mut solver = Solver::with_options(SolverOptions {
        random_generator: rng,
        ..Default::default()
    });
    let tag: ConstraintTag = solver.new_constraint_tag();

    let board_w = to_units(spec.board_w_mm);
    let board_h = to_units(spec.board_h_mm);
    let margin = to_units(spec.edge_margin_mm);

    let mut comp_refs: Vec<String> = spec.components.keys().cloned().collect();
    comp_refs.sort();
    let comp_ref_set: HashSet<String> = comp_refs.iter().cloned().collect();

    let mut vars: HashMap<String, CompVars> = HashMap::new();
    for r in &comp_refs {
        let c = &spec.components[r];
        let w0 = to_units(c.w0_mm);
        let h0 = to_units(c.h0_mm);
        let wh_min = w0.min(h0);
        let wh_max = w0.max(h0);

        let x0 = solver.new_bounded_integer(0, board_w);
        let y0 = solver.new_bounded_integer(0, board_h);
        let w = solver.new_bounded_integer(wh_min, wh_max);
        let h = solver.new_bounded_integer(wh_min, wh_max);
        let cx = solver.new_bounded_integer(0, board_w);
        let cy = solver.new_bounded_integer(0, board_h);
        let rot = if c.rotatable {
            solver.new_bounded_integer(0, 3)
        } else {
            solver.new_bounded_integer(0, 0)
        };

        // AddElement equivalent (C5): (w,h) selected from the rotation
        // table, transcribed from model.py::add_rotation's
        // [w0,h0,w0,h0] / [h0,w0,h0,w0] tables.
        pumpkin_solver::element(rot, vec![w0, h0, w0, h0], w, tag).post(&mut solver);
        pumpkin_solver::element(rot, vec![h0, w0, h0, w0], h, tag).post(&mut solver);

        // 2*cx = 2*x0 + w  (avoids a fractional half-width; box center tied
        // to box origin + size exactly, in integer grid units).
        pumpkin_solver::equals(vec![cx.scaled(2), x0.scaled(-2), w.scaled(-1)], 0, tag).post(&mut solver);
        pumpkin_solver::equals(vec![cy.scaled(2), y0.scaled(-2), h.scaled(-1)], 0, tag).post(&mut solver);

        // Board edge margin (C2).
        pumpkin_solver::greater_than_or_equals(vec![x0.scaled(1)], margin, tag).post(&mut solver);
        pumpkin_solver::greater_than_or_equals(vec![y0.scaled(1)], margin, tag).post(&mut solver);
        pumpkin_solver::less_than_or_equals(vec![x0.scaled(1), w.scaled(1)], board_w - margin, tag).post(&mut solver);
        pumpkin_solver::less_than_or_equals(vec![y0.scaled(1), h.scaled(1)], board_h - margin, tag).post(&mut solver);

        vars.insert(r.clone(), CompVars { x0, y0, w, h, cx, cy, rot });
    }

    for c in &spec.constraints {
        let ctype = c.get("type").and_then(|v| v.as_str()).unwrap_or("");
        match ctype {
            "separated" => {
                let a = str_of(&c["a"]);
                let b = str_of(&c["b"]);
                let min_d = to_units(f64_of(&c["min_distance_mm"]));
                let refs_a = resolve(a, &comp_ref_set, &spec.zone_components);
                let refs_b = resolve(b, &comp_ref_set, &spec.zone_components);
                for ra in &refs_a {
                    for rb in &refs_b {
                        if ra == rb {
                            continue;
                        }
                        let va = vars[ra];
                        let vb = vars[rb];
                        // Chebyshev disjunction (C4): a is left of b by
                        // min_d, OR b is left of a, OR a is below b, OR b
                        // is below a. Direct transcription of
                        // handlers/separated.py / the verifier's
                        // gap_x=max(ax0-bx1,bx0-ax1)>=min_d check.
                        let l1 = solver.new_literal();
                        let l2 = solver.new_literal();
                        let l3 = solver.new_literal();
                        let l4 = solver.new_literal();
                        pumpkin_solver::less_than_or_equals(
                            vec![va.x0.scaled(1), va.w.scaled(1), vb.x0.scaled(-1)],
                            -min_d,
                            tag,
                        )
                        .implied_by(&mut solver, l1);
                        pumpkin_solver::less_than_or_equals(
                            vec![vb.x0.scaled(1), vb.w.scaled(1), va.x0.scaled(-1)],
                            -min_d,
                            tag,
                        )
                        .implied_by(&mut solver, l2);
                        pumpkin_solver::less_than_or_equals(
                            vec![va.y0.scaled(1), va.h.scaled(1), vb.y0.scaled(-1)],
                            -min_d,
                            tag,
                        )
                        .implied_by(&mut solver, l3);
                        pumpkin_solver::less_than_or_equals(
                            vec![vb.y0.scaled(1), vb.h.scaled(1), va.y0.scaled(-1)],
                            -min_d,
                            tag,
                        )
                        .implied_by(&mut solver, l4);
                        pumpkin_solver::clause(vec![l1, l2, l3, l4], tag).post(&mut solver);
                    }
                }
            }
            "adjacent" => {
                let a = str_of(&c["a"]);
                let b = str_of(&c["b"]);
                let max_d = to_units(f64_of(&c["max_distance_mm"]));
                let metric = c.get("metric").and_then(|v| v.as_str()).unwrap_or("edge_to_edge");
                if let (Some(va), Some(vb)) = (vars.get(a).copied(), vars.get(b).copied()) {
                    // Both axes bounded (AND, not OR) -- unlike SEPARATED
                    // this needs no disjunction: max(p,q)<=K iff p<=K AND q<=K.
                    if metric == "center_to_center" {
                        pumpkin_solver::less_than_or_equals(vec![va.cx.scaled(1), vb.cx.scaled(-1)], max_d, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![vb.cx.scaled(1), va.cx.scaled(-1)], max_d, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![va.cy.scaled(1), vb.cy.scaled(-1)], max_d, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![vb.cy.scaled(1), va.cy.scaled(-1)], max_d, tag).post(&mut solver);
                    } else {
                        pumpkin_solver::less_than_or_equals(
                            vec![va.x0.scaled(1), vb.x0.scaled(-1), vb.w.scaled(-1)],
                            max_d,
                            tag,
                        )
                        .post(&mut solver);
                        pumpkin_solver::less_than_or_equals(
                            vec![vb.x0.scaled(1), va.x0.scaled(-1), va.w.scaled(-1)],
                            max_d,
                            tag,
                        )
                        .post(&mut solver);
                        pumpkin_solver::less_than_or_equals(
                            vec![va.y0.scaled(1), vb.y0.scaled(-1), vb.h.scaled(-1)],
                            max_d,
                            tag,
                        )
                        .post(&mut solver);
                        pumpkin_solver::less_than_or_equals(
                            vec![vb.y0.scaled(1), va.y0.scaled(-1), va.h.scaled(-1)],
                            max_d,
                            tag,
                        )
                        .post(&mut solver);
                    }
                }
            }
            "aligned" => {
                let comps = str_vec_of(&c["components"]);
                let axis = c.get("axis").and_then(|v| v.as_str()).unwrap_or("x");
                let tol = to_units(f64_of(&c["tolerance_mm"]));
                let use_cx = axis == "x" || axis == "major";
                let refs: Vec<String> = comps.into_iter().filter(|r| vars.contains_key(r)).collect();
                for i in 0..refs.len() {
                    for j in (i + 1)..refs.len() {
                        let vi = vars[&refs[i]];
                        let vj = vars[&refs[j]];
                        let (pi, pj) = if use_cx { (vi.cx, vj.cx) } else { (vi.cy, vj.cy) };
                        pumpkin_solver::less_than_or_equals(vec![pi.scaled(1), pj.scaled(-1)], tol, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![pj.scaled(1), pi.scaled(-1)], tol, tag).post(&mut solver);
                    }
                }
            }
            "anchored" => {
                let comp = str_of(&c["component"]);
                if let Some(v) = vars.get(comp).copied() {
                    if let Some(pos) = c.get("position") {
                        let arr = pos.as_array().expect("position must be an array");
                        let px = to_units(f64_of(&arr[0]));
                        let py = to_units(f64_of(&arr[1]));
                        pumpkin_solver::equals(vec![v.cx.scaled(1)], px, tag).post(&mut solver);
                        pumpkin_solver::equals(vec![v.cy.scaled(1)], py, tag).post(&mut solver);
                    } else if let Some(reg) = c.get("region") {
                        let arr = reg.as_array().expect("region must be an array");
                        let rx0 = to_units(f64_of(&arr[0]));
                        let ry0 = to_units(f64_of(&arr[1]));
                        let rx1 = to_units(f64_of(&arr[2]));
                        let ry1 = to_units(f64_of(&arr[3]));
                        pumpkin_solver::greater_than_or_equals(vec![v.x0.scaled(1)], rx0, tag).post(&mut solver);
                        pumpkin_solver::greater_than_or_equals(vec![v.y0.scaled(1)], ry0, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![v.x0.scaled(1), v.w.scaled(1)], rx1, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![v.y0.scaled(1), v.h.scaled(1)], ry1, tag).post(&mut solver);
                    }
                }
            }
            "enclosing" => {
                let outer = str_of(&c["outer"]);
                let inner = str_vec_of(&c["inner"]);
                let margin_mm = to_units(c.get("margin_mm").and_then(|v| v.as_f64()).unwrap_or(0.0));
                if let Some(zone) = spec.zones.get(outer) {
                    let zx0 = to_units(zone.0);
                    let zy0 = to_units(zone.1);
                    let zx1 = to_units(zone.2);
                    let zy1 = to_units(zone.3);
                    for r in &inner {
                        if let Some(v) = vars.get(r).copied() {
                            pumpkin_solver::greater_than_or_equals(vec![v.x0.scaled(1)], zx0 + margin_mm, tag).post(&mut solver);
                            pumpkin_solver::greater_than_or_equals(vec![v.y0.scaled(1)], zy0 + margin_mm, tag).post(&mut solver);
                            pumpkin_solver::less_than_or_equals(vec![v.x0.scaled(1), v.w.scaled(1)], zx1 - margin_mm, tag).post(&mut solver);
                            pumpkin_solver::less_than_or_equals(vec![v.y0.scaled(1), v.h.scaled(1)], zy1 - margin_mm, tag).post(&mut solver);
                        }
                    }
                }
            }
            "keepout" => {
                let zone_name = str_of(&c["zone_name"]);
                let margin_mm = to_units(c.get("margin_mm").and_then(|v| v.as_f64()).unwrap_or(0.0));
                if let Some(zone) = spec.zones.get(zone_name) {
                    let kx0 = to_units(zone.0) - margin_mm;
                    let ky0 = to_units(zone.1) - margin_mm;
                    let kx1 = to_units(zone.2) + margin_mm;
                    let ky1 = to_units(zone.3) + margin_mm;
                    // Global: applies to every component (harness verifier's
                    // _check_keepout loops over all boxes, not a named list).
                    for r in &comp_refs {
                        let v = vars[r];
                        let l1 = solver.new_literal(); // box entirely left of keepout
                        let l2 = solver.new_literal(); // box entirely right of keepout
                        let l3 = solver.new_literal(); // box entirely below keepout
                        let l4 = solver.new_literal(); // box entirely above keepout
                        pumpkin_solver::less_than_or_equals(vec![v.x0.scaled(1), v.w.scaled(1)], kx0, tag).implied_by(&mut solver, l1);
                        pumpkin_solver::greater_than_or_equals(vec![v.x0.scaled(1)], kx1, tag).implied_by(&mut solver, l2);
                        pumpkin_solver::less_than_or_equals(vec![v.y0.scaled(1), v.h.scaled(1)], ky0, tag).implied_by(&mut solver, l3);
                        pumpkin_solver::greater_than_or_equals(vec![v.y0.scaled(1)], ky1, tag).implied_by(&mut solver, l4);
                        pumpkin_solver::clause(vec![l1, l2, l3, l4], tag).post(&mut solver);
                    }
                }
            }
            "on_side" => {
                let comps = str_vec_of(&c["components"]);
                let side = str_of(&c["side"]);
                let max_d = to_units(f64_of(&c["max_distance_mm"]));
                for r in &comps {
                    if let Some(v) = vars.get(r).copied() {
                        match side {
                            "left" => {
                                pumpkin_solver::less_than_or_equals(vec![v.x0.scaled(1)], max_d, tag).post(&mut solver);
                            }
                            "right" => {
                                pumpkin_solver::greater_than_or_equals(vec![v.x0.scaled(1), v.w.scaled(1)], board_w - max_d, tag)
                                    .post(&mut solver);
                            }
                            "top" => {
                                pumpkin_solver::greater_than_or_equals(vec![v.y0.scaled(1), v.h.scaled(1)], board_h - max_d, tag)
                                    .post(&mut solver);
                            }
                            "bottom" => {
                                pumpkin_solver::less_than_or_equals(vec![v.y0.scaled(1)], max_d, tag).post(&mut solver);
                            }
                            _ => {}
                        }
                    }
                }
            }
            "bounded" => {
                // 2026-08-11 board-sync-and-placement addition: a single
                // one-sided linear bound on one component's own coordinate,
                // `coord OP value_mm`. This is the exact wire-format
                // primitive `isolation_barrier.add_isolation_barrier_to_model`
                // needs and does not otherwise have here: that module (OR-Tools
                // CpModel-coupled, not reusable against this binary directly)
                // encodes the HV/SELV domain-only split as
                // `end <= barrier_lo` / `start >= barrier_hi`, and the
                // per-isolator pad-cluster straddle as
                // `center + fixed_offset_mm <= barrier_lo` /
                // `center + fixed_offset_mm >= barrier_hi` (fixed_offset_mm
                // precomputed in Python from the isolator's real pad geometry
                // and chosen rotation, via that module's own pure helpers --
                // see docs/evidence/2026-08-11-board-sync-and-placement.md).
                // None of "separated"/"adjacent"/"on_side"/"enclosing"/
                // "keepout" express an arbitrary single-component one-sided
                // bound at a caller-supplied constant with no other
                // component or zone involved -- "on_side" is the closest
                // but is fixed to the board's own edge, not an arbitrary
                // interior constant like a barrier corridor position.
                let comp = str_of(&c["component"]);
                let coord = str_of(&c["coord"]);
                let op = str_of(&c["op"]);
                let value = to_units(f64_of(&c["value_mm"]));
                if let Some(v) = vars.get(comp).copied() {
                    let terms = match coord {
                        "x_start" => vec![v.x0.scaled(1)],
                        "x_end" => vec![v.x0.scaled(1), v.w.scaled(1)],
                        "y_start" => vec![v.y0.scaled(1)],
                        "y_end" => vec![v.y0.scaled(1), v.h.scaled(1)],
                        "cx" => vec![v.cx.scaled(1)],
                        "cy" => vec![v.cy.scaled(1)],
                        _ => {
                            eprintln!("pumpkin_engine: unsupported bounded coord {coord:?}, aborting");
                            std::process::exit(2);
                        }
                    };
                    match op {
                        "le" => {
                            pumpkin_solver::less_than_or_equals(terms, value, tag).post(&mut solver);
                        }
                        "ge" => {
                            pumpkin_solver::greater_than_or_equals(terms, value, tag).post(&mut solver);
                        }
                        _ => {
                            eprintln!("pumpkin_engine: unsupported bounded op {op:?}, aborting");
                            std::process::exit(2);
                        }
                    }
                }
            }
            "fixed_rotation" => {
                // 2026-08-11 board-place-and-reroute addition: pin one
                // component's `rot` domain variable to an exact value
                // (0..3, the model's 4 axis-aligned rotations), the Pumpkin
                // analogue of `isolation_barrier.py`'s
                // `model.model_ref.Add(cvars.rot_ref == rot_value)` for the
                // OR-Tools CpModel. Deliberately a separate constraint type
                // from "bounded" rather than a `coord: "rot"` case there:
                // "bounded"'s `value_mm` is always scaled by `to_units`
                // (SCALE units/mm) before use, but a rotation index is a
                // unitless 0..3 selector, not a millimetre quantity -- reusing
                // "bounded" for it would silently scale the value by SCALE
                // and pin to nonsense. `rot` is never scaled (`v.rot.scaled(1)`
                // matches every other unscaled use of `rot` in this file,
                // e.g. the AddElement calls above).
                let comp = str_of(&c["component"]);
                let rot_value = c["rot"].as_i64().expect("fixed_rotation.rot must be an integer") as i32;
                if let Some(v) = vars.get(comp).copied() {
                    pumpkin_solver::equals(vec![v.rot.scaled(1)], rot_value, tag).post(&mut solver);
                }
            }
            "loop_area" => {
                let loop_name = str_of(&c["loop_name"]);
                let max_area_mm2 = f64_of(&c["max_area_mm2"]);
                let max_area_units2 = (max_area_mm2 * SCALE * SCALE).round() as i32;
                if let Some(refs) = spec.loop_components.get(loop_name) {
                    let comp_vars: Vec<CompVars> = refs.iter().filter_map(|r| vars.get(r).copied()).collect();
                    if !comp_vars.is_empty() {
                        let mut right_edges = Vec::new();
                        let mut top_edges = Vec::new();
                        for cv in &comp_vars {
                            let rx = solver.new_bounded_integer(0, board_w);
                            pumpkin_solver::equals(vec![rx.scaled(1), cv.x0.scaled(-1), cv.w.scaled(-1)], 0, tag).post(&mut solver);
                            right_edges.push(rx);
                            let ry = solver.new_bounded_integer(0, board_h);
                            pumpkin_solver::equals(vec![ry.scaled(1), cv.y0.scaled(-1), cv.h.scaled(-1)], 0, tag).post(&mut solver);
                            top_edges.push(ry);
                        }
                        let left_edges: Vec<DomainId> = comp_vars.iter().map(|cv| cv.x0).collect();
                        let bottom_edges: Vec<DomainId> = comp_vars.iter().map(|cv| cv.y0).collect();

                        let min_x = solver.new_bounded_integer(0, board_w);
                        let max_x = solver.new_bounded_integer(0, board_w);
                        let min_y = solver.new_bounded_integer(0, board_h);
                        let max_y = solver.new_bounded_integer(0, board_h);
                        pumpkin_solver::minimum(left_edges, min_x, tag).post(&mut solver);
                        pumpkin_solver::maximum(right_edges, max_x, tag).post(&mut solver);
                        pumpkin_solver::minimum(bottom_edges, min_y, tag).post(&mut solver);
                        pumpkin_solver::maximum(top_edges, max_y, tag).post(&mut solver);

                        let width = solver.new_bounded_integer(0, board_w);
                        let height = solver.new_bounded_integer(0, board_h);
                        // width = max_x - min_x  =>  width - max_x + min_x = 0
                        pumpkin_solver::equals(vec![width.scaled(1), max_x.scaled(-1), min_x.scaled(1)], 0, tag).post(&mut solver);
                        pumpkin_solver::equals(vec![height.scaled(1), max_y.scaled(-1), min_y.scaled(1)], 0, tag).post(&mut solver);

                        let area_ub = (board_w as i64).saturating_mul(board_h as i64).min(i32::MAX as i64) as i32;
                        let area = solver.new_bounded_integer(0, area_ub.max(1));
                        pumpkin_solver::times(width, height, area, tag).post(&mut solver);
                        pumpkin_solver::less_than_or_equals(vec![area.scaled(1)], max_area_units2, tag).post(&mut solver);
                    }
                }
            }
            _ => {
                // Unknown/unsupported constraint type: fail loudly rather
                // than silently under-constraining the model, matching the
                // repo's own fail-closed discipline (AGENTS.md).
                eprintln!("pumpkin_engine: unsupported constraint type {ctype:?}, aborting");
                std::process::exit(2);
            }
        }
    }

    // Minimum-displacement repair objective (C11), mirrors
    // model.py::add_displacement_objective: weight=1, Manhattan (L1) sum of
    // per-axis |actual - target|, Minimize.
    let mut obj_terms: Vec<DomainId> = Vec::new();
    if let Some(refmap) = &spec.minimize_displacement_to {
        let big = board_w.max(board_h) + 1;
        for (r, (tx, ty)) in refmap {
            if let Some(v) = vars.get(r).copied() {
                let txu = to_units(*tx);
                let tyu = to_units(*ty);
                let dx = solver.new_bounded_integer(0, big);
                let dy = solver.new_bounded_integer(0, big);
                pumpkin_solver::absolute(v.cx.offset(-txu), dx, tag).post(&mut solver);
                pumpkin_solver::absolute(v.cy.offset(-tyu), dy, tag).post(&mut solver);
                obj_terms.push(dx);
                obj_terms.push(dy);
            }
        }
    }

    // HPWL objective: for each net, span_x = max(cx) - min(cx) over members,
    // span_y likewise, both added to obj_terms (weight 1, matches D1's
    // un-weighted first-landing default in the wirelength plan). Nets with
    // fewer than 2 members present in this model contribute nothing (a
    // single-pin net's span is definitionally 0).
    if let Some(nets) = &spec.hpwl_nets {
        let mut net_names: Vec<&String> = nets.keys().collect();
        net_names.sort(); // deterministic variable-creation order across runs
        for name in net_names {
            let member_refs = &nets[name];
            let member_vars: Vec<CompVars> =
                member_refs.iter().filter_map(|r| vars.get(r).copied()).collect();
            if member_vars.len() < 2 {
                continue;
            }
            let cxs: Vec<DomainId> = member_vars.iter().map(|v| v.cx).collect();
            let cys: Vec<DomainId> = member_vars.iter().map(|v| v.cy).collect();

            let min_cx = solver.new_bounded_integer(0, board_w);
            let max_cx = solver.new_bounded_integer(0, board_w);
            let min_cy = solver.new_bounded_integer(0, board_h);
            let max_cy = solver.new_bounded_integer(0, board_h);
            pumpkin_solver::minimum(cxs.clone(), min_cx, tag).post(&mut solver);
            pumpkin_solver::maximum(cxs, max_cx, tag).post(&mut solver);
            pumpkin_solver::minimum(cys.clone(), min_cy, tag).post(&mut solver);
            pumpkin_solver::maximum(cys, max_cy, tag).post(&mut solver);

            let span_x = solver.new_bounded_integer(0, board_w);
            let span_y = solver.new_bounded_integer(0, board_h);
            // span_x - max_cx + min_cx = 0  =>  span_x = max_cx - min_cx
            pumpkin_solver::equals(vec![span_x.scaled(1), max_cx.scaled(-1), min_cx.scaled(1)], 0, tag)
                .post(&mut solver);
            pumpkin_solver::equals(vec![span_y.scaled(1), max_cy.scaled(-1), min_cy.scaled(1)], 0, tag)
                .post(&mut solver);

            obj_terms.push(span_x);
            obj_terms.push(span_y);
        }
    }

    let objective: Option<DomainId> = if obj_terms.is_empty() {
        None
    } else {
        let ub = (board_w as i64 + board_h as i64) as i32 * obj_terms.len() as i32 + 1000;
        let ov = solver.new_bounded_integer(0, ub.max(1));
        let mut terms: Vec<_> = obj_terms.iter().map(|d| d.scaled(1)).collect();
        terms.push(ov.scaled(-1));
        pumpkin_solver::equals(terms, 0, tag).post(&mut solver);
        Some(ov)
    };

    let mut brancher = solver.default_brancher();
    let mut resolver = ResolutionResolver::default();
    let mut termination = TimeBudget::starting_now(Duration::from_millis(spec.timeout_ms));

    #[allow(unused_assignments)]
    let mut status = "unknown";
    let mut positions: HashMap<String, (f64, f64)> = HashMap::new();
    let mut rotations: HashMap<String, i32> = HashMap::new();
    let mut objective_value: f64 = 0.0;

    if let Some(obj) = objective {
        let callback = |_solver: &Solver,
                         _sol: pumpkin_solver::core::results::SolutionReference,
                         _b: &pumpkin_solver::core::DefaultBrancher,
                         _r: &ResolutionResolver|
         -> ControlFlow<()> { ControlFlow::Continue(()) };
        let result = solver.optimise(
            &mut brancher,
            &mut termination,
            &mut resolver,
            LinearSatUnsat::new(OptimisationDirection::Minimise, obj, callback),
        );
        match result {
            OptimisationResult::Optimal(sol) => {
                status = "optimal";
                objective_value = sol.get_integer_value(obj) as f64;
                for r in &comp_refs {
                    let v = vars[r];
                    positions.insert(r.clone(), (to_mm(sol.get_integer_value(v.cx)), to_mm(sol.get_integer_value(v.cy))));
                    rotations.insert(r.clone(), sol.get_integer_value(v.rot));
                }
            }
            OptimisationResult::Satisfiable(sol) => {
                status = "feasible";
                objective_value = sol.get_integer_value(obj) as f64;
                for r in &comp_refs {
                    let v = vars[r];
                    positions.insert(r.clone(), (to_mm(sol.get_integer_value(v.cx)), to_mm(sol.get_integer_value(v.cy))));
                    rotations.insert(r.clone(), sol.get_integer_value(v.rot));
                }
            }
            OptimisationResult::Stopped(sol, _) => {
                status = "feasible";
                objective_value = sol.get_integer_value(obj) as f64;
                for r in &comp_refs {
                    let v = vars[r];
                    positions.insert(r.clone(), (to_mm(sol.get_integer_value(v.cx)), to_mm(sol.get_integer_value(v.cy))));
                    rotations.insert(r.clone(), sol.get_integer_value(v.rot));
                }
            }
            OptimisationResult::Unsatisfiable => {
                status = "infeasible";
            }
            OptimisationResult::Unknown => {
                status = "unknown";
            }
        }
    } else {
        match solver.satisfy(&mut brancher, &mut termination, &mut resolver) {
            SatisfactionResult::Satisfiable(sat) => {
                // No objective was posted: matches OR-Tools' own convention
                // of returning OPTIMAL (not FEASIBLE) for an objective-free
                // model once any solution is found (harness doc Sec 4.3:
                // status_set={"optimal"} even for the objective-free `small`
                // corpus).
                status = "optimal";
                let sol = sat.solution();
                for r in &comp_refs {
                    let v = vars[r];
                    positions.insert(r.clone(), (to_mm(sol.get_integer_value(v.cx)), to_mm(sol.get_integer_value(v.cy))));
                    rotations.insert(r.clone(), sol.get_integer_value(v.rot));
                }
            }
            SatisfactionResult::Unsatisfiable(_, _, _) => {
                status = "infeasible";
            }
            SatisfactionResult::Unknown(_, _, _) => {
                status = "unknown";
            }
        }
    }

    let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;

    let mut positions_json = serde_json::Map::new();
    for (k, (x, y)) in &positions {
        positions_json.insert(k.clone(), json!([x, y]));
    }

    let out = json!({
        "status": status,
        "positions": Value::Object(positions_json),
        "rotations": rotations,
        "objective_value": objective_value,
        "solve_time_ms": elapsed_ms,
    });
    println!("{out}");
}
