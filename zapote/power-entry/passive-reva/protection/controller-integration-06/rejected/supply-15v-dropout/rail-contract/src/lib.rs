//! Fail-closed checks for the A5 HOT15/5V producer boundary.
//!
//! These checks validate the interface contract, not regulator silicon.  The
//! electrical source and the manufacturer data remain the authorities for pin
//! identity, tolerance, thermal and transient qualification.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RailVerdict {
    Pass,
    Fail,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RailSample {
    pub aux_raw_v: f64,
    pub aux15_v: f64,
    pub logic5_v: f64,
    /// True only when the independent TPS3700 overvoltage output is released.
    pub aux15_ov_n: bool,
    pub aux15_current_ma: f64,
    pub logic5_current_ma: f64,
}

const RAW_MIN: f64 = 14.625;
const RAW_OVP_MAX: f64 = 20.25;
const AUX15_MIN: f64 = 14.25;
const AUX15_MAX: f64 = 15.75;
const LOGIC5_MIN: f64 = 4.75;
const LOGIC5_MAX: f64 = 5.25;
const AUX15_CURRENT_MAX_MA: f64 = 75.0;
const LOGIC5_CURRENT_MAX_MA: f64 = 200.0;

fn finite_in_range(value: f64, low: f64, high: f64) -> bool {
    value.is_finite() && value >= low && value <= high
}

/// Return Pass only when every required producer and consumer condition is
/// explicitly present. Unknown/non-finite values fail closed.
pub fn check(sample: RailSample) -> RailVerdict {
    if !finite_in_range(sample.aux_raw_v, RAW_MIN, RAW_OVP_MAX)
        || !finite_in_range(sample.aux15_v, AUX15_MIN, AUX15_MAX)
        || !finite_in_range(sample.logic5_v, LOGIC5_MIN, LOGIC5_MAX)
        || !sample.aux15_ov_n
        || !sample.aux15_current_ma.is_finite()
        || sample.aux15_current_ma < 0.0
        || sample.aux15_current_ma > AUX15_CURRENT_MAX_MA
        || !sample.logic5_current_ma.is_finite()
        || sample.logic5_current_ma < 0.0
        || sample.logic5_current_ma > LOGIC5_CURRENT_MAX_MA
    {
        return RailVerdict::Fail;
    }
    RailVerdict::Pass
}

pub fn is_safe(sample: RailSample) -> bool {
    check(sample) == RailVerdict::Pass
}

#[cfg(test)]
mod tests {
    use super::*;

    fn nominal() -> RailSample {
        RailSample {
            aux_raw_v: 15.0,
            aux15_v: 15.0,
            logic5_v: 5.0,
            aux15_ov_n: true,
            aux15_current_ma: 60.0,
            logic5_current_ma: 100.0,
        }
    }

    #[test]
    fn nominal_rails_pass() {
        assert_eq!(check(nominal()), RailVerdict::Pass);
    }

    #[test]
    fn producer_ovp_is_safe_after_limited_regulator() {
        let mut s = nominal();
        s.aux_raw_v = 20.25;
        s.aux15_v = 15.0;
        assert!(is_safe(s));
    }

    #[test]
    fn raw_ovp_reaching_driver_fails_closed() {
        let mut s = nominal();
        s.aux_raw_v = 20.25;
        s.aux15_v = 20.25;
        assert_eq!(check(s), RailVerdict::Fail);
    }

    #[test]
    fn dropout_fails_closed() {
        let mut s = nominal();
        s.aux15_v = 14.0;
        assert_eq!(check(s), RailVerdict::Fail);
    }

    #[test]
    fn logic5_loss_fails_closed() {
        let mut s = nominal();
        s.logic5_v = 0.0;
        assert_eq!(check(s), RailVerdict::Fail);
    }

    #[test]
    fn load_limits_are_enforced() {
        let mut s = nominal();
        s.aux15_current_ma = 75.1;
        assert_eq!(check(s), RailVerdict::Fail);
        s.aux15_current_ma = 75.0;
        s.logic5_current_ma = 200.1;
        assert_eq!(check(s), RailVerdict::Fail);
    }

    #[test]
    fn unknown_values_fail_closed() {
        let mut s = nominal();
        s.aux15_v = f64::NAN;
        assert_eq!(check(s), RailVerdict::Fail);
        s.aux15_v = f64::INFINITY;
        assert_eq!(check(s), RailVerdict::Fail);
    }
}
