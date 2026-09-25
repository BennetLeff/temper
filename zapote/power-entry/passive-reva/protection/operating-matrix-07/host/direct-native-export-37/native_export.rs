//! Bounded post-stop native raw writer for the direct-export-37 candidate.
//!
//! ngGet_Vec_Info returns borrowed pointers into ngspice's completed plot. We
//! copy only pointer/length/type metadata, then perform one read-only pass with
//! a 64 KiB BufWriter. No ngspice command or API call is made while those
//! pointers are borrowed.

use std::ffi::{c_char, CStr, CString};
use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::os::unix::fs::FileTypeExt;
use std::time::Instant;

#[repr(C)]
struct VectorInfo {
    v_name: *mut c_char,
    v_type: i32,
    v_flags: i16,
    v_realdata: *mut f64,
    v_compdata: *mut u8,
    v_length: i32,
}

extern "C" {
    fn ngGet_Vec_Info(name: *mut c_char) -> *mut VectorInfo;
}

const VF_REAL: i16 = 1;
const VF_COMPLEX: i16 = 2;
const VF_EVENT_NODE: i16 = 1 << 8;
const SV_TIME: i32 = 1;
const SV_VOLTAGE: i32 = 3;
const SV_CURRENT: i32 = 4;
const BUFFER_BYTES: usize = 64 * 1024;

#[allow(dead_code)] // each standalone host uses exactly one schema variant
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Schema { Normal15, Fault42 }

