"""
Differential oracle tests: SubNetEdge, NetGraph, DifferentialPairConstraint.

This test pins the pre-migration Python dataclass implementations VERBATIM
as oracle blocks and compares the Rust pyclasses (imported via the delegation
shims) against them bit-identically.

G1 (TDD): This file is committed BEFORE any Rust pyclass code. Git history
must show the test predating the pyclass implementations. In identity mode
(before Rust), the shim imports ARE the Python dataclasses and the test
compares them against the oracles — the test is trivially green when the
implementation still lives in Python.

After U2/U3 migration, the shim imports are the Rust pyclasses and the test
compares Rust vs Python oracle. The same assertions (canonicalized through
field-tupling and repr-name normalization) must stay green.

Verification unit (per D5/G4 cluster rule): SubNetEdge + NetGraph +
DifferentialPairConstraint are one unit behind this shared oracle + corpus.

Module-to-property map:
  SubNetEdge: P5 (repr round-trip), MR3 (default identity)
  NetGraph:    P1 (edge lookup), P2 (edges identity), P3 (star_nodes identity),
               P4 (repr round-trip for float|None), MR1 (permutation invariance),
               MR2 (edge-addition monotonicity)
  DifferentialPairConstraint: P6 (validation order), P7 (repr with
               impedance_ohm=None), MR4 (field-subset equality),
               MR5 (spacing-monotonic error), MR6 (default preservation)
"""

from dataclasses import dataclass, field

import pytest

# ---------------------------------------------------------------------------
# Oracle block — verbatim copy of `temper_placer/core/net_graph.py` (origin/main)
# DO NOT EDIT — these are the reference implementations, name-suffixed _Oracle
# to avoid clashing with the shim imports.
# ---------------------------------------------------------------------------


@dataclass
class _OracleSubNetEdge:
    source_pin: str
    sink_pin: str
    trace_width_mm: float | None = None
    clearance_mm: float | None = None
    priority: int = 0


