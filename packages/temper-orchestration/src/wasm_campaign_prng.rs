// Deterministic PRNG shared by every module's proptest-mirroring campaign in
// this crate (R19/U6: mirror the `proptest`-only properties in `timing.rs`,
// `host_math.rs`, `copper_length.rs`, `clearance.rs`, `grid_stage.rs`,
// `phased_assignment_stage.rs`, `zone_aware_slot_generation_stage.rs`,
// `phased_component_assignment_validator_stage.rs` onto the wasm32
// verification tier -- see each module's own `tests` doc comment for why).
//
// Same precedent as `temper-drc-rs/src/rules/drc/property_campaigns.rs`,
// `temper-geometry/src/property_campaigns.rs`, `temper-io-types/src/
// property_campaigns.rs`, `temper-rust-router-core/src/property_campaigns.rs`:
// `proptest` is a dev-dependency, absent from the ordinary (non-test) build
// this crate's `wasm-registry` feature compiles into, so a `proptest!` macro
// body cannot be registered directly. The fix already established across this
// tier is a *deterministic* equivalent: a fixed, seeded generator (no `rand`,
// no `proptest`, no OS entropy source -- `wasm32-unknown-unknown` has none),
// producing a small fixed corpus of cases per property, each wrapped as its
// own zero-argument `#[test]` so `scripts/gen_wasm_test_registry.py` can pick
// each one up individually. The native, randomized `proptest!` in each
// module's own `mod proptests` is NOT touched or removed by this -- it keeps
// exploring randomly on the native side; this generator only adds a
// wasm32-reachable, reproducible-from-its-seed sibling.
//
// The `mod wasm_campaign_prng;` declaration in `lib.rs` is UNCONDITIONAL;
// this file's own content is gated here instead (see `lib.rs`'s comment on
// that declaration for why: gating the declaration line itself, rather than
// the content, would make the registry generator's census misread it as a
// second, contentless test module). This file has no purpose outside a test
// build or the wasm-registry non-test build -- it would otherwise look
// unused (dead_code) in a plain `cargo build --features python` release
// binary, and it is needed under plain `cargo test` too, since the mirror
// tests it feeds run natively as well as on wasm32.
#![cfg(any(test, feature = "wasm-registry"))]
#![allow(dead_code)]

/// SplitMix64 -- a small, fast, deterministic PRNG. Not cryptographic, not
/// `rand`-crate: portable to `wasm32-unknown-unknown` with zero dependencies,
/// and (critically) reproducible from its `u64` seed alone, so a failing
/// campaign test names the exact seed to replay.
pub(crate) struct SplitMix64(u64);

impl SplitMix64 {
    pub(crate) fn new(seed: u64) -> Self {
        Self(seed)
    }

    pub(crate) fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform float in `[0, 1)`.
    pub(crate) fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Uniform float in `[lo, hi)`.
    pub(crate) fn range(&mut self, lo: f64, hi: f64) -> f64 {
        lo + self.next_f64() * (hi - lo)
    }

    /// Uniform integer in `[lo, hi)` (`i64`, for small counts).
    pub(crate) fn range_i64(&mut self, lo: i64, hi: i64) -> i64 {
        debug_assert!(hi > lo);
        lo + (self.next_u64() % (hi - lo) as u64) as i64
    }

    /// Uniform index in `[0, n)`. `n` is always a small, non-zero,
    /// compile-time-bounded corpus length in these campaigns.
    pub(crate) fn index(&mut self, n: usize) -> usize {
        debug_assert!(n > 0);
        (self.next_u64() % n as u64) as usize
    }

    /// A pseudo-random `bool`.
    pub(crate) fn bool(&mut self) -> bool {
        self.next_u64() & 1 == 0
    }

    /// A short deterministic ref-designator-shaped ASCII string
    /// (`[A-Z][0-9]`), matching the `"[A-Z][0-9]"` regex strategies the
    /// mirrored proptests use for component refs / net names.
    pub(crate) fn ref_like(&mut self) -> String {
        let letter = (b'A' + (self.index(26) as u8)) as char;
        let digit = (b'0' + (self.index(10) as u8)) as char;
        let mut s = String::with_capacity(2);
        s.push(letter);
        s.push(digit);
        s
    }
}

/// A property-local PRNG stream, independent of any other stream sharing the
/// same base `seed`, so one property's own randomized parameters don't
/// correlate with another's draws from the same seed. `salt` distinguishes
/// properties/roles sharing a base seed (mirrors `temper-drc-rs`'s
/// `sub_rng`).
pub(crate) fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn deterministic_in_seed() {
        let mut a = SplitMix64::new(12345);
        let mut b = SplitMix64::new(12345);
        assert_eq!(a.next_u64(), b.next_u64());
        assert_eq!(a.range(-1e6, 1e6).to_bits(), b.range(-1e6, 1e6).to_bits());
    }

    #[cfg_attr(test, test)]
    fn varies_with_seed() {
        let mut a = SplitMix64::new(1);
        let mut b = SplitMix64::new(2);
        assert_ne!(a.next_u64(), b.next_u64());
    }

    #[cfg_attr(test, test)]
    fn range_stays_in_bounds() {
        let mut rng = SplitMix64::new(7);
        for _ in 0..1000 {
            let v = rng.range(-5.0, 5.0);
            assert!((-5.0..5.0).contains(&v), "{v} out of [-5, 5)");
        }
    }

    #[cfg_attr(test, test)]
    fn index_stays_in_bounds() {
        let mut rng = SplitMix64::new(99);
        for _ in 0..1000 {
            let i = rng.index(7);
            assert!(i < 7);
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("wasm_campaign_prng::tests::deterministic_in_seed", deterministic_in_seed),
        ("wasm_campaign_prng::tests::varies_with_seed", varies_with_seed),
        ("wasm_campaign_prng::tests::range_stays_in_bounds", range_stays_in_bounds),
        ("wasm_campaign_prng::tests::index_stays_in_bounds", index_stays_in_bounds),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
