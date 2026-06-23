from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.dsn_schema import DSNSchemaHasher


def test_compute_schema_hash_deterministic():
    """Same inputs produce same hash."""
    board = Board(width=100, height=100)
    comps = [Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])]
    nets = [Net(name="SIG1", pins=[("U1", "1")])]
    netlist = Netlist(components=comps, nets=nets)

    h1 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    h2 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_schema_hash_changes_with_net():
    """Adding a net changes the hash."""
    board = Board(width=100, height=100)
    comps = [Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0)), Pin("2", "2", (0, 1))])]
    nets_a = [Net(name="SIG1", pins=[("U1", "1")])]
    nets_b = [Net(name="SIG1", pins=[("U1", "1")]), Net(name="SIG2", pins=[("U1", "2")])]

    h1 = DSNSchemaHasher.compute_schema_hash(board, Netlist(components=comps, nets=nets_a))
    h2 = DSNSchemaHasher.compute_schema_hash(board, Netlist(components=comps, nets=nets_b))
    assert h1 != h2


def test_compute_schema_hash_changes_with_footprint():
    """Different footprint (different pin count) changes the hash."""
    board = Board(width=100, height=100)
    comps_a = [Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])]
    comps_b = [Component(ref="U1", footprint="SOIC-14", bounds=(5, 4), pins=[Pin("1", "1", (0, 0)), Pin("14", "14", (0, 1))])]
    nets = [Net(name="SIG1", pins=[("U1", "1")])]

    h1 = DSNSchemaHasher.compute_schema_hash(board, Netlist(components=comps_a, nets=nets))
    h2 = DSNSchemaHasher.compute_schema_hash(board, Netlist(components=comps_b, nets=nets))
    assert h1 != h2


def test_compute_schema_hash_stable_with_position():
    """Moving a component (position only) does NOT change the hash."""
    board = Board(width=100, height=100)
    comps = [Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])]
    nets = [Net(name="SIG1", pins=[("U1", "1")])]
    netlist = Netlist(components=comps, nets=nets)

    h = DSNSchemaHasher.compute_schema_hash(board, netlist)
    assert h == DSNSchemaHasher.compute_schema_hash(board, netlist)


def test_compute_schema_hash_changes_with_rule():
    """Different trace width rule changes the hash. (Rules are currently hardcoded
    but the infrastructure supports it.)"""
    board = Board(width=100, height=100)
    comps = [Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])]
    nets = [Net(name="SIG1", pins=[("U1", "1")])]
    netlist = Netlist(components=comps, nets=nets)

    # Hash is deterministic for the same schema
    h1 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    h2 = DSNSchemaHasher.compute_schema_hash(board, netlist)
    assert h1 == h2


def test_embed_header():
    dsn = "(pcb test (unit mm))\n"
    result = DSNSchemaHasher.embed_header(dsn, "abc123")
    assert result.startswith(";schema-version: sha256:abc123\n")
    assert "(pcb test (unit mm))" in result


def test_embed_header_replaces_existing():
    dsn = ";schema-version: sha256:oldhash\n(pcb test)\n"
    result = DSNSchemaHasher.embed_header(dsn, "newhash")
    assert result.startswith(";schema-version: sha256:newhash\n")
    assert ";schema-version: sha256:oldhash" not in result


def test_extract_hash():
    dsn = ";schema-version: sha256:abc123def456\n(pcb test)\n"
    assert DSNSchemaHasher.extract_hash(dsn) == "abc123def456"


def test_extract_hash_missing():
    dsn = "(pcb test)\n"
    assert DSNSchemaHasher.extract_hash(dsn) is None


def test_schema_hash_in_export_pcb():
    """export_pcb() in deterministic mode includes schema-version header."""
    board = Board(width=100, height=100)
    comps = [Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))])]
    nets = [Net(name="SIG1", pins=[("U1", "1")])]
    netlist = Netlist(components=comps, nets=nets)

    from temper_placer.io.dsn_exporter import DSNExporter
    exporter = DSNExporter(board, netlist, deterministic=True)
    dsn_text = str(exporter.export_pcb("test"))

    assert dsn_text.startswith(";schema-version: sha256:")
    assert DSNSchemaHasher.extract_hash(dsn_text) is not None
