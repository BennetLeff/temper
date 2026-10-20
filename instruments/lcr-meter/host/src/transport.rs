//! POSIX serial transport for macOS and Linux USB CDC ports.
use crate::{
    crc32, decode_payload, frequency_hz, payload_len, Record, Result, Setup, DEFAULT_COUNT,
    HARDWARE_REVISION, MAX_COUNT, PROTOCOL_VERSION,
};
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::time::{Duration, Instant};

pub struct Device {
    port: File,
    pub setup: Setup,
}
fn ioerr(e: std::io::Error) -> String {
    e.to_string()
}
fn identity(line: &str, range: u32, fixture: &str) -> Result<Setup> {
    let words: Vec<_> = line.split_whitespace().collect();
    if words.len() == 9 && words[0] == "INFO" && words[1] == "1" {
        return Err(format!("device firmware speaks protocol 1 (undersampled packed 16-bit samples); flash protocol-{PROTOCOL_VERSION} boxcar firmware: {line}"));
    }
    if words.len() != 9
        || words[0] != "INFO"
        || words[1] != PROTOCOL_VERSION.to_string()
        || words[2] != HARDWARE_REVISION
        || words[6] != "120"
        || words[7] != MAX_COUNT.to_string()
        || !["PASS", "FAIL"].contains(&words[8])
    {
        return Err(format!("unexpected device identity: {line}"));
    }
    let setup = Setup {
        revision: words[2].into(),
        unit_id: words[3].into(),
        fixture: fixture.into(),
        range_ohm: range,
        system_clock_hz: words[4].parse().map_err(|_| "bad system clock")?,
        dds_clock_hz: words[5].parse().map_err(|_| "bad DDS clock")?,
    };
    setup.validate()?;
    Ok(setup)
}
fn ready(file: &File, events: i16) -> Result<()> {
    let mut pfd = libc::pollfd {
        fd: file.as_raw_fd(),
        events,
        revents: 0,
    };
    // SAFETY: pfd is initialized and points to one writable pollfd.
    let n = unsafe { libc::poll(&mut pfd, 1, 6000) };
    if n < 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    if n == 0 {
        return Err("USB CDC timeout".into());
    }
    if pfd.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {
        return Err("USB CDC disconnected".into());
    }
    Ok(())
}
impl Device {
    pub fn open(path: &str, range: u32, fixture: &str) -> Result<Self> {
        let port = OpenOptions::new()
            .read(true)
            .write(true)
            .open(path)
            .map_err(ioerr)?;
        let fd = port.as_raw_fd();
        // SAFETY: termios is POD, tcgetattr initializes it; this fd belongs to port.
        let mut term: libc::termios = unsafe { std::mem::zeroed() };
        if unsafe { libc::tcgetattr(fd, &mut term) } != 0 {
            return Err("port is not a POSIX serial device".into());
        }
        // SAFETY: term is a valid initialized termios and remains alive for these calls.
        unsafe {
            libc::cfmakeraw(&mut term);
            libc::cfsetispeed(&mut term, libc::B115200);
            libc::cfsetospeed(&mut term, libc::B115200);
        }
        term.c_cflag |= libc::CLOCAL | libc::CREAD;
        term.c_cc[libc::VMIN] = 0;
        term.c_cc[libc::VTIME] = 0;
        if unsafe { libc::tcsetattr(fd, libc::TCSANOW, &term) } != 0 {
            return Err("cannot set serial mode".into());
        }
        // Assert DTR so the Pico SDK CDC backend considers this an active console.
        let modem = libc::TIOCM_DTR | libc::TIOCM_RTS;
        unsafe {
            libc::ioctl(fd, libc::TIOCMBIS, &modem);
        }
        std::thread::sleep(Duration::from_millis(100));
        unsafe {
            libc::tcflush(fd, libc::TCIOFLUSH);
        }
        let mut d = Self {
            port,
            setup: Setup {
                revision: HARDWARE_REVISION.into(),
                unit_id: String::new(),
                fixture: fixture.into(),
                range_ohm: range,
                system_clock_hz: 0,
                dds_clock_hz: 0,
            },
        };
        d.command("INFO")?;
        let line = d.line()?;
        d.setup = identity(&line, range, fixture)?;
        // Keep a failed instrument accessible to SELFTEST, but captures also check firmware.
        Ok(d)
    }
    pub fn command(&mut self, line: &str) -> Result<()> {
        ready(&self.port, libc::POLLOUT)?;
        self.port
            .write_all(format!("{line}\n").as_bytes())
            .map_err(ioerr)?;
        self.port.flush().map_err(ioerr)
    }
    pub fn line(&mut self) -> Result<String> {
        let mut bytes = Vec::new();
        let start = Instant::now();
        loop {
            if start.elapsed() > Duration::from_secs(8) {
                return Err("line deadline exceeded".into());
            }
            ready(&self.port, libc::POLLIN)?;
            let mut byte = [0];
            if self.port.read(&mut byte).map_err(ioerr)? == 0 {
                continue;
            }
            if byte[0] == b'\n' {
                break;
            }
            if byte[0] != b'\r' {
                bytes.push(byte[0]);
            }
            if bytes.len() > 256 {
                return Err("oversized protocol line".into());
            }
        }
        String::from_utf8(bytes).map_err(|_| "non-UTF8 protocol line".into())
    }
    pub fn selftest(&mut self) -> Result<()> {
        self.command("SELFTEST")?;
        let line = self.line()?;
        if line != "SELFTEST PASS" {
            return Err(format!("ADC link self-test failed: {line}"));
        }
        Ok(())
    }
    pub fn capture(&mut self, word: u32, decimation: u32, source_enabled: bool) -> Result<Record> {
        if !frequency_hz(word).is_finite() {
            return Err("bad frequency word".into());
        }
        let command = if source_enabled { "CAPTURE" } else { "NOISE" };
        let response = if source_enabled { "DATA" } else { "NOISE" };
        self.command(&format!("{command} {word} {decimation} {DEFAULT_COUNT}"))?;
        let line = self.line()?;
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != 6
            || fields[0] != response
            || fields[1] != PROTOCOL_VERSION.to_string()
            || fields[2] != word.to_string()
            || fields[3] != decimation.to_string()
            || fields[4] != DEFAULT_COUNT.to_string()
        {
            return Err(format!("capture failed: {line}"));
        }
        let checksum: u32 = fields[5].parse().map_err(|_| "bad CRC header")?;
        let mut bytes = vec![0u8; payload_len(DEFAULT_COUNT)];
        let mut offset = 0;
        let started = Instant::now();
        while offset < bytes.len() {
            if started.elapsed() > Duration::from_secs(10) {
                return Err("payload deadline exceeded".into());
            }
            ready(&self.port, libc::POLLIN)?;
            let n = self.port.read(&mut bytes[offset..]).map_err(ioerr)?;
            offset += n;
        }
        if !self.line()?.is_empty() || self.line()? != "END" {
            return Err("missing capture terminator".into());
        }
        if crc32(&bytes) != checksum {
            return Err("USB payload CRC mismatch".into());
        }
        let (raw_min, raw_max, sums) = decode_payload(&bytes)?;
        let record = Record {
            protocol: PROTOCOL_VERSION,
            source_enabled,
            tuning_word: word,
            decimation,
            raw_min,
            raw_max,
            sums,
            transport_crc32: checksum,
            source_off: None,
            source_off_check: None,
            allowed_hazards: Vec::new(),
        };
        record.validate()?;
        Ok(record)
    }
}
impl Drop for Device {
    fn drop(&mut self) {
        let _ = self.port.write_all(b"OFF\n");
    }
}

