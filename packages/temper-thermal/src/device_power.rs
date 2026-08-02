//! Per-device power dissipation kernel (Wave 4, Phase A #2).
//!
//! Ports the pure scalar arithmetic of
//! `temper_placer/physics/device_power.py::_compute_single_device_power`
//! (the canonical per-device power model, issue #140 — ONE source of
//! truth for per-device power dissipation, used by BOTH the U6
//! operating-point gate and the U10 thermal helps-battery) to Rust.
//! The Python module keeps its public API (`DeviceLossConfig`,
//! `derive_power_map`, fail-closed validation) and delegates the
//! arithmetic here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! The arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential suite
//! in `packages/temper-placer/tests/physics/`):
//!
//! - **B1 (host libm via dlsym):** `math.sqrt(2)` and `I_load_rms ** 2`
//!   (CPython `float.__pow__` → host libm `pow(x, 2.0)`) come from the
//!   host Python runtime's libm.  A crate's statically-bound
//!   `f64::sqrt`/`powf` can differ in the last ulp (the uv standalone
//!   build's libm measured 1 ulp apart on real inputs).  Both are
//!   resolved via `dlsym(RTLD_DEFAULT, ...)` (cached in a `OnceLock`),
//!   falling back to the std intrinsic only when `dlsym` is unavailable.
//! - **B7 (f64 operation order):** `I_load_rms**2 * R_ds_on` is
//!   `pow(I, 2.0) * R_ds_on` — NOT `I*I * R_ds_on` (the two differ by 1
//!   ulp on ~0.14% of random floats, measured 2026-08-02 and pinned in
//!   the differential suite).  The waveform chain
//!   `0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)` stays five
//!   left-to-right ops (Python's evaluation order), with
//!   `I_peak = I_load_rms * sqrt(2)` computed before the chain.
//!   `(E_on + E_off) * f_sw` keeps the parenthesized sum.  `P_cond + P_sw`
//!   is the final left-to-right add.  No reassociation, no fusing.
//! - **B8 (denormal underflow):** the crate keeps default IEEE semantics
//!   (no fast-math, no FTZ/DAZ, no `mul_add` fusion); a denormal-band
//!   differential case pins that `P_cond + P_sw` in the denormal range
//!   matches CPython bit-for-bit.
//!
//! Branch semantics match Python's comparisons exactly: `R_ds_on > 0`
//! and `E_on > 0 or E_off > 0` are false for NaN (IEEE comparisons),
//! selecting the same arms CPython selects.

use std::sync::OnceLock;

use pyo3::prelude::*;
use temper_py_bridge;

/// Host-runtime libm function pointers, resolved once via `dlsym`.
type UnaryMathFn = unsafe extern "C" fn(f64) -> f64;
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

fn dlsym_unary(symbol: &str) -> Option<UnaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    unsafe {
        let p = dlsym(RTLD_DEFAULT, symbol.as_ptr());
        if p.is_null() {
            None
        } else {
            Some(std::mem::transmute::<*mut u8, UnaryMathFn>(p))
        }
    }
}

fn dlsym_binary(symbol: &str) -> Option<BinaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    unsafe {
        let p = dlsym(RTLD_DEFAULT, symbol.as_ptr());
        if p.is_null() {
            None
        } else {
            Some(std::mem::transmute::<*mut u8, BinaryMathFn>(p))
        }
    }
}

