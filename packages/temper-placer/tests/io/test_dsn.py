import pytest

from temper_placer.io.dsn import (
    DSNCircle,
    DSNExpression,
    DSNPath,
    DSNPoint,
    DSNPolygon,
    DSNRect,
    DSNShape,
    dsn_list,
)


def test_dsn_expression_serialization():
    expr = dsn_list("pcb", "sample", dsn_list("unit", "mm"))
    assert str(expr) == "(pcb sample (unit mm))"


def test_dsn_float_formatting():
    expr = dsn_list("coord", 10.0, 10.5, 10.54321)
    # 10.0 -> 10, 10.5 -> 10.5
    assert str(expr) == "(coord 10 10.5 10.54321)"


def test_dsn_string_quoting():
    expr = dsn_list("name", "GND", "VCC (Power)", 'Quoted "String"')
    assert str(expr) == '(name GND "VCC (Power)" "Quoted \\"String\\"")'


def test_dsn_rect():
    rect = DSNRect("pcb", 0, 0, 100, 100)
    assert str(rect.to_dsn()) == "(rect pcb 0 0 100 100)"


def test_dsn_circle():
    circle = DSNCircle("F.Cu", 1.5, 10, 20)
    assert str(circle.to_dsn()) == "(circle F.Cu 1.5 10 20)"


def test_dsn_path():
    path = DSNPath("F.Cu", 0.2, [(0, 0), (10, 0), (10, 10)])
    assert str(path.to_dsn()) == "(path F.Cu 0.2 0 0 10 0 10 10)"


def test_dsn_point():
    """DSNPoint.to_dsn() produces (point x y)."""
    point = DSNPoint(10.0, 20.0)
    expr = point.to_dsn()
    assert isinstance(expr, DSNExpression)
    assert str(expr) == "(point 10 20)"


def test_dsn_point_negative():
    """DSNPoint handles negative coordinates."""
    point = DSNPoint(-5.5, -3.2)
    assert str(point.to_dsn()) == "(point -5.5 -3.2)"


def test_dsn_polygon():
    """DSNPolygon.to_dsn() produces (polygon layer width x1 y1 x2 y2 ...)."""
    poly = DSNPolygon("F.Cu", 0.2, [(0, 0), (10, 0), (10, 10), (0, 10)])
    expr = poly.to_dsn()
    assert isinstance(expr, DSNExpression)
    # Order of points as given
    assert "(polygon F.Cu 0.2 0 0 10 0 10 10 0 10)" in str(expr) or "(polygon F.Cu 0.2 0 0 10 0 10 10 0 10)" == str(expr)


def test_dsn_polygon_single_point():
    """DSNPolygon with a single point."""
    poly = DSNPolygon("B.Cu", 0.5, [(5.0, 5.0)])
    expr = poly.to_dsn()
    assert isinstance(expr, DSNExpression)


def test_dsn_shape_to_dsn_raises():
    """DSNShape.to_dsn() raises NotImplementedError."""
    shape = DSNShape()
    with pytest.raises(NotImplementedError):
        shape.to_dsn()


def test_dsn_expression_with_comment():
    """DSNExpression.with_comment() returns a new expression with a comment line."""
    expr = dsn_list("pcb", "test")
    commented = expr.with_comment("My comment")
    text = str(commented)
    assert "My comment" in text
    assert "(pcb test)" in text
