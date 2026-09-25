//! Bind extractor energy constants and current bands to the generated cases.
use std::{env,fs,path::Path};
fn main()->Result<(),Box<dyn std::error::Error>> {
    let root=env::args().nth(1).ok_or("plant directory required")?;
    let root=Path::new(&root);
    for entry in fs::read_dir(root.join("traces"))? {
        let path=entry?.path(); if path.extension().and_then(|s|s.to_str())!=Some("tsv") {continue;}
        let name=path.file_stem().unwrap().to_str().unwrap();
        let cir=fs::read_to_string(root.join("raw").join(format!("{name}.cir")))?;
        let l=if name.contains("40_") {"100u"} else if name.contains("45_")||name=="normal_arm"||name=="slowed_gate_negative" {"180u"} else {"216u"};
        let gate=if name=="doubled_gate_charge" {"240n"} else if name=="slowed_gate_negative" {"480n"} else {"120n"};
        for expected in [format!(".param LBOOST={l}"),format!(".param GATE_TAU={gate}"),".param CLOCAL=19.8u".into(),".param MOS_COSS=344p".into(),".param MOS_CGD=112p".into(),"Cbank vb 0 2240u IC={VB_INIT}".into()] {
            if !cir.lines().any(|line|line==expected) {return Err(format!("{name}: extractor/netlist mismatch {expected}").into());}
        }
    }
    let summary=fs::read_to_string(root.join("traces/summary.csv"))?;
    for (name,min,max) in [("f2_open_40_adverse",40.,45.),("f2_open_45_adverse",45.,50.),("f2_open_50_adverse",50.,55.)] {
        let row=summary.lines().find(|l|l.starts_with(&format!("{name},"))).ok_or("missing current corner")?;
        let current:f64=row.split(',').nth(9).ok_or("missing opening current")?.parse()?;
        if !current.is_finite()||current<min||current>max {return Err(format!("{name}: actual opening current {current} outside{min}..{max}A").into());}
    }
    println!("PASS generated inductance/gate/capacitance parameters match extractor; actual opening currents cover40–45/45–50/50–55A bands");
    Ok(())
}