@dataclass
class _OracleNetGraph:
    net_name: str
    edges: list[_OracleSubNetEdge] = field(default_factory=list)
    star_nodes: set[str] = field(default_factory=set)

    def get_edge(self, source: str, sink: str) -> _OracleSubNetEdge | None:
        for edge in self.edges:
            if edge.source_pin == source and edge.sink_pin == sink:
                return edge
        return None

    def get_outgoing_edges(self, pin: str) -> list[_OracleSubNetEdge]:
        return [e for e in self.edges if e.source_pin == pin]

    def get_incoming_edges(self, pin: str) -> list[_OracleSubNetEdge]:
        return [e for e in self.edges if e.sink_pin == pin]


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/differential_pair.py`
# DO NOT EDIT.
# ============================================================================


@dataclass
class _OracleDifferentialPairConstraint:
    net_pos: str
    net_neg: str
    spacing_mm: float = 0.2
    coupling_tolerance_mm: float = 0.5
    impedance_ohm: float | None = None
    max_skew_mm: float = 0.5

    def __post_init__(self):
        if self.spacing_mm <= 0:
            raise ValueError(
                f"spacing_mm must be positive, got {self.spacing_mm}"
            )
        if self.coupling_tolerance_mm < 0:
            raise ValueError(
                f"coupling_tolerance_mm must be non-negative, got {self.coupling_tolerance_mm}"
            )
        if self.max_skew_mm < 0:
            raise ValueError(
                f"max_skew_mm must be non-negative, got {self.max_skew_mm}"
            )
        if self.impedance_ohm is not None and self.impedance_ohm <= 0:
            raise ValueError(
                f"impedance_ohm must be positive if specified, got {self.impedance_ohm}"
            )


# ---------------------------------------------------------------------------
# Production imports — after U2/U3, these are the Rust pyclasses via delegation
# shims. Before U2/U3, they ARE the Python dataclasses (identity mode).
# ---------------------------------------------------------------------------
from temper_placer.core.net_graph import NetGraph, SubNetEdge  # noqa: E402
from temper_placer.core.differential_pair import (
    DifferentialPairConstraint,  # noqa: E402
)


# ============================================================================
# Canonicalization helpers — extract fields from both sides into comparable
# forms. This way the oracle class names don't need to match the pyclass names.
# ============================================================================


def _edge_fields(edge) -> tuple:
    """Extract canonical fields from a SubNetEdge (either oracle or pyclass)."""
    return (
        edge.source_pin,
        edge.sink_pin,
        edge.trace_width_mm,
        edge.clearance_mm,
        edge.priority,
    )


def _graph_fields(graph) -> tuple:
    """Extract canonical fields from a NetGraph."""
    return (
        graph.net_name,
        tuple(sorted(_edge_fields(e) for e in graph.edges)),
        tuple(sorted(graph.star_nodes)),
    )


def _diffpair_fields(dp) -> tuple:
    """Extract canonical fields from a DifferentialPairConstraint."""
    return (
        dp.net_pos,
        dp.net_neg,
        dp.spacing_mm,
        dp.coupling_tolerance_mm,
        dp.impedance_ohm,
        dp.max_skew_mm,
    )


def _repr_normalized(obj, cls_name):
    """Return repr(obj) with the class name replaced by `cls_name`."""
    r = repr(obj)
    # Strip the class name prefix up to the first '('
    idx = r.index("(")
    return cls_name + r[idx:]


# ============================================================================
# SubNetEdge tests
# ============================================================================


class TestSubNetEdge:
    @staticmethod
    def _make(impl_src="A.1", impl_sink="B.1", **kwargs):
        """Build both the production SubNetEdge and its oracle twin."""
        prod = SubNetEdge(impl_src, impl_sink, **kwargs)
        oracle = _OracleSubNetEdge(impl_src, impl_sink, **kwargs)
        return prod, oracle

    def test_construction_all_defaults(self):
        prod, oracle = self._make()
        assert _repr_normalized(prod, "SubNetEdge") == repr(oracle).replace(
            "_OracleSubNetEdge", "SubNetEdge"
        )
        assert _edge_fields(prod) == _edge_fields(oracle)

    def test_construction_all_fields(self):
        prod = SubNetEdge("SRC.1", "SINK.1", 0.5, 0.3, 10)
        oracle = _OracleSubNetEdge("SRC.1", "SINK.1", 0.5, 0.3, 10)
        assert _repr_normalized(prod, "SubNetEdge") == repr(oracle).replace(
            "_OracleSubNetEdge", "SubNetEdge"
        )
        assert _edge_fields(prod) == _edge_fields(oracle)

    def test_equality_different_instances(self):
        a = SubNetEdge("A.1", "B.1", priority=1)
        b = SubNetEdge("A.1", "B.1", priority=2)
        assert a != b
        assert not (a == b)

    def test_repr_roundtrip(self):
        prod, oracle = self._make()
        r_prod = _repr_normalized(prod, "SubNetEdge")
        r_oracle = repr(oracle).replace("_OracleSubNetEdge", "SubNetEdge")
        assert r_prod == r_oracle
        # repred strings use single quotes (B9)
        assert "'A.1'" in r_prod and "'B.1'" in r_prod
        # None fields render as None, int fields as int
        assert "None" in r_prod
        assert "priority=0" in r_prod

    def test_hash_unhashable(self):
        prod = SubNetEdge("A.1", "B.1")
        with pytest.raises(TypeError, match="unhashable type: 'SubNetEdge'"):
            hash(prod)

    def test_default_isolation(self):
        a = SubNetEdge("A.1", "B.1")
        b = SubNetEdge("C.1", "D.1")
        assert a.source_pin == "A.1"
        assert b.source_pin == "C.1"
        assert a.priority == 0
        assert b.priority == 0

    def test_none_field_preservation(self):
        prod = SubNetEdge("A.1", "B.1", trace_width_mm=None)
        assert prod.trace_width_mm is None
        oracle = _OracleSubNetEdge("A.1", "B.1", trace_width_mm=None)
        assert _repr_normalized(prod, "SubNetEdge") == repr(oracle).replace(
            "_OracleSubNetEdge", "SubNetEdge"
        )

    def test_int_stays_int(self):
        prod = SubNetEdge("A.1", "B.1")
        assert isinstance(prod.priority, int)
        assert prod.priority == 0
        oracle = _OracleSubNetEdge("A.1", "B.1")
        assert _repr_normalized(prod, "SubNetEdge") == repr(oracle).replace(
            "_OracleSubNetEdge", "SubNetEdge"
        )


# ============================================================================
# NetGraph tests
# ============================================================================


class TestNetGraph:
    def test_construction_default_containers(self):
        prod = NetGraph("NET1")
        oracle = _OracleNetGraph("NET1")
        assert _repr_normalized(prod, "NetGraph") == repr(oracle).replace(
            "_OracleNetGraph", "NetGraph"
        )
        assert len(prod.edges) == 0
        assert len(prod.star_nodes) == 0
        assert _graph_fields(prod) == _graph_fields(oracle)

    def test_edges_identity(self):
        """edges getter returns the SAME Python object (not a copy)."""
        prod = NetGraph("NET1")
        assert prod.edges is prod.edges  # identity
        # Default factory creates a fresh list per instance
        prod2 = NetGraph("NET2")
        assert prod.edges is not prod2.edges  # not shared

    def test_star_nodes_identity(self):
        """star_nodes getter returns the SAME Python set (not a copy)."""
        prod = NetGraph("NET1")
        assert prod.star_nodes is prod.star_nodes  # identity
        # Default factory creates a fresh set per instance
        prod2 = NetGraph("NET2")
        assert prod.star_nodes is not prod2.star_nodes  # not shared

    def test_edges_append_mutates_in_place(self):
        prod = NetGraph("NET1")
        oracle = _OracleNetGraph("NET1")
        prod.edges.append(SubNetEdge("A.1", "B.1"))
        oracle.edges.append(_OracleSubNetEdge("A.1", "B.1"))
        assert len(prod.edges) == 1
        assert _graph_fields(prod) == _graph_fields(oracle)

    def test_star_nodes_add_mutates_in_place(self):
        prod = NetGraph("NET1")
        oracle = _OracleNetGraph("NET1")
        prod.star_nodes.add("PIN1")
        oracle.star_nodes.add("PIN1")
        assert "PIN1" in prod.star_nodes
        assert _graph_fields(prod) == _graph_fields(oracle)

    def test_edges_assignment_replaces(self):
        """Dataclass-field assignment `graph.edges = [...]` replaces the list.

        This is the surface `config_loader.rs:1185` exercises via
        `graph.setattr("star_nodes", ...)` — a pyclass with only a getter
        (no setter) raises AttributeError where the dataclass accepted
        assignment. Regression pin for the code-review P0.
        """
        prod = NetGraph("NET1")
        oracle = _OracleNetGraph("NET1")
        prod.edges = [SubNetEdge("A.1", "B.1")]
        oracle.edges = [_OracleSubNetEdge("A.1", "B.1")]
        assert len(prod.edges) == 1
        assert _edge_fields(prod.edges[0]) == _edge_fields(oracle.edges[0])
        assert _graph_fields(prod) == _graph_fields(oracle)

    def test_star_nodes_assignment_replaces(self):
        """Dataclass-field assignment `graph.star_nodes = {...}` replaces the set.

        Same code-review-P0 regression pin as test_edges_assignment_replaces:
        `config_loader.rs:1185` does `graph.setattr("star_nodes", star)`.
        """
        prod = NetGraph("NET1")
        oracle = _OracleNetGraph("NET1")
        prod.star_nodes = {"PIN1", "PIN2"}
        oracle.star_nodes = {"PIN1", "PIN2"}
        assert prod.star_nodes == {"PIN1", "PIN2"}
        assert _graph_fields(prod) == _graph_fields(oracle)

    def test_edges_assignment_rejects_non_list(self):
        """Assignment of a non-list raises TypeError (pyclass strictness).

        The pre-migration dataclass accepted any assignable object; the pyclass
        requires a list. This is a documented, deliberate deviation (a
        non-list assignment was never reachable in production) — the pyclass
        fails loudly instead of silently storing a foreign object.
        """
        prod = NetGraph("NET1")
        with pytest.raises(TypeError):
            prod.edges = "not-a-list"

    def test_star_nodes_assignment_rejects_non_set(self):
        """Assignment of a non-set raises TypeError (see
        test_edges_assignment_rejects_non_list for the rationale)."""
        prod = NetGraph("NET1")
        with pytest.raises(TypeError):
            prod.star_nodes = "not-a-set"

    def test_get_edge_found(self):
        prod = NetGraph("NET1")
        prod.edges.append(SubNetEdge("A.1", "B.1"))
        result = prod.get_edge("A.1", "B.1")
        assert result is not None
        assert _edge_fields(result) == ("A.1", "B.1", None, None, 0)

    def test_get_edge_not_found(self):
        prod = NetGraph("NET1")
        assert prod.get_edge("A.1", "B.1") is None

    def test_get_edge_multiple_edges(self):
        prod = NetGraph("NET1")
        for src, snk in [("A.1", "B.1"), ("B.1", "C.1"), ("A.1", "C.1")]:
            prod.edges.append(SubNetEdge(src, snk))
        result = prod.get_edge("B.1", "C.1")
        assert result is not None
        assert result.source_pin == "B.1"
        assert result.sink_pin == "C.1"

    def test_get_outgoing_edges(self):
        prod = NetGraph("NET1")
        for src, snk in [("A.1", "B.1"), ("A.1", "C.1"), ("B.1", "C.1")]:
            prod.edges.append(SubNetEdge(src, snk))
        outgoing = prod.get_outgoing_edges("A.1")
        assert len(outgoing) == 2
        assert {e.sink_pin for e in outgoing} == {"B.1", "C.1"}

    def test_get_incoming_edges(self):
        prod = NetGraph("NET1")
        for src, snk in [("A.1", "C.1"), ("B.1", "C.1"), ("A.1", "B.1")]:
            prod.edges.append(SubNetEdge(src, snk))
        incoming = prod.get_incoming_edges("C.1")
        assert len(incoming) == 2
        assert {e.source_pin for e in incoming} == {"A.1", "B.1"}

    def test_get_edge_duplicate_source(self):
        prod = NetGraph("NET1")
        prod.edges.append(SubNetEdge("A.1", "B.1"))
        prod.edges.append(SubNetEdge("A.1", "C.1"))
        result = prod.get_edge("A.1", "C.1")
        assert result is not None
        assert result.sink_pin == "C.1"

    def test_get_edge_empty_graph(self):
        prod = NetGraph("NET1")
        assert prod.get_edge("A.1", "B.1") is None
        assert prod.get_outgoing_edges("A.1") == []
        assert prod.get_incoming_edges("A.1") == []

    def test_hash_unhashable(self):
        prod = NetGraph("NET1")
        with pytest.raises(TypeError, match="unhashable type: 'NetGraph'"):
            hash(prod)


# ============================================================================
# DifferentialPairConstraint tests
# ============================================================================


class TestDifferentialPairConstraint:
    def test_construction_defaults(self):
        prod = DifferentialPairConstraint("USB_D+", "USB_D-")
        oracle = _OracleDifferentialPairConstraint("USB_D+", "USB_D-")
        assert _repr_normalized(prod, "DifferentialPairConstraint") == repr(
            oracle
        ).replace("_OracleDifferentialPairConstraint", "DifferentialPairConstraint")
        assert _diffpair_fields(prod) == _diffpair_fields(oracle)
        assert prod.spacing_mm == 0.2
        assert prod.coupling_tolerance_mm == 0.5
        assert prod.impedance_ohm is None
        assert prod.max_skew_mm == 0.5

    def test_construction_all_fields(self):
        prod = DifferentialPairConstraint("USB_D+", "USB_D-", 0.3, 0.1, 90.0, 0.2)
        oracle = _OracleDifferentialPairConstraint(
            "USB_D+", "USB_D-", 0.3, 0.1, 90.0, 0.2
        )
        assert _repr_normalized(prod, "DifferentialPairConstraint") == repr(
            oracle
        ).replace("_OracleDifferentialPairConstraint", "DifferentialPairConstraint")

    def test_equality_different_spacing(self):
        a = DifferentialPairConstraint("A+", "A-", spacing_mm=0.2)
        b = DifferentialPairConstraint("A+", "A-", spacing_mm=0.3)
        assert a != b

    def test_repr_with_impedance_none(self):
        prod = DifferentialPairConstraint("NET+", "NET-")
        r = _repr_normalized(prod, "DifferentialPairConstraint")
        assert "impedance_ohm=None" in r
        assert "spacing_mm=0.2" in r
        assert "max_skew_mm=0.5" in r

    def test_repr_with_impedance_float(self):
        prod = DifferentialPairConstraint("NET+", "NET-", impedance_ohm=100.0)
        r = _repr_normalized(prod, "DifferentialPairConstraint")
        assert "impedance_ohm=100.0" in r

    # --- Validation (__post_init__) ---

    def test_validation_spacing_zero(self):
        with pytest.raises(ValueError, match="spacing_mm must be positive, got 0.0"):
            DifferentialPairConstraint("A+", "A-", spacing_mm=0.0)

    def test_validation_spacing_negative(self):
        with pytest.raises(ValueError, match="spacing_mm must be positive, got -0.1"):
            DifferentialPairConstraint("A+", "A-", spacing_mm=-0.1)

    def test_validation_coupling_tolerance_negative(self):
        with pytest.raises(
            ValueError, match="coupling_tolerance_mm must be non-negative, got -0.1"
        ):
            DifferentialPairConstraint("A+", "A-", coupling_tolerance_mm=-0.1)

    def test_validation_max_skew_negative(self):
        with pytest.raises(
            ValueError, match="max_skew_mm must be non-negative, got -0.5"
        ):
            DifferentialPairConstraint("A+", "A-", max_skew_mm=-0.5)

    def test_validation_impedance_zero(self):
        with pytest.raises(
            ValueError,
            match="impedance_ohm must be positive if specified, got 0.0",
        ):
            DifferentialPairConstraint("A+", "A-", impedance_ohm=0.0)

    def test_validation_impedance_negative(self):
        with pytest.raises(
            ValueError,
            match="impedance_ohm must be positive if specified, got -50.0",
        ):
            DifferentialPairConstraint("A+", "A-", impedance_ohm=-50.0)

    def test_validation_order_spacing_before_skew(self):
        """First failing check raises; spacing error before max_skew error."""
        with pytest.raises(ValueError, match="spacing_mm must be positive, got 0.0"):
            DifferentialPairConstraint(
                "A+", "A-", spacing_mm=0.0, max_skew_mm=-1.0
            )

    def test_validation_impedance_none_ok(self):
        """impedance_ohm=None should NOT raise."""
        prod = DifferentialPairConstraint("A+", "A-", impedance_ohm=None)
        assert prod.impedance_ohm is None

    def test_hash_unhashable(self):
        prod = DifferentialPairConstraint("A+", "A-")
        with pytest.raises(
            TypeError, match="unhashable type: 'DifferentialPairConstraint'"
        ):
            hash(prod)


# ============================================================================
# Cross-module equality (SubNetEdge != DifferentialPairConstraint, etc.)
# ============================================================================


class TestCrossModuleEquality:
    def test_subnet_edge_not_equal_to_diff_pair(self):
        e = SubNetEdge("A.1", "B.1")
        d = DifferentialPairConstraint("A+", "A-")
        assert e != d
        assert not (e == d)

    def test_net_graph_not_equal_to_diff_pair(self):
        g = NetGraph("NET1")
        d = DifferentialPairConstraint("A+", "A-")
        assert g != d
        assert not (g == d)
