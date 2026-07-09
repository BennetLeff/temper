/// Module root for the loop extractor.
/// Re-exports public API: extract loops, classify components, and error types.

pub mod classify;
pub mod extract;
pub mod types;

pub use classify::{classify_component, Classification, CompInfo};
pub use extract::{auto_extract_loops, detect_half_bridge, HalfBridge, Component as ExtComponent,
                  Loop, Net as ExtNet, Pin as ExtPin};
pub use types::{
    ComponentClassification, ExtractionError, PinMapping, Subcategory, TO247_PINS,
};
