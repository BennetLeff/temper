"""Tests for core.ipc2221 module."""

import pytest

from temper_placer.core.ipc2221 import (
    TRACE_CURRENT_TABLE_1OZ,
    estimate_current_from_net_class,
    estimate_trace_current,
)


class TestTraceCurrentEstimation:
    """Tests for IPC-2221 trace current estimation."""

    def test_estimate_trace_current_default(self):
        """Estimate current for a 0.5mm trace with defaults."""
        current = estimate_trace_current(0.5)
        assert current > 0
        # Should be in the ~2A range for 0.5mm trace
        assert 1.0 < current < 5.0

    def test_estimate_trace_current_thicker_copper(self):
        """2oz copper should carry more current."""
        c1 = estimate_trace_current(0.5, thickness_oz=1.0)
        c2 = estimate_trace_current(0.5, thickness_oz=2.0)
        assert c2 > c1

    def test_estimate_trace_current_internal_layer(self):
        """Internal layers derate current."""
        c_ext = estimate_trace_current(0.5, internal_layer=False)
        c_int = estimate_trace_current(0.5, internal_layer=True)
        assert c_ext != c_int  # internal should be different

    def test_estimate_trace_current_zero_width(self):
        """Zero width should return zero or very small."""
        c = estimate_trace_current(0.0)
        assert c == 0.0

    def test_estimate_from_net_class_default(self):
        """estimate_current_from_net_class returns a valid positive current."""
        c = estimate_current_from_net_class(0.5)
        assert c > 0

    def test_estimate_from_net_class_with_thickness(self):
        c = estimate_current_from_net_class(0.5, thickness_oz=2.0, temp_rise_c=20.0)
        assert c > 0


class TestTraceCurrentTable:
    """Verify the lookup table is well-formed."""

    def test_table_entries(self):
        assert len(TRACE_CURRENT_TABLE_1OZ) > 0
        # All keys should be positive
        for k in TRACE_CURRENT_TABLE_1OZ:
            assert k > 0
