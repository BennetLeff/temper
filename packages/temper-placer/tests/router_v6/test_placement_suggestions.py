"""
Tests for Router V6 Feedback F.3: Generate Placement Suggestions

Part of temper-o35p
"""

import pytest

from temper_placer.router_v6.congestion_analysis import (
    CongestedRegion,
    CongestionMap,
    CongestionSeverity,
)
from temper_placer.router_v6.placement_suggestions import (
    PlacementSuggestion,
    PlacementSuggestions,
    generate_placement_suggestions,
)


def test_generate_no_suggestions():
    """Test placement suggestions with no congestion."""
    congestion = CongestionMap(regions=[])
    
    suggestions = generate_placement_suggestions(congestion)
    
    assert suggestions.suggestion_count == 0


def test_generate_with_critical_congestion():
    """Test placement suggestions for critical congestion."""
    region = CongestedRegion(
        center=(50.0, 50.0),
        radius=10.0,
        severity=CongestionSeverity.CRITICAL,
        failed_net_count=5,
        bottleneck_score=0.9,
    )
    congestion = CongestionMap(regions=[region])
    
    # Component near congested region
    components = {"U1": (55.0, 55.0)}
    
    suggestions = generate_placement_suggestions(congestion, components)
    
    # Should suggest moving component away
    assert suggestions.suggestion_count > 0


def test_placement_suggestion_dataclass():
    """Test PlacementSuggestion dataclass."""
    suggestion = PlacementSuggestion(
        component_id="U1",
        current_position=(50.0, 50.0),
        suggested_position=(60.0, 50.0),
        reason="Reduce high congestion",
        priority=0.8,
    )
    
    assert suggestion.component_id == "U1"
    assert suggestion.current_position == (50.0, 50.0)
    assert suggestion.suggested_position == (60.0, 50.0)
    assert suggestion.priority == 0.8


def test_placement_suggestions_dataclass():
    """Test PlacementSuggestions dataclass."""
    suggestion1 = PlacementSuggestion("U1", (50, 50), (60, 50), "test", 0.8)
    suggestion2 = PlacementSuggestion("U2", (30, 30), (40, 30), "test", 0.5)
    
    suggestions = PlacementSuggestions(suggestions=[suggestion1, suggestion2])
    
    assert suggestions.suggestion_count == 2


def test_get_high_priority_suggestions():
    """Test filtering high priority suggestions."""
    suggestion1 = PlacementSuggestion("U1", (50, 50), (60, 50), "test", 0.9)
    suggestion2 = PlacementSuggestion("U2", (30, 30), (40, 30), "test", 0.5)
    suggestion3 = PlacementSuggestion("U3", (70, 70), (80, 70), "test", 0.8)
    
    suggestions = PlacementSuggestions(suggestions=[suggestion1, suggestion2, suggestion3])
    
    high_priority = suggestions.get_high_priority_suggestions(threshold=0.7)
    assert len(high_priority) == 2  # suggestion1 and suggestion3


def test_low_congestion_no_suggestions():
    """Test that low congestion doesn't generate suggestions."""
    region = CongestedRegion(
        center=(50.0, 50.0),
        radius=10.0,
        severity=CongestionSeverity.LOW,
        failed_net_count=0,
        bottleneck_score=0.3,  # Below threshold
    )
    congestion = CongestionMap(regions=[region])
    
    components = {"U1": (55.0, 55.0)}
    
    suggestions = generate_placement_suggestions(congestion, components)
    
    # Low congestion should not generate suggestions
    assert suggestions.suggestion_count == 0


def test_multiple_components_in_region():
    """Test suggestions for multiple components in congested region."""
    region = CongestedRegion(
        center=(50.0, 50.0),
        radius=10.0,
        severity=CongestionSeverity.HIGH,
        failed_net_count=3,
        bottleneck_score=0.8,
    )
    congestion = CongestionMap(regions=[region])
    
    components = {
        "U1": (52.0, 52.0),
        "U2": (48.0, 48.0),
        "U3": (55.0, 55.0),
    }
    
    suggestions = generate_placement_suggestions(congestion, components)
    
    # Should suggest moving all components in the region
    assert suggestions.suggestion_count >= 3


def test_suggestion_priority_calculation():
    """Test that priority is calculated based on congestion severity."""
    high_region = CongestedRegion(
        center=(50.0, 50.0),
        radius=10.0,
        severity=CongestionSeverity.HIGH,
        failed_net_count=3,
        bottleneck_score=0.9,
    )
    
    low_region = CongestedRegion(
        center=(80.0, 80.0),
        radius=10.0,
        severity=CongestionSeverity.MEDIUM,
        failed_net_count=1,
        bottleneck_score=0.6,
    )
    
    congestion = CongestionMap(regions=[high_region, low_region])
    
    components = {
        "U1": (52.0, 52.0),  # In high congestion
        "U2": (82.0, 82.0),  # In medium congestion
    }
    
    suggestions = generate_placement_suggestions(congestion, components)
    
    # Find suggestions for each component
    u1_suggestion = next(s for s in suggestions.suggestions if s.component_id == "U1")
    u2_suggestion = next(s for s in suggestions.suggestions if s.component_id == "U2")
    
    # High congestion should have higher priority
    assert u1_suggestion.priority > u2_suggestion.priority
