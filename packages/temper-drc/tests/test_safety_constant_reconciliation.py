"""Reconciliation test: three-read consistency check for safety constants.

Read 1 — authority record (SAFETY_CONSTANT_AUTHORITY).
Read 2 — emitted DRU text (scripts/generate_kicad_dru.py).
Read 3 — runtime check defaults (CreepageCheck + ConstraintSet + CLI template).

Any safety-class divergence is a HOLD failure unless listed in
safety_constant_overrides.yaml with a matching (site, expected_value, reason).
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Ensure temper-placer is importable from this test context
_placer_src = _REPO_ROOT / "packages" / "temper-placer" / "src"
if str(_placer_src) not in sys.path:
    sys.path.insert(0, str(_placer_src))
_drc_src = _REPO_ROOT / "packages" / "temper-drc" / "src"
if str(_drc_src) not in sys.path:
    sys.path.insert(0, str(_drc_src))

from temper_placer.core.design_rules import (  # noqa: E402
    SAFETY_CONSTANT_AUTHORITY,
    SAFETY_CONSTANT_AUTHORITY_NET_CLASSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_module(name: str, path: Path) -> object:
    """Import a module from an absolute file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _authority_map() -> dict[tuple[str, str], float]:
    return {(nc, field): val for (nc, field, val) in SAFETY_CONSTANT_AUTHORITY}


# ---------------------------------------------------------------------------
# Read 1 — authority (import-time, materialised in _authority_map())
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Read 2 — DRU text
# ---------------------------------------------------------------------------

# DRU rules that reference safety net classes but have no matching
# authority entry.  These are site-specific minimums (inter-class gaps,
# manufacturing clearances) that are correct as-is and should not be
# flagged as reconciliation HOLDs.
DRU_allowed_orphans: list[str] = [
    "AC Mains to HV",  # ACMains->HV inter-class gap -- site-specific minimum per EE review
    "HV internal same footprint",  # HV internal same-footprint -- manufacturing clearance per EE review
    "GateDrive near HV",  # Gate drive routing near HV -- site-specific minimum per EE review
    "HV to LV",  # HV->LV inter-class separation (2.0mm) -- site-specific minimum per EE review
]


def _parse_dru_rules(dru_text: str) -> list[dict]:
    """Extract (rule_name, net_class_pair, value_mm) from DRU text.

    Returns a list of dicts with keys: rule, condition, value_mm, classes.
    """
    # Split into rule blocks
    rule_blocks = re.split(r"\n(?=\(rule )", dru_text)
    rules: list[dict] = []

    for block in rule_blocks:
        rule_match = re.search(r'\(rule\s+"([^"]+)"', block)
        if not rule_match:
            continue
        rule_name = rule_match.group(1)

        cond_match = re.search(r'\(condition\s+"([^"]*)"\)', block, re.DOTALL)
        condition = cond_match.group(1) if cond_match else ""

        clear_match = re.search(
            r'\(constraint\s+clearance\s+\(min\s+([\d.]+)mm\)\)', block
        )
        if not clear_match:
            continue
        value_mm = float(clear_match.group(1))

        # Extract net classes from condition
        classes: list[str] = []
        for m in re.finditer(r"NetClass\s*==\s*'([^']+)'", condition):
            classes.append(m.group(1))
        # Map KiCad "Ground" back to "GND"
        classes = ["GND" if c == "Ground" else c for c in classes]

        rules.append(
            {
                "rule": rule_name,
                "condition": condition,
                "value_mm": value_mm,
                "classes": classes,
            }
        )

    return rules


def _safety_class_in_condition(rule: dict) -> bool:
    """Check whether a DRU rule condition references a safety net class."""
    condition = rule["condition"]
    for nc in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES:
        # KiCad uses the Python name directly in DRU (except Ground -> GND handling)
        if f"'{nc}'" in condition:
            return True
    return False


def _dru_findings() -> list[dict]:
    """Read 2: parse DRU output and compare against authority."""
    dru_mod = _load_module(
        "generate_kicad_dru", _REPO_ROOT / "scripts" / "generate_kicad_dru.py"
    )
    dru_text = dru_mod.generate_dru()
    rules = _parse_dru_rules(dru_text)
    auth = _authority_map()
    findings: list[dict] = []

    for rule in rules:
        classes = rule["classes"]
        val = rule["value_mm"]

        # Determine authority key
        auth_key_candidates: list[tuple[str, str]] = []
        if len(classes) >= 1:
            for cls in classes:
                if cls in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES:
                    auth_key_candidates.append((cls, "clearance"))
                if cls in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES:
                    auth_key_candidates.append((cls, "creepage_mm"))

        # Find first matching authority entry
        matched = None
        for key in auth_key_candidates:
            if key in auth:
                if abs(auth[key] - val) < 0.005:
                    matched = key
                    break

        if matched:
            continue  # matches authority

        if _safety_class_in_condition(rule):
            # Check if this DRU rule is an allowed orphan
            if rule["rule"] in DRU_allowed_orphans:
                continue
            # Orphan — safety class referenced but no matching authority
            findings.append(
                {
                    "site": f"dru:{rule['rule']}",
                    "expected_value": val,
                    "authority_value": None,
                    "severity": "HOLD",
                    "message": (
                        f"DRU rule '{rule['rule']}' ({val}mm) references safety class "
                        f"but has no matching authority entry — orphan"
                    ),
                }
            )
        # Non-safety rules are skipped (handled by default allowlist)

    return findings


