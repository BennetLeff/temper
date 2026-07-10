"""
Elmer corroboration gate — wires the Elmer orchestrator, mesh converter, and
full-field comparison instrument into a fail-closed ``Gate`` subclass.

Produces a three-state result:
- ``CLEAN`` when Elmer is available and the FDM/Elmer fields agree within tolerance.
- ``VIOLATIONS`` when Elmer is available but the two fields disagree.
- ``UNMEASURED`` when Elmer is absent or any step fails — never a silent pass.

This is the validity-proxy rung of the three-target verification ladder
(correctness/soundness/validity), documented in
``docs/physics-verification-methodology.md``.

Requirements: R6 (scoped validity claim), R7 (fail-closed gate).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStatus,
    Violation,
    ViolationType,
)

if TYPE_CHECKING:
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.physics.tj_cross_check import DeviceThermalConfig


@dataclass(frozen=True)
class ElmerGateConfig:
    """Configuration for the Elmer corroboration gate.

    Attributes:
        fdm_config: FDM grid geometry and boundary conditions.
        devices: ``{ref: (x_mm, y_mm)}`` device centroids.
        power_map: ``{ref: power_W}`` per-device power dissipation.
        device_thermal: ``{ref: DeviceThermalConfig}`` per-device R_θ values
            with ``because`` citations.
        tolerance_C: Per-cell |ΔT| threshold for CLEAN/VIOLATIONS (°C).
        copper_grid: Optional per-cell copper fraction grid ``(H, W)``.
    """

    fdm_config: ThermalFDMConfig
    devices: dict[str, tuple[float, float]]
    power_map: dict[str, float]
    device_thermal: dict[str, DeviceThermalConfig]
    tolerance_C: float = 5.0
    copper_grid: np.ndarray | None = None  # noqa: F821


class ElmerCorroborationGate(Gate):
    """Gate: external Elmer-FEM corroboration of the FDM thermal field.

    Runs the full corroboration pipeline:
    1. Preflight: check Elmer CLI availability → UNMEASURED if absent.
    2. Mesh conversion: board → Elmer geometry + .sif.
    3. FDM solve: run ``solve_thermal_fdm`` at the given operating point.
    4. Elmer solve: run ``ElmerSolver`` (skipped if absent).
    5. Comparison: per-cell ΔT map + device T_j spot-checks.
    6. Gate result: CLEAN / VIOLATIONS with spatial attribution / UNMEASURED.

    The gate is fail-closed: any step that cannot execute yields UNMEASURED.
    Disagreement carries spatial attribution info (device, near-heatsink,
    far-field, copper-plane) in the violation context.
    """

    stage = __import__("temper_placer.placer.cp_sat.gates", fromlist=["GateStage"]).GateStage.ROUTING
    name = "elmer_corroboration"

    def __init__(
        self,
        config: ElmerGateConfig,
        output_dir: Path | None = None,
    ):
        self._config = config
        self._output_dir = output_dir or Path("elmermesh")

    def check(self, _state: BoardState) -> GateResult:
        """Run the Elmer corroboration pipeline and return a three-state result."""
        return self._check_inner()

    def _check_inner(self) -> GateResult:
        """Internal check that does not depend on BoardState.

        Splits from ``check()`` so tests can call directly without constructing
        a full ``BoardState``.
        """
        # --- Step 0: Preflight — Elmer availability ------------------------
        from temper_placer.validation.elmer import check_elmer

        if not check_elmer():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    "Elmer corroboration gate: ElmerGrid and/or ElmerSolver "
                    "not found on PATH — external FEM instrument is absent. "
                    "Fail-closed: UNMEASURED, never a silent pass."
                ),
            )

        # --- Step 1: Run the FDM solve -------------------------------------
        from temper_placer.physics.heat_removal import build_h_field
        from temper_placer.physics.thermal_fdm import solve_thermal_fdm

        cfg = self._config
        h_field = build_h_field(
            config=cfg.fdm_config,
            devices=cfg.devices,
            device_thermal=cfg.device_thermal,
        )
        fdm_result = solve_thermal_fdm(
            config=cfg.fdm_config,
            devices=cfg.devices,
            power_map=cfg.power_map,
            copper_grid=cfg.copper_grid,
            h_field=h_field,
        )

        if not fdm_result.is_usable:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    f"Elmer corroboration gate: FDM solve failed — "
                    f"{fdm_result.error_message}"
                ),
            )

        fdm_grid = fdm_result.field.grid

        # --- Step 2: Generate Elmer mesh and .sif ---------------------------
        from temper_placer.core.board import Board
        from temper_placer.validation.elmer_mesh import build_temper_mesh

        board = Board(
            width=cfg.fdm_config.width_cells * cfg.fdm_config.cell_size_mm,
            height=cfg.fdm_config.height_cells * cfg.fdm_config.cell_size_mm,
            origin=cfg.fdm_config.origin_mm,
        )
        try:
            mesh_dir, sif_path = build_temper_mesh(
                board=board,
                fdm_config=cfg.fdm_config,
                devices=cfg.devices,
                device_thermal=cfg.device_thermal,
                output_dir=self._output_dir,
            )
        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"Elmer corroboration gate: mesh generation failed — {exc}",
            )

        # --- Step 3: Run Elmer solve ----------------------------------------
        from temper_placer.validation.elmer import ElmerRunner

        runner = ElmerRunner(timeout_s=300.0)
        elmer_result = runner.run(mesh_dir=mesh_dir, sif_path=sif_path)

        if not elmer_result.success:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    f"Elmer corroboration gate: ElmerSolver failed — "
                    f"{elmer_result.error_message}"
                ),
            )

        # --- Step 4: Compare fields -----------------------------------------

        from temper_placer.validation.elmer_compare import compare_fields

        # Project Elmer 1-D field onto FDM 2-D grid
        elmer_t = elmer_result.temperature_field
        if elmer_t is None:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="Elmer corroboration gate: Elmer returned empty temperature field",
            )

        # Reshape to FDM grid if possible (Elmer may output per-node array)
        H, W = fdm_grid.shape
        expected_n = H * W
        if len(elmer_t) == expected_n:
            elmer_2d = elmer_t.reshape(H, W)
        else:
            # Interpolate / down-sample to FDM grid size — simple reshape
            # for when Elmer mesh matches FDM cell count
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    f"Elmer corroboration gate: cannot project Elmer field "
                    f"(size {len(elmer_t)}) onto FDM grid ({H}x{W} = {expected_n})"
                ),
            )

        comparison = compare_fields(
            fdm_field=fdm_grid,
            elmer_field=elmer_2d,
            fdm_config=cfg.fdm_config,
            devices=cfg.devices,
            copper_grid=cfg.copper_grid,
            tolerance_C=cfg.tolerance_C,
        )

        if not comparison.is_clean and comparison.error_message:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"Elmer corroboration: comparison failed — {comparison.error_message}",
            )

        if not comparison.is_clean:
            violation = Violation(
                type=ViolationType.THERMAL,
                severity=comparison.max_delta_C,
                threshold=cfg.tolerance_C,
                description=(
                    f"Elmer-FDM full-field corroboration: max |ΔT| = "
                    f"{comparison.max_delta_C:.1f}°C > tolerance "
                    f"{cfg.tolerance_C:.1f}°C. "
                    f"Devices: {comparison.per_device_deltas}. "
                    f"Attribution: {comparison.attribution}"
                ),
                context={
                    "because": (
                        "two-model corroboration (U4): Elmer 3-D FEM and "
                        "FDM 2-D produce inconsistent full-board temperature "
                        "fields — the validity-proxy rung is not satisfied"
                    ),
                    "max_delta_C": comparison.max_delta_C,
                    "tolerance_C": cfg.tolerance_C,
                    "device_deltas": comparison.per_device_deltas,
                    "attribution": comparison.attribution,
                },
            )
            return GateResult(GateStatus.VIOLATIONS, violations=(violation,))

        return GateResult(GateStatus.CLEAN)
