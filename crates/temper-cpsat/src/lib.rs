//! CP-SAT through OR-Tools' C++ API, with no Python in the process.
//!
//! The whole interface is bytes in, bytes out: a `CpModelProto` goes down, a
//! `CpSolverResponse` comes back. That is why the 1,605 LOC of Python bound to
//! `ortools` is bound to a protobuf *schema* rather than to Python -- see
//! `docs/evidence/2026-08-06-ortools-ffi-spike.md`.

pub mod sat {
    #![allow(clippy::all)]
    include!(concat!(env!("OUT_DIR"), "/operations_research.sat.rs"));
}

use prost::Message;
pub use sat::{CpModelProto, CpSolverResponse, SatParameters};

unsafe extern "C" {
    fn temper_cpsat_solve(
        model_buf: *const u8,
        model_len: usize,
        params_buf: *const u8,
        params_len: usize,
        out_buf: *mut *mut u8,
        out_len: *mut usize,
    ) -> i32;
    fn temper_cpsat_free(buf: *mut u8);
}

#[derive(Debug, PartialEq, Eq)]
pub enum SolveError {
    ModelParse,
    ParamsParse,
    ResponseSerialize,
    OutOfMemory,
    ResponseDecode,
    Unknown(i32),
}

/// Solve a model. `params` may be `None` for OR-Tools' defaults.
pub fn solve(
    model: &CpModelProto,
    params: Option<&SatParameters>,
) -> Result<CpSolverResponse, SolveError> {
    let mut model_buf = Vec::with_capacity(model.encoded_len());
    model.encode(&mut model_buf).expect("encode is infallible into a Vec");

    let params_buf: Option<Vec<u8>> = params.map(|p| {
        let mut b: Vec<u8> = Vec::with_capacity(p.encoded_len());
        p.encode(&mut b).expect("encode is infallible into a Vec");
        b
    });
    let (p_ptr, p_len) = match &params_buf {
        Some(b) => (b.as_ptr(), b.len()),
        None => (std::ptr::null(), 0),
    };

    let mut out: *mut u8 = std::ptr::null_mut();
    let mut out_len: usize = 0;
    let rc = unsafe {
        temper_cpsat_solve(model_buf.as_ptr(), model_buf.len(), p_ptr, p_len, &mut out, &mut out_len)
    };
    match rc {
        0 => {}
        1 => return Err(SolveError::ModelParse),
        2 => return Err(SolveError::ParamsParse),
        3 => return Err(SolveError::ResponseSerialize),
        4 => return Err(SolveError::OutOfMemory),
        other => return Err(SolveError::Unknown(other)),
    }

    // SAFETY: rc == 0 means the shim malloc'd `out_len` bytes at `out`.
    let bytes = unsafe { std::slice::from_raw_parts(out, out_len) }.to_vec();
    unsafe { temper_cpsat_free(out) };

    CpSolverResponse::decode(&bytes[..]).map_err(|_| SolveError::ResponseDecode)
}
