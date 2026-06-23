"""Tests for Hypothesis PBT validation and golden fixture infrastructure."""

import pytest


class TestHypothesisInvariants:
    def test_import_invariants(self):
        from temper_placer.profiling.validation.invariants import (
            test_connectivity_invariant,
            test_determinism_invariant,
            test_boundary_containment,
        )
        assert callable(test_connectivity_invariant)
        assert callable(test_determinism_invariant)
        assert callable(test_boundary_containment)


class TestGoldenFixtures:
    def test_fixture_directory_exists(self):
        import os
        fixture_dir = os.path.join(
            os.path.dirname(__file__),
            "..", "src", "temper_placer", "profiling", "validation", "fixtures",
        )
        assert os.path.isdir(fixture_dir)
