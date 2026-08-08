"""Drift tests for ``tools/wasm/test_family_map.json`` vs. the live wasm32
test registry.

The map is a hand-curated classification (see
``tools/wasm/gen_test_family_map.py``) of every wasm32-registered
``temper-drc-rs`` test into a rule family, consumed by
``tools/wasm/coverage_report.py`` for the R7/R8 per-family non-vacuity
report. It was written once against a 95-test registry (commit
``934cfbb2``, 2026-08-07) and silently fell 52 tests behind when the
registry grew to 147 (commits ``4261eb4e`` +17, ``a6ccfefd`` +35) -- nobody
re-ran a generator, because none existed. ``gen_test_family_map.py`` is that
generator; this file is the standing gate that keeps the two from
re-diverging, following the same shape as
``packages/temper-placer/tests/validation/test_gate_input_registry.py``'s
``test_every_invoked_ci_gate_script_is_registered`` (re-derive the live
source of truth, diff against the registered/mapped set, fail on any gap).

``TestSyntheticDivergence`` is the smoke test that the detector actually
fires: it constructs an in-memory map with one entry deliberately removed
and asserts ``diff_registration`` reports it -- proving the two real-file
assertions below aren't vacuously passing because the files already happen
to agree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_WASM = _REPO_ROOT / "tools" / "wasm"
if str(_TOOLS_WASM) not in sys.path:
    sys.path.insert(0, str(_TOOLS_WASM))

from gen_test_family_map import (  # noqa: E402
    FAMILIES,
    OUT_PATH,
    build_map,
    diff_registration,
    live_registered_tests,
)


@pytest.fixture(scope="module")
def live_names() -> set[str]:
    return {name for _, _, name in live_registered_tests()}


@pytest.fixture(scope="module")
def committed_map() -> dict:
    return json.loads(OUT_PATH.read_text())


# --- the real gate: committed file vs. live registry ---------------------


def test_no_live_test_is_missing_from_the_map(live_names, committed_map):
    """Every wasm32-registered test must be classified.

    This is the exact failure mode the 2026-08-07 incident produced: the
    registry grew from 95 to 147 tests (rules::emc, rules::erc,
    rules::placement, validation_kernels) and the map wasn't regenerated,
    leaving 52 live tests -- including the entire `erc` family -- absent
    from every family-coverage report built on this map.
    """
    mapped_names = set(committed_map["per_test"])
    missing, _stale = diff_registration(live_names, mapped_names)
    assert not missing, (
        f"{len(missing)} wasm32-registered test(s) are not in "
        f"tools/wasm/test_family_map.json: {sorted(missing)[:10]}"
        + (" ..." if len(missing) > 10 else "")
        + " -- run `python3 tools/wasm/gen_test_family_map.py`"
    )


def test_no_mapped_test_names_a_test_that_no_longer_exists(live_names, committed_map):
    """The reverse direction: a map entry naming a deleted/renamed test.

    This is the same defect class as the CI group that referenced a deleted
    file and collected zero tests -- a name-enumerated list drifting stale
    in the direction where it silently over-claims coverage instead of
    under-claiming it.
    """
    mapped_names = set(committed_map["per_test"])
    _missing, stale = diff_registration(live_names, mapped_names)
    assert not stale, (
        f"tools/wasm/test_family_map.json names {len(stale)} test(s) absent from "
        f"the live wasm32 registry: {sorted(stale)}"
    )


def test_committed_map_matches_a_fresh_regeneration(committed_map):
    """Full-content drift check, not just key-set: catches a wrong family
    assignment even when the key set already matches (e.g. a test hand-edited
    into the wrong bucket without adding or removing any entry)."""
    fresh = build_map()
    assert committed_map["per_test"] == fresh["per_test"]
    assert committed_map["family_counts"] == fresh["family_counts"]


def test_family_counts_match_per_test_tally(committed_map):
    tally = dict.fromkeys(FAMILIES, 0)
    for families in committed_map["per_test"].values():
        for fam in families:
            tally[fam] += 1
    assert committed_map["family_counts"] == tally


def test_canary_defects_reference_live_tests(live_names, committed_map):
    for family, canary in committed_map["canary_defects"].items():
        assert canary["test"] in live_names, (
            f"canary_defects[{family!r}] names {canary['test']!r}, which is not "
            "in the live wasm32 registry"
        )


# --- smoke test: prove the detector actually fires on a real gap ---------


class TestSyntheticDivergence:
    """``diff_registration`` against a manufactured gap, not the real files.

    If this class didn't exist, a bug that made ``diff_registration`` always
    return ``(set(), set())`` (e.g. an accidentally-flipped set difference)
    would pass every test above simply because the checked-in map happens to
    already be in sync -- exactly the silent-pass failure mode this whole
    task exists to close.
    """

    def test_fires_on_a_missing_entry(self):
        live = {"rules::erc::floating_pins::tests::floating_pins_empty_board_no_violations"}
        mapped: set[str] = set()  # simulates the pre-fix 95-test map's blind spot
        missing, stale = diff_registration(live, mapped)
        assert missing == live
        assert stale == set()

    def test_fires_on_a_stale_entry(self):
        live: set[str] = set()
        mapped = {"rules::drc::deleted_module::tests::this_test_was_removed"}
        missing, stale = diff_registration(live, mapped)
        assert missing == set()
        assert stale == mapped

    def test_silent_on_a_real_synthetic_divergence_from_the_actual_map(self, committed_map):
        """Drop one real, currently-mapped test and confirm the detector
        catches exactly that one -- using real data, not toy strings."""
        mapped_names = set(committed_map["per_test"])
        victim = next(iter(mapped_names))
        synthetic_mapped = mapped_names - {victim}
        missing, _stale = diff_registration(mapped_names, synthetic_mapped)
        assert missing == {victim}

    def test_clean_when_sets_are_equal(self):
        s = {"a", "b", "c"}
        missing, stale = diff_registration(s, set(s))
        assert missing == set()
        assert stale == set()
