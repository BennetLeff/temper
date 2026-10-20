//! MCP2221A HID framing (DS20005565, section 3) and AD5933 rev F register protocol.
use std::thread::sleep;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::{range_bounds, Complex, Point, Result, Setup, Sweep};

pub const VID: u16 = 0x04d8;
pub const PID: u16 = 0x00dd;
pub const ADDRESS: u8 = 0x0d;
const OPTIONS: u8 = 0x03; // D10:D9=01 (range 4), D8=1 (PGA x1), rev F tables 10/11.

pub trait ReportIo {
    fn exchange(&mut self, report: [u8; 64]) -> Result<[u8; 64]>;
}

#[cfg(feature = "usb")]
pub struct Usb {
    device: hidapi::HidDevice,
}
#[cfg(feature = "usb")]
impl Usb {
    pub fn list() -> Result<Vec<String>> {
        let api = hidapi::HidApi::new().map_err(|e| e.to_string())?;
        Ok(api
            .device_list()
            .filter(|d| d.vendor_id() == VID && d.product_id() == PID)
            .map(|d| {
                format!(
                    "serial={} interface={} path={}",
                    d.serial_number().unwrap_or("<none>"),
                    d.interface_number(),
                    d.path().to_string_lossy()
                )
            })
            .collect())
    }
    pub fn open(serial: Option<&str>) -> Result<Self> {
        let api = hidapi::HidApi::new().map_err(|e| e.to_string())?;
        let devices: Vec<_> = api
            .device_list()
            .filter(|d| {
                d.vendor_id() == VID
                    && d.product_id() == PID
                    && serial.is_none_or(|s| d.serial_number() == Some(s))
            })
            .collect();
        if devices.len() != 1 {
            return Err(format!(
                "expected one matching MCP2221A HID interface, found {}; use list/--serial",
                devices.len()
            ));
        }
        let device = devices[0].open_device(&api).map_err(|e| e.to_string())?;
        Ok(Self { device })
    }
}
#[cfg(feature = "usb")]
impl ReportIo for Usb {
    fn exchange(&mut self, report: [u8; 64]) -> Result<[u8; 64]> {
        let mut out = [0u8; 65];
        out[1..].copy_from_slice(&report);
        let written = self.device.write(&out).map_err(|e| e.to_string())?;
        if written != out.len() {
            return Err(format!("short HID write: {written}"));
        }
        let mut response = [0u8; 64];
        let read = self
            .device
            .read_timeout(&mut response, 1000)
            .map_err(|e| e.to_string())?;
        if read != 64 || response[0] != report[0] {
            return Err(format!(
                "short, timed-out, or mismatched HID reply to 0x{:02x}",
                report[0]
            ));
        }
        Ok(response)
    }
}

