"""Per-net-pair clearance in the routing decision.

See docs/evidence/2026-08-12-router-safety-clearances.md.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6.astar_core import RoutePath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.pair_clearance import (
    UNASSIGNED_NETCLASS,
    PairClearanceTable,
    kicad_class_name,
    load_pair_clearance_table,
    resolve_profiles,
)
from temper_placer.router_v6.profile_grids import ProfileGrids

REPO_ROOT = Path(__file__).resolve().parents[4]
GENERATOR = REPO_ROOT / "scripts" / "generate_kicad_dru.py"
PAIR_YAML = (
    REPO_ROOT / "packages" / "temper-placer" / "configs" / "pair_clearance.generated.yaml"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_dru_pc", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The table is a measurement of the emitted .kicad_dru, not a restatement
# ---------------------------------------------------------------------------


def test_generated_yaml_is_not_stale():
    """The checked-in table still equals what the generator emits today.

    This is the drift gate. If it fails, `pcb/temper.kicad_dru`'s rules have
    changed and the router is deciding against figures kicad-cli no longer
    enforces -- regenerate with `uv run python scripts/generate_kicad_dru.py`.
    """
    generator = _load_generator()
    expected = generator.render_pair_clearance_yaml(generator.generate_dru())
    assert PAIR_YAML.read_text(encoding="utf-8") == expected


def test_unassigned_class_name_agrees_with_the_generator():
    assert _load_generator().UNASSIGNED_NETCLASS == UNASSIGNED_NETCLASS


def test_router_class_names_translate_to_the_generators():
    generator = _load_generator()
    for python_key, kicad_name in generator.KICAD_NAME_MAP.items():
        assert kicad_class_name(python_key) == kicad_name


# ---------------------------------------------------------------------------
# Lookup semantics
# ---------------------------------------------------------------------------


def test_table_is_symmetric_and_carries_the_safety_bars():
    table = load_pair_clearance_table()
    # The two figures the whole change exists for: mains and the HV bus
    # against an unclassified (SELV) net.
    assert table.required("ACMains", UNASSIGNED_NETCLASS) == 6.0
    assert table.required("HighVoltage", UNASSIGNED_NETCLASS) == 2.0
    for class_a in table.classes:
        for class_b in table.classes:
            assert table.required(class_a, class_b) == table.required(class_b, class_a)


def test_gnd_resolves_through_the_kicad_name():
    """The router calls it GND; the rule file calls it Ground."""
    table = load_pair_clearance_table()
    assert table.required("GND", "HighVoltage") == table.required("Ground", "HighVoltage")
    assert table.required("GND", "HighVoltage") == 2.0


def test_unknown_class_falls_back_to_unassigned_never_raises():
    table = load_pair_clearance_table()
    assert table.required("NoSuchClass", "ACMains") == table.required(
        UNASSIGNED_NETCLASS, "ACMains"
    )
    assert table.required(None, None) == table.required(
        UNASSIGNED_NETCLASS, UNASSIGNED_NETCLASS
    )


def test_missing_pair_falls_back_to_the_default_clearance():
    table = PairClearanceTable(pairs={}, classes=("Default",), default_clearance_mm=0.25)
    assert table.required("Default", "Default") == 0.25


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@pytest.fixture
def board_profiles():
    table = load_pair_clearance_table()
    widths = {
        "ACMains": 3.0,
        "FinePitch": 0.127,
        "GND": 1.0,
        "GateDriveHV": 0.4,
        "GateDriveSELV": 0.4,
        "HighVoltage": 3.0,
        "HighVoltageIsolated": 2.0,
        "HighVoltageTank": 3.0,
        "Power": 1.0,
    }
    clearances = {
        "ACMains": 6.0,
        "FinePitch": 0.1,
        "GND": 0.3,
        "GateDriveHV": 0.25,
        "GateDriveSELV": 0.25,
        "HighVoltage": 2.0,
        "HighVoltageIsolated": 6.0,
        "HighVoltageTank": 2.0,
        "Power": 0.5,
    }
    return resolve_profiles(table, widths, clearances, 0.2, 0.2), clearances


def test_profiles_collapse_the_live_classes(board_profiles):
    profiles, _ = board_profiles
    # 9 live classes + Default = 10, collapsing to strictly fewer profiles.
    assert len(profiles.profile_of_class) == 10
    assert 1 < len(profiles.profiles) < 10
    # The tank node was carved out of HighVoltage but imposes and receives the
    # same figures at the same width, so it must not cost a whole extra grid.
    assert profiles.profile_for_class("HighVoltageTank") == profiles.profile_for_class(
        "HighVoltage"
    )


def test_a_merged_profile_is_exact_not_approximate(board_profiles):
    """Classes only share a family when every stamp radius agrees."""
    profiles, _ = board_profiles
    for class_a, key in profiles.profile_of_class.items():
        for class_b, other_key in profiles.profile_of_class.items():
            if key != other_key:
                continue
            for marked in profiles.profile_of_class:
                assert profiles.stamp_clearance_mm(
                    marked, profiles.profile_for_class(class_a)
                ) == profiles.stamp_clearance_mm(marked, profiles.profile_for_class(class_b))


def test_never_looser_than_the_single_grid_model(board_profiles):
    """Every stamp is at least what the old model wrote for the same net.

    The old model stamped `clearance_mm` of the MARKED net's class, full stop.
    Any pair whose new radius came out below that would be a safety
    regression dressed up as a fix.
    """
    profiles, clearances = board_profiles
    for marked, own in clearances.items():
        for profile in profiles.profiles:
            assert profiles.stamp_clearance_mm(marked, profile) >= own


def test_the_pair_requirement_actually_raises_something(board_profiles):
    """An unclassified track must now block a mains search at 6.0mm+.

    This is the defect: today `Default` is stamped at 0.2mm and a later
    ACMains route is free to run 0.2mm from it.
    """
    profiles, _ = board_profiles
    acmains_profile = profiles.profile_for_class("ACMains")
    stamp = profiles.stamp_clearance_mm(UNASSIGNED_NETCLASS, acmains_profile)
    assert stamp >= 6.0
    assert stamp > profiles.stamp_clearance_mm(
        UNASSIGNED_NETCLASS, profiles.profile_for_class(UNASSIGNED_NETCLASS)
    )


def test_default_is_always_a_profile_even_with_no_live_classes():
    table = load_pair_clearance_table()
    profiles = resolve_profiles(table, {}, {}, 0.2, 0.2)
    assert profiles.profile_for_class(UNASSIGNED_NETCLASS) in profiles.profiles
    assert profiles.profile_for_class("AnythingElse") in profiles.profiles


# ---------------------------------------------------------------------------
# ProfileGrids
# ---------------------------------------------------------------------------


def _grid(layer: str = "F.Cu") -> OccupancyGrid:
    array = np.zeros((80, 80), dtype=np.int8)
    return OccupancyGrid(
        layer_name=layer,
        grid=array,
        origin=(0.0, 0.0),
        cell_size=0.1,
        width_cells=80,
        height_cells=80,
        static_mask=array == -1,
    )


@pytest.fixture
def grids_and_profiles(board_profiles):
    profiles, _ = board_profiles
    base = {"F.Cu": _grid()}
    assignments = {"mains": "ACMains", "selv": UNASSIGNED_NETCLASS}
    return ProfileGrids(base, profiles, assignments), base


def test_first_family_is_the_caller_s_dict_not_a_copy(grids_and_profiles):
    """A single-profile board must cost nothing and stay aliased."""
    profile_grids, base = grids_and_profiles
    first = profile_grids._families[profile_grids.profiles.profiles[0]]
    assert first is base


def test_families_are_independent_arrays(grids_and_profiles):
    profile_grids, base = grids_and_profiles
    arrays = [
        id(family["F.Cu"].grid) for family in profile_grids._families.values()
    ]
    assert len(set(arrays)) == len(arrays)


def test_a_selv_route_blocks_more_of_the_mains_family_than_its_own(grids_and_profiles):
    """The whole point, on a real grid: one route, two different halos."""
    profile_grids, _ = grids_and_profiles
    path = RoutePath(
        net_name="selv",
        coordinates=[(2.0, 4.0), (6.0, 4.0)],
        layer_name="F.Cu",
        path_length=4.0,
    )
    profile_grids.mark_route(path, "selv", trace_width=0.2, net_id=7)

    selv_family = profile_grids.grids_for_net("selv")
    mains_family = profile_grids.grids_for_net("mains")
    assert selv_family is not mains_family

    selv_blocked = int(np.count_nonzero(selv_family["F.Cu"].grid))
    mains_blocked = int(np.count_nonzero(mains_family["F.Cu"].grid))
    assert selv_blocked > 0
    # 6.0mm + the mains half-width vs 0.2mm: an order of magnitude, not a nudge.
    assert mains_blocked > 10 * selv_blocked


def test_unmark_restores_every_family(grids_and_profiles):
    profile_grids, _ = grids_and_profiles
    path = RoutePath(
        net_name="selv",
        coordinates=[(2.0, 4.0), (6.0, 4.0)],
        layer_name="F.Cu",
        path_length=4.0,
    )
    profile_grids.mark_route(path, "selv", trace_width=0.2, net_id=7)
    profile_grids.unmark_route(path, "selv", trace_width=0.2, net_id=7)
    for family in profile_grids._families.values():
        assert int(np.count_nonzero(family["F.Cu"].grid)) == 0


def test_unknown_net_routes_as_unassigned(grids_and_profiles):
    profile_grids, _ = grids_and_profiles
    assert profile_grids.net_class("a-net-nobody-classified") == UNASSIGNED_NETCLASS
    assert profile_grids.grids_for_net("a-net-nobody-classified") is not None


def test_mark_path_ignores_a_layer_no_family_has(grids_and_profiles):
    """A tree branch on an ungridded layer is a no-op, never a KeyError."""
    profile_grids, _ = grids_and_profiles
    profile_grids.mark_path("In7.Cu", [(1.0, 1.0), (2.0, 2.0)], "selv", 0.2, 7)
    for family in profile_grids._families.values():
        assert int(np.count_nonzero(family["F.Cu"].grid)) == 0