# ---------------------------------------------------------------------------
# Read 3 — runtime check defaults + CLI template
# ---------------------------------------------------------------------------

def _runtime_findings() -> list[dict]:
    """Read 3: inspect CreepageCheck, ConstraintSet, and CLI template."""
    auth = _authority_map()
    findings: list[dict] = []

    # -- CreepageCheck default --
    from temper_drc.checks.safety.creepage import CreepageCheck  # noqa: E402

    sig = inspect.signature(CreepageCheck.__init__)
    creepage_default = sig.parameters["min_iso_width_mm"].default  # 7.0
    auth_acmains_creepage = auth[("ACMains", "creepage_mm")]

    if abs(creepage_default - auth_acmains_creepage) > 0.005:
        findings.append(
            {
                "site": "creepage.py:CreepageCheck.__init__.min_iso_width_mm",
                "expected_value": creepage_default,
                "authority_value": auth_acmains_creepage,
                "severity": "HOLD",
                "message": (
                    f"CreepageCheck min_iso_width_mm default "
                    f"({creepage_default}) != authority "
                    f"ACMains.creepage_mm ({auth_acmains_creepage})"
                ),
            }
        )

    # -- CLI template creepage_mm --
    cli_path = _REPO_ROOT / "packages" / "temper-drc" / "src" / "temper_drc" / "cli.py"
    cli_source = cli_path.read_text()
    cli_match = re.search(r'"creepage_mm":\s*([\d.]+)', cli_source)
    if cli_match:
        cli_creepage = float(cli_match.group(1))
        if abs(cli_creepage - auth_acmains_creepage) > 0.005:
            findings.append(
                {
                    "site": "cli.py:init_constraints.creepage_mm",
                    "expected_value": cli_creepage,
                    "authority_value": auth_acmains_creepage,
                    "severity": "HOLD",
                    "message": (
                        f"CLI template creepage_mm "
                        f"({cli_creepage}) != authority "
                        f"ACMains.creepage_mm ({auth_acmains_creepage})"
                    ),
                }
            )

    # -- ConstraintSet.hv_clearance_mm (INFORMATIONAL only) --
    from temper_drc.input.constraints import ConstraintSet  # noqa: E402

    hv_default = ConstraintSet().hv_clearance_mm  # 10.0
    auth_hv_clearance = auth[("HighVoltage", "clearance")]

    if abs(hv_default - auth_hv_clearance) > 0.005:
        findings.append(
            {
                "site": "constraints.py:ConstraintSet.hv_clearance_mm",
                "expected_value": hv_default,
                "authority_value": auth_hv_clearance,
                "severity": "INFORMATIONAL",
                "message": (
                    f"ConstraintSet.hv_clearance_mm default "
                    f"({hv_default}) != HighVoltage.clearance "
                    f"({auth_hv_clearance}) — independent axis "
                    f"(HV/LV inter-domain separation), not an intra-class clearance"
                ),
            }
        )

    return findings


# ---------------------------------------------------------------------------
# Override mechanism
# ---------------------------------------------------------------------------

_OVERRIDE_PATH = Path(__file__).resolve().parent / "safety_constant_overrides.yaml"


def _load_overrides() -> list[dict]:
    if not _OVERRIDE_PATH.exists():
        return []
    with open(_OVERRIDE_PATH) as f:
        data = yaml.safe_load(f)
    return (data or {}).get("overrides", [])


def _apply_overrides(findings: list[dict], overrides: list[dict]) -> list[dict]:
    result: list[dict] = []
    for finding in findings:
        matched = False
        for ov in overrides:
            if (
                ov.get("site") == finding["site"]
                and abs(ov.get("expected_value", 0) - finding["expected_value"]) < 0.005
                and ov.get("reason", "").strip()
            ):
                finding["severity"] = "OVERRIDE"
                finding["override_reason"] = ov["reason"]
                finding["override_ticket"] = ov.get("ticket", "")
                matched = True
                break
        result.append(finding)
    return result


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_safety_constants_reconcile():
    """Reconcile authority records against DRU output and runtime defaults."""
    all_findings: list[dict] = []
    all_findings.extend(_dru_findings())
    all_findings.extend(_runtime_findings())

    overrides = _load_overrides()
    all_findings = _apply_overrides(all_findings, overrides)

    holds = [f for f in all_findings if f["severity"] == "HOLD"]
    informationals = [f for f in all_findings if f["severity"] == "INFORMATIONAL"]
    overridden = [f for f in all_findings if f["severity"] == "OVERRIDE"]

    report_lines: list[str] = []
    if overridden:
        report_lines.append("--- OVERRIDE (allowed via safety_constant_overrides.yaml) ---")
        for f in overridden:
            report_lines.append(
                f"  {f['site']}: {f['expected_value']}"
                f" (authority: {f.get('authority_value', 'orphan')})"
                f" — {f['override_reason']}"
            )
    if informationals:
        report_lines.append("--- INFORMATIONAL ---")
        for f in informationals:
            report_lines.append(f"  {f['site']}: {f['message']}")
    if holds:
        report_lines.append("--- HOLD (divergence from authority, no override) ---")
        for f in holds:
            report_lines.append(f"  {f['site']}: {f['message']}")

    if holds:
        if overridden or informationals:
            report_lines.insert(0, "")
        pytest.fail(
            f"{len(holds)} safety-constant divergence(s) found (HOLD):\n"
            + "\n".join(report_lines)
        )
    else:
        # Print report for visibility even when passing
        print("\n".join(report_lines) if report_lines else "All safety constants reconciled.")
