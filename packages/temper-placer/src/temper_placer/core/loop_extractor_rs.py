"""Python wrapper for the Rust loop extractor.

Delegates to Rust `auto_extract_loops_rust` when the temper-rust-router
extension is importable, and falls back to the existing Python extractor
when unavailable. (R23)
"""

from __future__ import annotations

import json
import warnings
from typing import Any

from temper_placer.core.loop import Loop, LoopCollection
from temper_placer.core.netlist import Netlist


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
                "pins": [
                    {"name": p.name, "net": p.net}
                    for p in c.pins
                ],
            }
            for c in netlist.components
        ],
        "nets": [
            {"name": n.name, "pins": [[ref, name] for ref, name in n.pins]}
            for n in netlist.nets
        ],
    }


def _dict_to_loop_collection(data: dict[str, Any]) -> LoopCollection:
    """Convert a Rust-produced dict to a LoopCollection."""
    from temper_placer.core.loop import Loop as PyLoop, LoopEvent, LoopPin

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
            pins=[],  # Pins not serialized across boundary
            nets=nets,
            priority=0,
            max_area_mm2=max_area,
            events=LoopEvent(),
            return_layer="",
            return_net="",
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
    except Exception as e:
        warnings.warn(
            f"Rust loop extraction failed: {e} — falling back to Python",
            stacklevel=2,
        )
        return None
