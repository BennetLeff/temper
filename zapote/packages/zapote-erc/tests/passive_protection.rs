//! Historical checks of rejected native-05, not the canonical candidate.
//! Source-bound logical checks. They do not model propagation, rail ramps,
//! comparator dynamics, or fuse interruption; see IMPLEMENTATION.md.
use std::collections::BTreeMap;
use zapote_erc::source_circuit::Circuit;

const ENTRY: &str = "elec/src/power_entry_passive_reva.ato:PowerEntryPassiveReva";
const MANIFEST: &str = include_str!("../../../power-entry/passive-reva/native-05/source-manifest.json");

fn circuit() -> Circuit { Circuit::parse(MANIFEST, ENTRY).unwrap() }

#[derive(Clone, Copy)]
struct Inputs {
    arm: bool, permit: bool, healthy: bool, por: bool, pre: bool, ready: bool, timeout: bool,
}
impl Default for Inputs {
    fn default() -> Self {
        Self { arm:false, permit:false, healthy:true, por:true, pre:true, ready:false, timeout:false }
    }
}
struct Logic<'a> { c: &'a Circuit, q: bool, clock: bool }
impl<'a> Logic<'a> {
    fn new(c: &'a Circuit) -> Self { Self { c, q:false, clock:false } }
    fn settle(&self, i: Inputs) -> BTreeMap<String,bool> {
        let mut n = BTreeMap::new();
        for (pin, value) in [
            ("protection.latch.14",true), ("protection.latch.7",false),
            ("protection.r_arm_input.2",i.arm), ("permit.1",i.permit),
            ("protection.compare_bus.2",i.healthy), ("protection.por.1",i.por),
            ("protection.compare_aux.14",i.pre), ("protection.compare_aux.13",i.ready),
            ("protection.timer.6",i.timeout), ("protection.latch.5",self.q),
        ] { n.insert(self.c.net(pin).unwrap().to_owned(),value); }
        for _ in 0..20 {
            let before = n.clone();
            for component in ["schmitt1","schmitt2"] {
                for (input,output) in [(1,2),(3,4),(5,6),(9,8),(11,10),(13,12)] {
                    let a=self.c.net(&format!("protection.{component}.{input}")).unwrap();
                    let y=self.c.net(&format!("protection.{component}.{output}")).unwrap();
                    if let Some(v)=n.get(a).copied() { n.insert(y.to_owned(),!v); }
                }
            }
            for component in ["gates1","gates2"] {
                for (pa,pb,py) in [(1,2,3),(4,5,6),(9,10,8),(12,13,11)] {
                    let a=self.c.net(&format!("protection.{component}.{pa}")).unwrap();
                    let b=self.c.net(&format!("protection.{component}.{pb}")).unwrap();
                    let y=self.c.net(&format!("protection.{component}.{py}")).unwrap();
                    if let (Some(a),Some(b))=(n.get(a).copied(),n.get(b).copied()) {
                        n.insert(y.to_owned(),a && b);
                    }
                }
            }
            if n == before { return n; }
        }
        panic!("logic did not settle");
    }
    fn step(&mut self, i: Inputs) -> (bool,bool) {
        let n=self.settle(i);
        let get=|pin| *n.get(self.c.net(pin).unwrap()).expect("undriven logic input");
        let clock=get("protection.latch.3");
        if !get("protection.latch.1") { self.q=false; }
        else if clock && !self.clock { self.q=get("protection.latch.2"); }
        self.clock=clock;
        let n=self.settle(i);
        (n[self.c.net("gate_driver.1").unwrap()], n[self.c.net("protection.service.2").unwrap()])
    }
}
fn start(m:&mut Logic<'_>) {
    let mut i=Inputs::default();
    assert_eq!(m.step(i),(false,false));
    i.arm=true; assert_eq!(m.step(i),(false,false));
    i.permit=true; assert_eq!(m.step(i),(true,false));
}
#[test]
fn startup_does_not_require_full_bank_voltage() {
    let c=circuit(); let mut m=Logic::new(&c); start(&mut m);
    let i=Inputs {arm:true,permit:true,ready:true,..Inputs::default()};
    assert_eq!(m.step(i),(true,true));
}
#[test]
fn every_fault_latches_off_until_a_new_qualified_arm_edge() {
    let c=circuit();
    for kind in 0..4 {
        let mut m=Logic::new(&c);start(&mut m);
        let mut i=Inputs {arm:true,permit:true,..Inputs::default()};
        match kind {0=>i.healthy=false,1=>i.por=false,2=>i.timeout=true,_=>i.pre=false};
        assert_eq!(m.step(i),(false,false));
        i.healthy=true;i.por=true;i.timeout=false;i.pre=true;
        for _ in 0..10 {assert_eq!(m.step(i),(false,false));}
        i.permit=false; assert_eq!(m.step(i),(false,false));
        i.permit=true; assert_eq!(m.step(i),(false,false));
        i.permit=false;i.arm=false;m.step(i);
        i.arm=true;m.step(i);
        i.permit=true;assert_eq!(m.step(i),(true,false));
    }
}
#[test]
fn stuck_high_arm_during_power_recovery_cannot_start() {
    let c=circuit(); let mut m=Logic::new(&c);
    m.q=true;
    let mut i=Inputs {arm:true,permit:true,por:false,..Inputs::default()};
    assert_eq!(m.step(i),(false,false));
    i.por=true;
    assert_eq!(m.step(i),(false,false));
    i.permit=false;m.step(i);i.permit=true;
    assert_eq!(m.step(i),(false,false));
}
#[test]
fn arm_with_permit_high_is_rejected() {
    let c=circuit();let mut m=Logic::new(&c);
    let i=Inputs {arm:true,permit:true,..Inputs::default()};
    assert_eq!(m.step(i),(false,false));
}
#[test]
fn combinational_shutdown_does_not_wait_for_clock_or_bank_ready() {
    let c=circuit();
    for kind in 0..4 {
        let mut m=Logic::new(&c);start(&mut m);
        let mut i=Inputs {arm:true,permit:true,ready:true,..Inputs::default()};
        match kind {0=>i.healthy=false,1=>i.por=false,2=>i.timeout=true,_=>i.pre=false};
        let n=m.settle(i);
        assert!(!n[c.net("gate_driver.1").unwrap()]);
        assert!(!n[c.net("protection.service.2").unwrap()]);
    }
}
#[test]
fn timeout_request_survives_disarming_so_trip_is_not_self_cancelled() {
    let c=circuit();let mut m=Logic::new(&c);start(&mut m);
    let i=Inputs {arm:true,permit:true,timeout:true,..Inputs::default()};
    m.step(i);
    let n=m.settle(i);
    assert!(n[c.net("protection.timer.1").unwrap()]);
}
fn topology(c:&Circuit) -> Result<(),String> {
    for pins in [
        vec!["d_boost.2","c_hf.1","c_hf.4","f2_port.1","r_vtop.1","protection.r_vd1.1"],
        vec!["f2_port.2","c1.1","c2.1","c3.1","c4.1","output.1","protection.r_vb1.1"],
        vec!["q_boost.3","gate_driver.3","protection.buffer.11","aux.2"],
        vec!["gate_driver.1","protection.gates2.6","r_permit_gate.1","gate_enable_pd.1"],
        vec!["gate_driver.7","r_gate.1"],
        vec!["pfc.8","gate_input.1"],
        vec!["gate_input.2","gate_driver.2"],
        vec!["gate_driver.4","gate_driver.8","q_boost.3"],
        vec!["protection.ldo.4","protection.ldo.9","q_boost.3"],
        vec!["protection.schmitt2.11","protection.compare_bus.2","protection.compare_bus.1","protection.compare_bus.13","protection.compare_bus.14"],
    ] {c.require_net(&pins)?;}
    c.require_distinct(&["d_boost.2","c1.1","q_boost.3","shunt.2"])?;
    c.require_distinct(&["pfc.6","protection.buffer.3","protection.buffer.5"])?;
    Ok(())
}
#[test]
fn power_and_independent_observation_match_compiled_package_pins() {topology(&circuit()).unwrap();}
#[test]
fn graph_mutations_expose_fuse_bypass_and_unsupervised_driver() {
    for (pin, other) in [("f2_port.1","c1.1"),("gate_driver.1","permit.1"),("protection.buffer.3","pfc.6")] {
        let mut c=circuit();let value=c.net(other).unwrap().to_owned();
        c.pins.insert(pin.to_owned(),value);
        assert!(topology(&c).is_err());
    }
}
#[test]
fn retained_parts_and_four_lead_reservoir_are_exact() {
    let c=circuit();
    for (instance,mpn) in [("gate_driver","UCC27624DR"),("c_hf","B32776P6226K000"),
        ("protection.schmitt2","SN74HCS14PWR"),("protection.latch","SN74HCT74DR"),
        ("protection.timer","LTC6994IS6-1#TRMPBF")] {
        assert_eq!(c.components[instance].mpn,mpn);
    }
    for pin in ["c_hf.1","c_hf.2","c_hf.3","c_hf.4"] {
        assert_eq!(c.physical_multiplicity[pin],1);
    }
}
