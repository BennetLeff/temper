from temper_placer.io.kicad_exporter import TraceVia
from temper_placer.io.via_dedup import deduplicate_vias


def test_exact_duplicates_removed():
    """Vias at identical position are deduplicated."""
    vias = [
        TraceVia(net="GND", position=(10.0, 20.0), size=0.8, drill=0.4, layers=["F.Cu", "B.Cu"]),
        TraceVia(net="+3V3", position=(10.0, 20.0), size=0.8, drill=0.4, layers=["F.Cu", "B.Cu"]),
    ]
    result = deduplicate_vias(vias)
    assert len(result) == 1
    assert result[0].position == (10.0, 20.0)


def test_floating_point_tolerance():
    """Vias within tolerance are considered duplicates."""
    vias = [
        TraceVia(net="GND", position=(10.0, 20.0), size=0.8, drill=0.4, layers=["F.Cu", "B.Cu"]),
        TraceVia(net="+3V3", position=(10.0001, 20.0001), size=0.8, drill=0.4, layers=["F.Cu", "B.Cu"]),
    ]
    result = deduplicate_vias(vias, tolerance_mm=0.001)
    assert len(result) == 1


def test_distinct_positions_preserved():
    """Vias at different positions are kept."""
    vias = [
        TraceVia(net="GND", position=(10.0, 20.0), size=0.8, drill=0.4, layers=["F.Cu", "B.Cu"]),
        TraceVia(net="GND", position=(15.0, 25.0), size=0.8, drill=0.4, layers=["F.Cu", "B.Cu"]),
    ]
    result = deduplicate_vias(vias)
    assert len(result) == 2
