//! The `wasm32` entropy source: there isn't one, said out loud.
//!
//! `rand 0.8` -> `rand_core 0.6` -> `getrandom 0.2`, and on
//! `wasm32-unknown-unknown` getrandom has no OS RNG to call. It refuses to
//! compile there unless the crate picks a source, and the two choices are not
//! equivalent for this repo:
//!
//! * `getrandom/js` links a wasm-bindgen shim that reaches out to
//!   `crypto.getRandomValues` / Node's `randomFillSync`. It compiles, but it
//!   adds ~27 imports from `__wbindgen_placeholder__` to the module. A
//!   WebAssembly module with imports cannot be instantiated without the
//!   matching generated JS glue, and nothing in this repo runs `wasm-bindgen`
//!   to produce that glue -- so the module could not be instantiated at all,
//!   in Node or in a Worker isolate. The tier's premise is a module that
//!   instantiates against `{}`.
//! * `getrandom/custom` lets this crate supply the source. That is what this
//!   module does.
//!
//! # Why the source fails rather than substitutes a PRNG
//!
//! A fixed-seed PRNG would make [`crate::transform::gumbel_softmax`] "work" on
//! `wasm32` -- and would make every isolate draw the identical noise sequence
//! while the function's documentation still says the samples are random. That
//! is the failure mode this repo has already been bitten by once, in
//! `host_math`'s `dlsym` lookup: a fallback that returns a *plausible* answer
//! is worse than one that returns none, because nothing downstream can notice.
//! (See `host_math::tests::host_libm_symbols_actually_resolve`, which exists
//! solely to catch that class of silent substitution.)
//!
//! So the source reports `UNSUPPORTED`. `rand::thread_rng()` panics on a failed
//! seed, which on this target aborts into a trap, which the `wasm32` test
//! runner reports as a failing test naming the entropy consumer. Loud, local,
//! and attributable.
//!
//! Nothing outside `gumbel_softmax` draws entropy in this crate, so the blast
//! radius is that one kernel and the two of its tests that sample noise; both
//! are recorded in `tools/wasm/wasm_expected_failures_geometry.json`. A wasm32
//! consumer that genuinely needs randomness should thread a seed in explicitly
//! rather than re-enabling `js` here.

/// Fail every entropy request.
///
/// `UNSUPPORTED` rather than a custom code because it is the accurate one:
/// this target has no entropy source available to the module.
fn no_entropy(_dest: &mut [u8]) -> Result<(), getrandom::Error> {
    Err(getrandom::Error::UNSUPPORTED)
}

getrandom::register_custom_getrandom!(no_entropy);
