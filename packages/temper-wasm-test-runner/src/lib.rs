//! `wasm32` entry point that runs Temper crates' unit tests one at a time.
//!
//! # Why this crate exists
//!
//! `cargo test`'s libtest harness cannot target `wasm32-unknown-unknown`: the
//! target has no argv, no threads, and no `std::process::exit`, so there is no
//! test *binary* to run.  Each participating crate's `wasm_test_registry`
//! instead exposes every eligible `#[test]` as a `(&'static str, fn())` in a
//! flat, indexable list, and this crate turns those lists into a C ABI the host
//! can drive: ask how many tests there are, read each name out of linear
//! memory, then invoke them one index at a time.
//!
//! # Why one runner for several crates
//!
//! A registry entry is a *structural* type — `(&'static str, fn())` — so
//! `temper_drc_rs::wasm_test_registry::ALL` and
//! `temper_geometry::wasm_test_registry::ALL` are already the same Rust type.
//! Nothing has to be converted, wrapped, or duplicated to run both: the
//! registries concatenate.  A second runner crate would have meant a second
//! copy of the panic hook, the ABI constants, and the seven exports, kept in
//! sync by hand — the version-skew bug `ABI_VERSION` exists to prevent, moved
//! from the host boundary into this repo.  So the crate list is a *feature*
//! (`drc-registry`, `geometry-registry`), and the exports are written once
//! against the concatenation.
//!
//! Which crates are linked is therefore a build-time choice, and the module can
//! carry one crate or several.  The host sees only a flat index either way; the
//! test names it reads back are the crate-relative paths each registry baked in
//! (`board::tests::…`, `smooth::tests::…`), so a results file is still
//! attributable per test without the host knowing the feature set.
//!
//! # How failure is signalled
//!
//! A test fails by panicking, exactly as under libtest.  This crate is built
//! with `panic = "abort"` (see `Cargo.toml`), and on `wasm32-unknown-unknown`
//! abort lowers to the `unreachable` instruction — so a failing test surfaces
//! to the host as a **WebAssembly trap**, not as a return value.  The host
//! catches the trap; `temper_run_test` never returns for a failing test.
//!
//! Because the trap carries no payload, a panic hook copies the panic message
//! into a module-static buffer *before* the abort.  The WebAssembly store
//! survives a trap, so the host can call `temper_panic_message_ptr` / `_len`
//! after catching one and recover the assertion text.  Read it before
//! re-instantiating, or it is lost.
//!
//! # Host contract
//!
//! All pointers are offsets into the module's exported `memory`, and all
//! strings are UTF-8 without a NUL terminator — always pair a `_ptr` with its
//! `_len`.  Every export is nullary or takes a single `u32` index, so the host
//! needs no argument marshalling and no `wasm-bindgen` glue.

use std::sync::Mutex;
use std::sync::Once;

/// One test as every registry represents it: a fully qualified name and a
/// nullary callable.  Structurally identical to each crate's own `WasmTest`
/// alias, which is what lets the registries below concatenate.
type WasmTest = (&'static str, fn());

/// The registries linked into this module, in a stable order.
///
/// Each element is one crate's `ALL` — itself a list of per-module slices,
/// individually `#[cfg]`-gated on that crate's family features.  Flattening is
/// two levels deep, and empty slices (a family that was not selected) simply
/// contribute nothing.
///
/// A module built with neither crate's feature has an empty registry and
/// reports zero tests.  That is deliberate rather than a compile error:
/// `make wasm-runner` builds `--no-default-features` to measure the floor cost
/// of the ABI itself.  `temper_test_count` is how a host distinguishes that
/// from a real run — a runner reporting everything green because it silently
/// ran nothing is the failure mode that export exists to make detectable.
const REGISTRIES: &[&[&[WasmTest]]] = &[
    #[cfg(feature = "drc-registry")]
    temper_drc_rs::wasm_test_registry::ALL,
    #[cfg(feature = "geometry-registry")]
    temper_geometry::wasm_test_registry::ALL,
    #[cfg(feature = "thermal-registry")]
    temper_thermal::wasm_test_registry::ALL,
    #[cfg(feature = "design-bundle-registry")]
    temper_design_bundle::wasm_test_registry::ALL,
    #[cfg(feature = "router-core-registry")]
    temper_rust_router_core::wasm_test_registry::ALL,
    #[cfg(feature = "constraint-compiler-registry")]
    temper_constraint_compiler::wasm_test_registry::ALL,
    #[cfg(feature = "quality-oracle-registry")]
    temper_quality_oracle::wasm_test_registry::ALL,
    #[cfg(feature = "io-types-registry")]
    temper_io_types::wasm_test_registry::ALL,
    #[cfg(feature = "pcl-ir-registry")]
    temper_pcl_ir::wasm_test_registry::ALL,
];

/// How many tests are linked in, across every registry.
fn registry_count() -> usize {
    REGISTRIES
        .iter()
        .map(|crate_registry| {
            crate_registry
                .iter()
                .map(|module| module.len())
                .sum::<usize>()
        })
        .sum()
}

/// The test at `index` in the flattened concatenation of all registries.
fn registry_get(index: usize) -> Option<&'static WasmTest> {
    let mut remaining = index;
    for crate_registry in REGISTRIES {
        for module in *crate_registry {
            if remaining < module.len() {
                return Some(&module[remaining]);
            }
            remaining -= module.len();
        }
    }
    None
}

