//! `FabricationEnvelope` — a portable fabrication-tolerance shape for Phase
//! 2's manufacturing-variation sweep.
//!
//! Origin: U1 of
//! `docs/plans/2026-08-11-001-feat-wasm-tier-phase2-plan.md`.
//!
//! # Shape, not values
//!
//! This module names the fabrication envelope a board will eventually be
//! swept across (U4, a *later*, unimplemented unit): etch/trace-width
//! tolerance, layer-registration offset, copper-thickness variation, drill
//! tolerance, solder-mask registration. It does **not** implement the
//! sweep kernel (U4), the cost measurement (U3), the value-sourcing
//! maintainer question (U2, parent Q3 — still open), or the non-vacuity
//! canary (U5). Those are separate, later units; see the plan.
//!
//! **No field here is presented as fabricator-verified.** The four axes
//! that carry non-placeholder numbers are reproduced from `FabPreset`
//! (`temper-io-types`) and the pre-migration tolerances implementation
//! (formerly pinned as `ToleranceTable` in `temper-design-bundle`, deleted
//! 2026-08-20 with the orphaned tolerances kernel cluster) —
//! differential-testing artifacts ported from a pre-migration Python
//! implementation for parity, not sourced from a real fabricator capability
//! sheet (see [`VALUE_SOURCES`] and the module-level "Value sourcing"
//! section below). The fifth axis, copper-thickness variation, has no
//! source anywhere in the repo and is left `None` — a placeholder, not an
//! invented number — pending U2/O2.
//!
//! # Why this crate, not `temper-io-types` or `temper-design-bundle`
//!
//! Two fabrication-tolerance representations already exist in the repo,
//! and neither is the right *dependency* for a wasm32 tier-dispatch type
//! (plan D2.2):
//!
//! - `packages/temper-design-bundle/src/manufacturing_tolerances.rs`
//!   (deleted 2026-08-20) previously held `ToleranceTable` as a
//!   `#[pyclass]` carrying unconditional `use pyo3::prelude::*` and
//!   `Py<PyAny>` dict fields (`etch_tolerance`, `registration`), and the
//!   whole module was gated `#[cfg(feature = "python")]` at that crate's
//!   `lib.rs`. It was structurally absent from any `wasm32-unknown-unknown
//!   --no-default-features` build — not a candidate to depend on or
//!   retrofit here (that retrofit is explicitly out of this plan's scope).
//! - `packages/temper-io-types/src/placer_core/manufacturing.rs`'s
//!   `FabPreset` *is* plain Rust (`#[derive(Clone, Debug, PartialEq)]`, no
//!   `pyo3`), wasm32-buildable, and already registered in that crate's own
//!   wasm test registry. But `temper-io-types` is not one of the 6
//!   **deployed** tiers today (no Cloudflare Worker, no
//!   `wasm_tier_topology.json` entry, no nightly R19 arm) — depending on
//!   it from `temper-drc-rs`, a deployed tier, would pull an undeployed
//!   crate's release cadence into a deployed one for a phase that does not
//!   need that unblock. Deploying `temper-io-types` is its own unit for
//!   whoever owns tier-topology expansion, not this one (Scope Boundaries,
//!   Outstanding Question O1 below).
//!
//! `FabricationEnvelope` is therefore a new, small, dependency-free type
//! local to this crate — deliberately shaped like `FabPreset` (same field
//! meanings and the same non-placeholder default values for the four axes
//! `FabPreset` already carries) so the two representations do not diverge
//! by accident, without `temper-drc-rs` taking on `temper-io-types` as a
//! dependency.
//!
//! ## Outstanding Question O1 — should this converge with `FabPreset` later?
//!
//! Recorded here rather than only in the PR body, since it is a property
//! of this type's shape: if `temper-io-types` is ever deployed as its own
//! tier, maintaining two field-identical representations stops paying for
//! itself. Convergence is not purely mechanical, though — `FabPreset` has
//! no `copper_thickness_variation_mm` or `solder_mask_registration_mm`
//! axis today, so convergence would first need those two upstreamed (or
//! `FabricationEnvelope` kept as a strict superset). Left open, per the
//! plan's Scope Boundaries, for whoever executes that deployment unit.
//!
//! # No resolution / grid-cell-size field — on purpose
//!
//! This type has no field for occupancy-grid resolution, raster cell size,
//! or any other rasterization parameter, and it should never grow one. Per
//! the parent plan's R2 measurement, a six-layer occupancy grid costs 24 MB
//! at 0.1 mm resolution and **2,400 MB at 0.01 mm** — against a 128 MiB
//! wasm32 isolate ceiling. Design decision D2.3 is that a sweep point
//! perturbs *geometry* (trace widths, pad/hole edges, layer offsets) fed
//! into the existing rule kernels at whatever resolution production
//! already uses, and never varies raster resolution itself. Every field
//! below is a tolerance *band on geometry*, not a rendering parameter, so
//! there is nowhere on this type to plug in a resolution value — a future
//! sweep unit that wants to vary resolution has to invent a different type
//! to do it, not extend this one.
//!
//! # Value sourcing (R2.2)
//!
//! | Field | Source |
//! |---|---|
//! | `trace_width_tolerance_pct` | `FabPreset` (differential-testing artifact) |
//! | `min_trace_width_mm` | `FabPreset` (differential-testing artifact) |
//! | `min_clearance_mm` | `FabPreset` (differential-testing artifact) |
//! | `etch_undercut_mm` | `FabPreset` (differential-testing artifact) |
//! | `layer_registration_mm` | `FabPreset` (differential-testing artifact) |
//! | `drill_tolerance_mm` | `FabPreset` (differential-testing artifact) |
//! | `copper_thickness_variation_mm` | **TBD, needs maintainer** — no source in-repo (U2/O2) |
//! | `solder_mask_registration_mm` | pre-migration tolerances impl (formerly `ToleranceTable`, deleted 2026-08-20) |
//!
//! [`VALUE_SOURCES`] is the same table, machine-checkable (see
//! `value_sources_cover_every_axis` below) so it cannot silently drift from
//! the struct's field list.