fn host_sqrt() -> &'static UnaryMathFn {
    static F: OnceLock<Option<UnaryMathFn>> = OnceLock::new();
    F.get_or_init(|| dlsym_unary("sqrt").or(Some(fallback_sqrt)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

fn host_pow() -> &'static BinaryMathFn {
    static F: OnceLock<Option<BinaryMathFn>> = OnceLock::new();
    F.get_or_init(|| dlsym_binary("pow").or(Some(fallback_pow)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

unsafe extern "C" fn fallback_sqrt(x: f64) -> f64 {
    f64::sqrt(x)
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    x.powf(y)
}

/// CPython `math.sqrt(x)`, bit-exact with the reference.
fn math_sqrt(x: f64) -> f64 {
    unsafe { host_sqrt()(x) }
}

/// CPython `x ** y` (libm `pow`), bit-exact with the reference.
fn math_pow(x: f64, y: f64) -> f64 {
    unsafe { host_pow()(x, y) }
}

/// Device-type code passed across the FFI boundary.  The Python wrapper
/// maps `device_type == "DIODE"` to `DIODE`; every other string is sent
/// as `IGBT_OR_MOSFET` (the reference's else-branch covers both).
pub(crate) const DEVICE_DIODE: i64 = 1;
pub(crate) const DEVICE_IGBT_OR_MOSFET: i64 = 0;

/// Compute total power dissipation for ONE device (W).
///
/// Mirrors `_compute_single_device_power`'s arithmetic verbatim:
///
/// - **DIODE:** `I_avg = I_load_rms * 0.5`; `P_cond = I_avg * V_f`;
///   `P_sw = E_rr * f_sw`; return `P_cond + P_sw`.
/// - **IGBT / MOSFET:** `P_cond = pow(I_load_rms, 2.0) * R_ds_on` when
///   `R_ds_on > 0`, else `I_load_rms * V_ce_sat`; switching is the energy
///   method `(E_on + E_off) * f_sw` when either energy is `> 0`, else the
///   waveform fallback `0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)`
///   with `I_peak = I_load_rms * sqrt(2)`; return `P_cond + P_sw`.
///
/// # Arguments
///
/// * `device_type_code` — `DEVICE_DIODE` or `DEVICE_IGBT_OR_MOSFET`.
/// * `v_ce_sat`, `r_ds_on`, `e_on`, `e_off`, `v_f`, `e_rr` — per-device
///   loss parameters (V, Ω, J, J, V, J).
/// * `v_bus` — DC bus voltage (V); only used by the waveform fallback.
/// * `i_load_rms` — worst-case RMS load current (A).
/// * `f_sw` — switching frequency (Hz).
/// * `t_rise`, `t_fall` — switching waveform rise/fall times (s).
///
/// # Returns
///
/// Total per-device power dissipation in watts.
#[allow(clippy::too_many_arguments)]
pub fn single_device_power(
    device_type_code: i64,
    v_ce_sat: f64,
    r_ds_on: f64,
    e_on: f64,
    e_off: f64,
    v_f: f64,
    e_rr: f64,
    v_bus: f64,
    i_load_rms: f64,
    f_sw: f64,
    t_rise: f64,
    t_fall: f64,
) -> f64 {
    if device_type_code == DEVICE_DIODE {
        // I_avg = I_load_rms * 0.5; P_cond = I_avg * V_f;
        // P_sw = E_rr * f_sw; return P_cond + P_sw.
        let i_avg = i_load_rms * 0.5;
        let p_cond = i_avg * v_f;
        let p_sw = e_rr * f_sw;
        return p_cond + p_sw;
    }

    // IGBT or MOSFET.
    // `I_load_rms**2` is CPython float_pow → host-libm pow(x, 2.0),
    // NOT x*x (B7; differs on ~0.14% of random floats, pinned in the
    // differential suite).
    let p_cond = if r_ds_on > 0.0 {
        math_pow(i_load_rms, 2.0) * r_ds_on
    } else {
        i_load_rms * v_ce_sat
    };

    let p_sw = if e_on > 0.0 || e_off > 0.0 {
        (e_on + e_off) * f_sw
    } else {
        // Waveform fallback: I_peak = I_load_rms * math.sqrt(2) (host
        // libm sqrt — B1), then the five-op left-to-right chain
        // 0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall) (B7).
        let i_peak = i_load_rms * math_sqrt(2.0);
        0.5 * v_bus * i_peak * f_sw * (t_rise + t_fall)
    };

    p_cond + p_sw
}

/// pyo3 bridge for [`single_device_power`].
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (device_type, v_ce_sat, r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_load_rms, f_sw, t_rise, t_fall))]
pub fn single_device_power_py(
    device_type: String,
    v_ce_sat: f64,
    r_ds_on: f64,
    e_on: f64,
    e_off: f64,
    v_f: f64,
    e_rr: f64,
    v_bus: f64,
    i_load_rms: f64,
    f_sw: f64,
    t_rise: f64,
    t_fall: f64,
) -> PyResult<f64> {
    let device_type_code = if device_type == "DIODE" {
        DEVICE_DIODE
    } else {
        DEVICE_IGBT_OR_MOSFET
    };
    temper_py_bridge::catch_unwind(|| {
        single_device_power(
            device_type_code,
            v_ce_sat,
            r_ds_on,
            e_on,
            e_off,
            v_f,
            e_rr,
            v_bus,
            i_load_rms,
            f_sw,
            t_rise,
            t_fall,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    // The differential suite is the primary oracle; these unit tests pin
    // the branch structure and the pow-vs-mul discrimination without a
    // Python runtime.

    #[test]
    fn diode_closed_form() {
        // I_avg = 8.0, P_cond = 8.4, P_sw = 1.5 → 9.9
        let p = single_device_power(DEVICE_DIODE, 0.0, 0.0, 0.0, 0.0, 1.05, 0.06e-3, 325.0, 16.0, 25000.0, 50e-9, 50e-9);
        assert_eq!(p, 9.9);
    }

    #[test]
    fn igbt_energy_method() {
        // P_cond = 27.2, P_sw = 13.25 → 40.45
        let p = single_device_power(DEVICE_IGBT_OR_MOSFET, 1.7, 0.0, 0.32e-3, 0.21e-3, 0.0, 0.0, 325.0, 16.0, 25000.0, 50e-9, 50e-9);
        assert_eq!(p, 40.45);
    }

    #[test]
    fn waveform_fallback_zero_f_sw_is_conduction_only() {
        // f_sw = 0 → P_sw = 0 → P = 16 * 1.7 = 27.2
        let p = single_device_power(DEVICE_IGBT_OR_MOSFET, 1.7, 0.0, 0.0, 0.0, 0.0, 0.0, 325.0, 16.0, 0.0, 50e-9, 50e-9);
        assert_eq!(p, 27.2);
    }

    #[test]
    fn mosfet_uses_pow_not_mul() {
        // The kernel must compute `I_load_rms**2` via host-libm
        // pow(x, 2.0) — the CPython `**2` semantics — never x*x.  The
        // pow-vs-mul DISCRIMINATION (they differ on ~0.14% of floats
        // inside the uv-standalone Python runtime) is pinned by the
        // Python differential suite, where dlsym resolves to the same
        // libm CPython uses; in a bare `cargo test` binary the system
        // libm may implement pow(x, 2.0) as x*x, so here we only pin
        // the semantic: output == pow(x, 2.0) * R_ds_on.
        let x = 974.5535622665931;
        let p_pow = math_pow(x, 2.0) * 3.0;
        let got = single_device_power(DEVICE_IGBT_OR_MOSFET, 0.0, 3.0, 0.0, 0.0, 0.0, 0.0, 100.0, x, 0.0, 50e-9, 50e-9);
        assert_eq!(got, p_pow);
    }

    #[test]
    fn nan_rdson_selects_v_ce_sat_branch() {
        // NaN > 0.0 is false in both CPython and Rust → V_ce_sat branch.
        let p = single_device_power(DEVICE_IGBT_OR_MOSFET, 2.0, f64::NAN, 1e-3, 0.0, 0.0, 0.0, 100.0, 10.0, 10000.0, 50e-9, 50e-9);
        assert_eq!(p, 10.0 * 2.0 + 1e-3 * 10000.0);
    }

    #[test]
    fn energy_method_additivity_order() {
        // (E_on + E_off) * f_sw with the parenthesized sum first.
        let a = single_device_power(DEVICE_IGBT_OR_MOSFET, 0.0, 0.0, 1.0e-3, 2.0e-3, 0.0, 0.0, 0.0, 0.0, 10000.0, 50e-9, 50e-9);
        assert_eq!(a, (1.0e-3 + 2.0e-3) * 10000.0);
        // 0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall) chain
        let b = single_device_power(DEVICE_IGBT_OR_MOSFET, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 10.0, 10000.0, 50e-9, 50e-9);
        let i_peak = 10.0 * math_sqrt(2.0);
        assert_eq!(b, 0.5 * 100.0 * i_peak * 10000.0 * (50e-9 + 50e-9));
    }
}