impl Schema {
    pub fn names(self) -> &'static [&'static str] {
        match self {
            Schema::Normal15 => &[
                "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
                "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
                "v(fault)", "v(vcomp)", "v(icomp)",
            ],
            Schema::Fault42 => &[
                "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
                "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
                "v(fault)", "v(vcomp)", "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)",
                "v(pwm)", "v(pwm_input)", "v(xdriver.driver_req)", "v(xdriver.drv_delay)",
                "v(xu.phase)", "v(xu.blank)", "v(isense)", "v(xu.ov)", "v(xu.fault)",
                "v(xu.pcl_hold)", "v(xu.pcl_request)", "v(disable)", "v(xu.m1)", "v(xu.m2)",
                "v(acsrc,acn)", "i(Vchannel)", "i(Vbody)", "v(f2ctl)", "v(standby_req)",
                "v(arm)", "v(permit)", "i(Vf2sense)", "i(Vdboost1sense)",
                "i(Vdboost2sense)", "v(fault_inject)",
            ],
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExportStats {
    pub rows: usize,
    pub columns: usize,
    pub bytes_written: u64,
    pub borrowed_data_bytes: u64,
    pub buffer_bytes: usize,
    pub export_elapsed_ms: u64,
}

#[derive(Clone, Copy)]
struct Borrowed {
    real: *const f64,
    length: usize,
}

fn validate_metadata(name: &str, length: i32, flags: i16, v_type: i32, real: *mut f64, complex: *mut u8, points: usize) -> Result<Borrowed, String> {
    let length = usize::try_from(length).map_err(|_| format!("negative length: {name}"))?;
    if length != points { return Err(format!("length mismatch for {name}: {length} != {points}")); }
    if flags & VF_REAL == 0 || flags & VF_COMPLEX != 0 || flags & VF_EVENT_NODE != 0 || real.is_null() || !complex.is_null() {
        return Err(format!("vector is not real: {name}"));
    }
    let expected_type = if name == "time" { SV_TIME } else if name.starts_with("i(") { SV_CURRENT } else { SV_VOLTAGE };
    if v_type != expected_type { return Err(format!("unexpected type for {name}: {v_type} != {expected_type}")); }
    Ok(Borrowed { real: real.cast_const(), length })
}

fn returned_name_matches(request: &str, actual: &[u8]) -> bool {
    let actual = actual.to_ascii_lowercase();
    let request = request.to_ascii_lowercase();
    if request == "time" { return actual == b"time"; }
    let Some(inner) = request.strip_prefix("v(").and_then(|s| s.strip_suffix(')')) else {
        let Some(inner) = request.strip_prefix("i(").and_then(|s| s.strip_suffix(')')) else { return false; };
        return actual == inner.as_bytes() || actual == format!("{inner}#branch").as_bytes();
    };
    actual == inner.as_bytes()
}

fn lookup(name: &str, points: usize) -> Result<Borrowed, String> {
    let c = CString::new(name).map_err(|e| format!("invalid vector {name}: {e}"))?;
    let info = unsafe { ngGet_Vec_Info(c.as_ptr().cast_mut()) };
    if info.is_null() { return Err(format!("vector lookup failed: {name}")); }
    let info = unsafe { &*info };
    if info.v_name.is_null() || !returned_name_matches(name, unsafe { CStr::from_ptr(info.v_name) }.to_bytes()) {
        return Err(format!("vector alias mismatch for {name}"));
    }
    validate_metadata(name, info.v_length, info.v_flags, info.v_type, info.v_realdata, info.v_compdata, points)
}

fn unit(name: &str) -> &'static str {
    if name == "time" { "time" }
    else if name.starts_with("i(") { "current" }
    else if name == "v(acsrc,acn)" { "notype" }
    else { "voltage" }
}

fn header(names: &[&str], rows: usize) -> Vec<u8> {
    let mut out = Vec::new();
    out.extend_from_slice(b"Title: direct-native-export-37\nDate: direct-export-37\nCommand: direct-native-export-37\nPlotname: transient\nFlags: real\n");
    out.extend_from_slice(format!("No. Variables: {}\nNo. Points: {}\nVariables:\n", names.len(), rows).as_bytes());
    for (index, name) in names.iter().enumerate() {
        out.extend_from_slice(format!("\t{index}\t{name}\t{}\n", unit(name)).as_bytes());
    }
    out.extend_from_slice(b"Binary:\n");
    out
}

fn value(vector: Borrowed, row: usize) -> f64 {
    // The caller has checked row < length and real flags. This is a read-only
    // dereference of the simulator-owned completed plot.
    unsafe { *vector.real.add(row) }
}

fn open_export(path: &str) -> Result<File, String> {
    let result = match std::fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_fifo() => OpenOptions::new().write(true).open(path),
        Ok(meta) if meta.file_type().is_symlink() => {
            // Follow inherited /dev/fd/N or a symlinked FIFO, but never request
            // truncation. The target type is checked after opening.
            let file = OpenOptions::new().write(true).open(path)
                .map_err(|e| format!("open export {path}: {e}"))?;
            if !file.metadata().map_err(|e| format!("stat export {path}: {e}"))?.file_type().is_fifo() {
                return Err(format!("refusing existing non-FIFO export target {path}"));
            }
            Ok(file)
        }
        Ok(_) => return Err(format!("refusing to overwrite existing regular export {path}")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => OpenOptions::new().write(true).create_new(true).open(path),
        Err(error) => Err(error),
    };
    result.map_err(|e| format!("open export {path}: {e}"))
}

/// Export a canonical native raw plot without issuing a mutating ngspice API
/// call. `points` is the callback count recorded by the unchanged host.
pub fn export(path: &str, schema: Schema, points: usize) -> Result<ExportStats, String> {
    if points == 0 { return Err("cannot export zero points".into()); }
    let started = Instant::now();
    let names = schema.names();
    enum Slot { Vector(Borrowed), Difference(Borrowed, Borrowed) }
    let mut slots: Vec<Option<Slot>> = Vec::with_capacity(names.len());
    let mut borrowed_data_bytes = 0u64;
    let mut acsrc = None;
    let mut acn = None;
    for &name in names {
        if name == "v(acsrc,acn)" { slots.push(None); continue; }
        let vector = lookup(name, points)?;
        borrowed_data_bytes = borrowed_data_bytes.checked_add((vector.length as u64) * 8).ok_or("borrowed byte count overflow")?;
        if name == "v(acsrc)" { acsrc = Some(vector); }
        if name == "v(acn)" { acn = Some(vector); }
        slots.push(Some(Slot::Vector(vector)));
    }
    let derived = if schema == Schema::Fault42 {
        let a = acsrc.ok_or("derived v(acsrc,acn) missing acsrc")?;
        let b = acn.ok_or("derived v(acsrc,acn) missing acn")?;
        Some((a, b))
    } else { None };
    for (index, &name) in names.iter().enumerate() {
        if name == "v(acsrc,acn)" {
            let (a, b) = derived.ok_or("derived vector requested for normal schema")?;
            slots[index] = Some(Slot::Difference(a, b));
        }
    }
    if slots.len() != names.len() || slots.iter().any(Option::is_none) { return Err("slot count mismatch".into()); }
    let file = open_export(path)?;
    let mut writer = BufWriter::with_capacity(BUFFER_BYTES, file);
    let header = header(names, points);
    let mut bytes_written = header.len() as u64;
    writer.write_all(&header).map_err(|e| format!("write header: {e}"))?;
    for row in 0..points {
        for (column, slot) in slots.iter().enumerate() {
            let number = match slot.as_ref().ok_or("missing export slot")? {
                Slot::Vector(vector) => value(*vector, row),
                Slot::Difference(a, b) => value(*a, row) - value(*b, row),
            };
            if !number.is_finite() { return Err(format!("nonfinite value in {} row {row}", names[column])); }
            let row_bytes = number.to_le_bytes();
            writer.write_all(&row_bytes).map_err(|e| format!("write row {row}: {e}"))?;
            bytes_written = bytes_written.checked_add(8).ok_or("output byte count overflow")?;
        }
    }
    writer.flush().map_err(|e| format!("flush export: {e}"))?;
    Ok(ExportStats { rows: points, columns: names.len(), bytes_written, borrowed_data_bytes, buffer_bytes: BUFFER_BYTES, export_elapsed_ms: started.elapsed().as_millis() as u64 })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schemas_have_expected_width_and_units() {
        assert_eq!(Schema::Normal15.names().len(), 15);
        assert_eq!(Schema::Fault42.names().len(), 42);
        assert_eq!(unit("time"), "time");
        assert_eq!(unit("i(Vac)"), "current");
        assert_eq!(unit("v(acsrc,acn)"), "notype");
    }

    #[test]
    fn header_is_canonical_and_bounded() {
        let h = header(Schema::Normal15.names(), 2);
        let text = String::from_utf8(h).expect("header ascii");
        assert!(text.contains("No. Variables: 15\nNo. Points: 2\n"));
        assert!(text.ends_with("Binary:\n"));
        assert_eq!(text.matches("Variables:\n").count(), 1);
    }

    #[test]
    fn type_and_pointer_checks_are_explicit() {
        assert!(validate_metadata("time", 2, VF_REAL, SV_TIME, std::ptr::null_mut(), std::ptr::null_mut(), 2).is_err());
        assert!(validate_metadata("time", -1, VF_REAL, SV_TIME, 1usize as *mut f64, std::ptr::null_mut(), 2).is_err());
        assert!(validate_metadata("i(Vac)", 2, VF_COMPLEX, SV_CURRENT, 1usize as *mut f64, 1usize as *mut u8, 2).is_err());
        assert!(validate_metadata("i(Vac)", 2, VF_REAL | VF_EVENT_NODE, SV_CURRENT, 1usize as *mut f64, std::ptr::null_mut(), 2).is_err());
        assert!(validate_metadata("i(Vac)", 2, VF_REAL, SV_VOLTAGE, 1usize as *mut f64, std::ptr::null_mut(), 2).is_err());
        assert!(validate_metadata("i(Vac)", 2, VF_REAL, SV_CURRENT, 1usize as *mut f64, std::ptr::null_mut(), 2).is_ok());
        assert!(returned_name_matches("v(acsrc)", b"acsrc"));
        assert!(returned_name_matches("i(Vac)", b"Vac#branch"));
        assert!(!returned_name_matches("v(acsrc)", b"acn"));
    }

    #[test]
    fn vector_info_abi_matches_external_oracle() {
        use std::mem::{align_of, size_of, MaybeUninit};
        assert_eq!(size_of::<VectorInfo>(), 40);
        assert_eq!(align_of::<VectorInfo>(), 8);
        let value = MaybeUninit::<VectorInfo>::uninit();
        let base = value.as_ptr() as usize;
        let offsets = unsafe {
            [
                std::ptr::addr_of!((*value.as_ptr()).v_name) as usize - base,
                std::ptr::addr_of!((*value.as_ptr()).v_type) as usize - base,
                std::ptr::addr_of!((*value.as_ptr()).v_flags) as usize - base,
                std::ptr::addr_of!((*value.as_ptr()).v_realdata) as usize - base,
                std::ptr::addr_of!((*value.as_ptr()).v_compdata) as usize - base,
                std::ptr::addr_of!((*value.as_ptr()).v_length) as usize - base,
            ]
        };
        assert_eq!(offsets, [0, 8, 12, 16, 24, 32]);
    }

    #[test]
    fn existing_regular_output_is_refused_without_truncation() {
        let path = std::env::temp_dir().join(format!("direct-export-37-regular-{}", std::process::id()));
        std::fs::write(&path, b"keep").expect("fixture");
        assert!(open_export(path.to_str().expect("utf8")).is_err());
        assert_eq!(std::fs::read(&path).expect("read fixture"), b"keep");
        std::fs::remove_file(path).expect("cleanup");
    }
}
