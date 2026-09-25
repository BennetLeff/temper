use std::fs;
fn main() -> Result<(), String> {
    let cold = fs::read_to_string("cold.cir").map_err(|e| e.to_string())?;
    let base_cold = fs::read_to_string("../first-invalid-capture/run/cold.cir").map_err(|e| e.to_string())?;
    let restored_cold = cold.replace("v(xdriver.driver_req)", "v(drv_req)").replace("v(xdriver.drv_delay)", "v(drv)");
    if restored_cold != base_cold { return Err("cold.cir differs beyond diagnostic save names".into()); }
    let progress = fs::read_to_string("progress.rs").map_err(|e| e.to_string())?;
    let base_progress = fs::read_to_string("../first-invalid-capture/run/progress.rs").map_err(|e| e.to_string())?;
    let restored_progress = progress.replace("xdriver.driver_req", "drv_req").replace("xdriver.drv_delay", "drv");
    if restored_progress != base_progress { return Err("progress.rs differs beyond diagnostic names".into()); }
    let source = fs::read_to_string("../normal-tracked/protection.inc").map_err(|e| e.to_string())?;
    let candidate = fs::read_to_string("protection.inc").map_err(|e| e.to_string())?;
    let old = "* UCC27511A functional surrogate; actual unchanged TI model checked separately.\nBdriver_req drv_req 0 V=(V(disable)<1.2 && V(pwm_input)>2.2 && V(aux15)>4.5) ? V(aux15) : 0\nRdriver_delay drv_req drv 1\nCdriver_delay drv 0 {EN_TAU}\nBen en 0 V=(V(disable)<1.2 && V(aux15)>4.5) ? 5 : 0\nRdriver drv gate_cmd 1\n";
    let new = ".include authored_logic_hysteretic.inc\nXdriver disable pwm_input aux15 0 gate_cmd AUTH_UCC27511A_H\nBen en 0 V=5*(1-V(xdriver.inm_logic))*V(xdriver.aux_logic)\n";
    if candidate != source.replace(old, new) { return Err("protection.inc differs beyond authored driver block and Ben monitor".into()); }
    for name in ["clamp.inc", "standby.inc", "ucc28180-pwm-latch.inc"] {
        if fs::read(name).map_err(|e| e.to_string())? != fs::read(format!("../normal-tracked/{name}")).map_err(|e| e.to_string())? { return Err(format!("unchanged include differs: {name}")); }
    }
    if fs::read("authored_logic_hysteretic.inc").map_err(|e| e.to_string())? != fs::read("../numerical-repair/driver-hysteresis-candidate/authored_logic_hysteretic.inc").map_err(|e| e.to_string())? { return Err("authored logic source differs".into()); }
    println!("inverse-cold-and-progress-proof PASS");
    println!("inverse-protection-block-proof PASS");
    println!("unchanged-includes-and-authored-logic-byte-proof PASS");
    println!("diagnostic-mask=16/16; full-run=UNSTARTED");
    Ok(())
}