/// Bumped whenever the meaning of an export changes, so a host built against
/// an older module fails loudly instead of misreading linear memory.
///
/// Unchanged at 1 by the multi-crate change: every export means exactly what it
/// did, because a host only ever saw a flat index and a name, never a crate.
const ABI_VERSION: u32 = 1;

/// `temper_run_test` returned normally: the test passed.
const RUN_OK: u32 = 0;
/// `temper_run_test` was handed an index outside the registry.  Distinct from
/// a failing test, which traps rather than returning.
const RUN_BAD_INDEX: u32 = 1;

/// The most recent panic message, captured by the hook installed in
/// [`install_panic_hook`].
///
/// A `Mutex` rather than a `static mut` because `set_hook` requires the hook
/// to be `Send + Sync`.  There is exactly one thread on this target, so it is
/// never contended.
static PANIC_MESSAGE: Mutex<String> = Mutex::new(String::new());

static HOOK: Once = Once::new();

/// Redirect panic messages into `PANIC_MESSAGE`.
///
/// The default hook writes to stderr, which on `wasm32-unknown-unknown` goes
/// nowhere — the message would be lost and the host would see a bare trap with
/// no explanation of which assertion failed.
fn install_panic_hook() {
    HOOK.call_once(|| {
        std::panic::set_hook(Box::new(|info| {
            let rendered = match info.location() {
                Some(loc) => format!("{} at {}:{}", info, loc.file(), loc.line()),
                None => format!("{info}"),
            };
            store_panic_message(rendered);
        }));
    });
}

/// Write `message` into the static buffer, tolerating a poisoned lock.
///
/// Poisoning cannot actually happen here (this target aborts rather than
/// unwinds), but recovering the inner value is still the right move: losing
/// the panic text to a lock error would defeat the buffer's whole purpose.
fn store_panic_message(message: String) {
    let mut slot = match PANIC_MESSAGE.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };
    *slot = message;
}

/// Run `f` against the current panic message without cloning it.
fn with_panic_message<T>(f: impl FnOnce(&str) -> T) -> T {
    let slot = match PANIC_MESSAGE.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };
    f(slot.as_str())
}

/// The ABI version this module implements.  Hosts should reject anything else.
#[unsafe(no_mangle)]
pub extern "C" fn temper_wasm_abi_version() -> u32 {
    ABI_VERSION
}

/// How many tests are registered.
///
/// The host uses this to bound its index loop, and — more importantly — to
/// check that the number of tests it actually executed matches the number
/// registered.  A runner that reports everything green because it silently ran
/// nothing is the failure mode this export exists to make detectable.
#[unsafe(no_mangle)]
pub extern "C" fn temper_test_count() -> u32 {
    // A registry larger than u32::MAX cannot occur (these are static arrays in
    // the binary), and saturating beats a panic in an infallible accessor.
    u32::try_from(registry_count()).unwrap_or(u32::MAX)
}

/// Offset in linear memory of test `index`'s name, or 0 if out of range.
///
/// Pair with [`temper_test_name_len`]; the name is UTF-8 and not
/// NUL-terminated.  The pointer is to a `&'static str` baked into the module,
/// so it stays valid for the life of the instance and must not be freed.
#[unsafe(no_mangle)]
pub extern "C" fn temper_test_name_ptr(index: u32) -> u32 {
    match registry_get(index as usize) {
        Some((name, _)) => name.as_ptr() as u32,
        None => 0,
    }
}

/// Byte length of test `index`'s name, or 0 if out of range.
#[unsafe(no_mangle)]
pub extern "C" fn temper_test_name_len(index: u32) -> u32 {
    match registry_get(index as usize) {
        Some((name, _)) => u32::try_from(name.len()).unwrap_or(0),
        None => 0,
    }
}

/// Invoke test `index`.
///
/// Returns [`RUN_OK`] if the test passed and [`RUN_BAD_INDEX`] if `index` is
/// outside the registry.  **A failing test does not return** — it panics,
/// which aborts, which traps.  The host must treat "call trapped" as the
/// failure signal and a normal return of `RUN_OK` as the pass signal; anything
/// that only inspects the return value will score every failure as a pass.
#[unsafe(no_mangle)]
pub extern "C" fn temper_run_test(index: u32) -> u32 {
    install_panic_hook();
    match registry_get(index as usize) {
        Some((_, test_fn)) => {
            test_fn();
            RUN_OK
        }
        None => RUN_BAD_INDEX,
    }
}

/// Offset in linear memory of the last panic message.
///
/// Only meaningful after [`temper_run_test`] has trapped.  The WebAssembly
/// store survives a trap, so this is callable on the same instance that just
/// failed — but re-instantiating clears it.
#[unsafe(no_mangle)]
pub extern "C" fn temper_panic_message_ptr() -> u32 {
    with_panic_message(|message| message.as_ptr() as u32)
}

/// Byte length of the last panic message; 0 if no panic has been captured.
#[unsafe(no_mangle)]
pub extern "C" fn temper_panic_message_len() -> u32 {
    with_panic_message(|message| u32::try_from(message.len()).unwrap_or(0))
}
