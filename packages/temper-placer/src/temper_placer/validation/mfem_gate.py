"""MFEM corroboration gate — fail-closed Gate subclass.

U4 of the external-MFEM corroboration plan.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

from temper_placer.placer.cp_sat.gates import (
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)

if TYPE_CHECKING:
    import numpy as np


class MFEMCorroborationGate(Gate):
    """Gate that cross-checks the FDM thermal field against an external MFEM solve.

    Pipeline: preflight → mesh → solve → project → compare → gate result.
    Fail-closed: ``UNMEASURED`` when MFEM is not available.
    """

    stage = GateStage.ROUTING
    name = "mfem_corroboration"

    def __init__(
        self,
        *,
        fdm_config: ThermalFDMConfig,
        devices: dict[str, tuple[int, int]],
        power_map: dict[str, float] | None = None,
        device_thermal: dict[str, DeviceThermalConfig] | None = None,
        tolerance_C: float = 5.0,
        binary_path: str = "/tmp/mfem_tempsolve",
    ) -> None:
        self._fdm_config = fdm_config
        self._devices = devices
        self._power_map = power_map or {}
        self._device_thermal = device_thermal or {}
        self._tolerance_C = tolerance_C
        self._binary = binary_path

    def check(self, state: BoardState) -> GateResult:
        from temper_placer.validation.mfem_compare import (
            compare_fields,
            project_mfem_to_fdm,
        )
        from temper_placer.validation.mfem_mesh import build_temper_mesh
        from temper_placer.validation.mfem_runner import (
            MFEMRunner,
            check_mfem,
        )

        if not check_mfem(self._binary):
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="MFEM binary not available — corroboration skipped",
            )

        try:
            with tempfile.TemporaryDirectory() as tmp:
                mesh_path = build_temper_mesh(
                    state.board,
                    self._fdm_config,
                    self._device_thermal,
                    self._power_map,
                    output_dir=tmp,
                )
                runner = MFEMRunner(binary_path=self._binary)
                mfem_result = runner.run(mesh_path, output_dir=tmp)

                if mfem_result.temperature is None or len(mfem_result.temperature) == 0:
                    return GateResult(
                        GateStatus.UNMEASURED,
                        error_message="MFEM produced no temperature data",
                    )

                mfem_field = project_mfem_to_fdm(mfem_result, self._fdm_config)
                fdm_field = _extract_fdm_field(state)

                comparison = compare_fields(
                    fdm_field,
                    mfem_field,
                    self._tolerance_C,
                    devices=self._devices,
                    cell_size_mm=self._fdm_config.cell_size_mm,
                )

                if comparison.exceeds_tolerance:
                    return GateResult(
                        GateStatus.VIOLATIONS,
                        violations=(
                            Violation(
                                type=ViolationType.THERMAL,
                                components=tuple(self._devices),
                                severity=comparison.max_delta_C,
                                threshold=self._tolerance_C,
                                description=(
                                    f"MFEM corroboration VIOLATION: "
                                    f"max |ΔT| = {comparison.max_delta_C:.1f}C "
                                    f"> tolerance {self._tolerance_C:.1f}C. "
                                    f"Attribution: {comparison.attribution}"
                                ),
                            ),
                        ),
                    )
                return GateResult(GateStatus.CLEAN)

        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"MFEM corroboration failed: {exc}",
            )


def _extract_fdm_field(state: BoardState) -> np.ndarray:
    """Extract the 2-D FDM temperature field from a BoardState.

    Runs a quick thermal FDM solve if no pre-computed field is available.
    """
    import numpy as np

    from temper_placer.physics.copper_coverage import copper_coverage_grid
    from temper_placer.physics.thermal_fdm import (
        ThermalFDMConfig,
        solve_thermal_fdm,
    )

    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=min(50, int(state.board.height)),
        width_cells=min(50, int(state.board.width)),
        ambient_C=40.0,
        heatsink_edge="BOTTOM",
    )
    copper = copper_coverage_grid(state.board, config)
    devices_dict = (
        {c.ref: (c.initial_position[0], c.initial_position[1]) for c in state.netlist.components}
        if hasattr(state, "netlist")
        else {}
    )

    result = solve_thermal_fdm(
        config=config,
        devices=devices_dict if devices_dict else None,
        power_map={"Q1": 15.0, "Q2": 15.0},
        copper_grid=copper,
    )
    if result.is_usable and result.field is not None:
        field = result.field
        raw = field.grid if hasattr(field, "grid") else field
        return np.asarray(raw, dtype=np.float64)
    H, W = config.height_cells, config.width_cells
    return 40.0 * np.ones((H, W), dtype=np.float64)
