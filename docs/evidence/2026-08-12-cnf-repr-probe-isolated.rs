// Clean, cold-start, single-arm-per-process clause-representation probe.
// Mirrors docs/evidence/2026-08-12-router-model-memory-counterfactual.rs's
// methodology exactly (one process per arm, argv-selected, real
// /proc/self/status VmRSS, no shared-process allocator-slack confound).
//
// The per-constraint clause-length histogram (16 length-1, 2038 length-2,
// 1728 length-3 clauses per Sinz sequential-counter AtMostK(n=110,k=17)
// constraint) was independently VERIFIED against the real
// temper_rust_router_core::encoding::encode_to_cnf output at num_channels=
// 2000 and 6000 (see cnf_repr_probe.rs / repr_probe run log): predicted
// 7,564,000 / 22,692,000 total clauses and 18,552,000 / 55,656,000 total
// literals matched the real encoder's output EXACTLY at both scales. This
// probe reuses that verified histogram to build ONLY the clause structure
// (arm A or arm C) from a cold process, avoiding the confound of cloning
// on top of an already-fragmented heap.
//
// Usage: clause_repr_probe <A|C> <num_channels>
fn rss_kb() -> usize {
    let s = std::fs::read_to_string("/proc/self/status").unwrap();
    for l in s.lines() {
        if let Some(r) = l.strip_prefix("VmRSS:") {
            return r.trim().trim_end_matches(" kB").trim().parse().unwrap();
        }
    }
    0
}

// Verified-real per-constraint histogram (n=110 nets, Sinz k=17).
const LEN1_PER_CONSTRAINT: usize = 16;
const LEN2_PER_CONSTRAINT: usize = 2038;
const LEN3_PER_CONSTRAINT: usize = 1728;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let which = args.get(1).cloned().unwrap_or_else(|| "A".into());
    let num_channels: usize = args.get(2).map(|s| s.parse().unwrap()).unwrap_or(2000);

    let n1 = LEN1_PER_CONSTRAINT * num_channels;
    let n2 = LEN2_PER_CONSTRAINT * num_channels;
    let n3 = LEN3_PER_CONSTRAINT * num_channels;
    let num_clauses = n1 + n2 + n3;
    let literal_count = n1 * 1 + n2 * 2 + n3 * 3;

    let base = rss_kb();

    match which.as_str() {
        "A" => {
            // Today: CnfFormula.clauses: Vec<Vec<i32>> (encoding.rs:13).
            let mut clauses: Vec<Vec<i32>> = Vec::with_capacity(num_clauses);
            let mut lit: i32 = 1;
            for _ in 0..n1 {
                clauses.push(vec![lit]);
                lit = lit.wrapping_add(1);
            }
            for _ in 0..n2 {
                clauses.push(vec![lit, -lit]);
                lit = lit.wrapping_add(1);
            }
            for _ in 0..n3 {
                clauses.push(vec![lit, -lit, lit + 1]);
                lit = lit.wrapping_add(1);
            }
            let after = rss_kb();
            let d = (after as i64 - base as i64) as f64;
            println!(
                "ARM A  Vec<Vec<i32>>  num_channels={num_channels}  num_clauses={num_clauses}  literal_count={literal_count}"
            );
            println!(
                "ARM A  cold-start RSS delta = {:.3} GB  bytes/clause = {:.2}",
                d / 1_048_576.0,
                d * 1024.0 / num_clauses as f64
            );
            std::hint::black_box(&clauses);
        }
        "C" => {
            // Packed alternative: flat Vec<i32> literal pool + Vec<u32> clause offsets.
            let mut literals: Vec<i32> = Vec::with_capacity(literal_count);
            let mut offsets: Vec<u32> = Vec::with_capacity(num_clauses + 1);
            offsets.push(0);
            let mut lit: i32 = 1;
            for _ in 0..n1 {
                literals.push(lit);
                offsets.push(literals.len() as u32);
                lit = lit.wrapping_add(1);
            }
            for _ in 0..n2 {
                literals.push(lit);
                literals.push(-lit);
                offsets.push(literals.len() as u32);
                lit = lit.wrapping_add(1);
            }
            for _ in 0..n3 {
                literals.push(lit);
                literals.push(-lit);
                literals.push(lit + 1);
                offsets.push(literals.len() as u32);
                lit = lit.wrapping_add(1);
            }
            let after = rss_kb();
            let d = (after as i64 - base as i64) as f64;
            println!(
                "ARM C  flat Vec<i32> + Vec<u32> offsets  num_channels={num_channels}  num_clauses={num_clauses}  literal_count={literal_count}"
            );
            println!(
                "ARM C  cold-start RSS delta = {:.3} GB  bytes/clause = {:.2}",
                d / 1_048_576.0,
                d * 1024.0 / num_clauses as f64
            );
            std::hint::black_box((&literals, &offsets));
        }
        _ => panic!("unknown arm"),
    }
}