#[cfg(test)]
mod tests {
    use super::identity;
    #[test]
    fn only_fixed_local_compensation_identity_is_accepted() {
        let line = "INFO 2 C-local100p device 120000000 24000000 120 16384 PASS";
        assert!(identity(line, 100, "fixture").is_ok());
        for old in ["A", "B", "C"] {
            assert!(identity(
                &line.replace(" C-local100p ", &format!(" {old} ")),
                100,
                "fixture"
            )
            .is_err());
        }
        assert!(identity(&line.replace("PASS", "FAIL"), 100, "fixture").is_ok());
        assert!(identity(&line.replace("PASS", "UNKNOWN"), 100, "fixture").is_err());
    }
    #[test]
    fn protocol_one_firmware_is_rejected_by_name() {
        let v1 = "INFO 1 C-local100p device 120000000 24000000 120 32768 PASS";
        let error = identity(v1, 100, "fixture").unwrap_err();
        assert!(error.contains("protocol 1"), "{error}");
        // A v2 banner with the old v1 record limit is not accepted either.
        let mixed = "INFO 2 C-local100p device 120000000 24000000 120 32768 PASS";
        assert!(identity(mixed, 100, "fixture").is_err());
        assert!(identity(&v1.replace("INFO 1", "INFO 3"), 100, "fixture").is_err());
    }
}
