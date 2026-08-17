//! `DrcCount` — a DRC violation count that knows whether it's capped or honest.
//!
//! KiCad's DRC engine truncates the *reported* violations per category at a
//! GUI list-widget performance constant (`pcbnew/drc/drc_engine.cpp`,
//! 10.0 branch — quoted verbatim in
//! `docs/evidence/2026-08-12-dru-rule-precedence.md` sec 4):
//!
//! ```c
//! #define ERROR_LIMIT 199
//! #define EXTENDED_ERROR_LIMIT 499
//! ```
//!
//! A count at exactly its category's limit is therefore a **saturation
//! floor** — "the true count is >= N" — NOT a real count. This type makes
//! trusting a saturated count as a real count *unrepresentable*: the only
//! way to get the bare number as a true count is [`DrcCount::honest_count`],
//! which returns `Err` on a capped count, forcing the caller to handle the
//! ambiguity (re-measure with `scripts/measure_uncapped_drc.py`, or treat
//! the value as a lower bound).
//!
//! ## Per-category caps (why the category parameter is load-bearing)
//!
//! The limit is assigned per violation type:
//!
//! * `clearance` and `unconnected_items` get `EXTENDED_ERROR_LIMIT` (499);
//! * every other type gets `ERROR_LIMIT` (199) — *when its provider honours
//!   the limit*. `creepage` is the one empirically-measured exception: its
//!   provider bypasses the limit entirely (a 20 mm creepage rule reports
//!   3,311 violations, and the board's own 198–200 `creepage` counts are
//!   real run-to-run variance, not saturation — same evidence doc sec 4,
//!   "The `creepage` 'chronic scatter' is not this").
//!
//! The category parameter exists precisely so a count of exactly 199 in an
//! *uncapped* category (`creepage`, or `clearance` at 199 — below *its*
//! 499 cap) is not falsely flagged, and a count of exactly 499 in a
//! 199-capped category cannot be a cap (the engine never prints past 199
//! for it). A naive "199 or 499 always means capped" rule flags `creepage`
//! 198–200 and `clearance` 199 as saturated — the reverse diagnostic error.
//!
//! ## `--all-track-errors` overshoot
//!
//! `--all-track-errors` (which `temper_placer.validation._drc_api.run_drc`
//! always passes) checks the limit between whole per-track batches, so a
//! saturated category can overshoot its nominal cap by a variable 0–~14
//! (measured in `scripts/measure_uncapped_drc.py`, `SAFE_MARGIN = 20`).
//! Exact-equality detection (`from_kicad`) is the *provable* floor signal;
//! a count merely *near* a cap is **suspected** saturated and needs the
//! determinism re-run protocol (`_verified_count` there) — repeat-exact
//! counts are true, cap-disturbed counts are not. `DrcCount` never
//! guesses in the near-cap zone; it reports exactly what is knowable from
//! a single raw count.
//!
//! Pure data, no pyo3 — unconditional (like `ipc`/`manufacturing`), so it
//! is present in a `--no-default-features` wasm32 build and unit-testable
//! without Python. The pyo3 surface is `drc_count_pyo3`.

/// `#define ERROR_LIMIT 199` — the default per-category reporting cap.
pub const KICAD_ERROR_LIMIT: u32 = 199;

/// `#define EXTENDED_ERROR_LIMIT 499` — the reporting cap for `clearance`
/// and `unconnected_items` (KiCad's DRCE_CLEARANCE / DRCE_UNCONNECTED_ITEMS).
pub const KICAD_EXTENDED_ERROR_LIMIT: u32 = 499;

/// KiCad violation types assigned `EXTENDED_ERROR_LIMIT` in
/// `drc_engine.cpp`'s `m_errorLimits` loop
/// (`ii == DRCE_CLEARANCE || ii == DRCE_UNCONNECTED_ITEMS`).
const EXTENDED_LIMIT_TYPES: &[&str] = &["clearance", "unconnected_items"];

/// KiCad violation types whose provider is empirically known NOT to honour
/// the limit at all, so even a count equal to `KICAD_ERROR_LIMIT` is a real
/// count. `creepage`: a 20 mm creepage rule reports 3,311 — see
/// `docs/evidence/2026-08-12-dru-rule-precedence.md` sec 4, and the
/// `drc_ceiling.json` `_march` log, which records `creepage`'s 198–200 as
/// genuine run-to-run scatter for this exact reason.
const UNLIMITED_TYPES: &[&str] = &["creepage"];

/// The reporting cap for a kicad-cli violation *type*, or `None` when the
/// category is known not to cap at all.
///
/// * `clearance`, `unconnected_items` → `Some(KICAD_EXTENDED_ERROR_LIMIT)`
/// * `creepage` → `None` (provider bypasses the limit, measured)
/// * everything else → `Some(KICAD_ERROR_LIMIT)` (KiCad's `else` branch)
pub fn cap_for(category: &str) -> Option<u32> {
    if UNLIMITED_TYPES.contains(&category) {
        return None;
    }
    if EXTENDED_LIMIT_TYPES.contains(&category) {
        return Some(KICAD_EXTENDED_ERROR_LIMIT);
    }
    Some(KICAD_ERROR_LIMIT)
}

