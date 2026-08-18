//! Type-system guard enforcement, via `trybuild`.
//!
//! # Why this exists alongside the `compile_fail` doctests
//!
//! Every safety-critical invariant in this crate that is enforced by the type
//! system carries a `compile_fail` doctest. Those doctests assert exactly one
//! thing: *the snippet does not compile*. They do NOT assert **why**.
//!
//! Measured on this repo, rustc 1.97.1 (2026-08-17):
//!
//! * A `compile_fail` doctest annotated with the WRONG error code still
//!   passes. `world_position.rs`'s private-field guard (really E0451)
//!   annotated `compile_fail,E0433` passed green.
//! * A doctest whose body fails only because of a TYPO passes identically.
//!   Renaming `WorldPosition` to `WrldPositionTYPO` in the guard snippet --
//!   which deletes all contact with the guard -- still passed.
//!
//! So a future edit that breaks a guard, but leaves the snippet failing for
//! some *other* reason, is invisible to `cargo test --doc`. The doctests state
//! intent; they do not verify it.
//!
//! `trybuild` closes that gap: it compiles each case and diffs the FULL rustc
//! stderr against a checked-in `.stderr` expectation. The error code, the
//! message, and the span are all part of the comparison, so:
//!
//! * deleting the guard (making the case compile) fails the test, and
//! * changing WHICH error fires fails the test with a visible diff.
//!
//! # Maintaining these
//!
//! The `.stderr` files are generated, not hand-written. After an intentional
//! change to a guard, regenerate with:
//!
//! ```text
//! TRYBUILD=overwrite cargo test --test compile_fail --no-default-features \
//!     --manifest-path packages/temper-geometry/Cargo.toml
//! ```
//!
//! and READ THE DIFF before committing it. A regenerated `.stderr` that no
//! longer mentions the expected error code means the guard moved, not that the
//! expectation was stale. Never regenerate to make a red test green without
//! understanding which error replaced which.
//!
//! The `compile_fail` doctests are deliberately KEPT: they are the
//! documentation (they render in rustdoc next to the type they protect), and
//! `cargo test --doc` still runs them. This file is the enforcement.

#[test]
fn type_system_guards_fail_to_compile_for_the_stated_reason() {
    let t = trybuild::TestCases::new();
    // WorldPosition -- no raw-coordinate path into the type (the naive
    // `comp_pos + pin_pos` bug, hit three times).
    t.compile_fail("tests/compile_fail/world_position_struct_literal.rs");
    t.compile_fail("tests/compile_fail/world_position_from_tuple.rs");
    // Layer -- no hardcoded stale copy of a board's copper stackup.
    t.compile_fail("tests/compile_fail/layer_struct_literal.rs");
    // RotationQuadrant -- a 0-3 index is not degrees.
    t.compile_fail("tests/compile_fail/rotation_quadrant_div.rs");
    // NetRouteResult::Connected -- no fabricated routing completion.
    t.compile_fail("tests/compile_fail/net_route_result_fabricated.rs");
    // ClearanceHalo -- the conservative-superset guarantee cannot be forged.
    t.compile_fail("tests/compile_fail/clearance_halo_private_polygon.rs");
    t.compile_fail("tests/compile_fail/conservative_superset_fabricated.rs");
}

/// Second enforcement layer: pin the ERROR CODE independently of the message.
///
/// # Why this exists on top of trybuild
///
/// trybuild diffs the full rustc stderr, which is strict but also
/// message-text-sensitive: rustc rewords diagnostics between releases, and CI
/// runs `ubuntu-latest`'s stock toolchain with no `rust-toolchain.toml` pin. So
/// the `.stderr` files WILL eventually go red for a purely cosmetic reason, and
/// the fix for that is `TRYBUILD=overwrite`.
///
/// That regeneration is the hazard. Run blindly, it happily absorbs a guard
/// that has started failing for a completely different reason -- restoring
/// exactly the vacuity this whole file exists to remove, while leaving CI
/// green. This test makes that specific mistake loud: the error CODE is
/// asserted from a table written here, so a regenerated `.stderr` whose code
/// changed fails even though its text now matches.
///
/// Error codes are far more stable than message text, so this layer is
/// expected to survive toolchain upgrades that legitimately churn the
/// `.stderr` files.
///
/// If this test fails, do NOT edit the table to match. A changed error code
/// means the guard changed shape -- go read the guard.
#[test]
fn each_guard_expectation_still_pins_its_intended_error_code() {
    // (case stem, error code the guard MUST fail with, what it protects)
    const EXPECTED: &[(&str, &str, &str)] = &[
        (
            "world_position_struct_literal",
            "E0451",
            "WorldPosition fields private -- no raw-coordinate path in",
        ),
        (
            "world_position_from_tuple",
            "E0277",
            "no From<(f64, f64)> -- a raw pair cannot skip the rotation kernel",
        ),
        (
            "layer_struct_literal",
            "E0451",
            "Layer fields private -- no hardcoded stale copper stackup",
        ),
        (
            "rotation_quadrant_div",
            "E0369",
            "no Div -- a 0-3 quadrant index is not degrees",
        ),
        (
            "net_route_result_fabricated",
            "E0451",
            "VerifiedRoute fields private -- no fabricated Connected verdict",
        ),
        (
            "clearance_halo_private_polygon",
            "E0616",
            "ClearanceHalo.polygon private -- no unverified halo substitution",
        ),
        (
            "conservative_superset_fabricated",
            "E0451",
            "ConservativeSuperset cannot be minted outside its module",
        ),
    ];

    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/compile_fail");
    let mut problems = Vec::new();

    for (stem, code, protects) in EXPECTED {
        let path = dir.join(format!("{stem}.stderr"));
        let Ok(text) = std::fs::read_to_string(&path) else {
            problems.push(format!(
                "{stem}: expectation file {} is MISSING -- the guard for \"{protects}\" \
                 is no longer enforced",
                path.display()
            ));
            continue;
        };
        let marker = format!("error[{code}]");
        if !text.contains(&marker) {
            let found: Vec<&str> = text
                .lines()
                .filter(|l| l.starts_with("error["))
                .take(3)
                .collect();
            problems.push(format!(
                "{stem}: expected `{marker}` (guard: {protects}) but the checked-in \
                 expectation contains {found:?}. A changed error code means the guard \
                 changed shape -- read the guard, do NOT edit the table to match."
            ));
        }
    }

    assert!(problems.is_empty(), "\n{}\n", problems.join("\n"));

    // Guard against the table itself silently drifting out of sync with the
    // cases actually registered above.
    // NB: no unwrap/expect -- these crates set `expect_used = "deny"`, and a
    // guard-enforcement test is the last place that should be panicking on a
    // path it can report cleanly.
    let listing = std::fs::read_dir(&dir);
    assert!(
        listing.is_ok(),
        "tests/compile_fail is missing at {} -- without it NO guard case is \
         registered and this whole file is vacuous",
        dir.display()
    );
    let case_count = listing
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .filter(|e| e.path().extension().is_some_and(|x| x == "rs"))
        .count();
    assert_eq!(
        case_count,
        EXPECTED.len(),
        "tests/compile_fail has {case_count} .rs cases but the error-code table pins \
         {}. Every compile_fail case must pin its error code here.",
        EXPECTED.len()
    );
}
