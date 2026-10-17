//! Frequency-domain supply impedance of parallel, independent series-RLC branches.
//!
//! R and L include capacitor ESR/ESL and the complete supply/return route.
//! Shared inductance and mutual coupling are NOT represented by this model;
//! those require the extracted multiport model. Capacitance is effective C at
//! the operating bias and temperature, not its nominal nameplate value.
use super::{ensure, finite, identities, nonnegative, positive, Error};
use serde::{Deserialize, Serialize};
use std::f64::consts::TAU;

/// A supply-to-return capacitor branch.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Branch {
    /// Capacitor and route identity.
    pub object: String,
    /// Effective capacitance, F.
    pub capacitance_f: f64,
    /// Total series resistance, ohms; positive to represent loss at resonance.
    pub resistance_ohm: f64,
    /// Total series inductance, H.
    pub inductance_h: f64,
}

/// Phasor result at one frequency for a 1 A total excitation.
#[derive(Debug, Clone, Serialize)]
pub struct FrequencyPoint {
    /// Frequency, Hz.
    pub frequency_hz: f64,
    /// Magnitude of supply impedance, ohms.
    pub impedance_ohm: f64,
    /// Real part of supply impedance, ohms.
    pub real_ohm: f64,
    /// Imaginary part of supply impedance, ohms.
    pub imaginary_ohm: f64,
    /// Branch current magnitudes relative to total current, in input order.
    /// May exceed 1 at antiresonance; these are not probabilities.
    pub branch_current_ratios: Vec<f64>,
}

/// Sweep specified frequencies in O(branches × frequencies).
///
/// # Errors
/// Rejects empty populations, duplicate objects, invalid R/L/C/frequency and
/// non-finite or unrepresentable impedance/admittance.
pub fn sweep(branches: &[Branch], frequencies_hz: &[f64]) -> Result<Vec<FrequencyPoint>, Error> {
    ensure(
        !branches.is_empty() && !frequencies_hz.is_empty(),
        "decoupling population is empty",
    )?;
    identities(branches.iter().map(|b| b.object.as_str()))?;
    for b in branches {
        positive(b.capacitance_f, "capacitance_f")?;
        positive(b.resistance_ohm, "resistance_ohm")?;
        nonnegative(b.inductance_h, "inductance_h")?;
    }
    let mut admittance = Vec::with_capacity(branches.len());
    let mut results = Vec::with_capacity(frequencies_hz.len());
    for &frequency in frequencies_hz {
        let omega = positive(
            TAU * positive(frequency, "frequency_hz")?,
            "angular frequency",
        )?;
        admittance.clear();
        let (mut g, mut susceptance) = (0.0, 0.0);
        for b in branches {
            let capacitive_admittance = positive(omega * b.capacitance_f, "capacitive admittance")?;
            let x = finite(
                omega * b.inductance_h - 1.0 / capacitive_admittance,
                "reactance",
            )?;
            // Scaled reciprocal avoids squaring large impedances.
            let norm = positive(b.resistance_ohm.hypot(x), "branch impedance")?;
            let real = (b.resistance_ohm / norm) / norm;
            let imag = -(x / norm) / norm;
            g += real;
            susceptance += imag;
            admittance.push((real, imag));
        }
        finite(g, "total conductance")?;
        finite(susceptance, "total susceptance")?;
        let norm = positive(g.hypot(susceptance), "total admittance")?;
        let real = finite((g / norm) / norm, "real impedance")?;
        let imag = finite(-(susceptance / norm) / norm, "imaginary impedance")?;
        let ratios = admittance
            .iter()
            .map(|(a, b)| finite(a.hypot(*b) / norm, "branch participation"))
            .collect::<Result<Vec<_>, _>>()?;
        results.push(FrequencyPoint {
            frequency_hz: frequency,
            impedance_ohm: positive(1.0 / norm, "impedance magnitude")?,
            real_ohm: real,
            imaginary_ohm: imag,
            branch_current_ratios: ratios,
        });
    }
    Ok(results)
}
