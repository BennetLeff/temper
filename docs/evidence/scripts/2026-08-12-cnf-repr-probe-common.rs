use temper_rust_router_core::types::{InternalConstraint, InternalConstraintModel, InternalVariable};

pub const NETS: usize = 110;

pub fn rss_kb() -> usize {
    let s = std::fs::read_to_string("/proc/self/status").unwrap();
    for l in s.lines() {
        if let Some(r) = l.strip_prefix("VmRSS:") {
            return r.trim().trim_end_matches(" kB").trim().parse().unwrap();
        }
    }
    0
}

fn edge_id(i: usize) -> String {
    let x = 123.456789f64 + (i % 1000) as f64 * 0.001;
    let y = 98.765432f64 + (i % 997) as f64 * 0.001;
    format!("F.Cu_E{i}_({:.6}, {:.6})_({:.6}, {:.6})", x, y, x + 1.1, y + 1.1)
}

/// Build a real InternalConstraintModel with `num_channels` capacity-bound
/// channels, each with NETS=110 competing nets and a capacity chosen so
/// max_nets floors to K=17 -- matching the K ~= 17-17.5 DERIVED in
/// docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md
/// "The capacity finding" (two independent equations from the 2026-07-27
/// 42,145,777-var/78,107,180-clause measurement). This is the monolithic
/// (unbatched) shape: capacity terms carry all NETS nets per channel, so
/// AtMostK's `k >= n` early-return at encoding.rs:28-30 does NOT fire, and
/// encoding.rs:148's guard (`max_nets < var_indices.len()`) DOES encode --
/// exactly the "batched vs monolithic" distinction the concurrent capacity
/// plan (2026-08-12-003) is about.
pub fn build_model(num_channels: usize) -> InternalConstraintModel {
    let mut variables = Vec::with_capacity(num_channels * NETS);
    let mut constraints = Vec::with_capacity(num_channels);

    // capacity / slack chosen so floor(capacity*slack/width) == 17, matching
    // the DERIVED K in plan 2026-08-12-002.
    let capacity = 100.0_f64;
    let slack = 1.0_f64;
    let width = 100.0_f64 / 17.5_f64; // floor(100/5.714286) == 17

    for c in 0..num_channels {
        let ch = edge_id(c);
        let mut terms = Vec::with_capacity(NETS);
        for n in 0..NETS {
            let name = format!("uses_N{n}_{ch}");
            variables.push(InternalVariable::NetChannel {
                name: name.clone(),
                net_idx: n,
                channel_id: ch.clone(),
            });
            terms.push((name, width));
        }
        constraints.push(InternalConstraint::Capacity {
            channel_id: ch,
            capacity,
            slack_factor: slack,
            terms,
        });
    }

    InternalConstraintModel { variables, constraints }
}
