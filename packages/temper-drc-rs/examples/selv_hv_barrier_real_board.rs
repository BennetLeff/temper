//! Run `routing::IsolationBarrierCheck` against the real
//! `pcb/temper.kicad_pcb` board with an explicit, documented isolation
//! barrier — since nothing in this project's committed config
//! (`temper_constraints.yaml`) defines one (see
//! `constraints::IsolationBarrier`'s doc comment).
//!
//! This does NOT modify `pcb/temper.kicad_pcb` or any committed file: the
//! board is read once via the existing production bridge
//! (`tools/wasm/r2_serialize_board.py`, already used for the R2 cost-model
//! benchmark) into a throwaway JSON snapshot, and the barrier is supplied
//! purely as a constraints-JSON input to this binary.
//!
//! Usage:
//!   uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json
//!   # then write a constraints JSON with an `isolation_barriers` entry
//!   # (see this file's own doc comment for the shape), and:
//!   cargo run --example selv_hv_barrier_real_board -- /tmp/board.json /tmp/board.constraints.json
#![allow(clippy::unwrap_used, clippy::expect_used)] // standalone demonstration example: a panic IS the failure mode

use std::collections::HashMap;

use temper_drc_rs::board::BoardState;
use temper_drc_rs::constraints::ConstraintSet;
use temper_drc_rs::rules::routing::IsolationBarrierCheck;
use temper_drc_rs::rules::DrcRule;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "usage: selv_hv_barrier_real_board <board.json> <constraints.json>"
        );
        std::process::exit(1);
    }
    let board_json = std::fs::read_to_string(&args[1])
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", args[1]));
    let constraints_json = std::fs::read_to_string(&args[2])
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", args[2]));

    let board: BoardState =
        serde_json::from_str(&board_json).expect("failed to deserialize BoardState");
    let constraints: ConstraintSet =
        serde_json::from_str(&constraints_json).expect("failed to deserialize ConstraintSet");

    println!(
        "Board: {:.1}mm x {:.1}mm, {} zones, {} traces",
        board.width_mm,
        board.height_mm,
        board.zones.len(),
        board.traces.len()
    );
    println!("Barriers supplied: {}", constraints.isolation_barriers.len());
    for b in &constraints.isolation_barriers {
        println!(
            "  '{}' x={:.3}mm y_span=[{:.1},{:.1}] layers={} clearance_mm={:.2}",
            b.name, b.x_mm, b.y_span[0], b.y_span[1], b.layers, b.clearance_mm
        );
    }

    // Layer/net census of what's actually being checked, so a "0
    // violations" result is auditable rather than trust-me.
    let mut zones_by_layer: HashMap<&str, usize> = HashMap::new();
    let mut nets: std::collections::BTreeSet<&str> = std::collections::BTreeSet::new();
    for z in &board.zones {
        *zones_by_layer.entry(z.layer.as_str()).or_insert(0) += 1;
        nets.insert(z.net.0.as_str());
    }
    println!("Zones by layer: {:?}", zones_by_layer);
    println!("Distinct zone nets ({}): {:?}", nets.len(), nets);

    let check = IsolationBarrierCheck::new();
    let violations = check.check(&board, &constraints);

    println!("\n=== IsolationBarrierCheck result: {} violation(s) ===", violations.len());
    for v in &violations {
        println!(
            "  [{}] {} — {}",
            v.code,
            v.severity,
            v.message
        );
    }
    if violations.is_empty() {
        println!(
            "Clean. NOTE: the real board's In1.Cu/In2.Cu are currently empty \
             (no power-plane pours generated yet), so a clean inner-layer \
             result here is expected and is not, by itself, evidence the \
             detector works — see the synthetic pass/fail fixtures in \
             src/rules/routing/isolation_barrier.rs's test module for that. \
             This run's non-trivial evidence is the {} real F.Cu/B.Cu zones \
             and {} real traces genuinely checked against the barrier \
             without error.",
            board.zones.len(),
            board.traces.len()
        );
    }
}
