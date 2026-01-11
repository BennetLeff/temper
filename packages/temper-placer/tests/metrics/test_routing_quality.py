import pytest
from unittest.mock import MagicMock
from temper_placer.metrics.routing_quality import evaluate_routing_quality, RoutingQualityScore

def test_evaluate_routing_quality_acceptable():
    """Test routing quality with acceptable parameters (completion >= 0.8, DRC = 0)."""
    routing_result = MagicMock()
    routing_result.completion_rate = 0.85
    routing_result.total_vias = 10
    routing_result.total_wirelength = 100.0
    routing_result.routed_nets = ["N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8"]
    routing_result.failed_nets = ["N9", "N10"]
    
    drc_result = MagicMock()
    drc_result.error_count = 0
    
    quality = evaluate_routing_quality(routing_result, drc_result)
    
    assert isinstance(quality, RoutingQualityScore)
    assert quality.completion_rate == 0.85
    assert quality.via_count == 10
    assert quality.total_length == 100.0
    assert quality.drc_violations == 0
    assert quality.is_acceptable is True
    assert quality.score > 0

def test_evaluate_routing_quality_unacceptable_completion():
    """Test routing quality with low completion rate (< 0.8)."""
    routing_result = MagicMock()
    routing_result.completion_rate = 0.75
    routing_result.total_vias = 10
    routing_result.total_wirelength = 100.0
    routing_result.routed_nets = ["N1"] * 75
    routing_result.failed_nets = ["N2"] * 25
    
    drc_result = MagicMock()
    drc_result.error_count = 0
    
    quality = evaluate_routing_quality(routing_result, drc_result)
    
    assert quality.is_acceptable is False

def test_evaluate_routing_quality_unacceptable_drc():
    """Test routing quality with DRC errors."""
    routing_result = MagicMock()
    routing_result.completion_rate = 1.0
    routing_result.total_vias = 10
    routing_result.total_wirelength = 100.0
    routing_result.routed_nets = ["N1"] * 10
    routing_result.failed_nets = []
    
    drc_result = MagicMock()
    drc_result.error_count = 1
    
    quality = evaluate_routing_quality(routing_result, drc_result)
    
    assert quality.is_acceptable is False

def test_routing_quality_threshold():
    """Verify the specific threshold: completion >= 0.8 AND drc == 0."""
    routing_result = MagicMock()
    drc_result = MagicMock()
    
    # Case 1: Just at threshold
    routing_result.completion_rate = 0.8
    routing_result.total_vias = 0
    routing_result.routed_nets = ["N1"] * 8
    routing_result.failed_nets = ["N2"] * 2
    drc_result.error_count = 0
    quality = evaluate_routing_quality(routing_result, drc_result)
    assert quality.is_acceptable is True
    
    # Case 2: Below completion threshold
    routing_result.completion_rate = 0.79
    quality = evaluate_routing_quality(routing_result, drc_result)
    assert quality.is_acceptable is False
    
    # Case 3: Above completion but has DRC
    routing_result.completion_rate = 1.0
    drc_result.error_count = 1
    quality = evaluate_routing_quality(routing_result, drc_result)
    assert quality.is_acceptable is False