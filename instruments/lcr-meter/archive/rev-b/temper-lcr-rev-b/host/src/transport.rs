//! POSIX serial transport for macOS and Linux USB CDC ports.
use crate::{crc32, frequency_hz, Record, Result, Setup, DEFAULT_COUNT};
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
                revision: "B".into(),
                unit_id: String::new(),
                fixture: fixture.into(),
                range_ohm: range,
                system_clock_hz: 0,
                dds_clock_hz: 0,
            },
        };
        d.command("INFO")?;
        let line = d.line()?;
        let words: Vec<_> = line.split_whitespace().collect();
        if words.len() != 9
            || words[0] != "INFO"
            || words[1] != "1"
            || words[2] != "B"
            || words[6] != "120"
            || words[7] != "32768"
        {
            return Err(format!("unexpected device identity: {line}"));
        }
        d.setup.unit_id = words[3].into();
        d.setup.system_clock_hz = words[4].parse().map_err(|_| "bad system clock")?;
        d.setup.dds_clock_hz = words[5].parse().map_err(|_| "bad DDS clock")?;
        d.setup.validate()?;
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
    pub fn capture(&mut self, word: u32, divider: u32, source_enabled: bool) -> Result<Record> {
        if !frequency_hz(word).is_finite() {
            return Err("bad frequency word".into());
        }
        let command = if source_enabled { "CAPTURE" } else { "NOISE" };
        let response = if source_enabled { "DATA" } else { "NOISE" };
        self.command(&format!("{command} {word} {divider} {DEFAULT_COUNT}"))?;
        let line = self.line()?;
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != 6
            || fields[0] != response
            || fields[1] != "1"
            || fields[2] != word.to_string()
            || fields[3] != divider.to_string()
            || fields[4] != DEFAULT_COUNT.to_string()
        {
            return Err(format!("capture failed: {line}"));
        }
        let checksum: u32 = fields[5].parse().map_err(|_| "bad CRC header")?;
        let mut bytes = vec![0u8; DEFAULT_COUNT * 4];
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
        let packed_samples = bytes
            .chunks_exact(4)
            .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
            .collect();
        let record = Record {
            source_enabled,
            tuning_word: word,
            sample_divider: divider,
            packed_samples,
            transport_crc32: checksum,
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
