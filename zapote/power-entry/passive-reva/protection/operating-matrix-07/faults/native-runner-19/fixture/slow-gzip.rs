//! TEST_ONLY compressor fixture: consume FIFO input, delay the footer, gzip it.
use std::{io::{Read, Write}, process::{Command, Stdio}, thread, time::Duration};

fn main() {
    let mut input = Vec::new();
    std::io::stdin().read_to_end(&mut input).expect("read raw FIFO");
    thread::sleep(Duration::from_secs(2));
    let mut gzip = Command::new("gzip")
        .args(["-c"])
        .stdin(Stdio::piped())
        .stdout(Stdio::inherit())
        .spawn()
        .expect("spawn gzip");
    gzip.stdin.take().expect("gzip stdin").write_all(&input).expect("write gzip input");
    let status = gzip.wait().expect("wait gzip");
    assert!(status.success(), "gzip failed: {status}");
}