/// The fabrication envelope a board is (eventually) swept across: per-axis
/// tolerance bands meant to be fed as *geometry perturbations* into the
/// existing DRC/ERC/safety rule kernels, at whatever resolution the
/// consuming rule already uses in production. See the module docs for why
/// there is deliberately no resolution field.
///
/// Field shape and the four non-placeholder defaults are seeded from
/// `FabPreset` (`packages/temper-io-types/src/placer_core/manufacturing.rs`);
/// `solder_mask_registration_mm`'s default reproduces the pre-migration
/// tolerances implementation's dataclass default (0.075) — the
/// `ToleranceTable` pyclass that used to carry it was deleted 2026-08-20
/// with the orphaned tolerances kernel cluster.
/// Neither source is fabricator-verified — see the module docs.
#[derive(Clone, Debug, PartialEq)]
pub struct FabricationEnvelope {
    /// Provenance label for this envelope point (e.g. `"jlcpcb_standard"`,
    /// or empty for an anonymous/default envelope). Not itself a swept
    /// axis — excluded from [`VALUE_SOURCES`].
    pub name: String,

    /// Etch/trace-width tolerance, as a fraction of nominal trace width
    /// (e.g. `0.15` means the realized width may deviate roughly ±15% from
    /// the drawn width). **Unit: dimensionless fraction**, not mm.
    /// Physical meaning: photoresist and etch-process deviation between
    /// the designed copper trace width and the as-fabricated width.
    pub trace_width_tolerance_pct: f64,

    /// Minimum trace width the fabrication process can reliably produce.
    /// **Unit: mm.** A sweep perturbing geometry toward this floor
    /// exercises the narrowest copper the process claims to support.
    pub min_trace_width_mm: f64,

    /// Minimum copper-to-copper clearance the fabrication process can
    /// reliably hold between adjacent conductors. **Unit: mm.**
    pub min_clearance_mm: f64,

