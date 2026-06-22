"""Shared safety keywords and resolve_safety_category for temper-drc safety checks."""

from __future__ import annotations

import sys

ISO_COMPONENT_KEYWORDS: tuple[str, ...] = (
    "iso", "opto", "coupler", "isolator", "transformer", "adum", "dcdc", "mev1",
)
ISO_ZONE_KEYWORDS: tuple[str, ...] = (
    "iso", "opto", "coupler", "transformer", "gutter", "slot",
)
HV_KEYWORDS: tuple[str, ...] = ("hv", "line", "ac", "neutral", "mains")
LV_KEYWORDS: tuple[str, ...] = ("lv", "signal", "3v3", "5v", "gnd", "analog")


def _warn_fallback(net_class_str: str, guessed: str) -> None:
    sys.stderr.write(
        f"[temper-drc] safety_category fallback: net_class='{net_class_str}' "
        f"guessed='{guessed}'. Declare safety_category on net class '{net_class_str}' "
        f"or add net to TEMPER_NET_ASSIGNMENTS.\n"
    )


def resolve_safety_category(net_class_str: str) -> str | None:
    """Resolve a net-class string to a safety category, with keyword fallback."""
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES

    rules = TEMPER_NET_CLASSES.get(net_class_str)
    if rules is not None and getattr(rules, "safety_category", None) is not None:
        return rules.safety_category
    # Fallback: keyword scan
    lc = net_class_str.lower()
    if any(k in lc for k in HV_KEYWORDS):
        guessed: str | None = "HV"
    elif any(k in lc for k in LV_KEYWORDS):
        guessed = "LV"
    elif any(k in lc for k in ISO_COMPONENT_KEYWORDS):
        guessed = "iso"
    else:
        return None
    _warn_fallback(net_class_str, guessed)
    return guessed
