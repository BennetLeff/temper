use std::{fs, path::Path};
fn main() -> Result<(), String> {
    let base = fs::read_to_string("../tracked/run/cold.cir").map_err(|e| e.to_string())?;
    let candidate = fs::read_to_string("cold.cir").map_err(|e| e.to_string())?;
    let inverse = candidate.replace(".options method=gear maxord=2 reltol=2e-4 abstol=1e-10 vntol=1e-7", ".options method=trap reltol=2e-4 abstol=1e-10 vntol=1e-7").replace(".param RLOAD=190 TSTOP=110m STEP=500n", ".param RLOAD=190 TSTOP=500m STEP=500n");
    if inverse != base { return Err("inverse replacement is not byte-identical to tracked/run/cold.cir".into()); }
    for name in ["clamp.inc", "protection.inc", "standby.inc", "ucc28180-pwm-latch.inc", "vendor/UCC27511A.lib"] {
        let a = fs::read(Path::new("../tracked/run").join(name)).map_err(|e| e.to_string())?;
        let b = fs::read(name).map_err(|e| e.to_string())?;
        if a != b { return Err(format!("include changed: {name}")); }
        println!("include-byte-identical {name}");
    }
    println!("inverse-cold-deck-byte-identical");
    println!("launch=UNSTARTED");
    Ok(())
}
