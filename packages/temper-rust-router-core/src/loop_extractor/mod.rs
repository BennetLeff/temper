/// Module root for the loop extractor.
/// Re-exports public API: extract loops, classify components, and error types.
pub mod classify;
pub mod classify_py;
pub mod extract;
pub mod types;

pub use classify::{Classification, CompInfo, classify_component};
pub use classify_py::{MalformedNumber, classify_component_py, parse_capacitance_py};
pub use extract::{
    Component as ExtComponent, HalfBridge, Loop, Net as ExtNet, Pin as ExtPin, auto_extract_loops,
    detect_half_bridge,
};
pub use types::{ComponentClassification, ExtractionError, PinMapping, Subcategory, TO247_PINS};