    /// Lateral etch undercut per copper edge: how much copper is removed
    /// from each trace/pad edge beyond the mask opening during etching.
    /// **Unit: mm, per edge.** Etch undercut widens gaps (reduces
    /// clearance) and narrows traces simultaneously — the two-sided
    /// effect a worst-case sweep point needs to model together.
    pub etch_undercut_mm: f64,

    /// Maximum layer-to-layer registration offset: misalignment between
    /// the drawn layer stack-up and the as-laminated/as-imaged stack
    /// (lamination press and imaging-step drift). **Unit: mm.**
    pub layer_registration_mm: f64,

    /// Drill-bit positional/diameter tolerance for through-holes and via
    /// barrels. **Unit: mm.**
    pub drill_tolerance_mm: f64,

    /// Copper-thickness variation relative to nominal copper weight across
    /// a panel or board. **Unit: mm** (thickness delta, not a plating
    /// percentage). **Not modeled anywhere else in this repo.** `None`
    /// means "not sourced yet" — a placeholder, not an invented value; see
    /// U2 / Outstanding Question O2 (parent Q3, unresolved since
    /// 2026-08-03) before treating any `Some(value)` assigned here as
    /// fabricator-verified.
    pub copper_thickness_variation_mm: Option<f64>,

    /// Solder-mask-to-copper registration tolerance: how far a solder-mask
    /// opening can drift from the pad it is meant to expose. **Unit: mm.**
    /// The one axis `FabPreset` lacks that the pre-migration tolerances
    /// dataclass had (default `0.075`; the `ToleranceTable` pyclass that
    /// carried it was deleted 2026-08-20).
    pub solder_mask_registration_mm: f64,
}

impl Default for FabricationEnvelope {
    /// The four `FabPreset`-sourced axes take `FabPreset::default()`'s
    /// values verbatim; `solder_mask_registration_mm` takes the
    /// pre-migration tolerances dataclass default (`0.075`);
    /// `copper_thickness_variation_mm` is `None` (TBD, needs maintainer —
    /// no source exists in-repo; see U2/O2). None of these values are
    /// fabricator-verified.
    fn default() -> Self {
        FabricationEnvelope {
            name: String::new(),
            trace_width_tolerance_pct: 0.15,
            min_trace_width_mm: 0.127,
            min_clearance_mm: 0.127,
            etch_undercut_mm: 0.05,
            layer_registration_mm: 0.1,
            drill_tolerance_mm: 0.05,
            copper_thickness_variation_mm: None,
            solder_mask_registration_mm: 0.075,
        }
    }
}

impl FabricationEnvelope {
    /// Mirrors `FabPreset::jlcpcb_standard()` for the four axes it
    /// carries; `solder_mask_registration_mm` and
    /// `copper_thickness_variation_mm` take the type default (see
    /// [`Default`]). Not fabricator-verified — see module docs.
    pub fn jlcpcb_standard() -> Self {
        FabricationEnvelope {
            name: "jlcpcb_standard".to_string(),
            trace_width_tolerance_pct: 0.15,
            min_trace_width_mm: 0.127,
            min_clearance_mm: 0.127,
            etch_undercut_mm: 0.05,
            layer_registration_mm: 0.1,
            ..FabricationEnvelope::default()
        }
    }

    /// Mirrors `FabPreset::jlcpcb_hdi()`. Not fabricator-verified.
    pub fn jlcpcb_hdi() -> Self {
        FabricationEnvelope {
            name: "jlcpcb_hdi".to_string(),
            trace_width_tolerance_pct: 0.10,
            min_trace_width_mm: 0.075,
            min_clearance_mm: 0.075,
            etch_undercut_mm: 0.03,
            layer_registration_mm: 0.05,
            ..FabricationEnvelope::default()
        }
    }

    /// Mirrors `FabPreset::oshpark()`. Note (same as the reference): OSH
    /// Park does **not** override `layer_registration_mm`, so it keeps the
    /// `0.1` type default — reproduced as-is, not a transcription gap.
    /// Not fabricator-verified.
    pub fn oshpark() -> Self {
        FabricationEnvelope {
            name: "oshpark".to_string(),
            trace_width_tolerance_pct: 0.12,
            min_trace_width_mm: 0.152,
            min_clearance_mm: 0.152,
            etch_undercut_mm: 0.04,
            ..FabricationEnvelope::default()
        }
    }
}