pub struct Mcp<T: ReportIo> {
    io: T,
}
impl<T: ReportIo> Mcp<T> {
    pub fn new(io: T) -> Self {
        Self { io }
    }
    fn command(&mut self, report: [u8; 64]) -> Result<[u8; 64]> {
        let r = self.io.exchange(report)?;
        if r[0] != report[0] || r[1] != 0 {
            return Err(format!(
                "MCP command 0x{:02x} failed: result=0x{:02x}, state=0x{:02x}",
                report[0], r[1], r[2]
            ));
        }
        Ok(r)
    }
    pub fn initialize(&mut self) -> Result<()> {
        let mut r = [0; 64];
        r[0] = 0x10;
        r[2] = 0x10;
        self.command(r)?;
        self.wait_idle()?;
        r = [0; 64];
        r[0] = 0x10;
        r[3] = 0x20;
        r[4] = 117; // 12MHz/(117+3)=100kHz.
        let reply = self.command(r)?;
        if reply[3] != 0x20 || reply[4] != 117 {
            return Err("MCP did not accept 100kHz I2C speed".into());
        }
        Ok(())
    }
    fn wait_idle(&mut self) -> Result<()> {
        let deadline = Instant::now() + Duration::from_millis(250);
        loop {
            let mut r = [0; 64];
            r[0] = 0x10;
            let r = self.command(r)?;
            // Linux's maintained MCP2221 driver checks this NACK latch even when
            // the engine has returned to idle (hid-mcp2221.c, status response).
            if r[20] & 0x40 != 0 {
                return Err(
                    "I2C address was not acknowledged; check analog power and wiring".into(),
                );
            }
            if r[8] == 0 {
                return Ok(());
            }
            if matches!(r[8], 0x12 | 0x23 | 0x25 | 0x44 | 0x62) {
                return Err(format!("I2C engine reported failure 0x{:02x}", r[8]));
            }
            if Instant::now() >= deadline {
                return Err(format!(
                    "I2C engine timeout (state 0x{:02x}); check address, power and pull-ups",
                    r[8]
                ));
            }
            sleep(Duration::from_millis(2));
        }
    }
    fn write(&mut self, bytes: &[u8]) -> Result<()> {
        if bytes.is_empty() || bytes.len() > 60 {
            return Err("I2C write must contain 1–60 bytes".into());
        }
        self.wait_idle()?;
        let mut r = [0; 64];
        r[0] = 0x90;
        r[1] = bytes.len() as u8;
        r[3] = ADDRESS << 1;
        r[4..4 + bytes.len()].copy_from_slice(bytes);
        self.command(r)?;
        self.wait_idle()
    }
    pub fn write_register(&mut self, register: u8, value: u8) -> Result<()> {
        self.write(&[register, value])
    }
    pub fn read_register(&mut self, register: u8) -> Result<u8> {
        // AD5933 rev F fig31: explicit address-pointer command then a stopped single-byte read.
        self.write(&[0xb0, register])?;
        let mut r = [0; 64];
        r[0] = 0x91;
        r[1] = 1;
        r[3] = (ADDRESS << 1) | 1;
        self.command(r)?;
        let deadline = Instant::now() + Duration::from_millis(250);
        loop {
            r = [0; 64];
            r[0] = 0x40;
            let reply = self.command(r)?;
            match reply[3] {
                1 if matches!(reply[2], 0x54 | 0x55) => {
                    let byte = reply[4];
                    self.wait_idle()?;
                    return Ok(byte);
                }
                0 if Instant::now() < deadline => sleep(Duration::from_millis(2)),
                n => {
                    return Err(format!(
                        "I2C read failed or timed out: bytes={n}, state=0x{:02x}",
                        reply[2]
                    ))
                }
            }
        }
    }
    fn write_word(&mut self, register: u8, word: u32, bytes: usize) -> Result<()> {
        for i in 0..bytes {
            self.write_register(register + i as u8, (word >> ((bytes - 1 - i) * 8)) as u8)?;
        }
        Ok(())
    }
    fn control(&mut self, mode: u8) -> Result<()> {
        self.write_register(0x80, mode | OPTIONS)
    }
    fn result(&mut self) -> Result<(Complex, u32)> {
        let deadline = Instant::now() + Duration::from_secs(2);
        while self.read_register(0x8f)? & 2 == 0 {
            if Instant::now() >= deadline {
                return Err("AD5933 DFT timed out".into());
            }
            sleep(Duration::from_millis(2));
        }
        let re = i16::from_be_bytes([self.read_register(0x94)?, self.read_register(0x95)?]);
        let im = i16::from_be_bytes([self.read_register(0x96)?, self.read_register(0x97)?]);
        Ok((
            normalize(re, im),
            i32::from(re)
                .unsigned_abs()
                .max(i32::from(im).unsigned_abs()),
        ))
    }
    pub fn capture(&mut self, setup: Setup, start: f64, stop: f64, count: usize) -> Result<Sweep> {
        setup.validate()?;
        let words = grid(&setup, start, stop, count)?;
        self.initialize()?;
        let outcome = self.capture_inner(setup, &words);
        // Try to leave excitation off on both success and ordinary errors. A disconnected USB
        // device cannot be commanded; USB suspend independently removes analog power on the PCB.
        let shutdown = self.control(0xa0);
        match (outcome, shutdown) {
            (Ok(s), Ok(())) => Ok(s),
            (Err(e), Ok(())) => Err(e),
            (Err(e), Err(stop)) => Err(format!(
                "{e}; power-down also failed: {stop}; unplug the meter"
            )),
            (Ok(_), Err(e)) => Err(format!("capture complete but power-down failed: {e}")),
        }
    }
    fn capture_inner(&mut self, setup: Setup, words: &[u32]) -> Result<Sweep> {
        self.control(0xb0)?;
        self.write_register(0x81, 0x18)?; // External clock + reset.
        self.write_register(0x81, 0x08)?;
        self.write_word(0x82, words[0], 3)?;
        self.write_word(
            0x85,
            if words.len() > 1 {
                words[1] - words[0]
            } else {
                0
            },
            3,
        )?;
        self.write_word(0x88, (words.len() - 1) as u32, 2)?;
        self.write_word(0x8a, u32::from(setup.settling_cycles), 2)?;
        self.control(0x10)?;
        // Allow >12 RC time constants for the 1uF / 47k||47k rebias path after standby.
        sleep(Duration::from_millis(300));
        self.control(0x20)?;
        let mut points = Vec::with_capacity(words.len());
        for (i, &word) in words.iter().enumerate() {
            if i > 0 {
                self.control(0x30)?;
            }
            let mut sum = Complex::default();
            let mut peak = 0;
            for j in 0..setup.averages {
                if j > 0 {
                    self.control(0x40)?;
                }
                let (v, p) = self.result()?;
                sum = sum + v;
                peak = peak.max(p);
            }
            points.push(Point {
                frequency_word: word,
                frequency_hz: word as f64 * setup.clock_hz as f64 / 536_870_912.0,
                raw: sum / Complex::new(f64::from(setup.averages), 0.0),
                peak_dft_component: peak,
            });
        }
        let captured_unix_seconds = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_secs();
        let sweep = Sweep {
            schema: "temper-lcr-raw-v1".into(),
            captured_unix_seconds,
            setup,
            points,
        };
        sweep.validate()?;
        Ok(sweep)
    }
}
/// Normalize the conjugated AD5933 DFT convention to standard electrical admittance.
/// Rev F pp19–20 defines Zphase=phase(raw DUT)-phase(raw resistor), including a -90deg capacitor.
pub fn normalize(re: i16, im: i16) -> Complex {
    Complex::new(f64::from(re), -f64::from(im))
}
pub fn frequency_word(hz: f64, clock: u32) -> Result<u32> {
    let word = (hz * 536_870_912.0 / f64::from(clock)).floor();
    if !word.is_finite() || !(1.0..=16_777_215.0).contains(&word) {
        return Err("frequency word out of range".into());
    }
    Ok(word as u32)
}
pub fn grid(setup: &Setup, start: f64, stop: f64, count: usize) -> Result<Vec<u32>> {
    let (_, _, min) = range_bounds(&setup.range)?;
    if !start.is_finite()
        || !stop.is_finite()
        || start < min
        || stop > 100_000.0
        || stop < start
        || count == 0
        || count > 512
        || (count == 1 && stop != start)
        || (count > 1 && stop == start)
    {
        return Err(
            "invalid sweep: 1–512 points, supported range frequency, ascending linear grid".into(),
        );
    }
    let first = frequency_word(start, setup.clock_hz)?;
    if count == 1 {
        return Ok(vec![first]);
    }
    let increment = frequency_word((stop - start) / (count - 1) as f64, setup.clock_hz)?;
    Ok((0..count).map(|i| first + i as u32 * increment).collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn frequency_word_matches_manufacturer_30khz_example() {
        assert_eq!(frequency_word(30_000.0, 16_000_000).unwrap(), 0x0f5c28);
    }
    #[test]
    fn low_drive_control_bits_match_datasheet_not_one_volt_range() {
        assert_eq!(OPTIONS, 0x03);
    }
    #[test]
    fn capacitor_phase_follows_manufacturer_negative_ninety_degree_example() {
        let cal = normalize(0, 10000);
        let dut = normalize(20000, 0);
        let z = cal * Complex::new(40.0, 0.0) / dut;
        assert!((z.im + 20.0).abs() < 1e-12 && z.re.abs() < 1e-12);
    }
    struct Mock {
        sent: Vec<[u8; 64]>,
        replies: std::collections::VecDeque<[u8; 64]>,
    }
    impl ReportIo for Mock {
        fn exchange(&mut self, r: [u8; 64]) -> Result<[u8; 64]> {
            self.sent.push(r);
            self.replies.pop_front().ok_or("mock exhausted".into())
        }
    }
    fn reply(cmd: u8) -> [u8; 64] {
        let mut r = [0; 64];
        r[0] = cmd;
        r
    }
    #[test]
    fn register_read_uses_ad5933_pointer_command_and_seven_bit_address() {
        let mut value = reply(0x40);
        value[2] = 0x55;
        value[3] = 1;
        value[4] = 0x82;
        let mock = Mock {
            sent: vec![],
            replies: [
                reply(0x10),
                reply(0x90),
                reply(0x10),
                reply(0x91),
                value,
                reply(0x10),
            ]
            .into(),
        };
        let mut m = Mcp::new(mock);
        assert_eq!(m.read_register(0x8f).unwrap(), 0x82);
        assert_eq!(&m.io.sent[1][..6], &[0x90, 2, 0, 0x1a, 0xb0, 0x8f]);
        assert_eq!(&m.io.sent[3][..4], &[0x91, 1, 0, 0x1b]);
    }
    #[test]
    fn rejects_error_byte_count_in_read_response() {
        let mut value = reply(0x40);
        value[3] = 127;
        let mock = Mock {
            sent: vec![],
            replies: [reply(0x10), reply(0x90), reply(0x10), reply(0x91), value].into(),
        };
        assert!(Mcp::new(mock).read_register(0x8f).is_err());
    }
    #[test]
    fn refuses_nack_latch_even_when_engine_reports_idle() {
        let mut status = reply(0x10);
        status[20] = 0x40;
        let mock = Mock {
            sent: vec![],
            replies: [status].into(),
        };
        assert!(Mcp::new(mock)
            .wait_idle()
            .unwrap_err()
            .contains("acknowledged"));
    }
    #[test]
    fn refuses_data_with_failed_i2c_read_state() {
        let mut value = reply(0x40);
        value[2] = 0x25;
        value[3] = 1;
        value[4] = 0x82;
        let mock = Mock {
            sent: vec![],
            replies: [reply(0x10), reply(0x90), reply(0x10), reply(0x91), value].into(),
        };
        assert!(Mcp::new(mock).read_register(0x8f).is_err());
    }
}
