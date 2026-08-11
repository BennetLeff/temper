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
proves it against the real board and the real, still-broken
`temper_constraints.yaml` -- read-only; this task's boundaries forbid
fixing that file, so the assertions pin the exact current violation set,
same convention as `scripts/tests/test_check_netclass_map_board_correspondence.py`.
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
    """Against the real board and the real, currently-broken config file.

    Read-only: this task's boundaries forbid fixing
    `temper_constraints.yaml`, so this pins today's exact violation set
    (5 of 11 keys, measured directly against `pcb/temper.kicad_pcb`'s own
    net table) rather than a hand-copied expectation.
    """

    @pytest.fixture(scope="class")
    def real_netlist(self):
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        parse_result = parse_kicad_pcb(REPO_ROOT / "pcb" / "temper.kicad_pcb")
        return parse_result.netlist

    @pytest.fixture(scope="class")
    def real_net_classes(self) -> dict[str, str]:
        config_path = (
            REPO_ROOT / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
        )
        return yaml.safe_load(config_path.read_text())["net_classes"]

    def test_strict_fails_loudly_on_the_real_broken_config(self, real_netlist, real_net_classes):
        with pytest.raises(ValueError) as exc_info:
            real_netlist.apply_net_class_mapping_strict(real_net_classes)
        msg = str(exc_info.value)
        # The mains-critical keys named in the task brief must be among
        # what a safety review would see: AC live, AC neutral, protective
        # earth, and ground -- exactly the ones the brief calls out as
        # "did nothing at all, silently".
        for broken_key in ("AC_L", "AC_N", "PE", "GND", "+340V_BUS"):
            assert broken_key in msg, f"{broken_key!r} missing from error: {msg}"
        assert "5 net_classes key(s)" in msg

    def test_existing_method_silently_no_ops_on_the_same_input(
        self, real_netlist, real_net_classes
    ):
        """Same real inputs, old method: no exception, partial silent
        application -- this is the defect this spike is about."""
        updated = real_netlist.apply_net_class_mapping(real_net_classes)
        assert updated == len(real_net_classes) - 5
