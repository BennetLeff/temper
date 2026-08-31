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

2026-08-17 (session 2): the registry grew five more fact families (via-
geometry defaults, per-netclass via diameter/drill, gate-drive net names,
gate-drive net-current citations, the HV<->LV separation gate threshold)
and the mechanism itself grew ``value_kind="str"`` support. Two new test
classes below extend the same two-sided proof pattern
(``TestSyntheticRegistry`` above) to the new mechanism, plus
``TestRealRegistryExtendedFamilies`` pins each new family's real-repo
state, mirroring ``TestRealRegistryKnownState``. The overall real-repo exit
state changed from VIOLATION (3) to TOOL ERROR (5) as part of this
extension -- the two new ``gate_h*_net_current_rating_a`` facts were
deliberately-red TOOL ERRORS (a citation that was never added, not merely a
wrong value), and tool-error takes priority in the gate's own exit-code
selection.

2026-08-17 (later, same day): docs/evidence/2026-08-17-gate-drive-ampacity-
key-rename-fix.md closed that TOOL ERROR window -- ``StackupGate.
_DEFAULT_NET_CURRENTS`` and ``ipc.rs``'s ``net_currents()`` both gained the
missing ``"GATE_HS"``/``"GATE_LS"`` keys, so both citations now resolve.
Exit state is back to VIOLATION (3) (the pre-existing, unrelated
``mains_voltage_v``/``pollution_degree``/``default_via_diameter_mm``/
``hv_lv_separation_gate_threshold_mm`` reds are untouched by this fix).
``test_gate_exits_violation_on_the_real_repo`` (renamed back from
``test_gate_exits_tool_error_on_the_real_repo``) pins this.
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
        """RENAMED 2026-08-17 (session 2, then again same day): the
        gate_hs_net_current_rating_a / gate_ls_net_current_rating_a TOOL
        ERROR window (see TestRealRegistryExtendedFamilies below) is now
        CLOSED -- docs/evidence/2026-08-17-gate-drive-ampacity-key-rename-
        fix.md added the missing "GATE_HS"/"GATE_LS" keys to both
        StackupGate._DEFAULT_NET_CURRENTS and ipc.rs's net_currents(), so
        both citations now resolve and match. has_tool_error is back to
        False. has_violation stays True: mains_voltage_v/pollution_degree/
        default_via_diameter_mm/hv_lv_separation_gate_threshold_mm are
        still red, unrelated pre-existing findings this fix does not
        touch. If has_tool_error ever goes back to True, verify it is a
        genuine new missing-citation site and not a regression of this
        fix (e.g. a pattern silently stopping to match after further
        edits to either table)."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        has_violation, has_tool_error = check._print_report(results)
        assert has_tool_error is False
        assert has_violation is True


# ---------------------------------------------------------------------------
# 2026-08-17 (session 2) extension: value_kind="str" (board net names)
# ---------------------------------------------------------------------------


def _net_name_fact(**overrides) -> check.Fact:
    base = dict(
        name="widget_net_name",
        category="test",
        authoritative_value="GATE_HS",
        value_kind="str",
        authoritative_source="test fixture",
        homes=(
            check.FactSite(
                file="a.py",
                description="site A",
                pattern=r'GATE_NET\s*=\s*"([^"]+)"',
            ),
            check.FactSite(
                file="b.rs",
                description="site B",
                pattern=r'insert\("([^"]+)"\.into\(\)\)',
            ),
        ),
    )
    base.update(overrides)
    return check.Fact(**base)


class TestStringValueKind:
    """Proves the value_kind="str" extension this changeset adds to the
    mechanism (previously float/int only) -- used for the gate_drive_*_
    net_name and gate_*_net_current_rating_a facts in the real registry.
    Same two-sided non-vacuity shape as TestSyntheticRegistry above: a real
    mismatch must fire, and the identical registry must go clean once
    reconciled."""

    def test_stale_net_name_is_a_violation(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", 'GATE_NET = "GATE_H"\n')  # stale
        _write(tmp_path, "b.rs", 'insert("GATE_HS".into())\n')  # correct
        monkeypatch.setattr(check, "REGISTRY", (_net_name_fact(),))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_violation is True
        assert has_tool_error is False
        by_file = {r.site.file: r for r in results}
        assert by_file["a.py"].matches is False
        assert by_file["a.py"].found_value == "GATE_H"
        assert by_file["b.rs"].matches is True

    def test_reconciled_net_names_are_clean(self, tmp_path, monkeypatch):
        # Identical registry shape, only file contents changed -- the
        # direct "can pass" proof, mirroring test_reconciled_sites_are_clean.
        _write(tmp_path, "a.py", 'GATE_NET = "GATE_HS"\n')
        _write(tmp_path, "b.rs", 'insert("GATE_HS".into())\n')
        monkeypatch.setattr(check, "REGISTRY", (_net_name_fact(),))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_violation is False
        assert has_tool_error is False

    def test_missing_citation_is_a_tool_error_not_a_silent_pass(self, tmp_path, monkeypatch):
        # This is the exact shape of the real gate_hs_net_current_rating_a /
        # gate_ls_net_current_rating_a facts: the pattern searches for a
        # LITERAL key ("GATE_HS") that was never added at the site, so the
        # regex has nothing to match at all -- must fail closed as a tool
        # error, never silently report "0 violations".
        _write(tmp_path, "a.py", 'GATE_NET = "GATE_H"\n')  # old key only
        _write(tmp_path, "b.rs", 'insert("GATE_H".into())\n')
        fact = _net_name_fact(
            homes=(
                check.FactSite(
                    file="a.py",
                    description="site A (GATE_HS specifically)",
                    pattern=r'GATE_NET\s*=\s*"(GATE_HS)"',
                ),
                check.FactSite(
                    file="b.rs",
                    description="site B (GATE_HS specifically)",
                    pattern=r'insert\("(GATE_HS)"\.into\(\)\)',
                ),
            )
        )
        monkeypatch.setattr(check, "REGISTRY", (fact,))

        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)

        assert has_tool_error is True
        assert has_violation is False  # nothing matched to compare


# ---------------------------------------------------------------------------
# 2026-08-17 (session 2): scope_anchor first-match ambiguity
# ---------------------------------------------------------------------------


class TestScopeAnchorFirstMatchAmbiguity:
    """Regression proof for a real bug this changeset caught in its own
    draft registry: ``anchor_re.search()`` returns only the FIRST match in
    the whole file. A scope_anchor that is not unique to the intended
    block silently scopes the search window to the WRONG occurrence
    instead of erroring -- caught here by hand for
    packages/temper-design-bundle/src/design_rules.rs, which has THREE
    ``#[pyo3(signature = (`` occurrences; the generic marker would have
    locked onto the first one (ViaTemplate::new, no via-default fields at
    all) instead of DesignRules::new(). Fixed in the real registry by
    anchoring on ``default_trace_width=0.2,`` instead, which is unique.
    This test proves the FAILURE mode a non-unique anchor produces (a tool
    error from the wrong window, not a crash and not a false match) so a
    future non-unique anchor is at least loud, and separately proves the
    fix pattern (a unique anchor) finds the real value."""

    _RUST_SNIPPET = (
        "#[pyo3(signature = (name, rows, cols))]\n"
        "pub fn new_via_template() {}\n"
        "\n"
        "#[pyo3(signature = (\n"
        "    default_trace_width=0.2,\n"
        "    default_via_diameter=0.6,\n"
        "))]\n"
        "pub fn new_design_rules() {}\n"
    )

    def test_non_unique_anchor_locks_onto_wrong_occurrence(self, tmp_path, monkeypatch):
        _write(tmp_path, "design_rules.rs", self._RUST_SNIPPET)
        fact = check.Fact(
            name="via_diameter_default",
            category="test",
            authoritative_value=0.6,
            value_kind="float",
            authoritative_source="test fixture",
            homes=(
                check.FactSite(
                    file="design_rules.rs",
                    description="non-unique anchor (the bug this test pins)",
                    pattern=r"default_via_diameter=([\d.]+),",
                    scope_anchor=r"#\[pyo3\(signature = \(",
                    scope_lines=3,  # window from the FIRST occurrence
                ),
            ),
        )
        monkeypatch.setattr(check, "REGISTRY", (fact,))

        results = check.run(tmp_path)
        assert len(results) == 1
        # The window starting at the FIRST "#[pyo3(signature = (" (the via
        # template stub, 3 lines) never reaches default_via_diameter at
        # all -- fails closed as a tool error, not a false match.
        assert results[0].error is not None
        assert "did not match" in results[0].error

    def test_unique_anchor_finds_the_real_value(self, tmp_path, monkeypatch):
        _write(tmp_path, "design_rules.rs", self._RUST_SNIPPET)
        fact = check.Fact(
            name="via_diameter_default",
            category="test",
            authoritative_value=0.6,
            value_kind="float",
            authoritative_source="test fixture",
            homes=(
                check.FactSite(
                    file="design_rules.rs",
                    description="unique anchor (the real registry's fix)",
                    pattern=r"default_via_diameter=([\d.]+),",
                    scope_anchor=r"default_trace_width=0\.2,",
                    scope_lines=3,
                ),
            ),
        )
        monkeypatch.setattr(check, "REGISTRY", (fact,))

        results = check.run(tmp_path)
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].found_value == pytest.approx(0.6)
        assert results[0].matches is True


# ---------------------------------------------------------------------------
# 2026-08-17 (session 2): real-repo pins for the new families
# ---------------------------------------------------------------------------


class TestRealRegistryExtendedFamilies:
    """Mirrors TestRealRegistryKnownState's pinning pattern for the five
    fact families added 2026-08-17 (session 2). See
    docs/evidence/2026-08-17-fact-registry-drift-gate-extension.md."""

    def test_default_via_diameter_rust_site_is_known_red(self):
        repo_root = find_repo_root()
        results = check.run(repo_root)
        by_key = {(r.fact, r.site.file): r for r in results}
        r = by_key[
            (
                "default_via_diameter_mm",
                "packages/temper-design-bundle/src/design_rules.rs",
            )
        ]
        assert r.error is None
        assert r.matches is False
        assert r.found_value == pytest.approx(0.6), (
            "expected the vestigial pyo3 #[new] default (0.6) -- if this "
            "now matches 0.9, the coordinated oracle re-pin fix landed; "
            "update this pin, don't delete it silently."
        )

    def test_default_via_diameter_other_four_sites_agree(self):
        repo_root = find_repo_root()
        results = check.run(repo_root)
        non_rust = [
            r
            for r in results
            if r.fact == "default_via_diameter_mm"
            and r.site.file != "packages/temper-design-bundle/src/design_rules.rs"
        ]
        assert len(non_rust) == 4
        for r in non_rust:
            assert r.error is None
            assert r.matches is True, f"{r.site.file} no longer agrees on 0.9mm"

    def test_default_via_drill_is_fully_clean(self):
        repo_root = find_repo_root()
        results = check.run(repo_root)
        drill_results = [r for r in results if r.fact == "default_via_drill_mm"]
        assert len(drill_results) == 5
        for r in drill_results:
            assert r.error is None
            assert r.matches is True

    def test_all_26_netclass_via_facts_are_present_and_clean(self):
        """13 net classes x 2 fields (diameter, drill) = 26 facts, 2 homes
        each -- the regression guard for the exact incident this whole
        extension is motivated by (HighVoltageSignal via 0.8/0.4 vs 1.0/0.4,
        56 sub-fab-floor vias, 4 days to discover)."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        netclass_results = [r for r in results if r.fact.startswith("netclass_")]
        assert len(netclass_results) == 26 * 2
        for r in netclass_results:
            assert r.error is None, f"{r.fact}/{r.site.file}: {r.error}"
            assert r.matches is True, f"{r.fact}/{r.site.file} diverged: {r.found_value}"

    def test_highvoltagesignal_via_facts_specifically_agree(self):
        """The exact fact family (HighVoltageSignal via_diameter/via_drill)
        that bit this project on 2026-08-13 (0.8/0.4 in netclass_rules.yaml
        vs 1.0/0.4 in design_rules.py, 56 sub-fab-floor vias) -- both now
        agree at 1.0/0.4, and this test is the named regression guard for
        that specific pair, not just the aggregate count above."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        by_key = {(r.fact, r.site.file): r for r in results}
        for fact_name, expected in (
            ("netclass_HighVoltageSignal_via_diameter_mm", 1.0),
            ("netclass_HighVoltageSignal_via_drill_mm", 0.4),
        ):
            for site_file in (
                "packages/temper-placer/src/temper_placer/core/design_rules.py",
                "packages/temper-placer/configs/netclass_rules.yaml",
            ):
                r = by_key[(fact_name, site_file)]
                assert r.error is None
                assert r.matches is True
                assert r.found_value == pytest.approx(expected)

    def test_gate_drive_net_names_agree_regression_guard(self):
        """PhysicsGate._GATE_NETS was fixed 2026-08-17 (PR #1310, earlier
        session) from ('GATE_H','GATE_L') to ('GATE_HS','GATE_LS'). Per the
        task's own coordination instruction ("register the invariant
        anyway so it cannot silently return"), this pins that fix as
        green, not merely absent from a known_red list."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        name_results = [
            r
            for r in results
            if r.fact in ("gate_drive_hs_net_name", "gate_drive_ls_net_name")
        ]
        assert len(name_results) == 4  # 2 facts x 2 homes
        for r in name_results:
            assert r.error is None
            assert r.matches is True

    def test_gate_net_current_citations_agree_regression_guard(self):
        """RENAMED 2026-08-17 (later, same day) from
        ``test_gate_net_current_citations_are_known_tool_errors``. The
        divergence this changeset's earlier sweep found -- unlike
        _GATE_NETS above, StackupGate._DEFAULT_NET_CURRENTS and
        temper_drc_rs::ipc::net_currents() were never updated from
        'GATE_H'/'GATE_L' to 'GATE_HS'/'GATE_LS' -- is now FIXED
        (docs/evidence/2026-08-17-gate-drive-ampacity-key-rename-fix.md).
        Per the task's coordination instruction ("register the invariant
        anyway so it cannot silently return"), this pins the fix as green,
        the same pattern ``test_gate_drive_net_names_agree_regression_
        guard`` above uses for PR #1310's earlier _GATE_NETS fix."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        current_results = [
            r
            for r in results
            if r.fact in ("gate_hs_net_current_rating_a", "gate_ls_net_current_rating_a")
        ]
        assert len(current_results) == 4  # 2 facts x 2 homes
        for r in current_results:
            assert r.error is None
            assert r.matches is True

    def test_hv_lv_separation_gate_threshold_is_now_clean(self):
        """UPDATED 2026-08-17 (docs/evidence/2026-08-17-gatedrive-class-
        pairs-gap.md, merging PR #1322 into this registry): this fact WAS
        known red -- both gates.py sites (PhysicsGate._CREEPAGE_MIN_MM and
        IECCreepageGate's inline Violation(...) literal) hardcoded 6.0mm
        against the board's actual enforced 12.6mm PD3 figure. PR #1322
        fixed both: `_CREEPAGE_MIN_MM` was confirmed dead and deleted (no
        site left to compare -- this fact now has a single home, the
        genuinely-literal `isolation_constants.MIN_BARRIER_WIDTH_MM`), and
        IECCreepageGate's inline literal now reads the SSOT-derived
        `HV_LV_CREEPAGE_MM` constant instead of hardcoding a number. See
        `test_hv_lv_creepage_derivation_parity_is_clean` below for the
        companion fact verifying gates.py's and generate_kicad_dru.py's
        derivations of that constant stay in lockstep."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        threshold_results = [
            r for r in results if r.fact == "hv_lv_separation_gate_threshold_mm"
        ]
        assert len(threshold_results) == 1
        for r in threshold_results:
            assert r.error is None
            assert r.matches is True
            assert r.found_value == pytest.approx(12.6)

    def test_hv_lv_creepage_derivation_parity_is_clean(self):
        """NEW 2026-08-17, added alongside the fix above: gates.py's
        HV_LV_CREEPAGE_MM and generate_kicad_dru.py's HV_CREEPAGE_PD3_MM
        must invoke creepage_table_lookup with byte-identical arguments, or
        the two enforcement points can silently diverge again."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        parity_results = [
            r for r in results if r.fact == "hv_lv_creepage_derivation_parity"
        ]
        assert len(parity_results) == 2
        for r in parity_results:
            assert r.error is None
            assert r.matches is True
            assert r.found_value == (
                'creepage_table_lookup(3, "IIIa/IIIb", ">250-400", "17").value_mm() * 2.0'
            )

    def test_hb_gnd_hv_domain_membership_is_clean_regression_guard(self):
        """docs/evidence/2026-08-17-hb-gnd-design-rules-classification-
        blast-radius.md: elec/domain_manifest.yaml's HV domain list and
        the corrected clearance_check test (PR #1300) already agreed
        hb-gnd is HV before this changeset -- this pins that agreement so
        it cannot silently regress (e.g. back to the pre-#1300 stale
        'GND' assertion, which would make the pattern fail to match at
        all, not merely compare a wrong value)."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        domain_results = [
            r for r in results if r.fact == "hb_gnd_hv_domain_membership"
        ]
        assert len(domain_results) == 2  # 1 fact x 2 homes
        for r in domain_results:
            assert r.error is None, f"{r.site.file}: {r.error}"
            assert r.matches is True
            assert r.found_value == "hb-gnd"

    def test_hb_gnd_is_now_classified_HV_on_both_enforced_surfaces(
        self,
    ):
        """Both enforced surfaces now classify `hb-gnd` as HighVoltage.

        RE-DERIVED 2026-08-24, and this test did exactly what it was built
        to do. Its previous name was
        `..._is_fixed_but_kicad_pro_sync_is_known_red`, pinning two halves:
        the TEMPER_NET_ASSIGNMENTS entry that had landed, and the
        pcb/temper.kicad_pro sync that deliberately had not --

            "This test pins BOTH halves: the fix that landed, and the
            honest red that didn't, so neither can silently change without
            this test being updated."

        The red half changed. #1328 (2cc9eeb1e, "sync hb-gnd HighVoltage
        into kicad_pro -- DRC now enforces HV rules on a -170V conductor")
        performed the sync the old docstring said would need "an owner
        decision plus routing remediation". pcb/temper.kicad_pro now
        carries `"hb-gnd": "HighVoltage"`, so the site resolves clean:
        found_value='HighVoltage', matches=True, error=None.

        The rename is part of the re-derivation. A test named
        `..._kicad_pro_sync_is_known_red` that asserts the sync is GREEN is
        a trap for the next reader, the same way
        `test_dru_rule_currently_selects_pd2` was once the DRU moved to
        PD3.

        Both halves are now pinned green, so a REGRESSION on either --
        someone dropping the assignment, or the kicad_pro sync being
        reverted to unblock DRC counts -- still fails here. That is the
        property worth keeping: this is a -170V conductor, and the whole
        point of the original test was that its classification must not
        move silently in either direction."""
        repo_root = find_repo_root()
        results = check.run(repo_root)
        by_key = {(r.fact, r.site.file): r for r in results}

        fixed = by_key[
            (
                "hb_gnd_temper_net_assignment_class",
                "packages/temper-placer/src/temper_placer/core/design_rules.py",
            )
        ]
        assert fixed.error is None
        assert fixed.matches is True
        assert fixed.found_value == "HighVoltage"

        synced = by_key[
            ("hb_gnd_temper_net_assignment_class", "pcb/temper.kicad_pro")
        ]
        assert synced.error is None
        assert synced.matches is True
        assert synced.found_value == "HighVoltage"
