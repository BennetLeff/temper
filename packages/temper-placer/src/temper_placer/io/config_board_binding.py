"""Config-to-board binding verification.

Re-exported from temper_io_types (Rust / pyo3).
"""

from temper_io_types import ConfigBoardMismatchError, extract_config_refs, verify_config_matches_netlist

__all__ = [
    "ConfigBoardMismatchError",
    "extract_config_refs",
    "verify_config_matches_netlist",
]

# OLD: A placement config is authored against a specific board (its component
# OLD: reference designators). Applying a config to a *different* board — e.g. a
# OLD: fixture config against the real production netlist — silently produces a
# OLD: meaningless placement. This module verifies, fail-closed, that every component
# OLD: reference a config names actually exists in the board's netlist.
# OLD:
# OLD: Design note (plan 2026-07-15-001, unit U2): the check is *derived*, not
# OLD: declared. It compares the set of refs the config mentions against the set of
# OLD: refs the netlist actually contains. Nothing is hand-declared (no
# OLD: ``expected_components: N``), so there is no number that can drift.
# OLD:
# OLD: This module intentionally does not migrate or rewrite any existing config. The
# OLD: repo's current configs are authored against the 33-component benchmark fixture
# OLD: and legitimately match the fixture board; they will (correctly) fail this check
# OLD: only if applied to the real board, once the production board exists and the
# OLD: gate is wired into the pipeline entry point (unit U4).
# OLD:
# OLD: from __future__ import annotations
# OLD:
# OLD: from collections.abc import Iterable, Mapping
# OLD: from typing import Any
# OLD:
# OLD:
# OLD: class ConfigBoardMismatchError(ValueError):
# OLD:     """A config references component refs absent from the board's netlist.
# OLD:
# OLD:     Attributes:
# OLD:         missing_refs: Sorted refs named by the config but not present in the
# OLD:             netlist.
# OLD:         config_name: Human-facing identifier for the offending config.
# OLD:     """
# OLD:
# OLD:     def __init__(self, missing_refs: Iterable[str], config_name: str) -> None:
# OLD:         self.missing_refs = sorted(missing_refs)
# OLD:         self.config_name = config_name
# OLD:         sample = ", ".join(self.missing_refs[:10])
# OLD:         more = "" if len(self.missing_refs) <= 10 else f" (+{len(self.missing_refs) - 10} more)"
# OLD:         super().__init__(
# OLD:             f"Config '{config_name}' references {len(self.missing_refs)} component "
# OLD:             f"ref(s) not present in the board netlist: {sample}{more}. "
# OLD:             f"This config was likely authored for a different board."
# OLD:         )
# OLD:
# OLD:
# OLD: # Config keys whose values are a single component reference designator.
# OLD: _SINGLE_REF_KEYS = frozenset(
# OLD:     {
# OLD:         "component",
# OLD:         "component_ref",
# OLD:         "signal_component",
# OLD:         "target_component",
# OLD:         "hv_component",
# OLD:         "from_component",
# OLD:         "to_component",
# OLD:     }
# OLD: )
# OLD:
# OLD: # Config keys whose values are a list of component reference designators.
# OLD: _LIST_REF_KEYS = frozenset({"components", "fixed_components"})
# OLD:
# OLD:
# OLD: def extract_config_refs(config: Mapping[str, Any]) -> set[str]:
# OLD:     """Collect every component reference designator a config mentions.
# OLD:
# OLD:     Walks the config recursively, pulling refs from the well-known ref-bearing
# OLD:     keys (``component``, ``components``, ``fixed_components``,
# OLD:     ``*_component``, ``component_ref``). ``fixed_components`` may be either a
# OLD:     list of refs or a mapping of ref -> placement, so both shapes are handled.
# OLD:
# OLD:     Unknown structure is traversed but ignored; this never raises on shape.
# OLD:     """
# OLD:     refs: set[str] = set()
# OLD:     _collect(config, refs)
# OLD:     return refs
# OLD:
# OLD:
# OLD: def _collect(node: Any, refs: set[str]) -> None:
# OLD:     if isinstance(node, Mapping):
# OLD:         for key, value in node.items():
# OLD:             if key in _SINGLE_REF_KEYS and isinstance(value, str):
# OLD:                 refs.add(value)
# OLD:             elif key in _LIST_REF_KEYS:
# OLD:                 _collect_ref_container(value, refs)
# OLD:             else:
# OLD:                 _collect(value, refs)
# OLD:     elif isinstance(node, (list, tuple)):
# OLD:         for item in node:
# OLD:             _collect(item, refs)
# OLD:
# OLD:
# OLD: def _collect_ref_container(value: Any, refs: set[str]) -> None:
# OLD:     """Handle a ref list or a ref->placement mapping (both valid shapes)."""
# OLD:     if isinstance(value, Mapping):
# OLD:         refs.update(k for k in value.keys() if isinstance(k, str))
# OLD:     elif isinstance(value, (list, tuple)):
# OLD:         refs.update(item for item in value if isinstance(item, str))
# OLD:
# OLD:
# OLD: def verify_config_matches_netlist(
# OLD:     config_refs: Iterable[str],
# OLD:     netlist_refs: Iterable[str],
# OLD:     *,
# OLD:     config_name: str,
# OLD: ) -> None:
# OLD:     """Fail-closed if any config ref is absent from the netlist.
# OLD:
# OLD:     Args:
# OLD:         config_refs: Component refs the config names.
# OLD:         netlist_refs: Component refs present in the board's netlist.
# OLD:         config_name: Identifier for the config, used in the error message.
# OLD:
# OLD:     Raises:
# OLD:         ConfigBoardMismatchError: If ``config_refs`` is not a subset of
# OLD:             ``netlist_refs``.
# OLD:     """
# OLD:     board_refs = set(netlist_refs)
# OLD:     missing = {ref for ref in config_refs if ref not in board_refs}
# OLD:     if missing:
# OLD:         raise ConfigBoardMismatchError(missing, config_name)
