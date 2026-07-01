"""
Decoupling capacitor proximity loss function.

This loss function ensures that decoupling capacitors are placed close to their
associated ICs (or specific power pins on the ICs). It is critical for
power integrity and high-frequency noise suppression.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.losses.decoupling_types import DecouplingClass, DecouplingDetection, DecouplingDetectionSet

POWER_IC_PIN_PATTERNS: list[str] = [
    "VCC", "VDD", "VSS", "VIN", "VOUT", "VBUS", "V+",
    "+5V", "+3V3", "+15V", "+12V", "PWR", "POWER",
    "AVCC", "AVDD", "DVCC", "DVDD",
]

SMALL_CAP_FOOTPRINTS: list[str] = [
    "0201", "0402", "0603", "0805", "1206", "1210", "SMD_C_",
]

LARGE_CAP_FOOTPRINTS: list[str] = [
    "ELEC_D12_5", "ELEC_D10", "ELEC_D8", "ELEC_D6_3",
    "CAP_ELECTRO", "TANT", "POLARIZED",
]

BYPASS_CAPACITANCE_PF: float = 1_000_000.0  # <= 1uF = bypass


def _build_net_class_map(netlist) -> dict[str, str]:
    """Build a mapping of net_name -> net_class from the netlist."""
    result: dict[str, str] = {}
    for net in netlist.nets:
        if hasattr(net, "net_class"):
            result[net.name] = net.net_class
    return result


def _is_capacitor(comp) -> bool:
    """Determine if a component is a capacitor.

    Checks ref prefix 'C' and known capacitor footprints.
    """
    if not comp.ref.upper().startswith("C"):
        return False
    fp = comp.footprint.upper() if comp.footprint else ""
    all_footprints = SMALL_CAP_FOOTPRINTS + LARGE_CAP_FOOTPRINTS
    for known_fp in all_footprints:
        if known_fp.upper() in fp:
            return True
    if comp.ref.upper().startswith("C") and len(comp.pins) == 2:
        return True
    return False


def _is_ic(comp) -> bool:
    """Determine if a component is an IC.

    An IC has 4 or more pins or starts with 'U'/'IC' prefix.
    """
    if len(comp.pins) >= 4:
        return True
    ref = comp.ref.upper()
    if ref.startswith("U") or ref.startswith("IC"):
        return True
    return False


def _shared_vital_net(cap, ic) -> str | None:
    """Find a power net shared between capacitor and IC.

    Returns the first power net found that connects both components.
    """
    cap_nets = {pin.net for pin in cap.pins if pin.net}
    ic_nets = {pin.net for pin in ic.pins if pin.net}
    shared = cap_nets & ic_nets
    for net_name in shared:
        upper = net_name.upper()
        for pattern in POWER_IC_PIN_PATTERNS:
            if pattern.upper() in upper:
                return net_name
    for net_name in shared:
        if "GND" not in net_name.upper() and "VSS" not in net_name.upper():
            return net_name
    if shared:
        return next(iter(shared))
    return None


def _is_power_net(net_name: str) -> bool:
    """Check if a net is a power net based on naming convention."""
    upper = net_name.upper()
    for pattern in POWER_IC_PIN_PATTERNS:
        if pattern.upper() in upper:
            return True
    if upper.startswith("V") or "VCC" in upper or "VDD" in upper or "BAT" in upper:
        return True
    return False


def _classify(cap, ic, net_name: str) -> DecouplingClass:
    """Classify the decoupling relationship between a capacitor and IC.

    Uses footprint size and capacitance value heuristics to determine
    BYPASS vs BULK classification.
    """
    if not _is_power_net(net_name):
        return DecouplingClass.NOT_DECOUPLING

    fp = cap.footprint.upper() if cap.footprint else ""

    for fp_name in LARGE_CAP_FOOTPRINTS:
        if fp_name.upper() in fp:
            return DecouplingClass.BULK

    for fp_name in SMALL_CAP_FOOTPRINTS:
        if fp_name.upper() in fp:
            return DecouplingClass.BYPASS

    cap_value = 0.0
    if hasattr(cap, "attributes") and "value" in cap.attributes:
        try:
            val_str = cap.attributes["value"].upper().replace("UF", "").replace("PF", "").strip()
            cap_value = float(val_str)
            if "PF" in cap.attributes["value"].upper():
                cap_value *= 1.0
            else:
                cap_value *= 1_000_000.0
        except (ValueError, KeyError):
            pass
    if cap_value > 0:
        if cap_value <= BYPASS_CAPACITANCE_PF:
            return DecouplingClass.BYPASS
        return DecouplingClass.BULK

    if _is_power_net(net_name):
        if len(cap.pins) == 2:
            return DecouplingClass.BULK

    return DecouplingClass.NOT_DECOUPLING


def _esl_is_decoupling(cap, ic) -> str | None:
    """Check if a capacitor serves as decoupling for an IC.

    Returns the shared vital net name, or None if not decoupling.
    This is clean dead-code-free: returns shared_vital only.
    """
    if not _is_capacitor(cap) or not _is_ic(ic):
        return None
    return _shared_vital_net(cap, ic)


def auto_detect_decoupling(
    netlist,
    _default_max_dist: float = 3.0,
) -> list:
    """
    Auto-detect decoupling capacitor associations from netlist.

    Heuristics:
    1. Identify capacitors by refdes prefix 'C' and known footprints.
    2. Identify ICs by pin count >= 4 or 'U' prefix.
    3. Find caps connected to a power net shared with an IC.
    4. Classify as BYPASS (small cap, close to IC) or BULK (large cap, reservoir).
    5. Return DecouplingRule list for use with DecouplingCapProximityLoss.

    Returns:
        List of DecouplingRule instances.
    """
    from temper_placer.losses.decoupling import DecouplingRule

    rules: list[DecouplingRule] = []

    caps = [c for c in netlist.components if _is_capacitor(c)]
    ics = [c for c in netlist.components if _is_ic(c)]

    for cap in caps:
        for ic in ics:
            net_name = _shared_vital_net(cap, ic)
            if net_name is None:
                continue
            classification = _classify(cap, ic, net_name)
            if classification == DecouplingClass.NOT_DECOUPLING:
                continue
            power_pin = None
            if cap.pins:
                power_pin = cap.pins[0].net
            rules.append(
                DecouplingRule(
                    cap_ref=cap.ref,
                    ic_ref=ic.ref,
                    max_distance_mm=classification.max_distance_mm,
                    power_pin=power_pin,
                )
            )

    return rules


def _compute_netlist_hash(netlist) -> str:
    """Compute a stable hash of the netlist for cache invalidation."""
    data = []
    for c in netlist.components:
        data.append(f"{c.ref}:{c.footprint}:{len(c.pins)}")
    for n in netlist.nets:
        data.append(f"{n.name}:{len(n.pins)}")
    return hashlib.sha256("|".join(data).encode()).hexdigest()[:16]


def auto_detect_decoupling_set(
    netlist,
) -> DecouplingDetectionSet:
    """
    Auto-detect decoupling capacitors and return a DecouplingDetectionSet.

    Returns:
        DecouplingDetectionSet with all detected associations.
    """
    detections: list[DecouplingDetection] = []

    caps = [c for c in netlist.components if _is_capacitor(c)]
    ics = [c for c in netlist.components if _is_ic(c)]

    for cap in caps:
        for ic in ics:
            net_name = _shared_vital_net(cap, ic)
            if net_name is None:
                continue
            classification = _classify(cap, ic, net_name)
            if classification == DecouplingClass.NOT_DECOUPLING:
                continue

            cap_value = 0.0
            if hasattr(cap, "attributes") and "value" in cap.attributes:
                try:
                    val_str = cap.attributes["value"].upper().replace("UF", "").replace("PF", "").strip()
                    cap_value = float(val_str)
                    if "PF" not in cap.attributes["value"].upper():
                        cap_value *= 1_000_000.0
                except (ValueError, KeyError):
                    pass

            power_pin_name = None
            for pin in cap.pins:
                if pin.net == net_name and _is_power_net(pin.net):
                    power_pin_name = pin.name
                    break
            if power_pin_name is None and cap.pins:
                power_pin_name = cap.pins[0].name

            detections.append(
                DecouplingDetection(
                    cap_ref=cap.ref,
                    ic_ref=ic.ref,
                    classification=classification,
                    power_pin=power_pin_name or "",
                    cap_value_pf=cap_value,
                    cap_package=cap.footprint,
                    net_name=net_name,
                )
            )

    return DecouplingDetectionSet(
        detections=tuple(detections),
        netlist_hash=_compute_netlist_hash(netlist),
    )


@dataclass(frozen=True)
class DecouplingRule:
    """
    Association between a decoupling cap and its IC.

    Attributes:
        cap_ref: Reference designator of the capacitor (e.g., "C1").
        ic_ref: Reference designator of the IC (e.g., "U1").
        max_distance_mm: Maximum allowed distance (center-to-center).
        power_pin: Optional name of the specific power pin on the IC.
    """

    cap_ref: str
    ic_ref: str
    max_distance_mm: float = 3.0
    power_pin: str | None = None


@dataclass
class DecouplingCapProximityLoss(LossFunction):
    """
    Penalize decoupling caps too far from their ICs.

    Uses softplus for smooth gradients near the constraint boundary.
    """

    cap_indices: Array  # (K,) indices of capacitors
    ic_indices: Array  # (K,) indices of associated ICs
    max_distances: Array  # (K,) max distance for each pair

    margin: float = 1.0  # Smoothness margin for softplus

    @property
    def name(self) -> str:
        return "decoupling_proximity"

    def __call__(
        self,
        positions: Array,
        rotations: Array,  # noqa: ARG002
        context: LossContext,  # noqa: ARG002
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
    ) -> LossResult:
        """
        Compute decoupling proximity penalty.
        """
        if self.cap_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        cap_pos = positions[self.cap_indices]  # (K, 2)
        ic_pos = positions[self.ic_indices]  # (K, 2)

        diff = cap_pos - ic_pos
        dist = jnp.sqrt(jnp.sum(diff**2, axis=1) + 1e-12)  # (K,)

        excess = dist - self.max_distances

        penalty_val = self.margin * jax.nn.softplus(excess / self.margin)
        total_penalty = jnp.sum(penalty_val**2)

        return LossResult(
            value=total_penalty,
            breakdown={
                "decoupling_max_dist": jnp.max(dist),
                "decoupling_avg_dist": jnp.mean(dist),
                "decoupling_violations": jnp.sum(dist > self.max_distances),
            },
        )


def create_decoupling_loss(
    netlist,  # Type: Netlist
    rules: list[DecouplingRule],
    margin: float = 1.0,
) -> DecouplingCapProximityLoss:
    """Factory to create DecouplingCapProximityLoss from rules."""
    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}

    cap_indices = []
    ic_indices = []
    max_dists = []

    for rule in rules:
        if rule.cap_ref in ref_to_idx and rule.ic_ref in ref_to_idx:
            cap_indices.append(ref_to_idx[rule.cap_ref])
            ic_indices.append(ref_to_idx[rule.ic_ref])
            max_dists.append(rule.max_distance_mm)

    return DecouplingCapProximityLoss(
        cap_indices=jnp.array(cap_indices, dtype=jnp.int32),
        ic_indices=jnp.array(ic_indices, dtype=jnp.int32),
        max_distances=jnp.array(max_dists, dtype=jnp.float32),
        margin=margin,
    )
