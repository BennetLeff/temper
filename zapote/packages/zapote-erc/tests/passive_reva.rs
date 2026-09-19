use zapote_erc::source_circuit::Circuit;

const SOURCE: &str =
    include_str!("../../../power-entry/passive-reva/native-01/source-manifest.json");
const NATIVE: &str = include_str!("../../../power-entry/shunt-repair/evidence/native-04.json");
const BOARD: &str = include_str!("../../../power-entry/passive-reva/candidate/section.kicad_pcb");
const ENTRY: &str = "elec/src/power_entry_passive_reva.ato:PowerEntryPassiveReva";

#[test]
fn compiled_passive_source_binds_exact_retained_native_board() {
    let native: serde_json::Value = serde_json::from_str(NATIVE).expect("native evidence parses");
    assert_eq!(
        native["board_file_utf8"].as_str(),
        Some(BOARD),
        "binding evidence must describe the actual passive candidate bytes"
    );
    let circuit = Circuit::parse(SOURCE, ENTRY).expect("passive source manifest parses");
    circuit
        .bind_native(NATIVE)
        .expect("source pin/component graph must bind the exact saved board export");
}
