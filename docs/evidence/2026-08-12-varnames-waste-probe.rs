// Probe for a SEPARATE finding surfaced while measuring the clause layer:
// encode_to_cnf's second return value, `var_names: Vec<String>`
// (encoding.rs:217, `var_map.iter().map(|v| v.name.clone())`), materializes
// one heap String per SAT variable -- including every Sinz sequential-
// counter auxiliary variable ("sc_r{i}_{j}", encoding.rs:44-46), which
// solve_with_cadical never reads (its `var_names` parameter is
// `_var_names: &[String]`, solver.rs:60 -- underscore-prefixed, unused) and
// which extract_topology only ever matches against a "uses_" prefix
// (extraction.rs:44) that no aux name has. This probe measures, cold-start,
// what that Vec<String> of aux-only placeholder names costs vs. carrying no
// name at all for aux variables (an index-only / Option<String> tag).
//
// Usage: varnames_probe <A|B> <num_channels>
// A = Vec<String>, one "sc_r{i}_{j}" String per aux var (today, effectively)
// B = no per-aux-var name storage at all (baseline for "what if we didn't")
fn rss_kb() -> usize {
    let s = std::fs::read_to_string("/proc/self/status").unwrap();
    for l in s.lines() {
        if let Some(r) = l.strip_prefix("VmRSS:") {
            return r.trim().trim_end_matches(" kB").trim().parse().unwrap();
        }
    }
    0
}

// Verified: aux vars per AtMostK(n=110, k=17) constraint = (n-1)*k = 1853.
const AUX_PER_CONSTRAINT: usize = 1853;
const N_MINUS_1: usize = 109;
const K: usize = 17;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let which = args.get(1).cloned().unwrap_or_else(|| "A".into());
    let num_channels: usize = args.get(2).map(|s| s.parse().unwrap()).unwrap_or(2000);
    let num_aux = AUX_PER_CONSTRAINT * num_channels;

    let base = rss_kb();
    match which.as_str() {
        "A" => {
            let mut names: Vec<String> = Vec::with_capacity(num_aux);
            for _ in 0..num_channels {
                for i in 0..N_MINUS_1 {
                    for j in 0..K {
                        names.push(format!("sc_r{i}_{j}"));
                    }
                }
            }
            let after = rss_kb();
            let d = (after as i64 - base as i64) as f64;
            println!("ARM A  Vec<String> aux names  num_aux={num_aux}");
            println!(
                "ARM A  cold-start RSS delta = {:.3} GB  bytes/aux-var = {:.2}",
                d / 1_048_576.0,
                d * 1024.0 / num_aux as f64
            );
            std::hint::black_box(&names);
        }
        "B" => {
            // No name at all: aux vars carried as a plain count (they don't
            // need identity beyond their index -- Sinz vars are addressed
            // purely by (constraint_idx, i, j) arithmetic, never by name
            // lookup). Represent as nothing (zero-sized) to show the floor.
            let mut aux_count: u64 = 0;
            for _ in 0..num_aux {
                aux_count += 1;
            }
            let after = rss_kb();
            let d = (after as i64 - base as i64) as f64;
            println!("ARM B  no per-aux name storage  num_aux={num_aux}  (sanity counter={aux_count})");
            println!(
                "ARM B  cold-start RSS delta = {:.3} GB  bytes/aux-var = {:.2}",
                d / 1_048_576.0,
                d * 1024.0 / num_aux as f64
            );
        }
        _ => panic!("unknown arm"),
    }
}
