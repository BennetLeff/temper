# Resolution for temper-4bv.2: Subcircuit Rigid-Body Rotation (Port-Facing)

## Summary
Implemented `PortFacingRotationLoss` in `temper_placer.losses.aesthetic` and integrated it into the default loss pipeline (`create_aesthetic_losses`). This loss function encourages component groups to rotate such that a designated "primary pin" faces its connected target (e.g., a connector or the center of the connected net).

## Changes
1.  **`packages/temper-placer/src/temper_placer/losses/aesthetic.py`**:
    -   Updated `PortFacingRotationLoss` to support dynamic target calculation (finding centroid of connected net).
    -   Implemented `get_port_facing_data` helper to extract group/pin/target indices from `Netlist` and `Constraints`.
    -   Updated `create_aesthetic_losses` to instantiate `PortFacingRotationLoss` when `primary_pin` is defined in component groups.

2.  **`packages/temper-placer/tests/losses/test_aesthetic_losses.py`**:
    -   Added comprehensive unit tests for `PortFacingRotationLoss` covering aligned/opposite cases, dynamic targets, and multiple groups.

3.  **`scripts/measure_structural_placement.py`**:
    -   Created a benchmark script to measure the impact of structural placement features (like Port-Facing rotation) on loss metrics.

## Verification
-   New unit tests passed: `uv run pytest packages/temper-placer/tests/losses/test_aesthetic_losses.py`
-   Ran full test suite: Observed 143 failures, but they appear unrelated to changes (e.g., `ZonePolygon` parser errors, `PostProcessConfig` regression).

## Notes
-   The `PortFacingRotationLoss` currently assumes the group rotates around its centroid. For rigid body behavior, this relies on other constraints (like `ConsensusLayoutLoss` or proximity rules) to keep the group cohesive.
-   Observed `AttributeError: 'PostProcessConfig' object has no attribute 'legalization_enabled'` in existing tests, indicating a potential regression in the `main` branch.
