use std::fs;
use std::path::{Path, PathBuf};
const CASES: [(&str, f64, f64); 2] = [("vm438_v035", -0.438, 0.350), ("vm5_v035", -5.0, 0.350)];
const VARS: [(&str, &str, &str); 5] = [
    ("trap_1n_orig", "method=trap reltol=1e-6 abstol=1e-12 vntol=1e-9", "1n"),
    ("trap_1n_tight", "method=trap reltol=1e-9 abstol=1e-15 vntol=1e-12", "1n"),
    ("trap_100p_tight", "method=trap reltol=1e-9 abstol=1e-15 vntol=1e-12", "100p"),
    ("gear2_1n_tight", "method=gear maxord=2 reltol=1e-9 abstol=1e-15 vntol=1e-12", "1n"),
    ("gear2_100p_tight", "method=gear maxord=2 reltol=1e-9 abstol=1e-15 vntol=1e-12", "100p"),
];
fn deck(path: &Path, case: &str, vsh: f64, vf: f64, variant: &str, options: &str, step: &str) {
    let text = format!(
"* limiting-envelope-13 peak diagnostic: {case}/{variant}\n* Same finite pulse and piecewise clamp as the parent fixture.\n.param VAMP={vsh:.3} VF={vf:.3} RSH=220 RCL=1m\nVSHUNT shunt 0 PULSE(0 {{VAMP}} 1u 10n 10n 4u 8u)\nVMEAS shunt shunt_m 0\nR_ISENSE shunt_m isense {{RSH}}\nCISENSE isense 0 1n\nBCLAMP 0 clamp_m I={{((-V(isense)>VF) ? ((-V(isense)-VF)/RCL) : 0)}}\nVCLAMP clamp_m isense 0\n.options {options}\n.save time v(shunt) v(shunt_m) v(isense) i(VMEAS) i(VCLAMP)\n.tran {step} 8u 0 {step}\n.control\nrun\nlet resistor_power=(v(shunt_m)-v(isense))*i(VMEAS)\nlet clamp_power=-v(isense)*i(VCLAMP)\nmeas tran isense_flat AVG v(isense) FROM=4u TO=4.8u\nmeas tran resistor_i_flat AVG i(VMEAS) FROM=4u TO=4.8u\nmeas tran clamp_i_flat AVG i(VCLAMP) FROM=4u TO=4.8u\nmeas tran resistor_i_max MAX i(VMEAS) FROM=0 TO=8u\nmeas tran clamp_i_max MAX i(VCLAMP) FROM=0 TO=8u\nmeas tran resistor_energy_total INTEG resistor_power FROM=0 TO=8u\nmeas tran clamp_energy_total INTEG clamp_power FROM=0 TO=8u\nwrite {case}_{variant}.raw time v(shunt) v(isense) i(VMEAS) i(VCLAMP)\nquit\n.endc\n.end\n"
    );
    fs::write(path, text).unwrap();
}
fn main() {
    let root = PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| ".".into()));
    let gen = root.join("generated"); fs::create_dir_all(&gen).unwrap();
    let mut csv = String::from("case,variant,vsh_v,vf_v,analytic_flat_current_a,analytic_peak_bound_a\n");
    for (case,vsh,vf) in CASES { for (variant,options,step) in VARS {
        deck(&gen.join(format!("{case}_{variant}.cir")), case, vsh, vf, variant, options, step);
        let bound = ((-vsh)-vf).max(0.0)/(220.001);
        csv.push_str(&format!("{case},{variant},{vsh:.6},{vf:.6},{bound:.12e},{bound:.12e}\n"));
    }}
    fs::write(root.join("analytic.csv"), csv).unwrap();
}
