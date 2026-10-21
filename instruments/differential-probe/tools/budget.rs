//! Rail-referenced warning-threshold budget, shared by tools/check.rs (the
//! committed design) and tools/fee_consolidation.rs (candidate part swaps).
//! Included with `#[path = "budget.rs"] mod budget;`; one implementation only.
//!
//! Ladder per polarity: rail - 66.5k (R87/R91) - LIM - 1k (R88/R92) - OUT_LIM -
//! 10k (R89/R93) - GND. Rails: ADP7142 (R81 over R82) and ADP7182 ADJ (R83 over
//! R84). Selected-output sense divider R71/R72, 10k/10k.
#![allow(dead_code)]

/// Worst-case resistor deviation over -25..85 C: initial tolerance plus TCR over
/// the 60 C worst displacement from 25 C.
pub const PRECISION: f64 = 0.001 + 25e-6 * 60.; // Yageo RT, 0.1 %, 25 ppm/C
pub const BASIC: f64 = 0.01 + 100e-6 * 60.; // Uni-Royal 0805W8F, 1 %, 100 ppm/C

/// Deviation class of a resistor MPN used in the budget; unknown MPNs panic, so
/// a BOM change cannot silently keep the old tolerance.
pub fn tolerance(mpn: &str) -> f64 {
    if mpn.starts_with("RT0805BRD07") || mpn.starts_with("RT0603BRD07") {
        PRECISION
    } else if mpn.starts_with("0805W8F") {
        BASIC
    } else {
        panic!("no tolerance class for {mpn}")
    }
}

#[derive(Clone, Copy)]
pub struct Res {
    pub nom: f64,
    pub tol: f64,
}

#[derive(Clone, Copy)]
pub struct Warn {
    pub r81: Res,
    pub r82: Res,
    pub r83: Res,
    pub r84: Res,
    pub ra: Res,
    pub rb: Res,
    pub rc: Res,
    pub sense: f64,
}

impl Warn {
    /// Nominal values with every resistor at the 0.1 % / 25 ppm class.
    pub fn precision() -> Self {
        let r = |nom| Res { nom, tol: PRECISION };
        Warn { r81: r(30_000.), r82: r(10_000.), r83: r(29_400.), r84: r(10_000.), ra: r(66_500.), rb: r(1_000.), rc: r(10_000.), sense: PRECISION }
    }
}

pub struct Out {
    pub pos_nom: f64,
    pub neg_nom: f64,
    pub pos_min: f64,
    pub neg_min: f64,
    pub pos_max: f64,
    pub neg_max: f64,
    pub rail_min: f64,
    pub rail_max: f64,
    pub tip_nom: f64,
    pub out_nom: f64,
    pub tip_max: f64,
    pub selected_max: f64,
    pub wide_late: f64,
    pub fine_late: f64,
    pub tip_early: f64,
    pub wide_early: f64,
    pub fine_early: f64,
}

pub const WIDE_OFFSET: f64 = 0.025;
pub const FINE_OFFSET: f64 = 0.130;

/// Untrimmed acceptance offsets (the budget before the Rev C zero trims); kept for
/// tools/fee_consolidation.rs, whose committed comparisons predate the trims.
pub fn warning(p: &Warn) -> Out {
    warning_with(p, WIDE_OFFSET, FINE_OFFSET)
}

/// Late/early-trip budget for a stated acceptance limit on the actual selected-path
/// zero (V at SELECTED) on each range.
pub fn warning_with(p: &Warn, wide_offset: f64, fine_offset: f64) -> Out {
    // Feedback ratio corners: Vout = Vref (1 + Rtop / Rbottom).
    let fb_hi = |t: Res, b: Res| 1. + t.nom * (1. + t.tol) / (b.nom * (1. - b.tol));
    let fb_lo = |t: Res, b: Res| 1. + t.nom * (1. - t.tol) / (b.nom * (1. + b.tol));
    // ADP7142 ADJ 1.2 V: +/-1.8 % over line/load/TJ -40..125 C; ADP7182 ADJ
    // -1.22 V nominal, 1.184..1.244 V magnitude (-2.95/+1.97 %).
    let pos_max = 1.2 * 1.018 * fb_hi(p.r81, p.r82);
    let neg_max = 1.244 * fb_hi(p.r83, p.r84);
    let pos_min = 1.2 * (1. - 0.018) * fb_lo(p.r81, p.r82);
    let neg_min = 1.184 * fb_lo(p.r83, p.r84);
    warning_rails(p, wide_offset, fine_offset, (pos_min, pos_max, neg_min, neg_max))
}

/// The same budget for stated rail magnitude ranges (pos_min, pos_max, neg_min,
/// neg_max), e.g. the band a rail monitor accepts instead of the regulated range.
pub fn warning_rails(p: &Warn, wide_offset: f64, fine_offset: f64, rails: (f64, f64, f64, f64)) -> Out {
    let (pos_min, pos_max, neg_min, neg_max) = rails;
    let rail_max = pos_max.max(neg_max);
    let rail_min = pos_min.min(neg_min);
    let (ra, rb, rc) = (p.ra, p.rb, p.rc);
    let hi = |r: Res| r.nom * (1. + r.tol);
    let lo = |r: Res| r.nom * (1. - r.tol);
    let tip_div_max = (hi(rb) + hi(rc)) / (lo(ra) + hi(rb) + hi(rc));
    let out_div_max = hi(rc) / (lo(ra) + lo(rb) + hi(rc));
    let tip_div_min = (lo(rb) + lo(rc)) / (hi(ra) + lo(rb) + lo(rc));
    let out_div_min = lo(rc) / (hi(ra) + hi(rb) + lo(rc));
    let comp_error = 0.0055 + 0.0002; // comparator offset and input-bias/PSRR allowance.
    let tip_max = (rail_max * tip_div_max + comp_error + 0.005) / 0.98 * 2000.;
    let sense_min = (1. - p.sense) / 2.; // matched nominal 10k/10k, opposing tolerances.
    let selected_max = (rail_max * out_div_max + comp_error) / sense_min;
    let wide_late = (selected_max + wide_offset) / 0.98 * 1000.;
    let fine_late = (selected_max + fine_offset) / 0.98 * 200.;
    let total = ra.nom + rb.nom + rc.nom;
    let tip_nom = 4.8 * (rb.nom + rc.nom) / total;
    let out_nom = 4.8 * rc.nom / total;
    let tip_early = ((rail_min * tip_div_min - comp_error - 0.005) / 1.02 * 2000.).max(0.);
    let sel_early = (rail_min * out_div_min - comp_error) / ((1. + p.sense) / 2.);
    Out {
        pos_nom: 1.2 * (1. + p.r81.nom / p.r82.nom),
        neg_nom: 1.22 * (1. + p.r83.nom / p.r84.nom),
        pos_min,
        neg_min,
        pos_max,
        neg_max,
        rail_min,
        rail_max,
        tip_nom,
        out_nom,
        tip_max,
        selected_max,
        wide_late,
        fine_late,
        tip_early,
        wide_early: (sel_early - wide_offset).max(0.) / 1.02 * 1000.,
        fine_early: (sel_early - fine_offset).max(0.) / 1.02 * 200.,
    }
}
