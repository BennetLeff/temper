from temper_placer.placer.template import ParametricComponentPosition, ParametricTemplate


def test_parametric_template_apply():
    # 10x10 template
    # Q1 at (2, 2)
    # Q2 at (8, 8)
    # Anchor is Q1
    components = [
        ParametricComponentPosition("Q1", 0.2, 0.2),
        ParametricComponentPosition("Q2", 0.8, 0.8),
    ]
    template = ParametricTemplate("test", components, "Q1")

    # Apply to 100x100 area at anchor (50, 50)
    # Q1 ratio (0.2, 0.2) maps to (20, 20) in 100x100
    # Anchor offset is (20, 20)

    # Q1 absolute should be (50, 50)
    # Q2 rel should be (80-20, 80-20) = (60, 60)
    # Q2 absolute should be (50+60, 50+60) = (110, 110)

    placements = template.apply(50, 50, 100, 100)

    assert placements["Q1"] == (50.0, 50.0, 0)
    assert placements["Q2"] == (110.0, 110.0, 0)

def test_parametric_half_bridge():
    template = ParametricTemplate.create_half_bridge()
    assert len(template.components) == 6
    assert template.anchor_ref == "Q1"
