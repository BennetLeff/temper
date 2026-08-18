//! Type-system guard enforcement, via `trybuild`.
//!
//! See `packages/temper-geometry/tests/compile_fail.rs` for the full rationale
//! and the measured evidence that a bare `compile_fail` doctest enforces only
//! "does not compile", never "does not compile FOR THIS REASON".
//!
//! Regenerate expectations with:
//!
//! ```text
//! TRYBUILD=overwrite cargo test --test compile_fail --no-default-features \
//!     --manifest-path packages/temper-orchestration/Cargo.toml
//! ```
//!
//! and read the diff before committing.
//!
//! NOTE: `Via::new`'s annular-ring floor clamp is NOT represented here. It is
//! a *runtime* clamp (a sub-floor diameter is enlarged to the board-wide
//! 0.3mm-ring convention), not a type-system guard -- there is no snippet that
//! fails to compile when the clamp is removed. It is covered by the runtime
//! tests `via_new_enforces_annular_floor_*` in `pipeline_route.rs`.

#[test]
fn type_system_guards_fail_to_compile_for_the_stated_reason() {
    let t = trybuild::TestCases::new();
    // Via -- no field access, so `emit_s_expr` is the only way to a sexpr and
    // the blind/buried type token can never be omitted.
    t.compile_fail("tests/compile_fail/via_private_field.rs");
}

/// Second enforcement layer: pin the ERROR CODE independently of the message.
/// See `packages/temper-geometry/tests/compile_fail.rs` for the full rationale
/// -- in short, trybuild's `.stderr` diff is message-text-sensitive and will
/// eventually need `TRYBUILD=overwrite` after a toolchain upgrade; run blindly
/// that regeneration would silently absorb a guard failing for a different
/// reason. This makes that specific mistake loud.
///
/// If this fails, do NOT edit the table to match. Go read the guard.
#[test]
fn each_guard_expectation_still_pins_its_intended_error_code() {
    const EXPECTED: &[(&str, &str, &str)] = &[(
        "via_private_field",
        "E0616",
        "Via fields private -- emit_s_expr is the only sexpr path, so the \
         blind/buried type token can never be omitted",
    )];

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
