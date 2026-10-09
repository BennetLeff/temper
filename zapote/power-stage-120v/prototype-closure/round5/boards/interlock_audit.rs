//! Evaluate the emitted pin-level discrete logic; not a second circuit authority.
use std::{collections::BTreeMap, fs, path::Path};
type Pins=Vec<Vec<String>>;
fn parse(s:&str)->Pins{s.lines().skip(1).map(|l|l.split('\t').map(str::to_owned).collect()).collect()}
fn net<'a>(p:&'a Pins,r:&str,pin:&str)->&'a str{p.iter().find(|x|x[8]==r&&x[4]==pin).unwrap()[7].as_str()}
fn eval(p:&Pins,n:&str,roots:&BTreeMap<&str,bool>,depth:usize)->Result<bool,String>{
 if let Some(v)=roots.get(n){return Ok(*v)}
 if depth>70{return Err(format!("logic cycle at {n}"))}
 if n=="POD_3V3"{return Ok(true)}
 if n=="AUX_0V"{return Ok(false)}
 let r=p.iter().find(|r|r[7]==n&&r[4]=="4"&&r[1].starts_with("SN74LVC1G"))
     .ok_or_else(||format!("no evaluated driver for {n}"))?;
 let input=|pin|eval(p,net(p,&r[8],pin),roots,depth+1);
 match r[1].as_str(){"SN74LVC1G08DBVR"=>Ok(input("1")?&&input("2")?),
  "SN74LVC1G32DBVR"=>Ok(input("1")?||input("2")?),"SN74LVC1G04DBVR"=>Ok(!input("2")?),
  _=>Err(format!("unsupported gate {}",r[1]))}
}
fn require(ok:bool,why:&str)->Result<(),String>{if ok{Ok(())}else{Err(why.into())}}
fn audit(text:&str)->Result<(),String>{
 let p=parse(text);
 for (r,pin,n) in [("U_ATTEMPT","1","ADMIT"),("U_ATTEMPT","2","ATTEMPT_D"),
 ("U_PROOF_ONCE","1","START_QUALIFIED"),("U_PROOF_ONCE","5","START_TOKEN"),
 ("U_PROOF_ONCE","6","TOKEN_CLEAR_N"),("UT_PROOF","1","PROOF_REQUEST"),
 ("U_BUDGET1","2","SESSION_BUDGET_OK"),("U_PROVEN","2","FINAL_PROOF_VALID"),
 ("U_PROVEN","6","FINAL_PROOF_CLEAR_N"),("U_MCU","5","ADMIT"),("U_MCU","62","PROOF_WINDOW")]{
  require(net(&p,r,pin)==n,&format!("{r}.{pin} must be {n}"))?;
 }
 for r in ["UT_START","UT_TOTAL","UT_PROOF"]{
  require(p.iter().find(|x|x[8]==r).unwrap()[1]=="LTC6993HS6-1#TRMPBF","timers must be nonretriggerable -1")?;
 }
 // Manufacturer physical-pin oracle: do not trust the inherited logical labels.
 for row in p.iter().filter(|r|r[1]=="SN74LVC1G74DCUR") {
  let expected=match row[4].as_str(){"1"=>"CLK","2"=>"D","3"=>"Q_N","4"=>"GND","5"=>"Q","6"=>"CLR_N","7"=>"PRE_N","8"=>"VCC",_=>return Err("unknown DCU pin".into())};
  require(row[5]==expected,"DCU physical pin function mismatch")?;
 }
 // Independent RUN permission: any lost mirror/excitation or asserted isolation command inhibits.
 let names=["PRE_ISO_RUN_OK","KPA_MIRROR","KPB_MIRROR","KPA_FB_EXC","KPB_FB_EXC","CMD_KPA","CMD_KPB"];
 for bits in 0..128u32{
  let roots:BTreeMap<_,_>=names.iter().enumerate().map(|(i,n)|(*n,bits&(1<<i)!=0)).collect();
  let expected=bits&31==31&&bits&96==0;
  require(eval(&p,"SUP_RUN_OK_LOCAL",&roots,0)?==expected,"RUN truth table mismatch")?;
 }
 // Physical source-off includes both signed voltage windows, diagnostics, all three NCs,
 // all three excitations and absence of actual source commands.
 let names=["BUS_SAFE_HI","BUS_SAFE_LO","CATCH_SAFE_HI","CATCH_SAFE_LO","VBUS_DIAG_N","VCATCH_DIAG_N",
 "K1_MIRROR","K2_MIRROR","KB_MIRROR","K1_FB_EXC","K2_FB_EXC","KB_FB_EXC","CMD_K1","CMD_K2","CMD_KB"];
 for bits in 0..32768u32{
  let roots:BTreeMap<_,_>=names.iter().enumerate().map(|(i,n)|(*n,bits&(1<<i)!=0)).collect();
  require(eval(&p,"SOURCE_OFF_PHYSICAL",&roots,0)?==(bits&4095==4095&&bits&28672==0),"source-off truth table mismatch")?;
 }
 // A consumed token cannot drop or restart an active ATTEMPT on repeated ADMIT edges.
 for bits in 0..16u32{
  let roots=BTreeMap::from([("ATTEMPT",bits&1!=0),("START_TOKEN",bits&2!=0),
   ("SOURCE_OFF_PHYSICAL",bits&4!=0),("ISO_HEALTH",bits&8!=0)]);
  require(eval(&p,"ATTEMPT_D",&roots,0)?==(bits&1!=0||bits&14==14),"admission hold mismatch")?;
 }
 for bits in 0..8u32{
  let roots=BTreeMap::from([("ADMIT",bits&1!=0),("SOURCE_OFF_PHYSICAL",bits&2!=0),("ISO_HEALTH",bits&4!=0)]);
  require(eval(&p,"TOKEN_ARM_VALID",&roots,0)?==(bits==6),"stale-high ADMIT may arm token")?;
 }
 for bits in 0..4u32{
  let roots=BTreeMap::from([("ATTEMPT",bits&1!=0),("ATTEMPT_CLEAR_N",bits&2!=0)]);
  require(eval(&p,"TOKEN_CLEAR_N",&roots,0)?==(bits==2),"accepted attempt must consume token")?;
 }
 // Coil energization: health plus a physical source-off state or active bounded admission.
 for bits in 0..64u32{
  let roots=BTreeMap::from([("BASIC_HEALTHY",bits&1!=0),("LATCH_OK",bits&2!=0),
   ("SOURCE_OFF_PHYSICAL",bits&4!=0),("ATTEMPT",bits&8!=0),("TOTAL_WINDOW",bits&16!=0),("SUP_RUN_OK_LOCAL",bits&32!=0)]);
  let expected=bits&3==3&&(bits&4!=0||(bits&24==24&&bits&32==0));
  require(eval(&p,"ISO_COIL_ALLOWED",&roots,0)?==expected,"coil authorization mismatch")?;
 }
 for bits in 0..4u32{
  let roots=BTreeMap::from([("PROOF_CAPTURE_VALID",bits&1!=0),("PRECHARGE_ISOLATED",bits&2!=0)]);
  require(eval(&p,"FINAL_PROOF_VALID",&roots,0)?==(bits==3),"first proof may qualify final latch")?;
 }
 for bits in 0..4u32 {
  let roots=BTreeMap::from([("ATTEMPT",bits&1!=0),("PRECHARGE_ISOLATED",bits&2!=0)]);
  require(eval(&p,"FINAL_PROOF_CLEAR_N",&roots,0)?==(bits==3),"final proof must clear on attempt end or lost isolation")?;
  let roots=BTreeMap::from([("TOTAL_WINDOW",bits&1!=0),("SESSION_BUDGET_OK",bits&2!=0)]);
  require(eval(&p,"BUDGET_OR_PROOF",&roots,0)?==(bits!=0),"current timeout gate must follow qualified retained RUN")?;
 }
 audit_session_candidate(&p)?;
 Ok(())
}
fn main(){let base=Path::new(file!()).parent().unwrap();let pins=fs::read_to_string(base.join("central/generated/pins.tsv")).unwrap();audit(&pins).unwrap();println!("PASS: emitted pin-level RUN128, source-off32768, admission16, token12, coil64, finalproof4 vectors; analog timing and asynchronous hazards require separate qualification");}
// In-memory design-review candidate only; no generated pins or native files are changed.
#[cfg(test)]
fn session_candidate(text:&str)->Pins {
 let mut p=parse(text);
 for (r,pin,n) in [("U_RUN3","2","RUNTIME_HEALTHY"),("U_RUN_ARM","1","SUP_RUN_OK_LOCAL"),
  ("U_RUN_ARM","6","FINAL_PROOF_CLEAR_N"),("U_BUDGET1","2","SESSION_BUDGET_OK")] {
  p.iter_mut().find(|x|x[8]==r&&x[4]==pin).unwrap()[7]=n.into();
 }
 for (pin,n) in [("1","RUN_ARMED"),("2","RUNTIME_HEALTHY"),("3","AUX_0V"),("4","SESSION_BUDGET_OK"),("5","POD_3V3")] {
  p.push(vec!["PROPOSED_GATE".into(),"SN74LVC1G08DBVR".into(),"Package_TO_SOT_SMD:SOT-23-5".into(),"HARDWARE".into(),pin.into(),"proposal".into(),"input".into(),n.into(),"U_SESSION_BUDGET".into()]);
 }
 p
}
fn audit_session_candidate(p:&Pins)->Result<(),String> {
 for (r,pin,n) in [("U_RUN_ARM","1","SUP_RUN_OK_LOCAL"),("U_RUN_ARM","2","POD_3V3"),("U_RUN_ARM","6","FINAL_PROOF_CLEAR_N"),("U_BUDGET1","2","SESSION_BUDGET_OK")] {
  require(net(p,r,pin)==n,"session latch physical contract mismatch")?;
 }
 // Every original RUN guard remains mandatory; interlock becomes mandatory at capture.
 let names=["MCU_RUN","BYPASS_PROVEN","LATCH_OK","CTRL_RAIL_OK_LOCAL","CTRL_HEARTBEAT_OK","NATIVE_FAULT_N","CTRL_INTERLOCK_OK_LOCAL","PRECHARGE_ISOLATED"];
 for bits in 0..256u32 {
  let roots=names.iter().enumerate().map(|(i,n)|(*n,bits&(1<<i)!=0)).collect();
  require(eval(p,"SUP_RUN_OK_LOCAL",&roots,0)?==(bits==255),"unqualified RUN can capture session")?;
 }
 for bits in 0..8u32 {
  let roots=BTreeMap::from([("TOTAL_WINDOW",bits&1!=0),("RUN_ARMED",bits&2!=0),("RUNTIME_HEALTHY",bits&4!=0)]);
  require(eval(p,"BUDGET_OR_PROOF",&roots,0)?==(bits&1!=0||bits&6==6),"session budget truth mismatch")?;
  require(eval(p,"RUNTIME_ALLOWED",&roots,0)?==(bits&2==0||bits&4!=0),"runtime fault latch bypassed")?;
 }
 for bits in 0..4u32 {
  let roots=BTreeMap::from([("ATTEMPT",bits&1!=0),("PRECHARGE_ISOLATED",bits&2!=0)]);
  require(eval(p,net(p,"U_RUN_ARM","6"),&roots,0)?==(bits==3),"session survives end/isolation loss")?;
 }
 Ok(())
}
#[cfg(test)]mod tests{
 use super::*;
 const P:&str=include_str!("central/generated/pins.tsv");
 #[test]fn rejects_inherited_physical_pinout(){assert!(audit(&P.replace("1\tCLK\tinput\tRESET_QUALIFIED\tU_FAULT","1\tCLR_N\tinput\tRESET_QUALIFIED\tU_FAULT")).is_err());}
 #[test]fn actual_discrete_contract(){assert!(audit(P).is_ok());}
 #[test]fn rejects_unqualified_final_capture(){assert!(audit(&P.replace("FINAL_PROOF_VALID\tU_PROVEN","PROOF_CAPTURE_VALID\tU_PROVEN")).is_err());}
 #[test]fn rejects_oneshot_lockout(){assert!(audit(&P.replace("PROOF_REQUEST\tUT_PROOF","PROOF_STARTED\tUT_PROOF")).is_err());}
 #[test]fn rejects_retriggerable_timer(){assert!(audit(&P.replace("LTC6993HS6-1#TRMPBF","LTC6993HS6-2#TRMPBF")).is_err());}
 #[test]fn rejects_attempt_clearing_after_token_consumed(){let mutated=P.lines().map(|l|if l.ends_with("\tU_ATTEMPT_HOLD"){l.replace("SN74LVC1G32DBVR","SN74LVC1G08DBVR")}else{l.into()}).collect::<Vec<String>>().join("\n");assert!(audit(&mutated).is_err());}
 #[test]fn proposed_session_preserves_live_guards(){assert!(audit_session_candidate(&session_candidate(P)).is_ok());}
 #[test]fn rejects_raw_mcu_session_clock(){let mut p=session_candidate(P);p.iter_mut().find(|x|x[8]=="U_RUN_ARM"&&x[4]=="1").unwrap()[7]="MCU_RUN".into();assert!(audit_session_candidate(&p).is_err());}
 #[test]fn rejects_capture_without_interlock(){let mut p=session_candidate(P);p.iter_mut().find(|x|x[8]=="U_RUN3"&&x[4]=="2").unwrap()[7]="CTRL_RAIL_OK_LOCAL".into();assert!(audit_session_candidate(&p).is_err());}
 #[test]fn rejects_session_escape_without_live_health(){let mut p=session_candidate(P);p.iter_mut().find(|x|x[8]=="U_SESSION_BUDGET"&&x[4]=="2").unwrap()[7]="POD_3V3".into();assert!(audit_session_candidate(&p).is_err());}
 #[test]fn proposed_session_state_sequences(){
  let p=session_candidate(P);
  let mut retained=false;let mut previous_clock=false;
  // (attempt, isolation, MCU_RUN, finalproof, livehealth, totalwindow, expectedsource)
  let trace=[(true,true,false,false,true,true,true), // uncompleted admission
   (true,false,false,true,true,true,true), // first proof cannot capture
   (true,true,false,true,true,true,true), // PB13 alone cannot capture
   (true,true,false,true,true,false,false), // expired incomplete admission drops source
   (false,true,false,false,true,false,false), // fresh reset required
   (true,true,true,true,true,true,true), // actual qualified RUN captures
   (true,true,false,true,true,false,true), // zero demand after expiry retains session
   (true,true,true,true,true,false,true), // resumed demand, no timer restart
   (true,true,false,true,false,false,false), // runtime fault removes escape
   (false,true,false,false,true,false,false), // hard fault/end clear
   (true,true,true,true,true,true,true),
   (true,false,false,true,true,false,false)]; // isolation loss clears
  for (attempt,iso,mcu,proof,health,total,expected) in trace {
   let roots=BTreeMap::from([("MCU_RUN",mcu),("BYPASS_PROVEN",proof),("LATCH_OK",attempt),("CTRL_RAIL_OK_LOCAL",health),("CTRL_HEARTBEAT_OK",health),("NATIVE_FAULT_N",health),("CTRL_INTERLOCK_OK_LOCAL",health),("PRECHARGE_ISOLATED",iso)]);
   let clock=eval(&p,"SUP_RUN_OK_LOCAL",&roots,0).unwrap();
   if !(attempt&&iso){retained=false}else if clock&&!previous_clock{retained=true}
   previous_clock=clock;
   let roots=BTreeMap::from([("RUN_ARMED",retained),("RUNTIME_HEALTHY",health),("TOTAL_WINDOW",total)]);
   let budget=eval(&p,"BUDGET_OR_PROOF",&roots,0).unwrap();
   assert_eq!(attempt&&budget,expected);
  }
 }

}
