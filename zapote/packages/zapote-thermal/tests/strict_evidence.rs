use zapote_thermal::parse_elmer_outputs_named;

const LOG: &[u8] = include_bytes!("fixtures/mesh-0.0005000/elmersolver.log");
const DATA: &[u8] = include_bytes!("fixtures/mesh-0.0005000/scalars.dat");
const NAMES: &[u8] = include_bytes!("fixtures/mesh-0.0005000/scalars.dat.names");

#[test]
fn rejects_other_variable_named_max() {
    let names = String::from_utf8_lossy(NAMES).replace("max: temperature", "max: potential");
    assert!(parse_elmer_outputs_named(LOG, DATA, Some(names.as_bytes())).is_err());
}

#[test]
fn rejects_malformed_column_trailer() {
    let mut names = NAMES.to_vec();
    names.extend_from_slice(b"\nnot a column\n");
    assert!(parse_elmer_outputs_named(LOG, DATA, Some(&names)).is_err());
}

#[test]
fn rejects_duplicate_measurement_in_log() {
    let mut log = LOG.to_vec();
    log.extend_from_slice(b"\nStatCurrentSolve: Total Heating Power : 4.64\n");
    assert!(parse_elmer_outputs_named(&log, DATA, Some(NAMES)).is_err());
}

#[test]
fn rejects_trailing_malformed_or_extra_scalar_row() {
    for tail in [b"\nmalformed\n".as_slice(), DATA] {
        let mut data = DATA.to_vec();
        data.extend_from_slice(tail);
        assert!(parse_elmer_outputs_named(LOG, &data, Some(NAMES)).is_err());
    }
}

#[test]
fn rejects_scalar_power_disagreeing_with_raw_log() {
    let data = String::from_utf8_lossy(DATA).replace("4.640000000000E+000", "4.000000000000E+000");
    assert!(parse_elmer_outputs_named(LOG, data.as_bytes(), Some(NAMES)).is_err());
}
