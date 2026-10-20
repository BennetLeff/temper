//! Run with: rustc --edition=2021 analog-review.rs -O -o /tmp/lcr-analog-review
//! Then: /tmp/lcr-analog-review [output-directory]
//! Generic loop sensitivity study, NOT an AD8606 manufacturer macromodel.
use std::{error::Error, fs, path::PathBuf, process::Command};

#[derive(Clone, Copy)]
struct Model {
    name: &'static str,
    gbw: f64,
    second_pole: f64,
    ro: f64,
}
#[derive(Clone)]
struct Load {
    name: String,
    netlist: String,
    range: usize,
    test_hz: f64,
}

fn main() -> Result<(), Box<dyn Error>> {
    let out = PathBuf::from(
        std::env::args()
            .nth(1)
            .unwrap_or_else(|| "analog-review".into()),
    );
    fs::create_dir_all(out.join("cases"))?;
    let temp = std::env::temp_dir().join(format!("temper-lcr-spice-{}", std::process::id()));
    fs::create_dir_all(&temp)?;
    let models = [
        Model {
            name: "nominal_generic",
            gbw: 10e6,
            second_pole: 20e6,
            ro: 20.0,
        },
        Model {
            name: "slow_high_ro",
            gbw: 8e6,
            second_pole: 10e6,
            ro: 50.0,
        },
        Model {
            name: "fast_low_ro",
            gbw: 12e6,
            second_pole: 40e6,
            ro: 10.0,
        },
    ];
    let rf = [20.0, 200.0, 2e3, 20e3];
    let cf = [100e-9, 10e-9, 1e-9, 100e-12];
    let mut loads = Vec::new();
    for (range, &feedback) in rf.iter().enumerate() {
        for (tag, z) in [
            ("low", feedback / 4.0),
            ("mid", feedback),
            ("high", feedback * 2.5),
        ] {
            loads.push(Load {
                name: format!("r{range}_res_{tag}"),
                netlist: format!("RDUT hi remote {z:e}"),
                range,
                test_hz: 50e3,
            });
            let capacitance = 1.0 / (2.0 * std::f64::consts::PI * 50e3 * z);
            loads.push(Load {
                name: format!("r{range}_cap_{tag}"),
                netlist: format!("CDUT hi remote {capacitance:e}"),
                range,
                test_hz: 50e3,
            });
        }
        loads.push(Load {
            name: format!("r{range}_open"),
            netlist: "ROPEN hi remote 1e12".into(),
            range,
            test_hz: 50e3,
        });
    }
    for (name, inductance, resistance) in [
        ("20uH", 20e-6, 1.0),
        ("80uH", 80e-6, 2.0),
        ("150uH", 150e-6, 1.0),
    ] {
        loads.push(Load {
            name: format!("r0_coil_{name}"),
            netlist: format!("RDUT hi coil {resistance:e}\nLDUT coil remote {inductance:e}"),
            range: 0,
            test_hz: 50e3,
        });
    }
    loads.push(Load {
        name: "r0_bus_9uF".into(),
        netlist: "RESR hi cap .05\nCDUT cap remote 9u".into(),
        range: 0,
        test_hz: 1e3,
    });
    let mut csv = String::from("case,model,test_hz,drive_gain_at_test,tia_gain_at_test,drive_peak_ac_gain,tia_peak_ac_gain,drive_min_V,drive_max_V,tia_min_V,tia_max_V,tia_tail_pp_V,linear_model_bounded\n");
    for model in models {
        for load in &loads {
            let name = format!("{}_{}", load.name, model.name);
            let ac = temp.join(format!("{name}-ac.dat"));
            let tr = temp.join(format!("{name}-tr.dat"));
            let circuit = format!(
                r#"Temper LCR generic two-pole loop sensitivity - {name}
* Explicit generic assumptions: A0=100000, GBW={gbw:e}, pole2={pole2:e}, Ro={ro}
* Input capacitances are sensitivity estimates, not extracted PCB parasitics.
* No current limiting, slew limiting, thermal behavior, noise or rail clamps.
.subckt generic plus minus out
EGAIN n1 0 plus minus 100000
RDOM n1 n2 1000
CDOM n2 0 {cdom:e}
RSECOND n2 n3 1000
CSECOND n3 0 {csecond:e}
EOUT internal 0 n3 0 1
ROUT internal out {ro}
CDIFF plus minus 4p
CMPLUS plus 0 2p
CMMINUS minus 0 2p
.ends generic
VRAIL vcc 0 3.3
RBIASP vcc bias 47k
RBIASN bias 0 47k
CBIAS bias 0 1u
* Direct input after AC rebias: 100mV, 1us pulse, 10ns edges.
* A short pulse avoids interpreting the bias network's DC drift as oscillation.
VIN stimulus 0 DC 1.65 AC 1 PULSE(1.65 1.75 10u 10n 10n 1u 4m)
XDRIVER stimulus drive drive generic
RSOURCE drive hi 10
CFIXHI hi 0 100p
{dut}
RLEAD remote lead .2
LLEAD lead lo 1u
CFIXLO lo 0 100p
XTIA bias lo tia generic
RFEEDBACK tia lo {feedback:e}
CFEEDBACK tia lo {feedback_cap:e}
RKEEP tia lo 1meg
CKEEP tia lo 22p
* Internal AD5933 unity receive stage is represented only by its 20k load.
RRECEIVE tia bias 20k
.options reltol=1e-5
.control
set wr_singlescale
set wr_vecnames
ac dec 120 1 100meg
let drivergain=mag(v(drive))
let tiagain=mag(v(tia))
wrdata {ac} drivergain tiagain
tran 10n 1m 0 10n
wrdata {tr} v(drive) v(tia)
quit
.endc
.end
"#,
                gbw = model.gbw,
                pole2 = model.second_pole,
                ro = model.ro,
                cdom = 100000.0 / (2.0 * std::f64::consts::PI * model.gbw * 1000.0),
                csecond = 1.0 / (2.0 * std::f64::consts::PI * model.second_pole * 1000.0),
                dut = load.netlist,
                feedback = rf[load.range],
                feedback_cap = cf[load.range],
                ac = ac.display(),
                tr = tr.display()
            );
            let path = out.join("cases").join(format!("{name}.cir"));
            fs::write(&path, circuit)?;
            let result = Command::new("ngspice").arg("-b").arg(&path).output()?;
            fs::write(
                out.join("cases").join(format!("{name}.log")),
                [result.stdout, result.stderr].concat(),
            )?;
            if !result.status.success() {
                return Err(format!("ngspice failed: {name}").into());
            }
            let read = |path: &PathBuf| -> Result<Vec<Vec<f64>>, Box<dyn Error>> {
                let data = fs::read_to_string(path)?;
                let rows: Vec<Vec<f64>> = data
                    .lines()
                    .skip(1)
                    .map(|line| line.split_whitespace().map(str::parse::<f64>).collect())
                    .collect::<Result<_, _>>()?;
                if rows.is_empty()
                    || rows
                        .iter()
                        .any(|r| r.len() != 3 || r.iter().any(|x| !x.is_finite()))
                {
                    return Err(format!("invalid simulation data: {}", path.display()).into());
                }
                Ok(rows)
            };
            let a = read(&ac)?;
            let t = read(&tr)?;
            let test = a
                .iter()
                .min_by(|a, b| {
                    (a[0] - load.test_hz)
                        .abs()
                        .total_cmp(&(b[0] - load.test_hz).abs())
                })
                .ok_or("no ac points")?;
            let max = |data: &[Vec<f64>], column| {
                data.iter()
                    .map(|r| r[column])
                    .fold(f64::NEG_INFINITY, f64::max)
            };
            let min = |data: &[Vec<f64>], column| {
                data.iter().map(|r| r[column]).fold(f64::INFINITY, f64::min)
            };
            let tail: Vec<_> = t.iter().filter(|r| r[0] > 0.0009).cloned().collect();
            let bounded = min(&t, 1) > 0.0
                && max(&t, 1) < 3.3
                && min(&t, 2) > 0.0
                && max(&t, 2) < 3.3
                && max(&tail, 2) - min(&tail, 2) < 0.001;
            csv.push_str(&format!("{name},{},{:.6},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{bounded}\n",model.name,test[0],test[1],test[2],max(&a,1),max(&a,2),min(&t,1),max(&t,1),min(&t,2),max(&t,2),max(&tail,2)-min(&tail,2)));
            fs::remove_file(ac)?;
            fs::remove_file(tr)?;
        }
    }
    fs::write(out.join("results.csv"), csv)?;
    fs::remove_dir(&temp)?;
    println!(
        "Completed {} generic-model cases; NOT a hardware qualification",
        loads.len() * models.len()
    );
    Ok(())
}