/// A DRC violation count that knows whether it's capped or honest.
///
/// KiCad caps `track_width`, `shorting_items`, `clearance` (and others) at
/// `ERROR_LIMIT=199` or `EXTENDED_ERROR_LIMIT=499`. A count at exactly
/// these values is a SATURATION FLOOR, not a real count. This type makes
/// trusting a saturated count as a real count unrepresentable.
///
/// ```
/// use temper_drc_rs::drc_count::{DrcCount, KICAD_ERROR_LIMIT};
///
/// let capped = DrcCount::from_kicad(KICAD_ERROR_LIMIT, "track_width");
/// assert!(capped.is_capped());
/// // The only way to get the bare count as a *true* count:
/// match capped.honest_count() {
///     Err(_) => { /* saturated — true count is >= 199, must re-measure */ }
///     Ok(_) => unreachable!("199 equals track_width's cap"),
/// }
///
/// let honest = DrcCount::from_kicad(42, "track_width");
/// assert_eq!(honest.honest_count(), Ok(42));
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DrcCount {
    count: u32,
    is_capped: bool,
    // Private — can only be constructed by `from_kicad`, so a capped flag
    // can never disagree with the count it classifies.
}

impl DrcCount {
    /// Construct from raw kicad-cli DRC output. Automatically detects
    /// saturation against the *category's own cap*: a count equal to the
    /// category's limit marks the count capped. See [`cap_for`] for the
    /// per-category table and why `category` is load-bearing.
    pub fn from_kicad(count: u32, category: &str) -> Self {
        let is_capped = cap_for(category).is_some_and(|cap| count == cap);
        Self { count, is_capped }
    }

    /// The displayed count. If capped, this is the FLOOR (minimum), not the
    /// true count — prefer [`Self::honest_count`] or [`Self::display`].
    pub fn count(&self) -> u32 {
        self.count
    }

    /// Is this count saturated (capped at KiCad's limit)?
    pub fn is_capped(&self) -> bool {
        self.is_capped
    }

    /// Is this count honest (not capped)?
    pub fn is_honest(&self) -> bool {
        !self.is_capped
    }

    /// Returns the count if honest, or an error if capped. Use this when you
    /// need the TRUE count — calling this on a capped count forces you to
    /// handle the ambiguity (re-measure, or treat the value as a floor).
    pub fn honest_count(&self) -> Result<u32, CappedCountError> {
        if self.is_capped {
            Err(CappedCountError { count: self.count })
        } else {
            Ok(self.count)
        }
    }

    /// Format for display: `"199 (CAPPED — true count >= 199)"` or `"42"`.
    pub fn display(&self) -> String {
        if self.is_capped {
            format!("{} (CAPPED — true count >= {})", self.count, self.count)
        } else {
            format!("{}", self.count)
        }
    }
}

/// Error returned by [`DrcCount::honest_count`] when the count is saturated
/// at KiCad's reporting cap: the number is a floor, not the truth.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CappedCountError {
    /// The raw (capped) count the caller asked to treat as true.
    pub count: u32,
}

impl std::fmt::Display for CappedCountError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "DRC count {} is capped at KiCad's ERROR_LIMIT — true count is >= {}, not exactly {}",
            self.count, self.count, self.count
        )
    }
}

