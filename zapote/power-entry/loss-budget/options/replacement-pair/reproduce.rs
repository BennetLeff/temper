//! Standalone arithmetic reproduction for the replacement-pair loss screen.
//!
//! This intentionally does not reimplement the PFC solver.  The switch-RMS
//! moments below are copied from the retained corrected Rust report (the
//! source hash is recorded in REPORT.md/candidates.json), then only the
//! disjoint terms reported in this option screen are calculated:
//! conduction `I_rms^2 * Rds(on)` and gate-network charge `Qg * Vdrive * fsw`.
//! Compile/run with `rustc reproduce.rs -o /tmp/replacement-pair-reproduce`
//! if a local numeric check is desired; no Cargo target is needed.

#[derive(Clone, Copy)]
struct LineCase {
    line_v: f64,
    switch_rms_a: f64,
}

const CASES: [LineCase; 3] = [
    LineCase {
        line_v: 108.0,
        switch_rms_a: 12.25325949559574,
    },
    LineCase {
        line_v: 120.0,
        switch_rms_a: 11.9091944502362,
    },
    LineCase {
        line_v: 132.0,
        switch_rms_a: 11.554950420013618,
    },
];

const FSW_HZ: f64 = 129_107.39198577;
const SOURCE_REPORT_SHA256: &str =
    "1c2f556023b8533c2d6b0c8455a19a7d082d923930686c24f067e856dfbd371f";

fn conduction(case_: LineCase, rds_ohm: f64) -> f64 {
    case_.switch_rms_a * case_.switch_rms_a * rds_ohm
}

fn gate_network(qg_nc: f64, vdrive: f64) -> f64 {
    qg_nc * 1e-9 * vdrive * FSW_HZ
}

fn main() {
    println!("source=loss-report.json sha256={SOURCE_REPORT_SHA256}");
    println!("fsw_hz={FSW_HZ:.11}");
    println!("line_v,switch_rms_a,A_48mohm_w,A_64mohm_w,A_67mohm_w,B_60mohm_w,B_44mohm_w,B_70mohm_w,B_50mohm_w");
    for case_ in CASES {
        println!(
            "{:.0},{:.15},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6}",
            case_.line_v,
            case_.switch_rms_a,
            conduction(case_, 0.048),
            conduction(case_, 0.064),
            conduction(case_, 0.067),
            conduction(case_, 0.060),
            conduction(case_, 0.044),
            conduction(case_, 0.070),
            conduction(case_, 0.050),
        );
    }
    println!("A_gate_qg33nC_at18V_w={:.6}", gate_network(33.0, 18.0));
    println!("B_gate_qg74nC_at15V_w={:.6}", gate_network(74.0, 15.0));
    println!("B_gate_qg74nC_at18V_reference_only_w={:.6}", gate_network(74.0, 18.0));
    println!("B_source_point_63uJ_at_fsw_w={:.6}", 63e-6 * FSW_HZ);
}
