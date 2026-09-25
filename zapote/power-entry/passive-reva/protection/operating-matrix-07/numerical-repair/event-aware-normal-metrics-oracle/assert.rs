use std::io::{self, Read};
fn main() {
    let mode = std::env::args().nth(1).expect("mode boundary|endpoint");
    let mut text = String::new();
    io::stdin().read_to_string(&mut text).unwrap();
    let times: Vec<f64> = text.lines().map(|line| line.split_whitespace().next().unwrap().parse().unwrap()).collect();
    match mode.as_str() {
        "boundary" => {
            assert!(times.len() >= 2, "need two decoded duplicate rows");
            let target = 0.05_f64 - 1.0_f64 / 60.0_f64;
            assert_eq!(times[0].to_bits(), target.to_bits(), "first boundary timestamp differs");
            assert_eq!(times[1].to_bits(), target.to_bits(), "second boundary timestamp differs");
            println!("boundary_target={target:.17e} bits=0x{:016x} decoded_rows={} equal_bits=true", target.to_bits(), times.len());
        }
        "endpoint" => {
            assert_eq!(times.len(), 1, "need one decoded endpoint row");
            let target = 0.05_f64;
            assert_eq!(times[0].to_bits(), target.to_bits(), "endpoint differs");
            println!("endpoint_target={target:.17e} bits=0x{:016x} decoded_bits=true", target.to_bits());
        }
        _ => panic!("unknown mode"),
    }
}
