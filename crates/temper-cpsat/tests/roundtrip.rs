//! The model is built in Rust, solved by OR-Tools' C++ API, and the response
//! parsed in Rust. No Python takes part.

use temper_cpsat::sat::{
    constraint_proto::Constraint, ConstraintProto, CpModelProto, CpObjectiveProto,
    IntegerVariableProto, LinearConstraintProto,
};
use temper_cpsat::solve;

/// x + y == 7, both in [0, 10], maximise x.
fn model() -> CpModelProto {
    let mut m = CpModelProto { name: "spike".into(), ..Default::default() };
    for name in ["x", "y"] {
        m.variables.push(IntegerVariableProto { name: name.into(), domain: vec![0, 10] });
    }
    m.constraints.push(ConstraintProto {
        constraint: Some(Constraint::Linear(LinearConstraintProto {
            vars: vec![0, 1],
            coeffs: vec![1, 1],
            domain: vec![7, 7],
        })),
        ..Default::default()
    });
    // CP-SAT minimises, so maximising x is minimising -x.
    m.objective = Some(CpObjectiveProto { vars: vec![0], coeffs: vec![-1], ..Default::default() });
    m
}

#[test]
fn solves_optimally_without_python() {
    let r = solve(&model(), None).expect("solve");
    assert_eq!(r.status, 4, "expected OPTIMAL (4), got {}", r.status);
    assert_eq!(r.solution, vec![7, 0], "x should take the whole budget");
    assert_eq!(r.objective_value, -7.0);
}

/// The wire format is the contract, so it is pinned. This is also what makes
/// the encoder port's differential exact: two implementations either emit the
/// same bytes or they do not -- no float tolerance, no fixture-coverage gap.
#[test]
fn model_encoding_is_byte_stable() {
    use prost::Message;
    let mut buf = Vec::new();
    model().encode(&mut buf).unwrap();
    assert_eq!(buf.len(), 58, "CpModelProto wire size changed");
    // Verified byte-identical against the same model built by the Python
    // ortools API on 2026-08-06 (see the spike doc).
    assert_eq!(
        hex(&buf[..24]),
        "0a057370696b6512070a01781202000a12070a0179120200",
        "wire bytes diverged from the pinned Python-produced encoding"
    );
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// An invalid model must come back as a STATUS, not a panic and not an Err.
///
/// The distinction matters at the boundary: a bad model is a normal answer the
/// caller has to handle, whereas `Err` is reserved for the shim itself failing
/// (bytes that are not a proto at all). Measured: an inverted domain is a
/// perfectly valid *proto*, so it parses, and OR-Tools reports
/// `MODEL_INVALID` = 1.
#[test]
fn an_invalid_model_is_a_status_not_a_panic() {
    let mut m = model();
    m.variables.push(IntegerVariableProto { name: "bad".into(), domain: vec![5, 1] });
    match solve(&m, None) {
        Ok(r) => assert_eq!(r.status, 1, "expected MODEL_INVALID (1), got {}", r.status),
        Err(e) => panic!("an invalid model should still produce a response, got {e:?}"),
    }
}
