use serde::de::DeserializeOwned;
use serde::Serialize;
use std::{env, fs, process};
use temper_lcr::transport::Device;
use temper_lcr::{
    analyze, calibrate, correct, divider_for, frequency_word, Calibration, Result, Sweep,
};

fn read<T: DeserializeOwned>(path: &str) -> Result<T> {
    serde_json::from_str(&fs::read_to_string(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())
}
fn write<T: Serialize>(path: &str, value: &T) -> Result<()> {
    fs::write(
        path,
        serde_json::to_string_pretty(value).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}
fn number<T: std::str::FromStr>(s: &str) -> Result<T> {
    s.parse().map_err(|_| format!("invalid number: {s}"))
}
fn run(a: &[String]) -> Result<()> {
    match a.get(1).map(String::as_str) {
        Some("info")|Some("selftest") if a.len()==3 => {
            let mut d=Device::open(&a[2],100,"diagnostic")?;
            d.selftest()?;
            println!("{}",serde_json::to_string_pretty(&d.setup).map_err(|e|e.to_string())?);
            println!("ADC dual-channel fixed-pattern link test: PASS");
        }
        Some("capture")|Some("noise") if a.len()==7 => {
            let range=number(&a[3])?;
            let mut d=Device::open(&a[2],range,&a[4])?;
            d.selftest()?;
            let mut records=Vec::new();
            for f in a[5].split(',') {
                let hz:f64=number(f)?;
                let word=frequency_word(hz)?;
                let record=d.capture(word,divider_for(hz),a[1]=="capture")?;
                if a[1]=="noise" {
                    println!("{}",serde_json::to_string(&temper_lcr::noise(&record)?).map_err(|e|e.to_string())?);
                }
                eprintln!("captured {hz} Hz: {} simultaneous sample pairs",record.packed_samples.len());
                records.push(record);
            }
            write(&a[6],&Sweep{setup:d.setup.clone(),records})?;
        }
        Some("calibrate") if a.len()==8 => {
            let short:Sweep=read(&a[2])?;
            let one:Sweep=read(&a[3])?;
            let two:Sweep=read(&a[5])?;
            let cal=calibrate(&short,&one,number(&a[4])?,&two,number(&a[6])?)?;
            write(&a[7],&cal)?;
            println!("Saved {} frequency-specific calibration points.",cal.points.len());
        }
        Some("analyze") if a.len()==3 || a.len()==4 => {
            let sweep:Sweep=read(&a[2])?;
            sweep.setup.validate()?;
            let cal:Option<Calibration>=if a.len()==4{Some(read(&a[3])?)}else{None};
            let mut values=Vec::new();
            for r in &sweep.records {
                let mut m=analyze(r,sweep.setup.range_ohm)?;
                if let Some(c)=&cal{correct(&mut m,r,&sweep.setup,c)?;}
                values.push(m);
            }
            println!("{}",serde_json::to_string_pretty(&values).map_err(|e|e.to_string())?);
            if values.iter().any(|m|!m.valid){return Err("one or more measurements failed signal-quality checks".into());}
        }
        Some("validate") if a.len()==6 => {
            let sweep:Sweep=read(&a[2])?;
            let cal:Calibration=read(&a[3])?;
            let resistance:f64=number(&a[4])?;
            let tolerance:f64=number(&a[5])?;
            if !resistance.is_finite() || resistance<=0.0 || !tolerance.is_finite() || tolerance<=0.0 {
                return Err("validation resistance and percent tolerance must be positive".into());
            }
            let mut pass=!sweep.records.is_empty();
            for r in &sweep.records {
                let mut m=analyze(r,sweep.setup.range_ohm)?;
                correct(&mut m,r,&sweep.setup,&cal)?;
                let error=(m.impedance_ohm-temper_lcr::Complex::new(resistance,0.0)).abs()/resistance*100.0;
                let ok=m.valid && error<=tolerance;
                pass&=ok;
                println!("{:.6} Hz: complex error {:.6}% {}",m.frequency_hz,error,if ok{"PASS"}else{"FAIL"});
            }
            if !pass {return Err("independent-standard validation failed".into());}
        }
        _ => return Err(
            "Usage:\n  temper-lcr info PORT\n  temper-lcr selftest PORT\n  temper-lcr capture PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json\n  temper-lcr noise PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json\n  temper-lcr analyze CAPTURE.json [CAL.json]\n  temper-lcr calibrate SHORT.json LOAD1.json LOAD1_OHM LOAD2.json LOAD2_OHM CAL.json\n  temper-lcr validate CAPTURE.json CAL.json KNOWN_OHM TOLERANCE_PERCENT".into())
    }
    Ok(())
}
fn main() {
    if let Err(e) = run(&env::args().collect::<Vec<_>>()) {
        eprintln!("{e}");
        process::exit(1);
    }
}
