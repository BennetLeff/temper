//! Topology-dependent induction screening; no measured field or hardware verdict.
use std::{error::Error, f64::consts::PI, fmt::Write, fs};
const MU0: f64 = 4e-7 * PI;
#[derive(Clone, Copy)]
struct Annulus {
    outer: f64,
    inner: f64,
    height: f64,
    resistivity: f64,
}
impl Annulus {
    fn checked(
        outer: f64,
        inner: f64,
        height: f64,
        resistivity: f64,
    ) -> Result<Self, &'static str> {
        if [outer, inner, height, resistivity]
            .iter()
            .any(|x| !x.is_finite())
            || outer <= inner
            || inner < 0.
            || height <= 0.
            || resistivity <= 0.
        {
            return Err("invalid annulus or material");
        }
        Ok(Self {
            outer,
            inner,
            height,
            resistivity,
        })
    }
    fn volume(self) -> f64 {
        PI * (self.outer.powi(2) - self.inner.powi(2)) * self.height
    }
    fn power(self, hz: f64, b: f64) -> f64 {
        PI * (2. * PI * hz * b).powi(2) * self.height * (self.outer.powi(4) - self.inner.powi(4))
            / (8. * self.resistivity)
    }
    fn regimes(self, hz: f64) -> (f64, f64, bool) {
        let local_dimension = self.height.min(self.outer - self.inner);
        let delta = (self.resistivity / (PI * hz * MU0)).sqrt();
        let skin = local_dimension / delta;
        let reaction = MU0 / self.resistivity * 2. * PI * hz * self.outer * local_dimension;
        (skin, reaction, skin <= 0.3 && reaction <= 0.3)
    }
}
struct Candidate {
    name: &'static str,
    head: Annulus,
    retainer: Option<Annulus>,
    rho: f64,
    cp: f64,
    k: f64,
    topology: &'static str,
}
fn ring(outer: f64, inner: f64, h: f64, res: f64) -> Annulus {
    Annulus::checked(outer * 1e-3, inner * 1e-3, h * 1e-3, res).expect("hardcoded valid geometry")
}
fn candidates() -> Vec<Candidate> {
    let steel = 0.75e-6;
    let ceramic = 1e9; // Conservative conductivity sensitivity, not universal grade minimum at250C.
    vec![
        Candidate {
            name: "cad_full_skirt_316L",
            head: ring(5., 0., 0.35, steel),
            retainer: Some(ring(5., 4.6, 1.65, steel)),
            rho: 8000.,
            cp: 500.,
            k: 15.,
            topology: "CLOSED_SKIRT",
        },
        Candidate {
            name: "pr1_full_skirt_316L",
            head: ring(5., 0., 0.15, steel),
            retainer: Some(ring(5., 4.6, 1.85, steel)),
            rho: 8000.,
            cp: 500.,
            k: 15.,
            topology: "CLOSED_SKIRT",
        },
        Candidate {
            name: "short_collar_316L",
            head: ring(5., 0., 0.15, steel),
            retainer: Some(ring(5., 4.6, 0.30, steel)),
            rho: 8000.,
            cp: 500.,
            k: 15.,
            topology: "CLOSED_SHORT_COLLAR",
        },
        Candidate {
            name: "skirtless_316L_nonmetal_retention",
            head: ring(5., 0., 0.15, steel),
            retainer: None,
            rho: 8000.,
            cp: 500.,
            k: 15.,
            topology: "METAL_DISK_ONLY_NO_METAL_RETENTION",
        },
        Candidate {
            name: "rubalit710f_nonmetal_retention",
            head: ring(5., 0., 0.30, ceramic),
            retainer: None,
            rho: 3800.,
            cp: 800.,
            k: 25.,
            topology: "NO_MACROSCOPIC_METAL_LOOP",
        },
        Candidate {
            name: "alunit170c_nonmetal_retention",
            head: ring(5., 0., 0.30, ceramic),
            retainer: None,
            rho: 3260.,
            cp: 700.,
            k: 170.,
            topology: "NO_MACROSCOPIC_METAL_LOOP",
        },
        Candidate {
            name: "rubalit710f_closed_316L_ring",
            head: ring(5., 0., 0.30, ceramic),
            retainer: Some(ring(5.5, 4.5, 0.25, steel)),
            rho: 3800.,
            cp: 800.,
            k: 25.,
            topology: "CLOSED_RETAINER_REINTRODUCES_LOOP",
        },
        Candidate {
            name: "alunit170c_closed_316L_ring",
            head: ring(5., 0., 0.30, ceramic),
            retainer: Some(ring(5.5, 4.5, 0.25, steel)),
            rho: 3260.,
            cp: 700.,
            k: 170.,
            topology: "CLOSED_RETAINER_REINTRODUCES_LOOP",
        },
        Candidate {
            name: "PR2_D8_skirtless316L_HEAD_ONLY",
            head: ring(4., 0., 0.15, steel),
            retainer: None,
            rho: 8000.,
            cp: 500.,
            k: 15.,
            topology: "SEE_SUSPENSION_TABLE_FOR_TABS_AND_BEAMS",
        },
        Candidate {
            name: "PR2_D8_alumina_HEAD_ONLY",
            head: ring(4., 0., 0.25, ceramic),
            retainer: None,
            rho: 3800.,
            cp: 800.,
            k: 25.,
            topology: "SEE_SUSPENSION_TABLE_FOR_TABS_AND_BEAMS",
        },
        Candidate {
            name: "PR2_D8_AlN_HEAD_ONLY",
            head: ring(4., 0., 0.25, ceramic),
            retainer: None,
            rho: 3260.,
            cp: 700.,
            k: 170.,
            topology: "SEE_SUSPENSION_TABLE_FOR_TABS_AND_BEAMS",
        },
    ]
}
/// Long, electrically isolated narrow strip in perpendicular uniform RMS field.
/// Finite end corrections and any conductive reconnection are excluded.
fn isolated_strip_power(hz: f64, b: f64, length: f64, width: f64, thickness: f64, res: f64) -> f64 {
    (2. * PI * hz * b).powi(2) / res * length * width * thickness * width.powi(2) / 12.
}
fn main() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let baseline = candidates()[1].head.power(40000., 0.001)
        + candidates()[1]
            .retainer
            .ok_or("baseline skirt absent")?
            .power(40000., 0.001);
    let mut s=String::from("evidence,candidate,hz,B_rms_mT,head_mass_g,metal_retainer_mass_g,head_C_J_K,retainer_C_J_K,head_R_vertical_over6mm2_K_W,head_loss_unshielded_W,retainer_loss_unshielded_W,total_loss_unshielded_W,ratio_to_PR1_same_field,max_wall_over_skin,max_reaction_parameter,regime,topology\n");
    for c in candidates() {
        for hz in [5000., 10000., 20000., 33000., 40000., 60000.] {
            for b in [0.1e-3, 1e-3, 10e-3] {
                let hp = c.head.power(hz, b);
                let rp = c.retainer.map_or(0., |r| r.power(hz, b));
                let (mut sk, mut re, mut valid) = c.head.regimes(hz);
                if let Some(r) = c.retainer {
                    let (a, b, v) = r.regimes(hz);
                    sk = sk.max(a);
                    re = re.max(b);
                    valid &= v;
                }
                let rm = c.retainer.map_or(0., |r| r.volume() * 8000.);
                writeln!(s,"SIMULATED,{},{hz},{},{:.9},{:.9},{:.9},{:.9},{:.9},{hp:.12},{rp:.12},{:.12},{:.6},{sk:.6},{re:.6},{},{}",c.name,b*1000.,c.head.volume()*c.rho*1000.,rm*1000.,c.head.volume()*c.rho*c.cp,rm*500.,c.head.height/(6e-6*c.k),hp+rp,(hp+rp)/(baseline*(hz/40000.).powi(2)*(b/0.001).powi(2)),if valid{"SMALL_PARAMETER_SCREEN_NOT_VALIDATED"}else{"OUTSIDE_SMALL_PARAMETER_REGIME"},c.topology)?;
            }
        }
    }
    fs::write("results/topology_comparison.csv", s)?;
    let mut s=String::from("evidence,outer_r_mm,inner_r_mm,height_mm,hz,B_rms_mT,loss_unshielded_W,ratio_to_PR1_full_skirt,regime\n");
    for outer in [5., 5.5, 7., 9.] {
        for width in [0.25, 0.5, 1.] {
            for h in [0.1, 0.25, 0.5] {
                let r = ring(outer, outer - width, h, 0.75e-6);
                let power = r.power(40000., 0.001);
                writeln!(
                    s,
                    "SIMULATED,{outer},{},{h},40000,1,{power:.9},{:.6},{}",
                    outer - width,
                    power / baseline,
                    if r.regimes(40000.).2 {
                        "SMALL_PARAMETER_SCREEN_NOT_VALIDATED"
                    } else {
                        "OUTSIDE_SMALL_PARAMETER_REGIME"
                    }
                )?;
            }
        }
    }
    fs::write("results/retainer_radius_sweep.csv", s)?;
    let mut s=String::from("evidence,hz,B_rms_mT,clip_count,clip_length_mm,clip_width_mm,clip_thickness_mm,isolated_clip_loss_W,closed_ring_loss_W,status\n");
    for hz in [20000., 40000., 60000.] {
        for b in [0.1e-3, 1e-3, 10e-3] {
            let clip = 3. * isolated_strip_power(hz, b, 3e-3, 0.5e-3, 0.1e-3, 0.75e-6);
            let closed = ring(5.5, 4.5, 0.25, 0.75e-6).power(hz, b);
            writeln!(s,"SIMULATED,{hz},{},3,3,0.5,0.1,{clip:.12},{closed:.12},IDEAL_ISOLATED_STRIP_ESTIMATE_RECONNECTION_INVALIDATES",b*1000.)?;
        }
    }
    fs::write("results/clip_topology.csv", s)?;
    let mut s=String::from("evidence,hz,head_B_rms_mT,beam_to_head_B_ratio,D8_316L_head_W,three_316L_tabs_strip_W,three_X750_beams_strip_W,metal_head_subtotal_W,ceramic_head_metal_hardware_subtotal_W,tab_mass_g,beam_mass_g,tab_heat_capacity_J_K,beam_heat_capacity_J_K,beam_1D_conductance_W_K,status\n");
    for hz in [20000., 40000., 60000.] {
        for b in [0.1e-3, 1e-3, 10e-3] {
            for field_ratio in [0.1, 0.3, 1.] {
                let head = ring(4., 0., 0.15, 0.75e-6).power(hz, b);
                let tabs = 3. * isolated_strip_power(hz, b, 2.2e-3, 0.8e-3, 0.15e-3, 0.75e-6);
                let beams =
                    3. * isolated_strip_power(hz, b * field_ratio, 7e-3, 2.1e-3, 0.08e-3, 1.22e-6);
                let tab_mass = 3. * 2.2e-3 * 0.8e-3 * 0.15e-3 * 8000.;
                let beam_mass = 3. * 7e-3 * 2.1e-3 * 0.08e-3 * 8280.;
                let beam_g = 3. * 12. * 2.1e-3 * 0.08e-3 / 7e-3;
                writeln!(s,"SIMULATED,{hz},{},{field_ratio},{head:.12},{tabs:.12},{beams:.12},{:.12},{:.12},{:.9},{:.9},{:.9},{:.9},{beam_g:.9},OUTSIDE_LONG_STRIP_ASPECT_REGIME_NO_HARDWARE_PREDICTION",b*1000.,head+tabs+beams,tabs+beams,tab_mass*1000.,beam_mass*1000.,tab_mass*500.,beam_mass*431.)?;
            }
        }
    }
    fs::write("results/PR2_suspension_sensitivity.csv", s)?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn head_and_skirt_reproduce_prior_formula() {
        let c = &candidates()[1];
        assert!(
            (c.head.power(40000., 0.001) + c.retainer.unwrap().power(40000., 0.001)
                - 0.013946065631)
                .abs()
                < 1e-11
        );
    }
    #[test]
    fn zero_field_zero_power() {
        assert_eq!(candidates()[0].head.power(40000., 0.), 0.);
    }
    #[test]
    fn field_quadratic() {
        let r = candidates()[1].head;
        assert_eq!(r.power(40000., 0.002) / r.power(40000., 0.001), 4.);
    }
    #[test]
    fn removed_skirt_does_not_remove_disk_loss() {
        assert!(candidates()[3].head.power(40000., 0.001) > 0.003);
    }
    #[test]
    fn small_parameter_screen_detects_full_skirt() {
        assert!(!candidates()[1].retainer.unwrap().regimes(40000.).2);
    }
    #[test]
    fn larger_retainer_radius_increases_loss() {
        assert!(
            ring(7., 6., 0.25, 0.75e-6).power(40000., 0.001)
                > ring(5.5, 4.5, 0.25, 0.75e-6).power(40000., 0.001)
        );
    }
    #[test]
    fn ceramic_does_not_hide_retainer_loss() {
        let c = &candidates()[6];
        assert!(c.retainer.unwrap().power(40000., 0.001) > 1e12 * c.head.power(40000., 0.001));
    }
    #[test]
    fn unit_conversion_resistivity_cm_to_m() {
        let ohm_cm = 1e11;
        assert_eq!(ohm_cm * 0.01, 1e9);
    }
    #[test]
    fn invalid_geometry_rejected() {
        assert!(Annulus::checked(0.005, 0.006, 0.0001, 0.75e-6).is_err());
    }
    #[test]
    fn nonfinite_geometry_rejected() {
        assert!(Annulus::checked(f64::NAN, 0., 0.0001, 0.75e-6).is_err());
    }
    #[test]
    fn strip_width_scaling_is_cubic() {
        assert!(
            (isolated_strip_power(40000., 0.001, 0.003, 0.001, 0.0001, 0.75e-6)
                / isolated_strip_power(40000., 0.001, 0.003, 0.0005, 0.0001, 0.75e-6)
                - 8.)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn full_volume_is_not_roof_only() {
        let c = &candidates()[1];
        assert!(
            (1e9 * (c.head.volume() + c.retainer.unwrap().volume()) - 34.098846661).abs() < 1e-8
        );
    }
    #[test]
    fn diameter_reduction_respects_fourth_power() {
        assert!(
            (ring(4., 0., 0.15, 0.75e-6).power(40000., 0.001)
                / ring(5., 0., 0.15, 0.75e-6).power(40000., 0.001)
                - 0.4096)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn independent_beam_field_enters_quadratically() {
        assert!(
            (isolated_strip_power(40000., 0.0003, 0.007, 0.0021, 0.00008, 1.22e-6)
                / isolated_strip_power(40000., 0.001, 0.007, 0.0021, 0.00008, 1.22e-6)
                - 0.09)
                .abs()
                < 1e-12
        );
    }
}
