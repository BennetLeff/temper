//! Low-disk transport probe for the runner-12 FIFO -> pigz export path.
//!
//! This is synthetic evidence only.  It never invokes ngspice or a campaign
//! host.  The producer emits a >4 GiB indexed stream without creating an
//! uncompressed file; the parent retains only pigz output and small receipts.

use std::{
    env,
    fs::{self, File},
    io::{self, BufRead, BufReader, Read, Write},
    path::Path,
    process::{Child, Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

const BLOCKS: u64 = 4_200;
const PAYLOAD_BYTES: u64 = 1_048_576;
const OUTPUT_CAP_BYTES: u64 = 100 * 1024 * 1024;
const DISK_FLOOR_BYTES: u64 = 10 * 1024 * 1024 * 1024;
const TIMEOUT: Duration = Duration::from_secs(120);
const HEADER: &str = "TEMPER_FIFO_EXPORT_PROBE v1\nBLOCKS=4200\nPAYLOAD_BYTES=1048576\nHEADER_END\n";

fn quote(path: &Path) -> Result<String, String> {
    let value = path.to_str().ok_or("non-UTF8 path")?;
    Ok(format!("'{}'", value.replace('\'', "'\\''")))
}

fn disk_free(path: &Path) -> Result<u64, String> {
    let output = Command::new("df")
        .args(["-k", path.to_str().ok_or("non-UTF8 disk path")?])
        .output().map_err(|error| format!("df: {error}"))?;
    if !output.status.success() { return Err("df failed".into()); }
    let available = String::from_utf8_lossy(&output.stdout).lines().nth(1)
        .and_then(|line| line.split_whitespace().nth(3))
        .ok_or("df omitted available blocks")?
        .parse::<u64>().map_err(|_| "df available blocks invalid".to_string())?;
    Ok(available * 1024)
}

fn sha256(path: &Path) -> Result<String, String> {
    let value = path.to_str().ok_or("non-UTF8 hash path")?;
    let output = Command::new("shasum").args(["-a", "256", value]).output()
        .map_err(|error| format!("shasum: {error}"))?;
    if !output.status.success() { return Err(format!("shasum failed for {}", path.display())); }
    String::from_utf8_lossy(&output.stdout).split_whitespace().next()
        .map(str::to_owned).ok_or_else(|| "shasum omitted digest".into())
}

fn parse_u64_line(line: &str, key: &str) -> Result<u64, String> {
    line.strip_prefix(key).ok_or_else(|| format!("header missing {key}"))?
        .trim().parse::<u64>().map_err(|_| format!("header {key} invalid"))
}

fn produce(path: &Path) -> Result<(), String> {
    let mut output = io::BufWriter::with_capacity(1024 * 1024, File::create(path)
        .map_err(|error| format!("open producer FIFO: {error}"))?);
    output.write_all(HEADER.as_bytes()).map_err(|error| format!("write header: {error}"))?;
    let mut payload = vec![0_u8; PAYLOAD_BYTES as usize];
    for block in 0..BLOCKS {
        output.write_all(&block.to_le_bytes()).map_err(|error| format!("write block index {block}: {error}"))?;
        output.write_all(&PAYLOAD_BYTES.to_le_bytes()).map_err(|error| format!("write block size {block}: {error}"))?;
        payload.fill((block % 251) as u8);
        output.write_all(&payload).map_err(|error| format!("write block {block}: {error}"))?;
    }
    output.flush().map_err(|error| format!("flush producer: {error}"))?;
    Ok(())
}

fn read_line_exact(reader: &mut BufReader<impl Read>, expected: &str) -> Result<(), String> {
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|error| format!("read header: {error}"))?;
    if line != expected { return Err(format!("header mismatch: expected {expected:?}, got {line:?}")); }
    Ok(())
}

fn verify(input: impl Read) -> Result<(), String> {
    let mut reader = BufReader::with_capacity(1024 * 1024, input);
    read_line_exact(&mut reader, "TEMPER_FIFO_EXPORT_PROBE v1\n")?;
    let mut line = String::new(); reader.read_line(&mut line).map_err(|e| e.to_string())?;
    if parse_u64_line(&line, "BLOCKS=")? != BLOCKS { return Err("unexpected block count".into()); }
    line.clear(); reader.read_line(&mut line).map_err(|e| e.to_string())?;
    if parse_u64_line(&line, "PAYLOAD_BYTES=")? != PAYLOAD_BYTES { return Err("unexpected payload size".into()); }
    read_line_exact(&mut reader, "HEADER_END\n")?;
    let mut header = [0_u8; 16];
    let mut payload = vec![0_u8; 1024 * 1024];
    for expected_block in 0..BLOCKS {
        reader.read_exact(&mut header).map_err(|error| format!("truncated block header {expected_block}: {error}"))?;
        let mut index_bytes = [0_u8; 8]; index_bytes.copy_from_slice(&header[..8]);
        let mut size_bytes = [0_u8; 8]; size_bytes.copy_from_slice(&header[8..]);
        let index = u64::from_le_bytes(index_bytes); let size = u64::from_le_bytes(size_bytes);
        if index != expected_block { return Err(format!("block order mismatch: expected {expected_block}, got {index}")); }
        if size != PAYLOAD_BYTES { return Err(format!("block {index} size mismatch")); }
        let expected_byte = (index % 251) as u8; let mut remaining = size as usize;
        while remaining != 0 {
            let take = remaining.min(payload.len());
            reader.read_exact(&mut payload[..take]).map_err(|error| format!("truncated block {index}: {error}"))?;
            if payload[..take].iter().any(|byte| *byte != expected_byte) { return Err(format!("payload mismatch in block {index}")); }
            remaining -= take;
        }
    }
    let mut trailing = [0_u8; 1];
    if reader.read(&mut trailing).map_err(|error| format!("read trailing bytes: {error}"))? != 0 { return Err("trailing bytes after final block".into()); }
    Ok(())
}

fn kill_reap(child: &mut Child) -> Option<ExitStatus> {
    let _ = child.kill(); child.wait().ok()
}

fn write_receipt(path: &Path, receipt: &str) -> Result<(), String> {
    fs::write(path, format!("{receipt}\n")).map_err(|error| format!("write receipt: {error}"))
}

fn run(out_dir: &Path, pigz: &Path) -> Result<(), String> {
    fs::create_dir_all(out_dir).map_err(|error| format!("create output dir: {error}"))?;
    if disk_free(out_dir)? < DISK_FLOOR_BYTES { return Err("disk floor below 10 GiB before probe".into()); }
    let fifo = out_dir.join("stream.fifo"); let output = out_dir.join("stream.raw.gz");
    for path in [&fifo, &output] { if path.exists() { return Err(format!("refusing existing output {}", path.display())); } }
    let status = Command::new("mkfifo").arg(&fifo).status().map_err(|error| format!("mkfifo: {error}"))?;
    if !status.success() { return Err("mkfifo failed".into()); }
    let executable = env::current_exe().map_err(|error| format!("current executable: {error}"))?;
    let compressor_script = format!("exec {} -p 4 -c < {} > {}", quote(pigz)?, quote(&fifo)?, quote(&output)?);
    let mut compressor = Command::new("sh").args(["-c", &compressor_script])
        .stdout(Stdio::null()).stderr(Stdio::from(File::create(out_dir.join("pigz.stderr")).map_err(|e| e.to_string())?))
        .spawn().map_err(|error| format!("spawn pigz shell: {error}"))?;
    let mut producer = Command::new(&executable).args(["--produce", fifo.to_str().ok_or("FIFO path")?])
        .stdout(Stdio::null()).stderr(Stdio::from(File::create(out_dir.join("producer.stderr")).map_err(|e| e.to_string())?))
        .spawn().map_err(|error| format!("spawn producer: {error}"))?;
    let start = Instant::now(); let mut producer_status = None; let mut compressor_status = None; let mut failure = None;
    while start.elapsed() < TIMEOUT {
        if disk_free(out_dir)? < DISK_FLOOR_BYTES { failure = Some("disk floor fell below 10 GiB".to_string()); break; }
        if output.exists() && fs::metadata(&output).map_err(|e| e.to_string())?.len() > OUTPUT_CAP_BYTES { failure = Some("compressed output exceeded 100 MiB cap".into()); break; }
        if producer_status.is_none() { producer_status = producer.try_wait().map_err(|e| format!("wait producer: {e}"))?; }
        if compressor_status.is_none() { compressor_status = compressor.try_wait().map_err(|e| format!("wait compressor: {e}"))?; }
        if compressor_status.is_some() && producer_status.is_none() { failure = Some("pigz exited before producer".into()); break; }
        if producer_status.is_some() && compressor_status.is_some() { break; }
        thread::sleep(Duration::from_millis(100));
    }
    if producer_status.is_none() || compressor_status.is_none() { failure.get_or_insert_with(|| "probe exceeded 120 s".into()); }
    if failure.is_some() { if producer_status.is_none() { producer_status = kill_reap(&mut producer); } if compressor_status.is_none() { compressor_status = kill_reap(&mut compressor); } }
    else { producer_status = producer_status.or_else(|| producer.wait().ok()); compressor_status = compressor_status.or_else(|| compressor.wait().ok()); }
    let raw_bytes = fs::metadata(&output).ok().map(|meta| meta.len()).unwrap_or(0);
    let raw_hash = if output.exists() { Some(sha256(&output)?) } else { None };
    let mut verify_status = None; let mut verify_detail = String::from("not_run");
    if failure.is_none() && producer_status.is_some_and(|s| s.success()) && compressor_status.is_some_and(|s| s.success()) && raw_bytes <= OUTPUT_CAP_BYTES {
        let mut decompressor = Command::new(pigz).args(["-dc", output.to_str().ok_or("output path")?]).stdout(Stdio::piped()).stderr(Stdio::from(File::create(out_dir.join("verify-pigz.stderr")).map_err(|e| e.to_string())?)).spawn().map_err(|e| format!("spawn verify pigz: {e}"))?;
        let stdout = decompressor.stdout.take().ok_or("verify pipe missing")?;
        let mut verifier = Command::new(&executable).arg("--verify").stdin(stdout).stdout(Stdio::null()).stderr(Stdio::from(File::create(out_dir.join("verify.stderr")).map_err(|e| e.to_string())?)).spawn().map_err(|e| format!("spawn verifier: {e}"))?;
        let v = verifier.wait().map_err(|e| format!("wait verifier: {e}"))?; let d = decompressor.wait().map_err(|e| format!("wait verify pigz: {e}"))?;
        verify_status = Some(v.success() && d.success()); verify_detail = format!("verifier_rc={} decompressor_rc={}", v.code().unwrap_or(-1), d.code().unwrap_or(-1));
    }
    let expected_bytes = HEADER.len() as u64 + BLOCKS * (16 + PAYLOAD_BYTES);
    let ok = failure.is_none() && producer_status.is_some_and(|s| s.success()) && compressor_status.is_some_and(|s| s.success()) && expected_bytes > 4 * 1024 * 1024 * 1024 && raw_bytes <= OUTPUT_CAP_BYTES && verify_status == Some(true);
    let receipt = format!("{{\n  \"status\": \"{}\",\n  \"synthetic_only\": true,\n  \"producer_exit\": {},\n  \"pigz_exit\": {},\n  \"compressed_bytes\": {},\n  \"compressed_sha256\": {},\n  \"decompressed_expected_bytes\": {},\n  \"verify\": {},\n  \"verify_detail\": {:?},\n  \"elapsed_s\": {:.3},\n  \"failure\": {:?},\n  \"limits\": {{\"compressed_cap_bytes\": {}, \"disk_floor_bytes\": {}, \"timeout_s\": {}}},\n  \"interpretation\": \"Success bounds this FIFO/pigz transport path only; failure does not identify the LL05 stall cause.\"\n}}", if ok { "PASS_TRANSPORT_ONLY" } else { "FAILED_TRANSPORT_PROBE" }, producer_status.and_then(|s| s.code()).unwrap_or(-1), compressor_status.and_then(|s| s.code()).unwrap_or(-1), raw_bytes, raw_hash.map_or_else(|| "null".into(), |v| format!("\"{v}\"")), HEADER.len() as u64 + BLOCKS * (16 + PAYLOAD_BYTES), verify_status.unwrap_or(false), verify_detail, start.elapsed().as_secs_f64(), failure, OUTPUT_CAP_BYTES, DISK_FLOOR_BYTES, TIMEOUT.as_secs());
    write_receipt(&out_dir.join("receipt.json"), &receipt)?;
    let _ = fs::remove_file(&fifo);
    if ok { Ok(()) } else { Err("synthetic FIFO export probe failed".into()) }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let result = match args.as_slice() {
        [_, mode, fifo] if mode == "--produce" => produce(Path::new(fifo)),
        [_, mode] if mode == "--verify" => verify(io::stdin()),
        [_, out, pigz] => run(Path::new(out), Path::new(pigz)),
        _ => Err("usage: probe OUT_DIR PIGZ | --produce FIFO | --verify".into()),
    };
    if let Err(error) = result { eprintln!("FIFO_EXPORT_PROBE_ERROR {error}"); std::process::exit(1); }
}
