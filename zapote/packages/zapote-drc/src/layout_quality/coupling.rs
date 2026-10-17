//! Signed inductive pickup and equivalent Kelvin-sense error.
//!
//! Mutuals use oriented ports from an external extraction. All slews in a
//! scenario are simultaneous, not independently selected waveform maxima.
//! Induced EMF is a series-source estimate, **not** the MOSFET's VGS: that
//! requires the gate impedance, Miller capacitance and driver transient model.
use super::{ensure, finite, identities, nonnegative, positive, Error};
use serde::{Deserialize, Serialize};

/// One oriented aggressor/victim mutual-inductance contribution.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InductiveTerm {
    /// Native object or extracted port pair.
    pub object: String,
    /// Signed mutual inductance, nH.
    pub mutual_nh: f64,
    /// Signed instantaneous aggressor current slew, A/ns.
    pub slew_a_per_ns: f64,
}

/// Signed pickup and a cancellation-independent bound for supplied magnitudes.
#[derive(Debug, Clone, Serialize)]
pub struct Pickup {
    /// Algebraic sum at the supplied operating point, V.
    pub signed_v: f64,
    /// Sum of absolute contributions, V; not a bound on missing paths.
    pub independent_sign_bound_v: f64,
    /// Largest contribution's identity.
    pub dominant_object: String,
    /// Signed value of that contribution, V.
    pub dominant_v: f64,
}

/// Compute Σ M di/dt without allocating a result per contribution.
/// Identity validation costs O(n log n); numerical accumulation costs O(n).
///
/// # Errors
/// Rejects empty populations, duplicate identities, non-finite values and overflow.
pub fn induced_voltage(terms: &[InductiveTerm]) -> Result<Pickup, Error> {
    ensure(!terms.is_empty(), "inductive population is empty")?;
    identities(terms.iter().map(|t| t.object.as_str()))?;
    let mut signed = 0.0;
    let mut bound = 0.0;
    let mut dominant = &terms[0];
    let mut dominant_v: f64 = 0.0;
    for term in terms {
        let v = finite(term.mutual_nh, "mutual_nh")? * finite(term.slew_a_per_ns, "slew_a_per_ns")?;
        finite(v, "induced voltage")?;
        signed += v;
        bound += v.abs();
        if v.abs() > dominant_v.abs() {
            dominant = term;
            dominant_v = v;
        }
    }
    Ok(Pickup {
        signed_v: finite(signed, "summed pickup")?,
        independent_sign_bound_v: finite(bound, "pickup bound")?,
        dominant_object: dominant.object.clone(),
        dominant_v,
    })
}

/// An aggressor's capacitive current into a victim.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CapacitiveTerm {
    /// Native object or extracted capacitance pair.
    pub object: String,
    /// Coupling capacitance, pF (nonnegative).
    pub capacitance_pf: f64,
    /// Signed differential voltage slew, V/ns.
    pub slew_v_per_ns: f64,
}

/// Sum C dv/dt, retaining signed current and the independent-sign bound, A.
///
/// # Errors
/// Rejects missing/duplicate objects, negative capacitance and non-finite results.
pub fn displacement_current(terms: &[CapacitiveTerm]) -> Result<(f64, f64), Error> {
    ensure(!terms.is_empty(), "capacitive population is empty")?;
    identities(terms.iter().map(|t| t.object.as_str()))?;
    let mut signed = 0.0;
    let mut bound = 0.0;
    for term in terms {
        let current = nonnegative(term.capacitance_pf, "capacitance_pf")?
            * finite(term.slew_v_per_ns, "slew_v_per_ns")?
            * 1e-3;
        finite(current, "displacement current")?;
        signed += current;
        bound += current.abs();
    }
    Ok((
        finite(signed, "summed current")?,
        finite(bound, "current bound")?,
    ))
}

/// Shared series copper in a sensitive return or Kelvin pickup.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SharedImpedance {
    /// Native shared-copper identity.
    pub object: String,
    /// Shared resistance, ohms.
    pub resistance_ohm: f64,
    /// Shared inductance, nH; sign is carried by current slew.
    pub inductance_nh: f64,
    /// Signed current, A.
    pub current_a: f64,
    /// Signed current slew, A/ns.
    pub slew_a_per_ns: f64,
}

