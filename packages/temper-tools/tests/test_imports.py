"""Smoke tests for temper-tools imports."""



def test_kicad_imports():
    """Verify KiCad tool modules can be imported."""
    from temper_tools.kicad import fix_schematics

    assert fix_schematics


def test_routing_imports():
    """Verify routing tool modules can be imported."""
    from temper_tools.routing import route

    assert route


def test_ato_imports():
    """Verify ato tool modules can be imported."""
    from temper_tools.ato import diff

    assert diff
