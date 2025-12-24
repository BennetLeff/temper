"""
Tests for quality_score module.
"""


from temper_placer.metrics.quality_score import QualityScore, compute_quality_score
from temper_placer.validation.drc_runner import DrcResult
from temper_placer.validation.metrics import PlacementMetrics


def test_compute_quality_score_perfect_placement():
    """Test quality score with perfect placement (no violations)."""
    # Create perfect metrics
    metrics = PlacementMetrics(
        overlap_count=0,
        boundary_violations=0,
        clearance_violations=0,
        hv_lv_violations=0,
        zone_violations=0,
        keepout_violations=0,
        total_wirelength=100.0,
    )

    # Perfect DRC (no violations)
    drc_result = DrcResult(error_count=0, warning_count=0)

    # Compute score
    score = compute_quality_score(metrics, drc_result)

    # Should be near perfect
    assert score.overall >= 95.0, f"Expected >= 95, got {score.overall}"
    assert score.interpretation == "excellent"
    assert score.pass_quality is True
    assert score.placement_score >= 95.0
    assert score.drc_score == 100.0
    assert score.routing_score is None


def test_compute_quality_score_with_violations():
    """Test quality score with various violations."""
    # Create metrics with moderate violations
    metrics = PlacementMetrics(
        overlap_count=1,
        total_overlap_area=2.0,
        boundary_violations=0,
        clearance_violations=2,
        hv_lv_violations=0,
        zone_violations=0,
        keepout_violations=0,
        total_wirelength=200.0,
    )

    # DRC with moderate errors
    drc_result = DrcResult(error_count=2, warning_count=3)

    # Compute score
    score = compute_quality_score(metrics, drc_result)

    # Should be lower due to violations but still passing
    assert 60 <= score.overall < 90, f"Expected 60-90 with moderate violations, got {score.overall}"
    assert score.pass_quality is True  # Passes threshold (60)
    assert score.interpretation in ["ok", "good"]


def test_compute_quality_score_failing():
    """Test quality score that fails threshold."""
    # Create metrics with many violations
    metrics = PlacementMetrics(
        overlap_count=10,
        total_overlap_area=50.0,
        boundary_violations=5,
        clearance_violations=15,
        hv_lv_violations=5,
        zone_violations=3,
        keepout_violations=2,
        total_wirelength=500.0,
    )

    # DRC with many errors
    drc_result = DrcResult(error_count=20, warning_count=10)

    # Compute score
    score = compute_quality_score(metrics, drc_result)

    # Should fail threshold
    assert score.overall < 60.0, f"Expected < 60 (failing), got {score.overall}"
    assert score.pass_quality is False
    assert score.interpretation in ["poor", "ok"]


def test_quality_score_interpretations():
    """Test interpretation thresholds."""
    # Create real QualityScore objects from actual computation
    perfect_metrics = PlacementMetrics()
    perfect_drc = DrcResult(error_count=0, warning_count=0)

    # Test excellent (score >= 90)
    score = compute_quality_score(perfect_metrics, perfect_drc)
    assert score.overall >= 90
    assert score.interpretation == "excellent"

    # Test that violations reduce score
    drc_with_errors = DrcResult(error_count=5, warning_count=5)
    metrics_with_issues = PlacementMetrics(
        overlap_count=2,
        clearance_violations=3,
    )
    score_with_violations = compute_quality_score(metrics_with_issues, drc_with_errors)
    assert score_with_violations.overall < score.overall

    # Test that interpretation changes with score
    # Poor score
    many_errors = DrcResult(error_count=20, warning_count=10)
    metrics_bad = PlacementMetrics(
        overlap_count=10,
        total_overlap_area=50.0,
        clearance_violations=15,
    )
    score_poor = compute_quality_score(metrics_bad, many_errors)
    assert score_poor.overall < 60
    assert score_poor.interpretation == "poor"
    assert score_poor.pass_quality is False


def test_quality_score_to_dict():
    """Test QualityScore.to_dict() serialization."""
    score = QualityScore(
        overall=85.5,
        placement_score=90.0,
        drc_score=80.0,
        routing_score=None,
        interpretation="good",
        pass_quality=True,
    )

    d = score.to_dict()

    assert d["overall"] == 85.5
    assert d["placement_score"] == 90.0
    assert d["drc_score"] == 80.0
    assert d["routing_score"] is None
    assert d["interpretation"] == "good"
    assert d["pass_quality"] is True
