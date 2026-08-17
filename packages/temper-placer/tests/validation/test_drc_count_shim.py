"""Shim tests for the DrcCount cap-classification kernels.

The classification itself (``DrcCount``, the per-category cap table,
``CappedCountError``) lives in ``temper_drc_rs`` (``drc_count.rs``) with
its own proptest suite; the pure-Rust behavior is exercised there, under
``cargo test``, in both ``--no-default-features`` and ``python`` builds.
These tests pin the Python-facing delegation surface
(``_drc_api.drc_count_from_kicad`` / ``classify_counts`` / ``drc_cap_for``)
so the shim can never drift from the kernel contract: a capped count
surfaces ``is_capped=True`` plus a floor-rendering ``display``, and the
bare number is only reachable as truth through ``is_honest``.

The cap table (docs/evidence/2026-08-12-dru-rule-precedence.md sec 4,
``pcbnew/drc/drc_engine.cpp``): ``clearance``/``unconnected_items`` cap at
EXTENDED_ERROR_LIMIT 499; ``creepage`` is uncapped (provider bypasses the
limit); every other category caps at ERROR_LIMIT 199.
"""

from __future__ import annotations

from temper_placer.validation._drc_api import (
    DrcCountInfo,
    classify_counts,
    drc_cap_for,
    drc_count_from_kicad,
)


class TestDrcCountShim:
    def test_exact_cap_is_capped_with_floor_display(self):
        info = drc_count_from_kicad(199, "track_width")
        assert isinstance(info, DrcCountInfo)
        assert info.count == 199
        assert info.is_capped
        assert not info.is_honest
        assert info.display == "199 (CAPPED — true count >= 199)"

    def test_extended_cap_is_capped_for_clearance(self):
        info = drc_count_from_kicad(499, "clearance")
        assert info.is_capped
        assert info.display == "499 (CAPPED — true count >= 499)"

    def test_199_in_clearance_is_honest(self):
        # 199 is below clearance's OWN cap (499): honest. The naive
        # "199 or 499 always means capped" rule flags this -- wrong.
        assert drc_count_from_kicad(199, "clearance").is_honest

    def test_creepage_199_is_honest(self):
        # creepage's provider bypasses the limit: 199 is a real count.
        assert drc_count_from_kicad(199, "creepage").is_honest

    def test_ordinary_counts_are_honest(self):
        assert drc_count_from_kicad(42, "track_width").is_honest
        assert drc_count_from_kicad(0, "track_width").is_honest
        assert drc_count_from_kicad(200, "track_width").is_honest
        assert drc_count_from_kicad(499, "track_width").is_honest  # not its cap

    def test_cap_for_table(self):
        assert drc_cap_for("clearance") == 499
        assert drc_cap_for("unconnected_items") == 499
        assert drc_cap_for("creepage") is None
        assert drc_cap_for("track_width") == 199
        assert drc_cap_for("shorting_items") == 199
        assert drc_cap_for("silk_overlap") == 199
        assert drc_cap_for("some_future_type") == 199


class TestClassifyCounts:
    def test_classifies_every_rule_independently(self):
        classified = classify_counts(
            {"track_width": 199, "clearance": 199, "creepage": 199, "shorting_items": 42}
        )
        assert classified["track_width"].is_capped
        assert classified["clearance"].is_honest  # 199 < clearance's 499 cap
        assert classified["creepage"].is_honest  # uncapped category
        assert classified["shorting_items"].is_honest

    def test_display_renders_capped_floor(self):
        classified = classify_counts({"track_width": 199})
        assert classified["track_width"].display == "199 (CAPPED — true count >= 199)"

    def test_uncapped_categories_never_flagged(self):
        classified = classify_counts({"creepage": 199})
        assert not classified["creepage"].is_capped
