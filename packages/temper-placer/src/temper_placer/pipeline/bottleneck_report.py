"""
Sidecar-as-contract data model for placement-routing feedback loop.

Defines the BottleneckReport that the router writes and the placer reads,
plus the DeclaredArtifact contract type used by Stage declarations.

Part of sidecar-feedback-contract (U1).

This module is a delegation shim. ``BottleneckNetEntry``, ``BottleneckRegion``,
``CongestionHeatmapData``, ``BottleneckReport`` and ``DeclaredArtifact`` are
Rust pyclasses in the ``temper-orchestration`` crate (Phase-C residual of the
Rust orchestration engine, plan 2026-08-09-001, module home ``bottleneck``;
bit-identical parity pinned by ``tests/pipeline/test_phase_c_tail_rust_differential.py``
against the verbatim pre-migration oracle
``tests/pipeline/_bottleneck_report_py_oracle.py``). The public API is
unchanged: the five dataclass names with the full serialization surface
(``to_dict`` / ``from_dict`` / ``to_json`` / ``from_json`` / ``write`` /
``read`` and the ``routed_count`` / ``failed_count`` properties).
"""

from __future__ import annotations

import temper_orchestration as _rs

BottleneckNetEntry = _rs.BottleneckNetEntry
BottleneckRegion = _rs.BottleneckRegion
CongestionHeatmapData = _rs.CongestionHeatmapData
BottleneckReport = _rs.BottleneckReport
DeclaredArtifact = _rs.DeclaredArtifact
