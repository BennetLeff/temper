
import pytest
from pathlib import Path
from temper_placer.templates.manager import TemplateManager

def test_template_manager_load_all():
    manager = TemplateManager()
    manager.load_all()
    assert "half_bridge" in manager.templates
    assert "ucc21550" in manager.templates

def test_template_composition():
    manager = TemplateManager()
    manager.load_all()
    
    # Compose temper_induction_cooker which extends others
    composed = manager.compose(["temper_induction"])
    
    assert "high_side_switch" in composed["components"]
    assert "tank_cap" in composed["components"]
    assert len(composed["constraints"]) >= 5
