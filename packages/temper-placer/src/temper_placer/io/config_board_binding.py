"""Config-to-board binding verification.

A placement config is authored against a specific board (its component
reference designators). Applying a config to a *different* board — e.g. a
fixture config against the real production netlist — silently produces a
meaningless placement. This module verifies, fail-closed, that every component
reference a config names actually exists in the board's netlist.

Design note (plan 2026-07-15-001, unit U2): the check is *derived*, not
declared. It compares the set of refs the config mentions against the set of
refs the netlist actually contains. Nothing is hand-declared (no
``expected_components: N``), so there is no number that can drift.

This module intentionally does not migrate or rewrite any existing config. The
repo's current configs are authored against the 33-component benchmark fixture
and legitimately match the fixture board; they will (correctly) fail this check
only if applied to the real board, once the production board exists and the
gate is wired into the pipeline entry point (unit U4).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


class ConfigBoardMismatchError(ValueError):
    """A config references component refs absent from the board's netlist.

    Attributes:
        missing_refs: Sorted refs named by the config but not present in the
            netlist.
        config_name: Human-facing identifier for the offending config.
    """

    def __init__(self, missing_refs: Iterable[str], config_name: str) -> None:
        self.missing_refs = sorted(missing_refs)
        self.config_name = config_name
        sample = ", ".join(self.missing_refs[:10])
        more = "" if len(self.missing_refs) <= 10 else f" (+{len(self.missing_refs) - 10} more)"
        super().__init__(
            f"Config '{config_name}' references {len(self.missing_refs)} component "
            f"ref(s) not present in the board netlist: {sample}{more}. "
            f"This config was likely authored for a different board."
        )


# Config keys whose values are a single component reference designator.
_SINGLE_REF_KEYS = frozenset(
    {
        "component",
        "component_ref",
        "signal_component",
        "target_component",
        "hv_component",
        "from_component",
        "to_component",
    }
)

# Config keys whose values are a list of component reference designators.
_LIST_REF_KEYS = frozenset({"components", "fixed_components"})


def extract_config_refs(config: Mapping[str, Any]) -> set[str]:
    """Collect every component reference designator a config mentions.

    Walks the config recursively, pulling refs from the well-known ref-bearing
    keys (``component``, ``components``, ``fixed_components``,
    ``*_component``, ``component_ref``). ``fixed_components`` may be either a
    list of refs or a mapping of ref -> placement, so both shapes are handled.

    Unknown structure is traversed but ignored; this never raises on shape.
    """
    refs: set[str] = set()
    _collect(config, refs)
    return refs


def _collect(node: Any, refs: set[str]) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in _SINGLE_REF_KEYS and isinstance(value, str):
                refs.add(value)
            elif key in _LIST_REF_KEYS:
                _collect_ref_container(value, refs)
            else:
                _collect(value, refs)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect(item, refs)


def _collect_ref_container(value: Any, refs: set[str]) -> None:
    """Handle a ref list or a ref->placement mapping (both valid shapes)."""
    if isinstance(value, Mapping):
        refs.update(k for k in value.keys() if isinstance(k, str))
    elif isinstance(value, (list, tuple)):
        refs.update(item for item in value if isinstance(item, str))


def verify_config_matches_netlist(
    config_refs: Iterable[str],
    netlist_refs: Iterable[str],
    *,
    config_name: str,
) -> None:
    """Fail-closed if any config ref is absent from the netlist.

    Args:
        config_refs: Component refs the config names.
        netlist_refs: Component refs present in the board's netlist.
        config_name: Identifier for the config, used in the error message.

    Raises:
        ConfigBoardMismatchError: If ``config_refs`` is not a subset of
            ``netlist_refs``.
    """
    board_refs = set(netlist_refs)
    missing = {ref for ref in config_refs if ref not in board_refs}
    if missing:
        raise ConfigBoardMismatchError(missing, config_name)
