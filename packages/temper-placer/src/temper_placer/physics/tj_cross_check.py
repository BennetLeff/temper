"""Datasheet-R_θ lumped-network cross-check gate (U11).

Corroborates each power device's junction temperature T_j — the number
gating the T_j ≤ T_j(max) hard SAFETY ceiling — against a genuinely
model-independent lumped R_θ network built from manufacturer datasheet
values.  Two independent models (distributed FDM + lumped R_θ ladder),
fail-closed on disagreement.

Partial L3 close: this gate alone lifts the safety number from
solver-validated to two-model-corroborated.  Full model-independence
of the whole thermal field still needs a genuinely different interior
formulation or hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)

if TYPE_CHECKING:
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig


# ---------------------------------------------------------------------------
# Per-device R_θ config with datasheet citations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceThermalConfig:
    """Per-device thermal resistance values with datasheet citations.

    Every R_θ value carries a ``because`` string linking it to the
    manufacturer datasheet, application note, or engineering standard
    that supports it — never a magic number.
    """

    name: str
    """Device reference designator (e.g. 'Q1', 'Q2')."""

    R_theta_jc: float
    """Junction-to-case thermal resistance (K/W)."""

    R_theta_cs: float
    """Case-to-sink thermal resistance (K/W)."""

    R_theta_sa: float
    """Sink-to-ambient thermal resistance (K/W)."""

    T_j_max: float
    """Maximum allowed junction temperature (°C)."""

    # --- Citations (required — no magic numbers) ------------------------

    R_jc_because: str
    """Datasheet citation for R_theta_jc."""

    R_cs_because: str
    """Datasheet / application-note citation for R_theta_cs."""

    R_sa_because: str
    """Datasheet / engineering-standard citation for R_theta_sa."""

    T_j_max_because: str = ""
    """Datasheet citation for T_j_max."""


# ---------------------------------------------------------------------------
# Indicator config for a single cross-check entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TjCheckEntry:
    """Per-device cross-check inputs and results.

    Shared inputs (same objective): P, T_amb.
    Independent inputs: transport model (distributed k_eff PDE vs lumped
    R_θ ladder), data source (derived conductivity vs manufacturer-measured
    R_θ, which folds in convection the conduction-only FDM interior omits).
    """

    device: str
    """Device reference designator."""

    power_W: float
    """Worst-case power dissipation (W) — shared input."""

    T_amb: float
    """Ambient temperature (°C) — shared input."""

    T_j_fdm: float
    """Junction temperature from the distributed FDM model (°C)."""

    T_j_lumped: float
    """Junction temperature from the lumped R_θ ladder (°C)."""

    delta_C: float
    """|T_j_fdm - T_j_lumped| (°C)."""

    exceeds_tau: bool
    """Whether the delta exceeds the cross-check tolerance."""

    attribution: str = ""
    """Human-readable attribution of a disagreement (empty when CLEAN)."""


# ---------------------------------------------------------------------------
# Shared vs independent inputs documentation
# ---------------------------------------------------------------------------

SHARED_INPUTS: tuple[str, ...] = (
    "P (per-device worst-case power dissipation, from operating-point gate U6)",
    "T_amb (ambient temperature, same for both models)",
)

INDEPENDENT_INPUTS: tuple[str, ...] = (
    "transport model: distributed k_eff conduction PDE with through-plane sink (FDM)"
    "  vs lumped R_θJC + R_θCS + R_θSA ladder (datasheet)",
    "data source: derived per-cell k_eff from copper coverage + per-cell h_sink"
    "  from shared R_θCS/R_θSA (FDM)"
    "  vs manufacturer-measured lumped R_θ values from device datasheets,"
    "  which match the FDM's sink path",
)


def shared_inputs() -> tuple[str, ...]:
    """Return the shared inputs between the FDM and lumped models."""
    return SHARED_INPUTS


def independent_inputs() -> tuple[str, ...]:
    """Return the genuinely independent inputs between the two models."""
    return INDEPENDENT_INPUTS


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class TjCrossCheckGate(Gate):
    """ROUTING-stage gate: datasheet-R_θ lumped-network cross-check.

    Compares each power device's junction temperature T_j from the
    distributed FDM thermal model against a lumped R_θ ladder built
    from manufacturer datasheet values, corroborating the safety-critical
    T_j ≤ T_j(max) ceiling with two independent models.

    **Same-objective discipline:** both estimates use the same
    worst-case per-device power (from the operating-point gate U6)
    and the same ambient temperature T_amb.  Mismatch would be a
    bfs-oracle-class error, not evidence.

    **Shared inputs:** P (power), T_amb.
    **Independent:** transport model (distributed k_eff PDE vs lumped
    R_θ ladder), data source (derived conductivity vs manufacturer R_θ).

    **Gate discipline (fail-closed):**
    - ``CLEAN``: |T_j_fdm - T_j_lumped| ≤ tau for every device.
    - ``VIOLATIONS``: disagreement > tau on at least one device; carries
      per-device delta + an attribution string diagnosing the likely
      assumption mismatch.
    - ``UNMEASURED``: any required R_θ value is missing — never silently
      skips a device.
    """

    stage = GateStage.ROUTING
    name = "tj_cross_check"

    def __init__(
        self,
        fdm_config: Any,
        devices: dict[str, tuple[float, float]],
        power_map: dict[str, float],
        device_thermal: dict[str, DeviceThermalConfig],
        *,
        tau_C: float = 5.0,
        T_amb: float = 40.0,
    ):
        """
        Args:
            fdm_config: ``ThermalFDMConfig`` for the distributed FDM solve.
            devices: ``{ref: (x_mm, y_mm)}`` device centroids.
            power_map: ``{ref: power_W}`` worst-case per-device power.
            device_thermal: ``{ref: DeviceThermalConfig}`` per-device
                datasheet R_θ with ``because`` citations.
            tau_C: Absolute tolerance (°C) for cross-check agreement.
            T_amb: Ambient temperature (°C) — shared input.
        """
        # Validate we have real config (catch None/empty early)
        if not devices:
            raise ValueError("TjCrossCheckGate: devices dict is empty")
        if not power_map:
            raise ValueError("TjCrossCheckGate: power_map dict is empty")
        if not device_thermal:
            raise ValueError("TjCrossCheckGate: device_thermal dict is empty")
        self._fdm_config = fdm_config
        self._devices = devices
        self._power_map = power_map
        self._device_thermal = device_thermal
        self._tau_C = tau_C
        self._T_amb = T_amb

    # ------------------------------------------------------------------
    # check
    # ------------------------------------------------------------------

    def check(self, _state: BoardState) -> GateResult:
        """Run the T_j cross-check against the current configuration."""
        from temper_placer.physics.thermal_fdm import solve_thermal_fdm

        return self._check_inner(solve_thermal_fdm)

    def _check_inner(self, fdm_solver) -> GateResult:
        """Internal check that accepts an injectable FDM solver.

        Splits from ``check()`` so tests can inject a mock/stub without
        constructing a ``BoardState``.
        """
        # --- Validate all required R_θ values are present ---------------
        for dev_name in self._devices:
            if dev_name not in self._device_thermal:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=(
                        f"T_j cross-check: device '{dev_name}' has no "
                        f"R_θ configuration — cannot cross-check. "
                        f"Fail-closed: never silently skip a device."
                    ),
                )

        # --- Build vertical sink field from device thermal configs (#141) ---
        from temper_placer.physics.heat_removal import build_h_field

        h_field = build_h_field(
            config=self._fdm_config,
            devices=self._devices,
            device_thermal=self._device_thermal,
        )

        # --- Run the distributed FDM solve ------------------------------
        fdm_result = fdm_solver(
            config=self._fdm_config,
            devices=self._devices,
            power_map=self._power_map,
            h_field=h_field,
        )

        if not fdm_result.is_usable:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    f"T_j cross-check: FDM solve returned UNMEASURED: "
                    f"{fdm_result.error_message}"
                ),
            )

        T_grid = fdm_result.field.grid
        cell_size = self._fdm_config.cell_size_mm
        ox, oy = self._fdm_config.origin_mm

        # --- Per-device cross-check -------------------------------------
        violations: list[Violation] = []

        for dev_name, (dx_mm, dy_mm) in self._devices.items():
            power = self._power_map.get(dev_name, 0.0)
            if power <= 0.0:
                continue

            dev_th = self._device_thermal[dev_name]

            # 1. Area-average T_case over the device footprint (FDM)
            T_case_fdm = _area_average_temperature(
                T_grid, dx_mm, dy_mm, cell_size, ox, oy,
            )

            if T_case_fdm is None:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=(
                        f"T_j cross-check: device '{dev_name}' footprint "
                        f"at ({dx_mm:.1f}, {dy_mm:.1f}) falls outside the "
                        f"FDM grid — cannot area-average."
                    ),
                )

            # 2. T_j from the distributed FDM model
            T_j_fdm = T_case_fdm + power * dev_th.R_theta_jc

            # 3. T_j from the lumped R_θ ladder
            R_total = (
                dev_th.R_theta_jc
                + dev_th.R_theta_cs
                + dev_th.R_theta_sa
            )
            T_j_lumped = self._T_amb + power * R_total

            delta = abs(T_j_fdm - T_j_lumped)

            # 4. Compare
            exceeds = delta > self._tau_C
            attribution = ""
            if exceeds:
                attribution = _classify_disagreement(
                    dev_name=dev_name,
                    delta=delta,
                    T_j_fdm=T_j_fdm,
                    T_j_lumped=T_j_lumped,
                    position_mm=(dx_mm, dy_mm),
                    fdm_config=self._fdm_config,
                )

            if exceeds:
                margin = dev_th.T_j_max - max(T_j_fdm, T_j_lumped)
                violations.append(
                    Violation(
                        type=ViolationType.THERMAL,
                        components=(dev_name,),
                        severity=T_j_fdm,
                        threshold=T_j_lumped,
                        description=(
                            f"T_j cross-check VIOLATION on {dev_name}: "
                            f"|T_j_fdm - T_j_lumped| = {delta:.1f}°C "
                            f"> tau = {self._tau_C:.1f}°C. "
                            f"T_j_fdm = {T_j_fdm:.1f}°C, "
                            f"T_j_lumped = {T_j_lumped:.1f}°C. "
                            f"T_j(max) margin = {margin:.1f}°C. "
                            f"Attribution: {attribution}"
                        ),
                        context={
                            "because": (
                                "two-model cross-check (U11): distributed "
                                "FDM and lumped datasheet R_θ disagree, "
                                "the T_j safety ceiling is NOT corroborated"
                            ),
                            "device": dev_name,
                            "T_j_fdm_C": T_j_fdm,
                            "T_j_lumped_C": T_j_lumped,
                            "delta_C": delta,
                            "tau_C": self._tau_C,
                            "T_j_max_C": dev_th.T_j_max,
                            "margin_C": margin,
                            "attribution": attribution,
                            "shared_inputs": list(SHARED_INPUTS),
                            "independent_inputs": list(INDEPENDENT_INPUTS),
                        },
                    )
                )

        if violations:
            return GateResult(
                GateStatus.VIOLATIONS, violations=tuple(violations)
            )
        return GateResult(GateStatus.CLEAN)

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------

    @property
    def shared_inputs(self) -> tuple[str, ...]:
        """Return the shared inputs between the FDM and lumped models."""
        return SHARED_INPUTS

    @property
    def independent_inputs(self) -> tuple[str, ...]:
        """Return the genuinely independent inputs between the two models."""
        return INDEPENDENT_INPUTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _area_average_temperature(
    T_grid: np.ndarray,
    cx_mm: float,
    cy_mm: float,
    cell_size_mm: float,
    ox: float,
    oy: float,
) -> float | None:
    """Area-average the temperature over a device footprint.

    Args:
        T_grid: ``(H, W)`` temperature field from the FDM solve.
        cx_mm, cy_mm: Device centroid in world coordinates (mm).
        cell_size_mm: Grid cell size (mm).
        ox, oy: Grid origin (mm).

    Returns:
        Mean temperature over the footprint cells (5mm × 5mm), or
        ``None`` if the footprint falls entirely outside the grid.
    """
    fp_mm = (5.0, 5.0)
    half_w = fp_mm[0] / 2.0
    half_h = fp_mm[1] / 2.0

    col_min = int(np.floor((cx_mm - half_w - ox) / cell_size_mm))
    col_max = int(np.ceil((cx_mm + half_w - ox) / cell_size_mm))
    row_min = int(np.floor((cy_mm - half_h - oy) / cell_size_mm))
    row_max = int(np.ceil((cy_mm + half_h - oy) / cell_size_mm))

    H, W = T_grid.shape
    col_min = max(0, col_min)
    col_max = min(W, col_max)
    row_min = max(0, row_min)
    row_max = min(H, row_max)

    if col_max <= col_min or row_max <= row_min:
        return None

    patch = T_grid[row_min:row_max, col_min:col_max]
    return float(np.mean(patch))


def _distance_to_heatsink_edge(
    position_mm: tuple[float, float],
    fdm_config: Any,
) -> float:
    """Distance from device centroid to the heatsink edge (mm)."""
    x, y = position_mm
    hs = fdm_config.heatsink_edge.upper().strip()
    ox, oy = fdm_config.origin_mm
    cell = fdm_config.cell_size_mm
    H = fdm_config.height_cells * cell
    W = fdm_config.width_cells * cell

    if hs == "TOP":
        return abs(oy + H - y)
    elif hs == "BOTTOM":
        return abs(y - oy)
    elif hs == "LEFT":
        return abs(x - ox)
    elif hs == "RIGHT":
        return abs(ox + W - x)
    return 0.0


def _classify_disagreement(
    dev_name: str,
    delta: float,
    T_j_fdm: float,
    T_j_lumped: float,
    position_mm: tuple[float, float],
    fdm_config: Any,
) -> str:
    """Attribute a T_j disagreement to a likely physical-model mismatch.

    Returns a human-readable attribution string diagnosing which
    assumption is biting:

    - ``far-from-heatsink``: the device sits far from the heatsink edge;
      the distributed FDM captures the spatial conduction gradient the
      single-resistor lumped model cannot → convection/edge-assumption
      localization.
    - ``uniform``: all devices show a similar delta → global k_eff or
      ambient mismatch.
    - ``JEDEC-consistent``: delta is consistent with JEDEC test-condition
      differences (e.g. R_θJA measured on a 1"×1" test board) → datasheet
      number may not apply to this layout.
    """
    dist = _distance_to_heatsink_edge(position_mm, fdm_config)
    board_span = max(
        fdm_config.height_cells * fdm_config.cell_size_mm,
        fdm_config.width_cells * fdm_config.cell_size_mm,
    )

    if dist > board_span / 3.0 and T_j_fdm > T_j_lumped:
        return (
            f"convection/edge-assumption localization: {dev_name} is "
            f"{dist:.1f}mm from the heatsink edge ({board_span:.1f}mm "
            f"board span). The distributed FDM captures the spatial "
            f"conduction gradient from the adiabatic non-heatsink edges "
            f"that the single-resistor lumped model cannot represent — "
            f"convection cooling at the far edge is unmodeled."
        )

    return (
        f"disagreement ({delta:.1f}°C) on {dev_name}: FDM={T_j_fdm:.1f}°C "
        f"vs lumped={T_j_lumped:.1f}°C. May indicate global k_eff/ambient "
        f"mismatch or JEDEC test-condition mismatch (datasheet R_θJA "
        f"measured on standard 1\"×1\" test board, not this layout)."
    )
