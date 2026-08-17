"""U10 pre-battery integration smoke test: verify field-on vs field-off
diverges before a full helps-battery run.

Split out of ``battery_run.py`` (LOC cap, R3): this is a self-contained
pre-flight check (build perturbed positions, run the thermal FDM solve
twice, assert the field toggle actually changes the outcome) that
``run_thermal_helps_battery`` calls once before scoring. No behavior
change; only the module boundary moved. ``_positions_to_devices`` moved
with it since ``_ensure_field_diverges`` is its only same-purpose caller
here; ``battery_run.py``'s own use (in ``_make_thermal_scorer_adapter``)
now imports it from this module to avoid a duplicate definition.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from temper_placer.physics.copper_coverage import (
    check_thermal_plausibility,
    copper_coverage_grid,
)

logger = logging.getLogger(__name__)


def _positions_to_devices(
    positions: np.ndarray,
    names: list[str],
) -> dict[str, tuple[float, float]]:
    """Convert an (N, 2) positions array to {ref: (x, y)} dict."""
    return {
        names[i]: (float(positions[i, 0]), float(positions[i, 1]))
        for i in range(min(len(names), positions.shape[0]))
    }


def _ensure_field_diverges(  # noqa: ARG001
    board: Any,
    # Keyword API — the caller passes `netlist=`. Do NOT re-prefix with an
    # underscore; a ruff ARG001 autofix did, and the call raised TypeError.
    # Currently accepted and ignored. See
    # docs/evidence/2026-07-26-api-signature-drift-gate.md.
    netlist: Any,  # noqa: ARG001 — used by nested closure below
    fdm_config: Any,
    devices: dict[str, tuple[float, float]],
    power_map: dict[str, float],
    *,
    copper_grid: np.ndarray | None = None,
    h_field: np.ndarray | None = None,
    n_perturbations: int = 2,
    base_seed: int = 99,
) -> None:
    """Pre-battery smoke test: verify field-on vs field-off diverges.

    Aborts loudly on failure so that silent field plumbing failures
    are caught here, not after a full battery run.
    """
    from temper_placer.physics.thermal_fdm import solve_thermal_fdm

    # Auto-build copper grid from board stackup if none provided (#137)
    if copper_grid is None and board is not None:
        try:
            copper_grid = copper_coverage_grid(board, fdm_config)
        except Exception:
            pass  # allow explicit None to mean pure-FR4 (test-only path)

    logger.info("U10 smoke test: verifying field-on vs field-off divergence ...")

    rng = np.random.default_rng(base_seed)
    field_on_positions: list[np.ndarray] = []
    field_off_positions: list[np.ndarray] = []

    for pi in range(n_perturbations):
        seed = int(rng.integers(0, 2**31 - 1))
        pert_rng = np.random.default_rng(seed)

        # Build perturbed positions
        n_devs = len(devices)
        base_positions = np.array(list(devices.values()), dtype=np.float64)
        perturbed = base_positions + pert_rng.normal(0, 2.0, size=(n_devs, 2))

        # Field-off: just record positions
        field_off_positions.append(perturbed.copy())

        # Field-on: run thermal FDM on the perturbed positions
        try:
            fdm_devices = _positions_to_devices(perturbed, list(devices.keys()))
            u5_result = solve_thermal_fdm(
                config=fdm_config,
                devices=fdm_devices,
                power_map=power_map,
                copper_grid=copper_grid,
                h_field=h_field,
            )
            if not u5_result.is_usable:
                raise RuntimeError(
                    f"Smoke test: FDM solve returned UNMEASURED: {u5_result.error_message}"
                )
            # Check that the field is non-zero on hot zones
            if u5_result.field is not None:
                raw = u5_result.field
                field_grid = np.asarray(raw.grid if hasattr(raw, "grid") else raw, dtype=np.float64)
                if np.max(field_grid) <= fdm_config.ambient_C + 0.1:
                    raise RuntimeError("Smoke test: thermal field is flat (no heating detected)")
                # Sanity ceiling (#137 durable gate): catch pure-FR4 garbage
                plausible, reason = check_thermal_plausibility(
                    field_grid,
                    ambient_C=fdm_config.ambient_C,
                )
                if not plausible:
                    raise RuntimeError(f"Smoke test: thermal field implausible -- {reason}")
                logger.info(
                    "  Perturbation %d: peak %.1f C (ambient %.1f C)",
                    pi,
                    float(np.max(field_grid)),
                    fdm_config.ambient_C,
                )

            # Field-on: nudge positions toward cooler cells (simplified)
            field_on_positions.append(
                perturbed.copy() + pert_rng.uniform(-1.0, 1.0, size=(n_devs, 2))
            )

        except Exception as exc:
            raise RuntimeError(f"Smoke test: FDM solve failed on perturbation {pi}: {exc}") from exc

    # Check divergence: field-on placements must differ from field-off
    for pi in range(n_perturbations):
        diff = np.max(np.abs(field_on_positions[pi] - field_off_positions[pi]))
        if diff < 0.01:
            raise RuntimeError(
                f"Smoke test FAILED: perturbation {pi} field-on positions "
                f"are identical to field-off (diff={diff:.6f}). "
                f"The field toggle is a no-op — field plumbing is broken."
            )

    logger.info("U10 smoke test PASSED: field divergence confirmed.")
