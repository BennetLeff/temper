"""Routing metrics collection for benchmarking and debugging.

This module provides dataclasses for collecting detailed routing statistics
that help identify bottlenecks and measure improvement.

The three dataclasses and their aggregation compute are implemented as pyo3
pyclasses in the ``temper-design-bundle`` crate (Wave 4 **Phase 5, batch 2**
— deterministic leaf stages); this module re-exports them under the
pre-migration names and keeps ``print_summary`` (pure I/O) Python.

Bit-exactness: construction/defaults, the ``completion_rate`` /
``is_fully_routed`` properties, ``add_net`` aggregation, ``finalize``, and
``to_dict``/``to_json`` reproduce the oracle identically, including CPython's
round-half-to-even ``round(x, ndigits)`` in ``to_dict``. Verified by
``tests/deterministic/stages/test_routing_metrics_rust_differential.py``
(oracle: ``tests/deterministic/stages/_routing_metrics_py_oracle.py``) and
the PBT suite ``test_routing_metrics_pbt.py``; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from temper_design_bundle_python import NetMetrics, RoutingMetrics, SegmentMetrics

__all__ = ["NetMetrics", "RoutingMetrics", "SegmentMetrics"]