/// Where a [`FabricationEnvelope`] axis's default value comes from (R2.2).
/// Every variant is explicitly *not* "fabricator-verified" — that status
/// does not exist yet anywhere in this enum, matching U2's still-open
/// maintainer question (parent Q3).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ValueSource {
    /// Reproduced from `FabPreset`'s default/preset constants
    /// (`temper-io-types`) — itself a differential-testing artifact ported
    /// from a pre-migration Python placer-core implementation for parity,
    /// not independently confirmed against a real PCB fabricator's
    /// capability sheet.
    FabPresetDerived,
    /// Reproduced from the pre-migration tolerances dataclass's default
    /// (`0.075`, formerly carried by `ToleranceTable` in
    /// `temper-design-bundle`, deleted 2026-08-20), same
    /// differential-testing caveat as `FabPresetDerived`.
    ToleranceTableDerived,
    /// No source anywhere in the repo. The field carries a placeholder
    /// (`None`), not an invented value; see U2 / Outstanding Question O2.
    TbdNeedsMaintainer,
}

/// `(field name, ValueSource)` for every swept axis on
/// [`FabricationEnvelope`], in declaration order — `name` (provenance
/// metadata, not an axis) is excluded. This is U1's evidence-of-closure
/// source table ("the evidence doc's source table has an entry for every
/// axis, with no axis silently omitted"), kept in code so it cannot drift
/// from the struct without a compile-checkable test failing
/// (`value_sources_cover_every_axis`).
pub const VALUE_SOURCES: &[(&str, ValueSource)] = &[
    ("trace_width_tolerance_pct", ValueSource::FabPresetDerived),
    ("min_trace_width_mm", ValueSource::FabPresetDerived),
    ("min_clearance_mm", ValueSource::FabPresetDerived),
    ("etch_undercut_mm", ValueSource::FabPresetDerived),
    ("layer_registration_mm", ValueSource::FabPresetDerived),
    ("drill_tolerance_mm", ValueSource::FabPresetDerived),
    ("copper_thickness_variation_mm", ValueSource::TbdNeedsMaintainer),
    ("solder_mask_registration_mm", ValueSource::ToleranceTableDerived),
];

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn default_matches_fab_preset_reference_values() {
        let env = FabricationEnvelope::default();
        assert_eq!(env.trace_width_tolerance_pct, 0.15);
        assert_eq!(env.min_trace_width_mm, 0.127);
        assert_eq!(env.min_clearance_mm, 0.127);
        assert_eq!(env.etch_undercut_mm, 0.05);
        assert_eq!(env.layer_registration_mm, 0.1);
        assert_eq!(env.drill_tolerance_mm, 0.05);
        assert_eq!(env.solder_mask_registration_mm, 0.075);
    }

    #[cfg_attr(test, test)]
    fn copper_thickness_variation_is_a_placeholder_not_an_invented_value() {
        // Must stay None until U2 sources a real value (parent Q3/O2) —
        // this test fails loudly if a future edit quietly fills it in.
        assert_eq!(FabricationEnvelope::default().copper_thickness_variation_mm, None);
        assert_eq!(FabricationEnvelope::jlcpcb_standard().copper_thickness_variation_mm, None);
    }

    #[cfg_attr(test, test)]
    fn jlcpcb_standard_matches_fab_preset_reference() {
        let env = FabricationEnvelope::jlcpcb_standard();
        assert_eq!(env.name, "jlcpcb_standard");
        assert_eq!(env.trace_width_tolerance_pct, 0.15);
        assert_eq!(env.min_trace_width_mm, 0.127);
        assert_eq!(env.min_clearance_mm, 0.127);
        assert_eq!(env.etch_undercut_mm, 0.05);
        assert_eq!(env.layer_registration_mm, 0.1);
        // drill_tolerance_mm / solder_mask_registration_mm inherited from
        // the type default, same as FabPreset's own preset constructors.
        assert_eq!(env.drill_tolerance_mm, 0.05);
        assert_eq!(env.solder_mask_registration_mm, 0.075);
    }

    #[cfg_attr(test, test)]
    fn jlcpcb_hdi_is_tighter_than_standard() {
        let standard = FabricationEnvelope::jlcpcb_standard();
        let hdi = FabricationEnvelope::jlcpcb_hdi();
        assert_eq!(hdi.name, "jlcpcb_hdi");
        assert!(hdi.min_trace_width_mm < standard.min_trace_width_mm);
        assert!(hdi.min_clearance_mm < standard.min_clearance_mm);
        assert!(hdi.etch_undercut_mm < standard.etch_undercut_mm);
        assert!(hdi.layer_registration_mm < standard.layer_registration_mm);
    }

    #[cfg_attr(test, test)]
    fn oshpark_keeps_the_default_registration() {
        // Mirrors FabPreset's own `oshpark_keeps_the_default_registration`
        // test — the reference does not override this field for OSH Park.
        assert_eq!(FabricationEnvelope::oshpark().layer_registration_mm, 0.1);
        assert_eq!(FabricationEnvelope::oshpark().name, "oshpark");
    }

    #[cfg_attr(test, test)]
    fn value_sources_cover_every_axis() {
        // Every field except `name` must have a VALUE_SOURCES entry
        // (R2.2 / U1 evidence-of-closure: "no axis silently omitted").
        let expected_axes = [
            "trace_width_tolerance_pct",
            "min_trace_width_mm",
            "min_clearance_mm",
            "etch_undercut_mm",
            "layer_registration_mm",
            "drill_tolerance_mm",
            "copper_thickness_variation_mm",
            "solder_mask_registration_mm",
        ];
        assert_eq!(VALUE_SOURCES.len(), expected_axes.len());
        for axis in expected_axes {
            assert!(
                VALUE_SOURCES.iter().any(|(name, _)| *name == axis),
                "axis {axis} missing from VALUE_SOURCES"
            );
        }
    }

    #[cfg_attr(test, test)]
    fn copper_thickness_variation_source_is_tbd_not_fab_preset_derived() {
        let entry = VALUE_SOURCES
            .iter()
            .find(|(name, _)| *name == "copper_thickness_variation_mm")
            .expect("copper_thickness_variation_mm must be in VALUE_SOURCES");
        assert_eq!(entry.1, ValueSource::TbdNeedsMaintainer);
    }

    #[cfg_attr(test, test)]
    fn envelopes_are_cloneable_and_comparable() {
        // Plain-data shape check: Clone/PartialEq are load-bearing for a
        // future sweep unit that will hold many envelope points at once.
        let a = FabricationEnvelope::jlcpcb_standard();
        let b = a.clone();
        assert_eq!(a, b);
        assert_ne!(a, FabricationEnvelope::oshpark());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("manufacturing::tests::default_matches_fab_preset_reference_values", default_matches_fab_preset_reference_values),
        ("manufacturing::tests::copper_thickness_variation_is_a_placeholder_not_an_invented_value", copper_thickness_variation_is_a_placeholder_not_an_invented_value),
        ("manufacturing::tests::jlcpcb_standard_matches_fab_preset_reference", jlcpcb_standard_matches_fab_preset_reference),
        ("manufacturing::tests::jlcpcb_hdi_is_tighter_than_standard", jlcpcb_hdi_is_tighter_than_standard),
        ("manufacturing::tests::oshpark_keeps_the_default_registration", oshpark_keeps_the_default_registration),
        ("manufacturing::tests::value_sources_cover_every_axis", value_sources_cover_every_axis),
        ("manufacturing::tests::copper_thickness_variation_source_is_tbd_not_fab_preset_derived", copper_thickness_variation_source_is_tbd_not_fab_preset_derived),
        ("manufacturing::tests::envelopes_are_cloneable_and_comparable", envelopes_are_cloneable_and_comparable),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
