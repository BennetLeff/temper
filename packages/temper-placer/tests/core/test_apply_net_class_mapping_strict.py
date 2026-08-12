"""`Netlist.apply_net_class_mapping_strict` -- parse-don't-validate boundary.

Spike: docs/evidence/2026-08-11-typed-net-refs-spike.md. Motivating defect:
31 `net_classes:` keys across 4 config files name no real net on
`pcb/temper.kicad_pcb`; the production consumer,
`Netlist.apply_net_class_mapping`, does an exact-key dict lookup and
silently skips a miss (its own docstring: "Nets not in the mapping retain
their current net_class"). `apply_net_class_mapping_strict` is an additive
Rust method (`netlist_contracts.rs`) that raises `ValueError` naming every
unresolved key instead, and applies nothing at all if any key is
unresolved (all-or-nothing).

Synthetic tests below prove the contract directly. `TestRealRepoIntegration`
proves it against the real board and `temper_constraints.yaml`.

UPDATED (fix/netclass-config-keys): `temper_constraints.yaml`'s 5 broken
keys (`AC_L`/`AC_N`/`GND` case mismatches, stale `+340V_BUS`, and the
genuinely-nonexistent `PE`, deleted rather than mapped onto a guess -- see
that file's own `net_classes:` comments) were reconciled in that PR. This
class now pins the fixed, *clean* state instead of the violation set, and
exists to catch a future regression (a new key drifting from the board
again) rather than to document a known-broken input.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb
import yaml

_rs = _tdb.netlist_contracts

REPO_ROOT = Path(__file__).resolve().parents[4]


def _netlist(names: list[str]) -> object:
    return _rs.Netlist(components=[], nets=[_rs.Net(name=n, pins=[]) for n in names])


class TestSyntheticContract:
    def test_exact_match_applies_and_returns_count(self):
        nl = _netlist(["ac_l", "gnd"])
        updated = nl.apply_net_class_mapping_strict({"ac_l": "ACMains", "gnd": "Ground"})
        assert updated == 2
        assert nl.get_net("ac_l").net_class == "ACMains"
        assert nl.get_net("gnd").net_class == "Ground"

    def test_unknown_net_raises_value_error(self):
        nl = _netlist(["ac_l"])
        with pytest.raises(ValueError, match=r"PE"):
            nl.apply_net_class_mapping_strict({"PE": "ACMains"})

    def test_case_mismatch_is_a_hard_error_not_a_silent_fold(self):
        """The exact `AC_L` vs. `ac_l` shape found in the real repo."""
        nl = _netlist(["ac_l"])
        with pytest.raises(ValueError, match=r"AC_L"):
            nl.apply_net_class_mapping_strict({"AC_L": "ACMains"})

    def test_one_bad_key_applies_nothing_all_or_nothing(self):
        nl = _netlist(["ac_l", "gnd"])
        net = nl.get_net("ac_l")
        assert net.net_class == "Signal"
        with pytest.raises(ValueError):
            nl.apply_net_class_mapping_strict({"ac_l": "ACMains", "PE": "ACMains"})
        # "ac_l" would have resolved on its own -- confirms the good key was
        # not applied just because it happened to come first.
        assert nl.get_net("ac_l").net_class == "Signal"

    def test_error_names_every_unresolved_key_not_just_the_first(self):
        nl = _netlist(["gnd"])
        with pytest.raises(ValueError) as exc_info:
            nl.apply_net_class_mapping_strict(
                {"AC_L": "ACMains", "AC_N": "ACMains", "PE": "ACMains"}
            )
        msg = str(exc_info.value)
        assert "AC_L" in msg
        assert "AC_N" in msg
        assert "PE" in msg

    def test_existing_apply_net_class_mapping_is_unchanged_and_still_silent(self):
        """`apply_net_class_mapping_strict` is additive -- the oracle-parity
        method it sits beside must keep its documented silent-skip
        behavior verbatim."""
        nl = _netlist(["ac_l"])
        updated = nl.apply_net_class_mapping({"AC_L": "ACMains", "PE": "ACMains"})
        assert updated == 0
        assert nl.get_net("ac_l").net_class == "Signal"

    def test_empty_mapping_is_a_no_op_not_an_error(self):
        nl = _netlist(["ac_l"])
        assert nl.apply_net_class_mapping_strict({}) == 0

    def test_reapplying_the_same_mapping_reports_zero_further_updates(self):
        nl = _netlist(["ac_l"])
        assert nl.apply_net_class_mapping_strict({"ac_l": "ACMains"}) == 1
        assert nl.apply_net_class_mapping_strict({"ac_l": "ACMains"}) == 0


class TestRealRepoIntegration:
    """Against the real board and the real, now-reconciled config file."""

    @pytest.fixture
    def real_netlist(self):
        # Function-scoped (not class-scoped): both tests below mutate net
        # classes in place, so each must start from a fresh, unmutated
        # netlist rather than observing the other test's applied changes.
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        parse_result = parse_kicad_pcb(REPO_ROOT / "pcb" / "temper.kicad_pcb")
        return parse_result.netlist

    @pytest.fixture(scope="class")
    def real_net_classes(self) -> dict[str, str]:
        config_path = (
            REPO_ROOT / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
        )
        return yaml.safe_load(config_path.read_text())["net_classes"]

    def test_strict_succeeds_on_the_reconciled_config(self, real_netlist, real_net_classes):
        """Every key in `temper_constraints.yaml`'s `net_classes:` now
        names a real board net, so the strict, all-or-nothing method must
        apply every one of them without raising -- and every one must land
        on its intended class, whether or not it required a change.

        ``updated`` (the count of nets whose ``net_class`` actually
        *changed*) is no longer necessarily ``len(real_net_classes)``: since
        the rust-net-classification fix, `real_netlist` (via
        `parse_kicad_pcb`'s default `TEMPER_NET_ASSIGNMENTS` mapping) already
        arrives with real classes for many nets, so some of this config's
        keys are now no-ops (same value, not a change) rather than first-time
        assignments -- `apply_net_class_mapping_strict` reports 0 for a
        no-op, matching `apply_net_class_mapping`'s documented change-count
        semantics. The end state (every key's net at its intended class) is
        the real invariant, asserted below regardless of how many were
        no-ops.
        """
        updated = real_netlist.apply_net_class_mapping_strict(real_net_classes)
        assert updated <= len(real_net_classes)
        for net_name, class_name in real_net_classes.items():
            assert real_netlist.get_net(net_name).net_class == class_name

    def test_existing_method_applies_everything_too(self, real_netlist, real_net_classes):
        """Same real inputs, old (silent-skip) method: now that no key is
        broken, it has nothing to silently skip -- both methods agree on
        the end state (some keys may be no-ops -- see the sibling test's
        docstring for why the change-count is no longer necessarily
        ``len(real_net_classes)``)."""
        updated = real_netlist.apply_net_class_mapping(real_net_classes)
        assert updated <= len(real_net_classes)
        for net_name, class_name in real_net_classes.items():
            assert real_netlist.get_net(net_name).net_class == class_name
