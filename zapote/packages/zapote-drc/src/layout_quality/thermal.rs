//! Linear thermal influence and sensitivity drift at a declared operating point.
//! Transfer resistances come from an assembly-specific thermal model. This
//! kernel does not invent airflow, package contacts, or transient responses.
use super::{ensure, finite, identities, nonnegative, Error};
use serde::{Deserialize, Serialize};

/// A heat source and its transfer resistance to one victim.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Influence {
    /// Source component identity.
    pub object: String,
    /// Nonnegative source dissipation, W.
    pub power_w: f64,
    /// Victim temperature rise per source watt, K/W.
    pub transfer_k_per_w: f64,
}

/// One sensitive component's thermal/drift scenario.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Input {
    /// Sensitive component identity.
    pub object: String,
    /// Ambient temperature, °C.
    pub ambient_c: f64,
    /// Temperature at which the nominal value was calibrated, °C.
    pub reference_c: f64,
    /// Signed first-order temperature coefficient, ppm/K.
    pub coefficient_ppm_per_k: f64,
    /// Model-valid temperature interval, °C; no extrapolation is allowed.
    pub valid_temperature_c: [f64; 2],
    /// Complete declared source population, including self-heating if relevant.
    pub influences: Vec<Influence>,
}

/// First-order operating temperature and drift.
#[derive(Debug, Clone, Serialize)]
pub struct ResultRow {
    /// Victim identity.
    pub object: String,
    /// Predicted operating temperature, °C.
    pub temperature_c: f64,
    /// Signed fractional drift relative to calibration, ppm.
    pub drift_ppm: f64,
    /// Largest temperature-rise contributor.
    pub dominant_source: String,
    /// That source's contribution, K.
    pub dominant_rise_k: f64,
}

/// Evaluate Σ Rθ P and first-order drift with O(n log n) identity validation
/// and O(n) numerical accumulation.
///
/// # Errors
/// Rejects missing sources, duplicate identities, invalid temperature intervals,
/// negative power/thermal resistance, out-of-domain predictions and overflow.
pub fn evaluate(input: &Input) -> Result<ResultRow, Error> {
    ensure(
        !input.object.trim().is_empty(),
        "thermal victim identity is blank",
    )?;
    ensure(
        !input.influences.is_empty(),
        "thermal influence population is empty",
    )?;
    identities(input.influences.iter().map(|i| i.object.as_str()))?;
    finite(input.ambient_c, "ambient_c")?;
    finite(input.reference_c, "reference_c")?;
    finite(input.coefficient_ppm_per_k, "coefficient_ppm_per_k")?;
    let [low, high] = input.valid_temperature_c;
    finite(low, "temperature interval low")?;
    finite(high, "temperature interval high")?;
    ensure(low >= -273.15 && low < high, "invalid temperature interval")?;
    ensure(
        (low..=high).contains(&input.reference_c) && (low..=high).contains(&input.ambient_c),
        "reference or ambient outside thermal model domain",
    )?;
    let mut rise = 0.0;
    let mut dominant = &input.influences[0];
    let mut dominant_rise = 0.0;
    for i in &input.influences {
        let term = finite(
            nonnegative(i.power_w, "power_w")?
                * nonnegative(i.transfer_k_per_w, "transfer_k_per_w")?,
            "temperature rise",
        )?;
        rise += term;
        if term > dominant_rise {
            dominant = i;
            dominant_rise = term;
        }
    }
    let temperature = finite(input.ambient_c + rise, "temperature")?;
    ensure(
        (low..=high).contains(&temperature),
        "predicted temperature outside thermal model domain",
    )?;
    Ok(ResultRow {
        object: input.object.clone(),
        temperature_c: temperature,
        drift_ppm: finite(
            (temperature - input.reference_c) * input.coefficient_ppm_per_k,
            "thermal drift",
        )?,
        dominant_source: dominant.object.clone(),
        dominant_rise_k: dominant_rise,
    })
}