impl std::error::Error for CappedCountError {}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    /// A representative sample of the category space: the two extended-limit
    /// types, the one known-unlimited type, a 199-capped type, and an
    /// unrecognised type (which KiCad's `else` branch caps at 199).
    fn categories() -> impl Strategy<Value = String> {
        prop_oneof![
            Just("clearance".to_string()),
            Just("unconnected_items".to_string()),
            Just("creepage".to_string()),
            Just("track_width".to_string()),
            Just("shorting_items".to_string()),
            Just("silk_overlap".to_string()),
            Just("some_future_type".to_string()),
        ]
    }

    proptest! {
        /// `is_capped` is exactly "count equals the category's own cap" —
        /// the flag can never disagree with `cap_for`.
        #[test]
        fn prop_capped_iff_count_equals_categories_cap(count in 0u32..1000u32, category in categories()) {
            let c = DrcCount::from_kicad(count, &category);
            assert_eq!(
                c.is_capped(),
                cap_for(&category) == Some(count),
                "count={count} category={category:?} cap={:?}",
                cap_for(&category)
            );
        }

        /// `honest_count` and `is_capped` are exact complements: an honest
        /// count always yields the count; a capped count always errors with
        /// the raw count attached.
        #[test]
        fn prop_honest_count_matches_cap_flag(count in 0u32..1000u32, category in categories()) {
            let c = DrcCount::from_kicad(count, &category);
            match c.honest_count() {
                Ok(n) => {
                    assert!(c.is_honest());
                    assert_eq!(n, count);
                }
                Err(e) => {
                    assert!(c.is_capped());
                    assert_eq!(e.count, count);
                }
            }
        }

        /// `is_honest` is the complement of `is_capped`, never an
        /// independent bit that can drift.
        #[test]
        fn prop_honest_is_complement_of_capped(count in 0u32..1000u32, category in categories()) {
            let c = DrcCount::from_kicad(count, &category);
            assert_eq!(c.is_honest(), !c.is_capped());
            assert_eq!(c.count(), count);
        }

        /// An honest count displays as the bare number; a capped count
        /// displays the floor marker — a reader can never mistake one for
        /// the other.
        #[test]
        fn prop_display_matches_cap_state(count in 0u32..1000u32, category in categories()) {
            let c = DrcCount::from_kicad(count, &category);
            if c.is_capped() {
                assert_eq!(c.display(), format!("{count} (CAPPED — true count >= {count})"));
            } else {
                assert_eq!(c.display(), count.to_string());
            }
        }

        /// A count strictly BELOW a category's cap is never flagged
        /// (honest); a count strictly ABOVE is never flagged either — the
        /// engine cannot print past the cap, so only equality is the
        /// saturation signal from a single raw count.
        #[test]
        fn prop_off_cap_counts_are_honest(count in 0u32..1000u32, category in categories()) {
            let c = DrcCount::from_kicad(count, &category);
            if let Some(cap) = cap_for(&category) {
                if count != cap {
                    assert!(c.is_honest(), "count={count} category={category:?} cap={cap}");
                }
            } else {
                assert!(c.is_honest(), "uncapped category flagged: count={count} category={category:?}");
            }
        }
    }

    #[test]
    fn exact_cap_values_are_capped_for_their_own_category() {
        // 199 is track_width's cap -> capped.
        let tw = DrcCount::from_kicad(KICAD_ERROR_LIMIT, "track_width");
        assert!(tw.is_capped());
        assert!(!tw.is_honest());
        assert_eq!(
            tw.honest_count(),
            Err(CappedCountError { count: KICAD_ERROR_LIMIT })
        );
        assert_eq!(
            tw.display(),
            "199 (CAPPED — true count >= 199)"
        );

        // 499 is clearance's cap -> capped.
        let cl = DrcCount::from_kicad(KICAD_EXTENDED_ERROR_LIMIT, "clearance");
        assert!(cl.is_capped());
        assert_eq!(
            cl.honest_count(),
            Err(CappedCountError { count: KICAD_EXTENDED_ERROR_LIMIT })
        );

        // shorting_items caps at 199, not 499: a 499 "shorting_items" count
        // is not a saturation reading (the engine stops at 199).
        let si = DrcCount::from_kicad(KICAD_EXTENDED_ERROR_LIMIT, "shorting_items");
        assert!(si.is_honest());
        assert_eq!(si.honest_count(), Ok(499));
    }

    #[test]
    fn counts_below_the_cap_are_honest() {
        assert_eq!(DrcCount::from_kicad(42, "track_width").honest_count(), Ok(42));
        assert_eq!(DrcCount::from_kicad(0, "track_width").honest_count(), Ok(0));
        assert_eq!(DrcCount::from_kicad(200, "track_width").honest_count(), Ok(200));
        assert_eq!(DrcCount::from_kicad(199, "clearance").honest_count(), Ok(199));
        assert_eq!(DrcCount::from_kicad(100, "creepage").honest_count(), Ok(100));
    }

    #[test]
    fn uncapped_categories_never_flag() {
        // creepage's provider bypasses the limit: even 199 is a real count.
        assert!(DrcCount::from_kicad(199, "creepage").is_honest());
        assert!(DrcCount::from_kicad(199, "creepage").honest_count().is_ok());
        // unconnected_items uses the 499 cap.
        assert!(DrcCount::from_kicad(199, "unconnected_items").is_honest());
        assert!(DrcCount::from_kicad(499, "unconnected_items").is_capped());
    }

    #[test]
    fn cap_for_matches_the_documented_table() {
        assert_eq!(cap_for("clearance"), Some(KICAD_EXTENDED_ERROR_LIMIT));
        assert_eq!(cap_for("unconnected_items"), Some(KICAD_EXTENDED_ERROR_LIMIT));
        assert_eq!(cap_for("creepage"), None);
        assert_eq!(cap_for("track_width"), Some(KICAD_ERROR_LIMIT));
        assert_eq!(cap_for("shorting_items"), Some(KICAD_ERROR_LIMIT));
        assert_eq!(cap_for("silk_overlap"), Some(KICAD_ERROR_LIMIT));
        assert_eq!(cap_for("hole_clearance"), Some(KICAD_ERROR_LIMIT));
        // Unrecognised types inherit KiCad's `else` branch: ERROR_LIMIT.
        assert_eq!(cap_for("some_future_type"), Some(KICAD_ERROR_LIMIT));
    }

    #[test]
    fn capped_count_error_is_a_std_error() {
        let err = CappedCountError { count: 199 };
        let msg = err.to_string();
        assert!(msg.contains("199"), "message should name the count: {msg}");
        assert!(msg.contains(">="), "message should state the floor: {msg}");
        let _ = format!("{err:?}");
    }
}
