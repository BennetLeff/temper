"""Python wrapper for the Rust loop extractor.

Delegates to Rust `auto_extract_loops_rust` when the temper-rust-router
extension is importable, and falls back to the existing Python extractor
when unavailable. (R23)

Schema contract — fields preserved vs reconstructed vs lost:
  PRESERVED: name, components, nets, max_area_mm2 (Rust computes these)
  RECONSTRUCTED: loop_type (string→enum), priority, events, return_layer,
    return_net (all deterministic from loop_type — same hardcoded values
    as the Python extractor)
  LOST: pins, description, source (Rust has no concept of these; pins are
    always [], description is generic, source is always absent)

Adding a new topology? Update _LOOP_TYPE_PRIORITY, _LOOP_TYPE_EVENTS,
_LOOP_TYPE_RETURN_LAYER, _LOOP_TYPE_RETURN_NET to match the Python
extractor's hardcoded values.
"""

from __future__ import annotations

import json
import warnings
from typing import Any

from temper_placer.core.loop import LoopCollection, LoopPriority, LoopType
from temper_placer.core.netlist import Netlist

# Reconstructed fields — deterministic from loop_type, matching the
# hardcoded values in the pure-Python extractor
# (trace_commutation_loop, trace_gate_drive_loop, trace_bootstrap_loop).
# Anything not listed defaults to the dataclass field default (MEDIUM
# priority, empty LoopEvent, empty return paths).

_LOOP_TYPE_PRIORITY: dict[LoopType, LoopPriority] = {
    LoopType.COMMUTATION: LoopPriority.CRITICAL,
    LoopType.GATE_DRIVE_HIGH: LoopPriority.CRITICAL,
    LoopType.GATE_DRIVE_LOW: LoopPriority.CRITICAL,
    LoopType.BOOTSTRAP: LoopPriority.HIGH,
}

_LOOP_TYPE_EVENTS: dict[LoopType, dict[str, float | None]] = {
    LoopType.COMMUTATION: {
        "di_dt": 1.0e9,  # 1 A/ns typical IGBT turn-off
        "dv_dt": 5.0e9,  # 5 V/ns switch node
        "frequency_hz": 25000.0,
        "peak_current_a": 30.0,
    },
    LoopType.GATE_DRIVE_HIGH: {
        "di_dt": 1.0e8,  # 100 mA/ns gate current
        "frequency_hz": 25000.0,
    },
    LoopType.GATE_DRIVE_LOW: {
        "di_dt": 1.0e8,
        "frequency_hz": 25000.0,
    },
    LoopType.BOOTSTRAP: {
        "frequency_hz": 25000.0,
        "peak_current_a": 0.5,  # Low bootstrap charging current
    },
}

_LOOP_TYPE_RETURN_LAYER: dict[LoopType, str] = {
    LoopType.COMMUTATION: "L2_GND",
}

_LOOP_TYPE_RETURN_NET: dict[LoopType, str] = {
    LoopType.COMMUTATION: "PGND",
}


def _netlist_to_dict(netlist: Netlist) -> dict[str, Any]:
    """Serialize a Netlist to a dict for crossing the Rust/Python boundary."""
    return {
        "components": [
            {
                "ref": c.ref,
                "footprint": c.footprint,
                "mpn": c.attributes.get("MPN", ""),
                "value": c.attributes.get("value", ""),
                "net_class": c.net_class,
                "pins": [{"name": p.name, "net": p.net} for p in c.pins],
            }
            for c in netlist.components
        ],
        "nets": [
            {"name": n.name, "pins": [[ref, name] for ref, name in n.pins]} for n in netlist.nets
        ],
    }


def _dict_to_loop_collection(data: dict[str, Any]) -> LoopCollection:
    """Convert a Rust-produced dict to a LoopCollection."""
    from temper_placer.core.loop import Loop as PyLoop
    from temper_placer.core.loop import LoopEvent

    loops = []
    for loop_dict in data.get("loops", []):
        components = loop_dict.get("components", [])
        nets = loop_dict.get("nets", [])
        loop_type_str = loop_dict.get("loop_type", "unknown")
        max_area = loop_dict.get("max_area_mm2", 500.0)

        from temper_placer.core.loop import LoopType

        try:
            lt = LoopType(loop_type_str)
        except ValueError:
            lt = LoopType.COMMUTATION

        py_loop = PyLoop(
            name=loop_dict["name"],
            loop_type=lt,
            description=f"Extracted via Rust: {loop_dict['name']}",
            components=components,
            pins=[],  # Pins not available from Rust (no pin-tracing concept yet)
            nets=nets,
            priority=_LOOP_TYPE_PRIORITY.get(lt, LoopPriority.MEDIUM),
            max_area_mm2=max_area,
            events=LoopEvent(**_LOOP_TYPE_EVENTS.get(lt, {})),
            return_layer=_LOOP_TYPE_RETURN_LAYER.get(lt, ""),
            return_net=_LOOP_TYPE_RETURN_NET.get(lt, ""),
        )
        loops.append(py_loop)

    return LoopCollection(loops=loops)


def auto_extract_loops_rs(
    netlist: Netlist,
    topology_hints: dict[str, str] | None = None,
) -> LoopCollection | None:
    """
    Extract loops using the Rust backend.

    Args:
        netlist: Parsed netlist.
        topology_hints: Optional topology hints (e.g., {'topology': 'half_bridge'}).

    Returns:
        LoopCollection on success, None if Rust is unavailable.
    """
    try:
        import temper_rust_router

        netlist_dict = _netlist_to_dict(netlist)
        if topology_hints:
            netlist_dict["topology_hints"] = topology_hints

        json_str = json.dumps(netlist_dict)
        result_json = temper_rust_router.auto_extract_loops_rust(json_str)

        result = json.loads(result_json)
        if not result.get("ok", False):
            error_msg = result.get("error", "Unknown Rust extraction error")
            raise RuntimeError(f"Rust loop extraction failed: {error_msg}")

        return _dict_to_loop_collection(result)

    except ImportError:
        warnings.warn(
            "temper-rust-router not available — falling back to Python loop extractor",
            stacklevel=2,
        )
        return None
    except (
        RuntimeError,
        json.JSONDecodeError,
        TypeError,
        AttributeError,
        KeyError,
        ValueError,
    ) as e:
        warnings.warn(
            f"Rust loop extraction failed: {e} — falling back to Python",
            stacklevel=2,
        )
        return None
