// Counterfactual memory prototype for the router SAT model at production scale.
// Mirrors temper-rust-router-core::types::InternalVariable and an interned
// index-based alternative. Measures real RSS, not estimates.
use std::fmt::Write as _;

const NETS: usize = 110;
const EDGES: usize = 204_490;
const N: usize = NETS * EDGES; // 22,493,900

fn rss_kb() -> usize {
    let s = std::fs::read_to_string("/proc/self/status").unwrap();
    for l in s.lines() {
        if let Some(r) = l.strip_prefix("VmRSS:") {
            return r.trim().trim_end_matches(" kB").trim().parse().unwrap();
        }
    }
    0
}

fn edge_id(layer: &str, i: usize, buf: &mut String) {
    buf.clear();
    let x = 123.456789f64 + (i % 1000) as f64 * 0.001;
    let y = 98.765432f64 + (i % 997) as f64 * 0.001;
    write!(buf, "{layer}_E{i}_({:.6}, {:.6})_({:.6}, {:.6})", x, y, x + 1.1, y + 1.1).unwrap();
}

// (B) current Rust internal representation
#[derive(Clone)]
#[allow(dead_code)]
enum InternalVariable {
    NetChannel { name: String, net_idx: usize, channel_id: String },
    Ordering { name: String, net1_idx: usize, net2_idx: usize, channel_id: String },
}

// (C) interned, index-based: names are a pure function of (net_idx, edge_idx)
#[derive(Clone, Copy)]
#[allow(dead_code)]
struct PackedNetChannelVar { net_idx: u32, edge_idx: u32 }

fn main() {
    let which = std::env::args().nth(1).unwrap_or_else(|| "C".into());
    let base = rss_kb();
    let mut buf = String::new();

    match which.as_str() {
        "B" => {
            let mut v: Vec<InternalVariable> = Vec::with_capacity(N);
            for i in 0..N {
                edge_id("F.Cu", i % EDGES, &mut buf);
                v.push(InternalVariable::NetChannel {
                    name: format!("uses_N{}_{}", i % NETS, buf),
                    net_idx: i % NETS,
                    channel_id: buf.clone(),
                });
            }
            let d = rss_kb() - base;
            println!("(B) InternalVariable enum  N={N}  RSS={:.2} GB  bytes/var={:.1}  size_of={}",
                d as f64 / 1048576.0, d as f64 * 1024.0 / N as f64, std::mem::size_of::<InternalVariable>());
            std::hint::black_box(&v);
        }
        "C" => {
            let mut v: Vec<PackedNetChannelVar> = Vec::with_capacity(N);
            for i in 0..N {
                v.push(PackedNetChannelVar { net_idx: (i % NETS) as u32, edge_idx: (i % EDGES) as u32 });
            }
            // The edge-id strings are interned ONCE (204,490 of them), not per-variable.
            let mut interned: Vec<String> = Vec::with_capacity(EDGES);
            for i in 0..EDGES { edge_id("F.Cu", i, &mut buf); interned.push(buf.clone()); }
            let d = rss_kb() - base;
            println!("(C) packed idx + interned edge ids  N={N}  RSS={:.2} GB  bytes/var={:.1}  size_of={}",
                d as f64 / 1048576.0, d as f64 * 1024.0 / N as f64, std::mem::size_of::<PackedNetChannelVar>());
            std::hint::black_box((&v, &interned));
        }
        _ => {}
    }
}
