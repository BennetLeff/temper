"""Tests for uncovered placer template functions.

Covers ComponentTemplate.apply, ComponentTemplate.get_anchor_position,
HalfBridgeTemplate.create_vertical, and load_template_from_yaml.
"""

from temper_placer.placer.template import (
    ComponentPosition,
    ComponentTemplate,
    HalfBridgeTemplate,
    load_template_from_yaml,
)


class TestComponentTemplateApply:
    """Test ComponentTemplate.apply()."""

    def test_apply_basic(self):
        template = ComponentTemplate(
            name="basic",
            components=[
                ComponentPosition("A", 0, 0, 0),
                ComponentPosition("B", 10, 0, 90),
            ],
            anchor_point="A",
        )
        result = template.apply(anchor_x=50.0, anchor_y=60.0, rotation=0)
        assert "A" in result
        assert "B" in result
        # Anchor A at (50, 60)
        x_a, y_a, r_a = result["A"]
        assert x_a == 50.0
        assert y_a == 60.0
        assert r_a == 0

    def test_apply_with_rotation(self):
        template = ComponentTemplate(
            name="rotated",
            components=[
                ComponentPosition("A", 0, 0, 0),
                ComponentPosition("B", 10, 0, 0),
            ],
            anchor_point="A",
        )
        result = template.apply(anchor_x=0.0, anchor_y=0.0, rotation=90)
        assert "A" in result
        assert "B" in result
        # B should be rotated 90 degrees relative to anchor
        _, _, r_b = result["B"]
        assert r_b == 90

    def test_apply_missing_anchor_raises(self):
        template = ComponentTemplate(
            name="bad",
            components=[
                ComponentPosition("B", 10, 0, 0),
            ],
            anchor_point="A",  # A is not in components
        )
        import pytest
        with pytest.raises(ValueError, match="Anchor point A not found"):
            template.apply(0.0, 0.0)


class TestComponentTemplateGetAnchor:
    """Test ComponentTemplate.get_anchor_position()."""

    def test_get_anchor_position_found(self):
        template = ComponentTemplate(
            name="test",
            components=[
                ComponentPosition("Q1", 0, 0, 0),
                ComponentPosition("Q2", 0, -20, 0),
            ],
            anchor_point="Q1",
        )
        anchor = template.get_anchor_position()
        assert anchor is not None
        assert anchor.ref == "Q1"
        assert anchor.x == 0.0
        assert anchor.y == 0.0

    def test_get_anchor_position_not_found(self):
        template = ComponentTemplate(
            name="test",
            components=[
                ComponentPosition("Q1", 0, 0, 0),
            ],
            anchor_point="MISSING",
        )
        anchor = template.get_anchor_position()
        assert anchor is None


class TestHalfBridgeTemplate:
    """Test HalfBridgeTemplate.create_vertical()."""

    def test_create_vertical_defaults(self):
        template = HalfBridgeTemplate.create_vertical()
        assert template.name == "half_bridge_vertical"
        assert len(template.components) == 6
        assert template.anchor_point == "Q1"

        refs = [c.ref for c in template.components]
        assert "Q1" in refs
        assert "Q2" in refs
        assert "D1" in refs
        assert "D2" in refs
        assert "C_BUS1" in refs
        assert "C_BUS2" in refs

    def test_create_vertical_custom_refs(self):
        template = HalfBridgeTemplate.create_vertical(
            q1_ref="SW_HI",
            q2_ref="SW_LO",
            d1_ref="D_HI",
            d2_ref="D_LO",
            c_bus1_ref="C1",
            c_bus2_ref="C2",
            switch_spacing=30.0,
            diode_offset=20.0,
            cap_offset=35.0,
        )
        refs = [c.ref for c in template.components]
        assert "SW_HI" in refs
        assert "SW_LO" in refs
        assert "D_HI" in refs
        assert "D_LO" in refs
        assert "C1" in refs
        assert "C2" in refs

        # Check Q2 is at y = -switch_spacing = -30.0
        q2 = next(c for c in template.components if c.ref == "SW_LO")
        assert q2.y == -30.0

    def test_vertical_template_can_be_applied(self):
        template = HalfBridgeTemplate.create_vertical()
        result = template.apply(anchor_x=100.0, anchor_y=100.0)
        assert "Q1" in result
        assert len(result) == 6


class TestLoadTemplateFromYaml:
    """Test load_template_from_yaml()."""

    def test_load_basic_yaml(self, tmp_path):
        yaml_content = """\
name: test_template
anchor_point: U1
description: "A test template"
width: 40.0
height: 30.0
components:
  - ref: U1
    x: 0.0
    y: 0.0
    rotation: 0
  - ref: R1
    x: 10.0
    y: 5.0
    rotation: 90
"""
        yaml_path = tmp_path / "template.yaml"
        yaml_path.write_text(yaml_content)

        template = load_template_from_yaml(yaml_path)
        assert template.name == "test_template"
        assert template.anchor_point == "U1"
        assert template.description == "A test template"
        assert template.width == 40.0
        assert template.height == 30.0
        assert len(template.components) == 2

        # Check first component
        c1 = template.components[0]
        assert c1.ref == "U1"
        assert c1.x == 0.0
        assert c1.y == 0.0
        assert c1.rotation == 0

        # Check second component
        c2 = template.components[1]
        assert c2.ref == "R1"
        assert c2.rotation == 90

    def test_load_yaml_missing_optional_fields(self, tmp_path):
        yaml_content = """\
name: minimal
components:
  - ref: U1
    x: 0.0
    y: 0.0
"""
        yaml_path = tmp_path / "minimal.yaml"
        yaml_path.write_text(yaml_content)

        template = load_template_from_yaml(yaml_path)
        assert template.name == "minimal"
        assert template.width == 0.0
        assert template.height == 0.0
        assert template.description == ""

    def test_loaded_template_can_be_applied(self, tmp_path):
        yaml_content = """\
name: loaded
anchor_point: U1
components:
  - ref: U1
    x: 0.0
    y: 0.0
  - ref: R1
    x: 10.0
    y: 0.0
"""
        yaml_path = tmp_path / "loaded.yaml"
        yaml_path.write_text(yaml_content)

        template = load_template_from_yaml(yaml_path)
        result = template.apply(anchor_x=50.0, anchor_y=50.0)
        assert "U1" in result
        assert "R1" in result
