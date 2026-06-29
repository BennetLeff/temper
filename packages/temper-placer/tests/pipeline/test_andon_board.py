"""Tests for AndonObserver live pipeline dashboard."""

import pytest


class TestAndonObserverState:
    """Tests for AndonObserver state management."""

    def test_can_create(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "geometric", "routing", "output"])
        assert obs.stage_order == ["input", "geometric", "routing", "output"]
        assert obs.port > 0

    def test_port_is_reproducible(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["a"], port=9999)
        assert obs.port == 9999

    def test_initial_state_has_all_stations_idle(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        stages = obs._state["stages"]
        assert len(stages) == 2
        assert all(s["status"] == "idle" for s in stages)

    def test_on_stage_start_sets_active(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        obs.on_stage_start("input", 0, {})
        stages = obs._state["stages"]
        assert stages[0]["status"] == "active"

    def test_on_stage_complete_sets_done(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        obs.on_stage_start("input", 0, {})
        obs.on_stage_complete("input", 2.5, {})
        stages = obs._state["stages"]
        assert stages[0]["status"] == "done"
        assert "2.5s" in stages[0]["timer"]

    def test_on_stage_skip_sets_skip(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        obs.on_stage_skip("input", "dry_run")
        stages = obs._state["stages"]
        assert stages[0]["status"] == "skip"

    def test_on_stage_error_sets_error(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        obs.on_stage_error("input", ValueError("bad input"))
        stages = obs._state["stages"]
        assert stages[0]["status"] == "error"

    def test_on_feedback_updates_footer(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        obs.on_feedback_triggered("routability", "routing", "geometric", 1)
        assert "routability" in obs._state["footer"]

    def test_on_pipeline_complete_updates_header(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["input", "output"])
        obs.on_pipeline_complete(True, 5.0, {"input": 2.0, "output": 3.0})
        assert "PASSED" in obs._state["header"]

    def test_on_epoch_updates_metric(self):
        from temper_placer.pipeline.andon_observer import AndonObserver
        obs = AndonObserver(stage_order=["geometric", "output"])
        obs.on_epoch("geometric", 42, 0.123)
        stages = obs._state["stages"]
        assert "epoch 42" in stages[0]["metric"]

    def test_html_page_served(self):
        """Verify the embedded HTML template is valid — server test done in isolation."""
        from temper_placer.pipeline.andon_observer import _ANDON_HTML
        assert "Andon Board" in _ANDON_HTML
        assert "EventSource" in _ANDON_HTML
        assert "station" in _ANDON_HTML
