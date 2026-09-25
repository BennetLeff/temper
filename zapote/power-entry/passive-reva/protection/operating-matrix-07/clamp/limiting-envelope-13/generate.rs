use std::fs;
use std::path::{Path, PathBuf};

const AMPS: [f64; 3] = [-0.438, -1.1, -5.0];
const VFS: [f64; 6] = [0.350, 0.438, 0.550, 0.700, 0.900, 1.100];
const R: f64 = 220.0;
const RCL: f64 = 1.0e-3;

fn ng(v: f64) -> String { format!("{v:.3}") }
fn stem(v: f64) -> String { format!("v{}", ng(v).replace('-', "m").replace('.', "p")) }

fn deck(path: &Path, name: &str, vsh: f64, clamp: Option<f64>) {
    let clamp_lines = match clamp {
        None => String::from("* OPEN CLAMP: no current path is connected.\n"),
        Some(vf) => format!(
            "* PIECEWISE HARD CLAMP: I=0 for -V(isense)<=VF; I=(-V(isense)-VF)/RCL otherwise.\n.param VF={vf:.3} RCL={RCL:.9}\nBCLAMP 0 clamp_m I={{((-V(isense)>VF) ? ((-V(isense)-VF)/RCL) : 0)}}\nVCLAMP clamp_m isense 0\n"
        ),
    };
    let bmeas = if clamp.is_some() {
        "meas tran clamp_i_max MAX i(VCLAMP) FROM=0 TO=8u\nmeas tran clamp_i_min MIN i(VCLAMP) FROM=0 TO=8u\nmeas tran clamp_i_flat AVG i(VCLAMP) FROM=4u TO=4.8u\nmeas tran clamp_energy INTEG clamp_power FROM=1u TO=5.02u\nmeas tran clamp_energy_total INTEG clamp_power FROM=0 TO=8u\n"
    } else { "" };
    let bvars = if clamp.is_some() {
        "let clamp_power=-v(isense)*i(VCLAMP)\n"
    } else { "" };
    let clamp_save = if clamp.is_some() { " i(VCLAMP)" } else { "" };
    let clamp_write = if clamp.is_some() { " i(VCLAMP)" } else { "" };
    let text = format!(
        "* limiting-envelope-13 {name}\n* Finite shunt pulse: 1 us delay, 10 ns edges, 4 us flat width.\n.param VAMP={vsh:.3} RSH={R:.1}\nVSHUNT shunt 0 PULSE(0 {{VAMP}} 1u 10n 10n 4u 8u)\nVMEAS shunt shunt_m 0\nR_ISENSE shunt_m isense {{RSH}}\nCISENSE isense 0 1n\n{clamp_lines}.options method=trap reltol=1e-6 abstol=1e-12 vntol=1e-9\n.save time v(shunt) v(shunt_m) v(isense) i(VMEAS){clamp_save}\n.tran 1n 8u 0 1n\n.control\nrun\nlet resistor_power=(v(shunt_m)-v(isense))*i(VMEAS)\n{bvars}meas tran isense_max MAX v(isense) FROM=0 TO=8u\nmeas tran isense_min MIN v(isense) FROM=0 TO=8u\nmeas tran isense_flat AVG v(isense) FROM=4u TO=4.8u\nmeas tran resistor_i_max MAX i(VMEAS) FROM=0 TO=8u\nmeas tran resistor_i_min MIN i(VMEAS) FROM=0 TO=8u\nmeas tran resistor_i_flat AVG i(VMEAS) FROM=4u TO=4.8u\nmeas tran resistor_energy INTEG resistor_power FROM=1u TO=5.02u\nmeas tran resistor_energy_total INTEG resistor_power FROM=0 TO=8u\n{bmeas}write {name}.raw time v(shunt) v(shunt_m) v(isense) i(VMEAS){clamp_write}\nquit\n.endc\n.end\n"
    );
    fs::write(path, text).expect("write netlist");
}

fn analytic(vsh: f64, vf: Option<f64>) -> (f64, f64, f64) {
    let (vis, im) = match vf {
        None => (vsh, 0.0),
        Some(v) if -vsh <= v => (vsh, 0.0),
        Some(v) => {
            let i = (-vsh - v) / (R + RCL);
            (-v - i * RCL, i)
        },
    };
    let p = im * im * R;
    (vis, im, p)
}

fn main() {
    let out = PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| ".".into()));
    let gen = out.join("generated");
    fs::create_dir_all(&gen).unwrap();
    let mut csv = String::from("fixture,vsh_v,vf_v,analytic_isense_v,analytic_current_a,analytic_resistor_power_w,pulse_flat_s\n");
    for vsh in AMPS {
        let open_name = format!("open_{}", stem(vsh));
        deck(&gen.join(format!("{open_name}.cir")), &open_name, vsh, None);
        let (vis, i, p) = analytic(vsh, None);
        csv.push_str(&format!("{open_name},{vsh:.6},, {vis:.9},{i:.9e},{p:.9e},4.0e-6\n"));
        for vf in VFS {
            let name = format!("hard_{}_{}", stem(vsh), stem(vf));
            deck(&gen.join(format!("{name}.cir")), &name, vsh, Some(vf));
            let (vis, i, p) = analytic(vsh, Some(vf));
            csv.push_str(&format!("{name},{vsh:.6},{vf:.6},{vis:.9},{i:.9e},{p:.9e},4.0e-6\n"));
        }
    }
    fs::write(out.join("analytic.csv"), csv).unwrap();
}
