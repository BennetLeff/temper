//! POSIX serial transport for macOS and Linux USB CDC ports.
use crate::rev_e::{self, InfoE, Protocol, RecordE, SetupE, SourceE};
use crate::{
    crc32, decode_payload, frequency_hz, payload_len, rails_from_line, Rails, Record, Result,
    Setup, DEFAULT_COUNT, HARDWARE_REVISION, MAX_COUNT, PROTOCOL_VERSION,
};
use serde::Serialize;
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
    ready_within(file, events, 6000)
}
fn ready_within(file: &File, events: i16, milliseconds: i32) -> Result<()> {
    let mut pfd = libc::pollfd {
        fd: file.as_raw_fd(),
        events,
        revents: 0,
    };
    // SAFETY: pfd is initialized and points to one writable pollfd.
    let n = unsafe { libc::poll(&mut pfd, 1, milliseconds) };
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
/// Opens a POSIX serial port in raw mode, asserts DTR/RTS and flushes stale input.
fn open_port(path: &str) -> Result<File> {
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
    Ok(port)
}
fn send_line(port: &mut File, line: &str) -> Result<()> {
    ready(port, libc::POLLOUT)?;
    port.write_all(format!("{line}\n").as_bytes())
        .map_err(ioerr)?;
    port.flush().map_err(ioerr)
}
fn read_line(port: &mut File, deadline: Duration, poll_ms: i32) -> Result<String> {
    let mut bytes = Vec::new();
    let start = Instant::now();
    loop {
        if start.elapsed() > deadline {
            return Err("line deadline exceeded".into());
        }
        ready_within(port, libc::POLLIN, poll_ms)?;
        let mut byte = [0];
        if port.read(&mut byte).map_err(ioerr)? == 0 {
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

/// The board that answered `INFO`: Rev D (protocol 2) or Rev E (protocol 3).
pub enum Board {
    D(Device),
    E(DeviceE),
}
impl Board {
    /// Opens the port, asks `INFO` and selects the protocol from the reply. `range` is the
    /// range the caller states for Rev D (software cannot sense its jumpers); on Rev E it is the
    /// relay the host will command and is recorded in the setup.
    pub fn open(path: &str, range: u32, fixture: &str) -> Result<Self> {
        let mut port = open_port(path)?;
        send_line(&mut port, "INFO")?;
        let line = read_line(&mut port, Duration::from_secs(8), 6000)?;
        match rev_e::detect_protocol(&line)? {
            Protocol::D => Ok(Board::D(Device::from_info_line(
                port, &line, range, fixture,
            )?)),
            Protocol::E => Ok(Board::E(DeviceE::from_info_line(
                port, &line, range, fixture,
            )?)),
        }
    }
}

impl Device {
    pub fn open(path: &str, range: u32, fixture: &str) -> Result<Self> {
        let mut port = open_port(path)?;
        send_line(&mut port, "INFO")?;
        let line = read_line(&mut port, Duration::from_secs(8), 6000)?;
        if rev_e::detect_protocol(&line)? == Protocol::E {
            return Err(format!(
                "the board is a Rev E ({}) with protocol 3, not Rev D: {line}",
                rev_e::HARDWARE_REVISION_E
            ));
        }
        Self::from_info_line(port, &line, range, fixture)
    }
    fn from_info_line(port: File, line: &str, range: u32, fixture: &str) -> Result<Self> {
        // Keep a failed instrument accessible to SELFTEST, but captures also check firmware.
        Ok(Self {
            port,
            setup: identity(line, range, fixture)?,
        })
    }
    pub fn command(&mut self, line: &str) -> Result<()> {
        send_line(&mut self.port, line)
    }
    pub fn line(&mut self) -> Result<String> {
        read_line(&mut self.port, Duration::from_secs(8), 6000)
    }
    pub fn selftest(&mut self) -> Result<()> {
        self.command("SELFTEST")?;
        let line = self.line()?;
        if line != "SELFTEST PASS" {
            return Err(format!("ADC link self-test failed: {line}"));
        }
        Ok(())
    }
    /// Reboots the RP2040 into its ROM USB bootloader (RPI-RP2 drive) for a UF2 update.
    pub fn boot(&mut self) -> Result<()> {
        self.command("BOOT")?;
        let line = self.line()?;
        if line != "OK" {
            return Err(format!("BOOT refused: {line}"));
        }
        Ok(())
    }
    /// Reads the +-12 V monitors and die temperature; an out-of-window rail is an error.
    pub fn rails(&mut self) -> Result<Rails> {
        self.command("RAILS")?;
        let rails = rails_from_line(&self.line()?)?;
        if !rails.pass {
            return Err(format!(
                "analog rail out of window: +12 V reads {:.2} V, -12 V reads {:.2} V; check the supply before measuring",
                rails.plus12_v, rails.minus12_v
            ));
        }
        Ok(rails)
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
/// `CODEC` reply: the codec's status registers, decimal.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CodecStatus {
    pub dev_sts0: u8,
    pub dev_sts1: u8,
    pub clk_det_sts0: u8,
    pub clk_err_sts0: u8,
    pub clk_err_sts1: u8,
}
pub fn parse_codec(line: &str) -> Result<CodecStatus> {
    let w: Vec<_> = line.split_whitespace().collect();
    let values: Option<Vec<u8>> = w.iter().skip(1).map(|x| x.parse().ok()).collect();
    match (w.first(), values) {
        (Some(&"CODEC"), Some(v)) if v.len() == 5 => Ok(CodecStatus {
            dev_sts0: v[0],
            dev_sts1: v[1],
            clk_det_sts0: v[2],
            clk_err_sts0: v[3],
            clk_err_sts1: v[4],
        }),
        _ => Err(format!("unexpected CODEC reply: {line}")),
    }
}
pub fn parse_reg(line: &str, register: u32) -> Result<u8> {
    let w: Vec<_> = line.split_whitespace().collect();
    if w.len() == 3 && w[0] == "REG" && w[1] == register.to_string() {
        if let Ok(v) = w[2].parse() {
            return Ok(v);
        }
    }
    Err(format!("unexpected REG reply: {line}"))
}

/// Protocol-3 client for the Rev E board (`E-codec`).
pub struct DeviceE {
    port: File,
    pub setup: SetupE,
    pub info: InfoE,
    /// Frames per period of the waveform the device is playing, tracked from commands.
    period: u32,
}
impl DeviceE {
    fn from_info_line(port: File, line: &str, range: u32, fixture: &str) -> Result<Self> {
        let info = rev_e::parse_info_e(line)?;
        let setup = SetupE::from_info(&info, range, fixture)?;
        Ok(Self {
            port,
            period: info.period,
            setup,
            info,
        })
    }
    pub fn command(&mut self, line: &str) -> Result<()> {
        send_line(&mut self.port, line)
    }
    pub fn line(&mut self) -> Result<String> {
        read_line(&mut self.port, Duration::from_secs(8), 6000)
    }
    fn line_within(&mut self, seconds: f64) -> Result<String> {
        let deadline = Duration::from_secs_f64(seconds);
        read_line(
            &mut self.port,
            deadline,
            deadline.as_millis().min(i32::MAX as u128) as i32,
        )
    }
    /// One command, one single-line reply; an `ERR` reply is an error.
    fn reply(&mut self, command: &str) -> Result<String> {
        self.command(command)?;
        let line = self.line()?;
        if line.starts_with("ERR") {
            return Err(format!(
                "{}: device replied {line}",
                command.split(' ').next().unwrap_or("")
            ));
        }
        Ok(line)
    }
    fn ok(&mut self, command: &str) -> Result<()> {
        let line = self.reply(command)?;
        if line != "OK" {
            return Err(format!("{command}: expected OK, device replied {line}"));
        }
        Ok(())
    }
    /// Frames per period of the waveform now playing.
    pub fn period(&self) -> u32 {
        self.period
    }
    /// Asks `INFO` again (range, waveform and self-test status).
    pub fn refresh_info(&mut self) -> Result<InfoE> {
        let line = self.reply("INFO")?;
        self.info = rev_e::parse_info_e(&line)?;
        self.period = self.info.period;
        Ok(self.info.clone())
    }
    pub fn selftest(&mut self) -> Result<()> {
        let line = self.reply("SELFTEST")?;
        if line != "SELFTEST PASS" {
            return Err(format!("codec link self-test failed: {line}"));
        }
        Ok(())
    }
    /// Switches the range relay (the firmware silences the source around it and restores it).
    pub fn range(&mut self, ohm: u32) -> Result<()> {
        if ![100, 5000, 100_000].contains(&ohm) {
            return Err("range must be 100, 5000 or 100000 ohms".into());
        }
        self.ok(&format!("RANGE {ohm}"))?;
        self.setup.range_ohm = ohm;
        self.setup.validate()
    }
    /// Silences the source; the stream keeps running.
    pub fn off(&mut self) -> Result<()> {
        self.ok("OFF")?;
        self.period = rev_e::MIN_PERIOD;
        Ok(())
    }
    /// Reads the +-12 V monitors and die temperature; an out-of-window rail is an error.
    pub fn rails(&mut self) -> Result<Rails> {
        let line = self.reply("RAILS")?;
        let rails = rails_from_line(&line)?;
        if !rails.pass {
            return Err(format!(
                "analog rail out of window: +12 V reads {:.2} V, -12 V reads {:.2} V; check the supply before measuring",
                rails.plus12_v, rails.minus12_v
            ));
        }
        Ok(rails)
    }
    pub fn codec(&mut self) -> Result<CodecStatus> {
        let line = self.reply("CODEC")?;
        if line.contains("ERR") {
            return Err(format!("CODEC: device replied {line}"));
        }
        parse_codec(&line)
    }
    /// Reads page-0 codec register `register` (0-127), read-only.
    pub fn reg(&mut self, register: u32) -> Result<u8> {
        if register > 127 {
            return Err("codec register must be 0..127".into());
        }
        let line = self.reply(&format!("REG {register}"))?;
        parse_reg(&line, register)
    }
    /// Reboots the RP2040 into its ROM USB bootloader (RPI-RP2 drive) for a UF2 update.
    pub fn boot(&mut self) -> Result<()> {
        let line = self.reply("BOOT")?;
        if line != "OK" {
            return Err(format!("BOOT refused: {line}"));
        }
        Ok(())
    }
    pub fn tone(&mut self, cycles: u32, period: u32, mv: u32) -> Result<()> {
        rev_e::check_tone(cycles, period, mv)?;
        self.ok(&format!("TONE {cycles} {period} {mv}"))?;
        self.period = period;
        Ok(())
    }
    /// Plays `hz` exactly: the smallest PERIOD that represents it. Returns (CYCLES, PERIOD).
    pub fn tone_hz(&mut self, hz: f64, mv: u32) -> Result<(u32, u32)> {
        let (cycles, period) = rev_e::tone_for_hz(hz)?;
        self.tone(cycles, period, mv)?;
        Ok((cycles, period))
    }
    /// Uploads one period of DAC words (any waveform, multitone included).
    pub fn wave(&mut self, words: &[i32]) -> Result<()> {
        let (bytes, crc) = rev_e::encode_wave(words)?;
        self.command(&format!("WAVE {} {crc}", words.len()))?;
        ready(&self.port, libc::POLLOUT)?;
        self.port.write_all(&bytes).map_err(ioerr)?;
        self.port.flush().map_err(ioerr)?;
        let line = self.line()?;
        if line != "OK" {
            return Err(format!("WAVE: device replied {line}"));
        }
        self.period = words.len() as u32;
        Ok(())
    }
    fn payload(&mut self, length: usize) -> Result<Vec<u8>> {
        let mut bytes = vec![0u8; length];
        let mut offset = 0;
        let started = Instant::now();
        while offset < bytes.len() {
            if started.elapsed() > Duration::from_secs(10) {
                return Err("payload deadline exceeded".into());
            }
            ready(&self.port, libc::POLLIN)?;
            offset += self.port.read(&mut bytes[offset..]).map_err(ioerr)?;
        }
        if !self.line()?.is_empty() || self.line()? != "END" {
            return Err("missing capture terminator".into());
        }
        Ok(bytes)
    }
    /// `CAPTURE skip periods`: the decoded payload and the device's CRC of it.
    pub fn capture(&mut self, skip: u32, periods: u32) -> Result<(rev_e::DataPayload, u32)> {
        self.data_capture(&format!("CAPTURE {skip} {periods}"), skip, periods, 0.0)
    }
    /// `REFCAPTURE range skip periods`: as [`DeviceE::capture`], of the internal 1 kOhm
    /// reference on `range`. The firmware closes K4 with `range`, captures, then RESETs and
    /// re-selects the range that was selected before, so the setup's range is unchanged.
    pub fn reference_capture(
        &mut self,
        range: u32,
        skip: u32,
        periods: u32,
    ) -> Result<(rev_e::DataPayload, u32)> {
        if ![100, 5000, 100_000].contains(&range) {
            return Err("range must be 100, 5000 or 100000 ohms".into());
        }
        // Two relay sequences (silence, 5 ms, three 20 ms pulses at most, 10 ms, restore).
        self.data_capture(
            &format!("REFCAPTURE {range} {skip} {periods}"),
            skip,
            periods,
            0.5,
        )
    }
    fn data_capture(
        &mut self,
        command: &str,
        skip: u32,
        periods: u32,
        extra_seconds: f64,
    ) -> Result<(rev_e::DataPayload, u32)> {
        rev_e::check_capture(skip, periods, self.period)?;
        self.command(command)?;
        let seconds = rev_e::capture_seconds(skip, periods, self.period) + extra_seconds;
        let line = self.line_within(seconds + 10.0)?;
        let (period, echoed, crc) = rev_e::parse_reply_header(&line, "DATA")?;
        if period != self.period || echoed != periods {
            return Err(format!("capture reply does not match the request: {line}"));
        }
        let bytes = self.payload(rev_e::data_payload_len(period as usize))?;
        rev_e::verify_crc(&bytes, crc)?;
        let payload = rev_e::decode_data(&bytes, period as usize)?;
        rev_e::check_header(payload.0)?;
        Ok((payload, crc))
    }
    /// `RAW count`: consecutive frames, int32 per channel.
    pub fn raw(&mut self, count: u32) -> Result<rev_e::RawPayload> {
        if count == 0 || count > rev_e::RAW_MAX_FRAMES {
            return Err(format!("RAW count must be 1..{}", rev_e::RAW_MAX_FRAMES));
        }
        self.command(&format!("RAW {count}"))?;
        let line = self.line_within(10.0)?;
        let (echoed, _, crc) = rev_e::parse_reply_header(&line, "RAW")?;
        if echoed != count {
            return Err(format!("RAW reply does not match the request: {line}"));
        }
        let bytes = self.payload(rev_e::raw_payload_len(count as usize))?;
        rev_e::verify_crc(&bytes, crc)?;
        let payload = rev_e::decode_raw(&bytes, count as usize)?;
        rev_e::check_header(payload.0)?;
        Ok(payload)
    }
    /// Plays `hz` at `mv` and captures it: SKIP and PERIODS default to the settling and length
    /// rules in [`rev_e`]. Returns the record with its CYCLES bin.
    pub fn capture_tone(
        &mut self,
        hz: f64,
        mv: u32,
        skip: Option<u32>,
        periods: Option<u32>,
    ) -> Result<RecordE> {
        let (cycles, period) = self.tone_hz(hz, mv)?;
        let skip = match skip {
            Some(s) => s,
            None => rev_e::default_skip_periods(self.setup.range_ohm, hz, period)?,
        };
        let periods = periods.unwrap_or_else(|| rev_e::default_periods(period));
        let (payload, crc) = self.capture(skip, periods)?;
        let record = RecordE::from_capture(
            SourceE::Tone { cycles, mv },
            vec![cycles],
            skip,
            periods,
            payload,
            crc,
        );
        record.validate()?;
        Ok(record)
    }
    /// The source-off check of a tone record just captured with [`DeviceE::capture_tone`]:
    /// uploads `PERIOD` zero words, captures with the record's SKIP and PERIODS, and judges the
    /// DFT line at its CYCLES bin against the record's own. `OFF` would not do: it plays
    /// PERIOD 16, whose bins cannot see the tone bin, and it would miss board activity locked
    /// to the waveform period. The same SKIP covers the step from tone to zero, which settles
    /// through the same filters, TIA and DUT as the step from silence to tone. Leaves the zero
    /// waveform playing (silent): the caller sets the next tone or sends `OFF`.
    pub fn source_off_check(&mut self, on: &RecordE) -> Result<rev_e::SourceOffCheckE> {
        let SourceE::Tone { cycles, .. } = on.source else {
            return Err("source-off check needs a tone record".into());
        };
        self.wave(&vec![0; on.period as usize])?;
        let (payload, crc) = self.capture(on.skip, on.periods)?;
        let off = RecordE::from_capture(
            SourceE::Wave,
            vec![cycles],
            on.skip,
            on.periods,
            payload,
            crc,
        );
        rev_e::source_off_check_e(on, &off)
    }
    /// Plays `hz` at `mv` and captures the internal reference on `range` (`REFCAPTURE`): the
    /// same defaults as [`DeviceE::capture_tone`], settling for `range`.
    pub fn reference_tone(
        &mut self,
        range: u32,
        hz: f64,
        mv: u32,
        skip: Option<u32>,
        periods: Option<u32>,
    ) -> Result<RecordE> {
        let (cycles, period) = self.tone_hz(hz, mv)?;
        let skip = match skip {
            Some(s) => s,
            None => rev_e::default_skip_periods(range, hz, period)?,
        };
        let periods = periods.unwrap_or_else(|| rev_e::default_periods(period));
        let (payload, crc) = self.reference_capture(range, skip, periods)?;
        let record = RecordE::from_capture(
            SourceE::Tone { cycles, mv },
            vec![cycles],
            skip,
            periods,
            payload,
            crc,
        );
        record.validate()?;
        Ok(record)
    }
    /// Uploads `words` and captures it, analysing `bins` (for example every bin of a multitone).
    pub fn capture_wave(
        &mut self,
        words: &[i32],
        bins: &[u32],
        skip: Option<u32>,
        periods: Option<u32>,
    ) -> Result<RecordE> {
        let period = words.len() as u32;
        rev_e::check_bins(bins, period)?;
        self.wave(words)?;
        let slowest = bins.iter().min().copied().unwrap_or(1);
        let skip = match skip {
            Some(s) => s,
            None => rev_e::default_skip_periods(
                self.setup.range_ohm,
                rev_e::tone_frequency_hz(slowest, period),
                period,
            )?,
        };
        let periods = periods.unwrap_or_else(|| rev_e::default_periods(period));
        let (payload, crc) = self.capture(skip, periods)?;
        let record =
            RecordE::from_capture(SourceE::Wave, bins.to_vec(), skip, periods, payload, crc);
        record.validate()?;
        Ok(record)
    }
}
impl Drop for DeviceE {
    fn drop(&mut self) {
        let _ = self.port.write_all(b"OFF\n");
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
        let line = "INFO 2 D-riso22 device 120000000 24000000 120 16384 PASS";
        assert!(identity(line, 100, "fixture").is_ok());
        for old in ["A", "B", "C", "C-local100p"] {
            assert!(identity(
                &line.replace(" D-riso22 ", &format!(" {old} ")),
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
        let v1 = "INFO 1 D-riso22 device 120000000 24000000 120 32768 PASS";
        let error = identity(v1, 100, "fixture").unwrap_err();
        assert!(error.contains("protocol 1"), "{error}");
        // A v2 banner with the old v1 record limit is not accepted either.
        let mixed = "INFO 2 D-riso22 device 120000000 24000000 120 32768 PASS";
        assert!(identity(mixed, 100, "fixture").is_err());
        assert!(identity(&v1.replace("INFO 1", "INFO 3"), 100, "fixture").is_err());
    }
}
