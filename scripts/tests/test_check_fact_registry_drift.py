"""Tests for check_fact_registry_drift.py.

``TestSyntheticRegistry`` proves the mechanism itself on a ``tmp_path`` tree
with a monkeypatched ``REGISTRY`` -- independent of whatever the real board's
files say on any given day. This is the direct "gate is not vacuous" proof:
a real divergence must fire (``test_mismatched_site_is_a_violation``), and
the identical registry must go clean once every home is reconciled to the
authoritative value (``test_reconciled_sites_are_clean``) -- the same
tmp_path tree, same registry shape, only the file contents change.

``TestRealRegistryKnownState`` runs the gate against the actual repo root
with the real, hardcoded ``REGISTRY``, pinning the documented, currently-red
``mains_voltage_v`` / ``pollution_degree`` finding (see the gate's own
module docstring) as a regression check: if it ever silently goes clean
without the coordinated fix described there landing, this test explains
why that would be suspicious rather than celebrated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_fact_registry_drift as check  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _voltage_fact(**overrides) -> check.Fact:
    base = dict(
        name="widget_voltage_v",
        category="test",
        authoritative_value=120.0,
        value_kind="float",
        authoritative_source="test fixture",
        homes=(
            check.FactSite(
                file="a.yaml",
                description="site A",
                pattern=r"voltage_v:\s*([\d.]+)",
            ),
            check.FactSite(
                file="b.rs",
                description="site B",
                pattern=r"voltage_v,\s*([\d.]+)_f64",
            ),
        ),
    )
    base.update(overrides)
    return check.Fact(**base)


class TestSyntheticRegistry:
    def test_mismatched_site_is_a_violation(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.yaml", "voltage_v: 120.0\n")
        _write(tmp_path, "b.rs", "voltage_v, 230.0_f64\n")
        monkeypatch.setattr(check, "REGISTRY", (_voltage_fact(),))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_violation is True
        assert has_tool_error is False
        by_file = {r.site.file: r for r in results}
        assert by_file["a.yaml"].matches is True
        assert by_file["b.rs"].matches is False
        assert by_file["b.rs"].found_value == pytest.approx(230.0)

    def test_reconciled_sites_are_clean(self, tmp_path, monkeypatch):
        # Identical registry shape, only the file contents changed --
        # proves the gate can pass, i.e. it is not wired to always fail.
        _write(tmp_path, "a.yaml", "voltage_v: 120.0\n")
        _write(tmp_path, "b.rs", "voltage_v, 120.0_f64\n")
        monkeypatch.setattr(check, "REGISTRY", (_voltage_fact(),))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_violation is False
        assert has_tool_error is False

    def test_missing_file_is_a_tool_error_not_a_pass(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.yaml", "voltage_v: 120.0\n")
        # b.rs deliberately not written.
        monkeypatch.setattr(check, "REGISTRY", (_voltage_fact(),))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_tool_error is True

    def test_renamed_field_is_a_tool_error_not_a_silent_pass(self, tmp_path, monkeypatch):
        # The field was renamed at the site; the pattern can no longer find
        # it. This must be loud (fail closed), never silently dropped.
        _write(tmp_path, "a.yaml", "voltage_v: 120.0\n")
        _write(tmp_path, "b.rs", "input_voltage, 120.0_f64\n")
        monkeypatch.setattr(check, "REGISTRY", (_voltage_fact(),))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_tool_error is True

    def test_scope_anchor_prevents_cross_class_false_match(self, tmp_path, monkeypatch):
        # Two classes in the same file both declare the field name; without
        # scoping, a regex could match the WRONG class's value.
        _write(
            tmp_path,
            "classes.py",
            'CLASSES = {\n'
            '    "Other": dict(voltage_v=999.0),\n'
            '    "ACMains": dict(voltage_v=120.0),\n'
            "}\n",
        )
        fact = check.Fact(
            name="acmains_voltage_v",
            category="test",
            authoritative_value=120.0,
            value_kind="float",
            authoritative_source="test fixture",
            homes=(
                check.FactSite(
                    file="classes.py",
                    description="ACMains only",
                    pattern=r"voltage_v=([\d.]+)",
                    scope_anchor=r'"ACMains":\s*dict\(',
                    scope_lines=2,
                ),
            ),
        )
        monkeypatch.setattr(check, "REGISTRY", (fact,))

        results = check.run(tmp_path)
        assert len(results) == 1
        assert results[0].found_value == pytest.approx(120.0)
        assert results[0].matches is True

    def test_empty_registry_is_a_tool_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(check, "REGISTRY", ())
        with pytest.raises(check.GateError):
            check.run(tmp_path)

    def test_fact_with_zero_homes_is_a_tool_error(self, tmp_path, monkeypatch):
        bad_fact = check.Fact(
            name="orphan",
            category="test",
            authoritative_value=1.0,
            value_kind="float",
            authoritative_source="test fixture",
            homes=(),
        )
        monkeypatch.setattr(check, "REGISTRY", (bad_fact,))
        with pytest.raises(check.GateError):
            check.run(tmp_path)


class TestRealRegistryKnownState:
    """Pins the documented, currently-red mains_voltage_v/pollution_degree
    finding. See check_fact_registry_drift.py's module docstring for the
    full investigation and why this is deliberately NOT fixed by editing
    the registry or the sites -- see docs/evidence/2026-08-17-fact-dedup-
    inventory-and-gate.md.

    2026-08-17 UPDATE: specification_contracts.rs's SafetySpec default was
    corrected to 120.0/PD3 and its oracle re-pinned (docs/evidence/
    2026-08-17-safetyspec-default-repin.md) -- removed from known_red
    below, per this class's own instruction ("if this test ever fails
    because a site now MATCHES... update this pin"). pcb_spec.yaml and
    design_rules.py remain open, still pinned-oracle-entangled /
    derivation-surface-unswept respectively."""

    def test_registry_is_non_empty(self):
        assert len(check.REGISTRY) >= 2

    def test_main_ato_agrees_with_authority(self):
        repo_root = find_repo_root()
        results = check.run(repo_root)
        by_key = {(r.fact, r.site.file): r for r in results}
        main_ato = by_key[("mains_voltage_v", "elec/src/main.ato")]
        assert main_ato.error is None
        assert main_ato.matches is True, (
            "elec/src/main.ato's v_ac_nominal is expected to already agree "
            "with REQ-SYS-01 (120V) -- if this now fails, either the .ato "
            "changed or REQ-SYS-01 changed; re-verify authoritative_value."
        )

    def test_specification_contracts_rs_now_agrees_with_authority(self):
        """2026-08-17: specification_contracts.rs's SafetySpec default was
        corrected to 120.0/PD3 (docs/evidence/2026-08-17-safetyspec-default-
        repin.md). Positive confirmation, not just an absence from
        known_red below -- if this ever fails, the site regressed back
        toward the stale 230.0/PD2 default."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        by_key = {(r.fact, r.site.file): r for r in results}
        rs_file = "packages/temper-design-bundle/src/specification_contracts.rs"
        for fact_name in ("mains_voltage_v", "pollution_degree"):
            r = by_key[(fact_name, rs_file)]
            assert r.error is None
            assert r.matches is True, (
                f"{fact_name} at {rs_file} no longer matches the "
                "authoritative value -- SafetySpec's default regressed."
            )

    def test_known_divergent_sites_are_still_divergent(self):
        # This is an EXPECTED-RED pin, not a normal regression guard: it
        # documents that the finding is real and still open. If this test
        # ever fails because a site now MATCHES, that is good news -- go
        # verify the coordinated fix (registry update, oracle re-pin,
        # test_specification.py corrections) actually landed, then update
        # this pin, don't just delete it.
        repo_root = find_repo_root()
        results = check.run(repo_root)
        by_key = {(r.fact, r.site.file): r for r in results}

        known_red = [
            ("mains_voltage_v", "packages/temper-placer/configs/pcb_spec.yaml"),
            (
                "mains_voltage_v",
                "packages/temper-placer/src/temper_placer/core/design_rules.py",
            ),
            ("pollution_degree", "packages/temper-placer/configs/pcb_spec.yaml"),
        ]
        for key in known_red:
            r = by_key[key]
            assert r.error is None, f"{key} is now a tool error, not a value: {r.error}"
            assert r.matches is False, (
                f"{key} now MATCHES the authoritative value -- if this is a "
                "real fix, update this pin (see the docstring above); if "
                "not, something silently changed the registry or the site."
            )

    def test_gate_exits_violation_on_the_real_repo(self):
        repo_root = find_repo_root()
        results = check.run(repo_root)
        has_violation, has_tool_error = check._print_report(results)
        assert has_tool_error is False
        assert has_violation is True
