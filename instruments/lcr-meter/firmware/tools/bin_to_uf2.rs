//! RP2040 main-flash UF2, matching Pico SDK 2.2.0 boot/uf2.h.
use std::{env, fs};
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 3 {
        return Err("usage: bin_to_uf2 INPUT.bin OUTPUT.uf2".into());
    }
    let data = fs::read(&args[1])?;
    if data.is_empty() || data.len() > 2 * 1024 * 1024 {
        return Err("invalid 2 MiB flash image size".into());
    }
    let count = data.len().div_ceil(256);
    let mut output = vec![0; count * 512];
    for (i, chunk) in data.chunks(256).enumerate() {
        let block = &mut output[i * 512..(i + 1) * 512];
        for (index, word) in [
            0x0a324655,
            0x9e5d5157,
            0x2000,
            0x10000000 + (i * 256) as u32,
            256,
            i as u32,
            count as u32,
            0xe48bff56,
        ]
        .iter()
        .enumerate()
        {
            block[index * 4..index * 4 + 4].copy_from_slice(&word.to_le_bytes());
        }
        block[32..32 + chunk.len()].copy_from_slice(chunk);
        block[508..512].copy_from_slice(&0x0ab16f30u32.to_le_bytes());
    }
    fs::write(&args[2], &output)?;
    // Read the actual output back and verify every header and recovered byte.
    let disk = fs::read(&args[2])?;
    let mut recovered = Vec::new();
    for (i, block) in disk.chunks_exact(512).enumerate() {
        let word =
            |n: usize| u32::from_le_bytes([block[n], block[n + 1], block[n + 2], block[n + 3]]);
        if word(0) != 0x0a324655
            || word(4) != 0x9e5d5157
            || word(8) != 0x2000
            || word(12) != 0x10000000 + (i * 256) as u32
            || word(16) != 256
            || word(20) != i as u32
            || word(24) != count as u32
            || word(28) != 0xe48bff56
            || word(508) != 0x0ab16f30
        {
            return Err("UF2 verification failed".into());
        }
        recovered.extend_from_slice(&block[32..288]);
    }
    if recovered[..data.len()] != data {
        return Err("UF2 payload mismatch".into());
    }
    println!(
        "Verified {count} UF2 blocks; {} firmware bytes; RP2040 family, flash 0x10000000",
        data.len()
    );
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
