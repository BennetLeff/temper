"""End-to-end golden fixture integration tests.

These tests verify the golden DSN generation and verification pipeline.
"""


from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.boundary_registry import get_boundary, list_boundaries
from temper_placer.io.dsn_exporter import DSNExporter
from temper_placer.io.dsn_normalizer import is_dsn_normalized, normalize_dsn
from temper_placer.io.dsn_schema import compute_dsn_schema_hash, embed_schema_header, extract_schema_hash
from temper_placer.io.dsn_validator import validate_dsn


def test_golden_flow_export_and_validate():
    """End-to-end: export DSN, normalize, embed hash, validate."""
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (0, 1)),
            ]),
        ],
        nets=[
            Net(name="SIG1", pins=[("U1", "1"), ("U1", "2")]),
        ]
    )

    exporter = DSNExporter(board, netlist, deterministic=True)
    dsn_text = str(exporter.export_pcb("temper"))

    normalized = normalize_dsn(dsn_text)
    assert is_dsn_normalized(normalized)

    schema_hash = compute_dsn_schema_hash(board, netlist)
    assert schema_hash is not None
    assert len(schema_hash) == 64

    embedded = embed_schema_header(normalized, schema_hash)
    assert embedded.startswith(f";schema-version: sha256:{schema_hash}")

    extracted = extract_schema_hash(embedded)
    assert extracted == schema_hash

    validate_dsn(embedded, schema_hash)


def test_golden_deterministic_byte_identical():
    """Two exports of same board+netlist produce identical normalized DSN."""
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("1", "1", (0, 0)),
            ]),
        ],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )

    exporter1 = DSNExporter(board, netlist, deterministic=True)
    exporter2 = DSNExporter(board, netlist, deterministic=True)

    dsn1 = normalize_dsn(str(exporter1.export_pcb("temper")))
    dsn2 = normalize_dsn(str(exporter2.export_pcb("temper")))

    assert dsn1 == dsn2


def test_boundary_registry_integration():
    """Boundary registry provides correct mappings for golden check flow."""
    from temper_placer.pipeline.orchestrator import PipelinePhase

    for boundary_name in list_boundaries():
        bd = get_boundary(boundary_name)
        # Map to PipelinePhase
        phase = PipelinePhase(bd.phase_name)
        assert phase is not None
        assert bd.output_format in {"dsn", "json"}


def test_schema_hash_changes_pipeline_output_header():
    """When netlist changes, schema hash in DSN header changes."""
    board = Board(width=100, height=100)
    netlist1 = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )
    netlist2 = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])],
        nets=[Net(name="SIG1", pins=[("U1", "1")]), Net(name="SIG2", pins=[("U1", "1")])]
    )

    exp1 = DSNExporter(board, netlist1, deterministic=True)
    exp2 = DSNExporter(board, netlist2, deterministic=True)

    h1 = extract_schema_hash(str(exp1.export_pcb("temper")))
    h2 = extract_schema_hash(str(exp2.export_pcb("temper")))

    assert h1 != h2
