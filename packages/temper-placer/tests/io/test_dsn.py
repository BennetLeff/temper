from temper_placer.io.dsn import DSNExpression, dsn_list, DSNRect, DSNCircle, DSNPath

def test_dsn_expression_serialization():
    expr = dsn_list("pcb", "sample", dsn_list("unit", "mm"))
    assert str(expr) == "(pcb sample (unit mm))"

def test_dsn_float_formatting():
    expr = dsn_list("coord", 10.0, 10.5, 10.54321)
    # 10.0 -> 10, 10.5 -> 10.5
    assert str(expr) == "(coord 10 10.5 10.54321)"

def test_dsn_string_quoting():
    expr = dsn_list("name", "GND", "VCC (Power)", "Quoted \"String\"")
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

