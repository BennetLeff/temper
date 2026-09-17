// Standalone reproducibility calculation; not a second engineering model.
// rustc gate_calc.rs -O -o /tmp/existing-drive-gate-calc && /tmp/existing-drive-gate-calc
//
// The values are conditional on the authored 10-ohm resistor, ST typical
// intrinsic Rg=3.3 ohm, the 6.2 V plateau assumption and ST typical Qgd=58 nC.
// They are an upper bound on current / lower bound on time because UCC output
// resistance and PCB parasitics are intentionally omitted.

fn main() {
    const R_SERIES_OHM: f64 = 10.0 + 3.3;
    const PLATEAU_V: f64 = 6.2;
    const QGD_C: f64 = 58e-9;
    const QG_C: f64 = 120e-9;
    const FSW_HZ: f64 = 129_107.392;
    for vdrive in [9.0_f64, 10.0, 11.0, 12.2, 15.0] {
        let plateau_current_a = (vdrive - PLATEAU_V) / R_SERIES_OHM;
        let qgd_time_ns = QGD_C / plateau_current_a * 1e9;
        let qg_supply_w = QG_C * vdrive * FSW_HZ;
        println!(
            "{vdrive:>4.1} V  Iplateau<= {plateau_current_a:.10} A  Qgd/I >= {qgd_time_ns:.7} ns  QgVf={qg_supply_w:.10} W"
        );
    }
}