/// Resistive and inductive disturbance in a shared return.
///
/// # Errors
/// Rejects empty populations, duplicate objects, negative R/L and overflow.
pub fn shared_voltage(terms: &[SharedImpedance]) -> Result<(f64, f64), Error> {
    ensure(!terms.is_empty(), "shared impedance population is empty")?;
    identities(terms.iter().map(|t| t.object.as_str()))?;
    let mut signed = 0.0;
    let mut bound = 0.0;
    for term in terms {
        let ir = nonnegative(term.resistance_ohm, "resistance_ohm")?
            * finite(term.current_a, "current_a")?;
        let ldi = nonnegative(term.inductance_nh, "inductance_nh")?
            * finite(term.slew_a_per_ns, "slew_a_per_ns")?;
        signed += ir + ldi;
        bound += ir.abs() + ldi.abs();
    }
    Ok((
        finite(signed, "shared voltage")?,
        finite(bound, "shared bound")?,
    ))
}

/// Explicit low-frequency/resistive victim model for a Kelvin sense pair.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KelvinInput {
    /// Shared copper terms; use explicit zero-valued terms for known zero coupling.
    pub shared: Vec<SharedImpedance>,
    /// Oriented magnetic pickup into the differential sense loop.
    pub magnetic: Vec<InductiveTerm>,
    /// Coupling into the positive sense conductor.
    pub positive_pickup: Vec<CapacitiveTerm>,
    /// Coupling into the negative sense conductor.
    pub negative_pickup: Vec<CapacitiveTerm>,
    /// Resistive transfer impedance at the positive input, ohms.
    pub positive_transfer_ohm: f64,
    /// Resistive transfer impedance at the negative input, ohms.
    pub negative_transfer_ohm: f64,
    /// Effective shunt transresistance, ohms, at the evaluated operating point.
    pub shunt_ohm: f64,
}

/// Equivalent differential input disturbance and trip-current error.
#[derive(Debug, Clone, Serialize)]
pub struct KelvinResult {
    /// Signed differential disturbance, V.
    pub error_v: f64,
    /// Independent-sign disturbance bound, V.
    pub error_bound_v: f64,
    /// Input-referred current error (the threshold shift has the opposite sign), A.
    pub equivalent_current_error_a: f64,
    /// Magnitude bound on equivalent current error, A.
    pub current_error_bound_a: f64,
}

/// Evaluate a declared resistive sense-input model; no implicit RC bandwidth.
///
/// # Errors
/// Rejects incomplete terms, invalid transfer/shunt resistance and overflow.
pub fn kelvin_error(input: &KelvinInput) -> Result<KelvinResult, Error> {
    let (shared, shared_bound) = shared_voltage(&input.shared)?;
    let magnetic = induced_voltage(&input.magnetic)?;
    let (pos, pos_bound) = displacement_current(&input.positive_pickup)?;
    let (neg, neg_bound) = displacement_current(&input.negative_pickup)?;
    let rp = nonnegative(input.positive_transfer_ohm, "positive_transfer_ohm")?;
    let rn = nonnegative(input.negative_transfer_ohm, "negative_transfer_ohm")?;
    let shunt = positive(input.shunt_ohm, "shunt_ohm")?;
    let error = finite(
        shared + magnetic.signed_v + rp * pos - rn * neg,
        "sense error",
    )?;
    let bound = finite(
        shared_bound + magnetic.independent_sign_bound_v + rp * pos_bound + rn * neg_bound,
        "sense bound",
    )?;
    Ok(KelvinResult {
        error_v: error,
        error_bound_v: bound,
        equivalent_current_error_a: finite(error / shunt, "current error")?,
        current_error_bound_a: finite(bound / shunt, "current error bound")?,
    })
}

/// Conservative EMI bypass voltage for supplied independent coupling magnitudes.
/// This is pickup at the victim port, not filter insertion loss or an EMC limit.
///
/// # Errors
/// Rejects missing coupling populations and invalid transfer impedance.
pub fn emi_bypass_voltage(
    magnetic: &[InductiveTerm],
    electric: &[CapacitiveTerm],
    transfer_ohm: f64,
) -> Result<f64, Error> {
    let m = induced_voltage(magnetic)?.independent_sign_bound_v;
    let c = displacement_current(electric)?.1;
    finite(
        m + c * nonnegative(transfer_ohm, "transfer_ohm")?,
        "EMI bypass voltage",
    )
}
