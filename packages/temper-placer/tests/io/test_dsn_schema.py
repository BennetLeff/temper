from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.dsn_schema import DSNSchemaHasher


def test_same_schema_produces_same_hash():
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "4", (0, 1)),
            ]),
        ],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )
    h1 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    h2 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_adding_net_changes_hash():
    board = Board(width=100, height=100)
    netlist1 = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )
    netlist2 = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])],
        nets=[
            Net(name="SIG1", pins=[("U1", "1")]),
            Net(name="SIG2", pins=[("U1", "1")]),
        ]
    )
    h1 = DSNSchemaHasher.compute_schema_hash(board, netlist1)
    h2 = DSNSchemaHasher.compute_schema_hash(board, netlist2)
    assert h1 != h2


def test_changing_footprint_pin_count_changes_hash():
    board = Board(width=100, height=100)
    netlist1 = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )
    netlist2 = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
            Pin("1", "1", (0, 0)),
            Pin("2", "2", (0, 1)),
        ])],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )
    h1 = DSNSchemaHasher.compute_schema_hash(board, netlist1)
    h2 = DSNSchemaHasher.compute_schema_hash(board, netlist2)
    assert h1 != h2


def test_moving_component_does_not_change_hash():
    """Position-only changes should not affect schema hash."""
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])],
        nets=[Net(name="SIG1", pins=[("U1", "1")])]
    )
    h1 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    h2 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    assert h1 == h2


def test_changing_layer_stackup_changes_hash():
    """Different layer counts should produce different hashes."""
    from temper_placer.core.board import Layer
    # Board with 4-layer default (all boards get 4-layer by default)
    board1 = Board(width=100, height=100)
    # Board with different layer config (more layers)
    stackup2 = LayerStackup(layers=[
        Layer(name="F.Cu", layer_type="signal"),
        Layer(name="In1.Cu", layer_type="plane"),
        Layer(name="In2.Cu", layer_type="power"),
        Layer(name="In3.Cu", layer_type="signal"),
        Layer(name="In4.Cu", layer_type="signal"),
        Layer(name="B.Cu", layer_type="signal"),
    ])
    board2 = Board(width=100, height=100, layer_stackup=stackup2)
    netlist = Netlist()
    h1 = DSNSchemaHasher.compute_schema_hash(board1, netlist)
    h2 = DSNSchemaHasher.compute_schema_hash(board2, netlist)
    assert h1 != h2


def test_embed_header_prepends_to_dsn():
    dsn = "(pcb test (unit mm))\n"
    result = DSNSchemaHasher.embed_header(dsn, "abc123")
    assert result.startswith(";schema-version: sha256:abc123\n")
    assert "(pcb test (unit mm))" in result


def test_embed_header_replaces_existing():
    dsn = ";schema-version: sha256:oldhash\n(pcb test (unit mm))\n"
    result = DSNSchemaHasher.embed_header(dsn, "newhash")
    assert result.startswith(";schema-version: sha256:newhash")
    assert "oldhash" not in result


def test_extract_hash_parses_correctly():
    dsn = ";schema-version: sha256:abc123def456\n(pcb test)\n"
    h = DSNSchemaHasher.extract_hash(dsn)
    assert h == "abc123def456"


def test_extract_hash_returns_none_when_missing():
    dsn = "(pcb test (unit mm))\n"
    h = DSNSchemaHasher.extract_hash(dsn)
    assert h is None


def test_schema_hash_is_stable_with_layer_order():
    """Hash should be stable regardless of layer order in the stackup list."""
    from temper_placer.core.board import Layer
    stackup1 = LayerStackup(layers=[
        Layer(name="F.Cu", layer_type="signal"),
        Layer(name="B.Cu", layer_type="signal"),
        Layer(name="In1.Cu", layer_type="plane"),
        Layer(name="In2.Cu", layer_type="plane"),
    ])
    stackup2 = LayerStackup(layers=[
        Layer(name="In2.Cu", layer_type="plane"),
        Layer(name="In1.Cu", layer_type="plane"),
        Layer(name="B.Cu", layer_type="signal"),
        Layer(name="F.Cu", layer_type="signal"),
    ])
    board1 = Board(width=100, height=100, layer_stackup=stackup1)
    board2 = Board(width=100, height=100, layer_stackup=stackup2)
    netlist = Netlist()
    h1 = DSNSchemaHasher.compute_schema_hash(board1, netlist)
    h2 = DSNSchemaHasher.compute_schema_hash(board2, netlist)
    assert h1 == h2
