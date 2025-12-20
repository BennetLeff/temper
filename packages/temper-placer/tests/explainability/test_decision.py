"""Tests for the explainability.decision module."""

import pytest
from datetime import datetime

from temper_placer.explainability import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)


class TestAlternative:
    """Tests for Alternative dataclass."""

    def test_create_basic_alternative(self):
        """Alternative can be created with required fields."""
        alt = Alternative(
            value=(50, 10),
            rejection_reason="Violates clearance constraint",
        )
        assert alt.value == (50, 10)
        assert alt.rejection_reason == "Violates clearance constraint"
        assert alt.constraint_violated is None
        assert alt.loss_if_chosen is None

    def test_create_full_alternative(self):
        """Alternative can be created with all fields."""
        alt = Alternative(
            value=(50, 10),
            rejection_reason="Violates 10mm HV clearance to U_MCU",
            constraint_violated="clearance.hv_lv",
            loss_if_chosen=0.85,
        )
        assert alt.value == (50, 10)
        assert alt.constraint_violated == "clearance.hv_lv"
        assert alt.loss_if_chosen == 0.85


class TestDecision:
    """Tests for Decision dataclass."""

    def test_create_default_decision(self):
        """Decision can be created with defaults."""
        d = Decision()
        assert d.id is not None
        assert len(d.id) == 8
        assert isinstance(d.timestamp, datetime)
        assert d.phase == DecisionPhase.GEOMETRIC
        assert d.decision_type == DecisionType.POSITION_UPDATE
        assert d.subject == ""
        assert d.value is None
        assert d.alternatives == []

    def test_create_placement_decision(self):
        """Decision can be created for component placement."""
        d = Decision(
            decision_type=DecisionType.INITIAL_POSITION,
            phase=DecisionPhase.GEOMETRIC,
            subject="Q1",
            value=(45.2, 12.3),
            reason="Thermal edge constraint requires IGBT within 5mm of top edge",
            constraint_refs=["thermal.Q1"],
        )
        assert d.subject == "Q1"
        assert d.value == (45.2, 12.3)
        assert d.reason == "Thermal edge constraint requires IGBT within 5mm of top edge"
        assert "thermal.Q1" in d.constraint_refs

    def test_decision_with_alternatives(self):
        """Decision can include rejected alternatives."""
        alt = Alternative(
            value=(50, 10),
            rejection_reason="Violates HV clearance",
            constraint_violated="clearance.hv_lv",
        )
        d = Decision(
            subject="Q1",
            value=(45.2, 12.3),
            reason="Best position for thermal and clearance",
            alternatives=[alt],
        )
        assert len(d.alternatives) == 1
        assert d.alternatives[0].value == (50, 10)

    def test_decision_to_dict(self):
        """Decision.to_dict() produces valid dictionary."""
        d = Decision(
            decision_type=DecisionType.ROTATION,
            subject="Q1",
            value=90,
            previous_value=0,
            reason="Rotated for pin alignment",
            epoch=100,
        )
        result = d.to_dict()
        assert result["subject"] == "Q1"
        assert result["value"] == 90
        assert result["previous_value"] == 0
        assert result["decision_type"] == "rotation"
        assert result["epoch"] == 100
        assert "timestamp" in result

    def test_decision_types(self):
        """All decision types can be used."""
        for dt in DecisionType:
            d = Decision(decision_type=dt, subject="test")
            assert d.decision_type == dt

    def test_decision_phases(self):
        """All decision phases can be used."""
        for phase in DecisionPhase:
            d = Decision(phase=phase, subject="test")
            assert d.phase == phase


class TestDecisionTrace:
    """Tests for DecisionTrace dataclass."""

    def test_create_empty_trace(self):
        """DecisionTrace can be created empty."""
        trace = DecisionTrace()
        assert len(trace) == 0
        assert trace.run_id is not None
        assert len(trace.run_id) == 12
        assert isinstance(trace.start_time, datetime)
        assert trace.end_time is None

    def test_add_decision(self):
        """Decisions can be added to trace."""
        trace = DecisionTrace()
        d = Decision(subject="Q1", value=(10, 20), reason="Initial")
        trace.add(d)
        assert len(trace) == 1
        assert trace.decisions[0] == d

    def test_query_subject(self):
        """query_subject returns decisions for a component."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Initial"))
        trace.add(Decision(subject="Q2", value=(30, 40), reason="Initial"))
        trace.add(Decision(subject="Q1", value=(15, 25), reason="Moved"))

        q1_decisions = trace.query_subject("Q1")
        assert len(q1_decisions) == 2
        assert all(d.subject == "Q1" for d in q1_decisions)

        q2_decisions = trace.query_subject("Q2")
        assert len(q2_decisions) == 1

        # Non-existent subject
        assert trace.query_subject("Q3") == []

    def test_query_phase(self):
        """query_phase returns decisions for a phase."""
        trace = DecisionTrace()
        trace.add(Decision(phase=DecisionPhase.SEMANTIC, subject="cluster1"))
        trace.add(Decision(phase=DecisionPhase.GEOMETRIC, subject="Q1"))
        trace.add(Decision(phase=DecisionPhase.GEOMETRIC, subject="Q2"))
        trace.add(Decision(phase=DecisionPhase.ROUTING, subject="NET1"))

        geo = trace.query_phase(DecisionPhase.GEOMETRIC)
        assert len(geo) == 2

        routing = trace.query_phase(DecisionPhase.ROUTING)
        assert len(routing) == 1

    def test_query_type(self):
        """query_type returns decisions of a specific type."""
        trace = DecisionTrace()
        trace.add(Decision(decision_type=DecisionType.INITIAL_POSITION, subject="Q1"))
        trace.add(Decision(decision_type=DecisionType.ROTATION, subject="Q1"))
        trace.add(Decision(decision_type=DecisionType.INITIAL_POSITION, subject="Q2"))

        positions = trace.query_type(DecisionType.INITIAL_POSITION)
        assert len(positions) == 2

        rotations = trace.query_type(DecisionType.ROTATION)
        assert len(rotations) == 1

    def test_query_constraint(self):
        """query_constraint returns decisions influenced by a constraint."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", constraint_refs=["thermal.Q1", "adjacent.Q1_Q2"]))
        trace.add(Decision(subject="Q2", constraint_refs=["thermal.Q2"]))
        trace.add(Decision(subject="U1", constraint_refs=["zone.mcu"]))

        thermal_q1 = trace.query_constraint("thermal.Q1")
        assert len(thermal_q1) == 1
        assert thermal_q1[0].subject == "Q1"

    def test_why(self):
        """why() returns explanation for final state."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Initial placement"))
        trace.add(
            Decision(
                subject="Q1",
                value=(15, 25),
                previous_value=(10, 20),
                reason="Moved for thermal clearance",
            )
        )

        explanation = trace.why("Q1")
        assert "Q1" in explanation
        assert "(15, 25)" in explanation
        assert "thermal clearance" in explanation

    def test_why_no_decisions(self):
        """why() handles subject with no decisions."""
        trace = DecisionTrace()
        explanation = trace.why("Q_UNKNOWN")
        assert "No decisions recorded" in explanation

    def test_why_not(self):
        """why_not() explains rejected alternatives."""
        alt = Alternative(
            value=(50, 10),
            rejection_reason="Violates HV clearance to MCU",
        )
        trace = DecisionTrace()
        trace.add(
            Decision(
                subject="Q1",
                value=(45, 12),
                reason="Best position",
                alternatives=[alt],
            )
        )

        explanation = trace.why_not("Q1", (50, 10))
        assert "(50, 10) was rejected" in explanation
        assert "HV clearance" in explanation

    def test_why_not_not_considered(self):
        """why_not() handles values never considered."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Initial"))

        explanation = trace.why_not("Q1", (999, 999))
        assert "No record" in explanation

    def test_history(self):
        """history() returns value progression."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Initial"))
        trace.add(Decision(subject="Q1", value=(15, 25), reason="Adjusted"))
        trace.add(Decision(subject="Q1", value=(12, 22), reason="Final"))

        hist = trace.history("Q1")
        assert len(hist) == 3
        assert hist[0] == ((10, 20), "Initial")
        assert hist[1] == ((15, 25), "Adjusted")
        assert hist[2] == ((12, 22), "Final")

    def test_finalize(self):
        """finalize() sets end time and final state."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Initial"))

        assert trace.end_time is None

        trace.finalize(
            positions={"Q1": (10, 20), "Q2": (30, 40)},
            metrics={"hpwl": 123.4, "overlap": 0.0},
        )

        assert trace.end_time is not None
        assert trace.final_positions == {"Q1": (10, 20), "Q2": (30, 40)}
        assert trace.final_metrics == {"hpwl": 123.4, "overlap": 0.0}

    def test_to_dict(self):
        """to_dict() produces valid dictionary."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Initial"))
        trace.finalize(positions={"Q1": (10, 20)})

        result = trace.to_dict()
        assert "run_id" in result
        assert "start_time" in result
        assert "end_time" in result
        assert "decisions" in result
        assert len(result["decisions"]) == 1
        assert result["final_positions"] == {"Q1": (10, 20)}

    def test_summary(self):
        """summary() produces decision statistics."""
        trace = DecisionTrace()
        trace.add(
            Decision(
                phase=DecisionPhase.GEOMETRIC,
                decision_type=DecisionType.INITIAL_POSITION,
                subject="Q1",
            )
        )
        trace.add(
            Decision(
                phase=DecisionPhase.GEOMETRIC, decision_type=DecisionType.ROTATION, subject="Q1"
            )
        )
        trace.add(
            Decision(
                phase=DecisionPhase.GEOMETRIC,
                decision_type=DecisionType.INITIAL_POSITION,
                subject="Q2",
            )
        )
        trace.add(
            Decision(
                phase=DecisionPhase.ROUTING, decision_type=DecisionType.NET_ORDER, subject="NET1"
            )
        )
        trace.finalize()

        summary = trace.summary()
        assert summary["total_decisions"] == 4
        assert summary["unique_subjects"] == 3
        assert summary["by_phase"]["geometric"] == 3
        assert summary["by_phase"]["routing"] == 1
        assert summary["by_type"]["initial_position"] == 2
        assert summary["duration_seconds"] is not None

    def test_iteration(self):
        """DecisionTrace is iterable."""
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=1))
        trace.add(Decision(subject="Q2", value=2))

        values = [d.value for d in trace]
        assert values == [1, 2]


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_placement_workflow(self):
        """Complete placement workflow with multiple decisions."""
        trace = DecisionTrace(config_snapshot={"epochs": 1000, "seed": 42})

        # Initial placements (semantic phase)
        trace.add(
            Decision(
                phase=DecisionPhase.SEMANTIC,
                decision_type=DecisionType.CLUSTER_MEMBERSHIP,
                subject="Q1",
                value="power_stage",
                reason="Q1 is an IGBT, belongs to power stage cluster",
            )
        )
        trace.add(
            Decision(
                phase=DecisionPhase.SEMANTIC,
                decision_type=DecisionType.CLUSTER_MEMBERSHIP,
                subject="U_MCU",
                value="control",
                reason="MCU belongs to control cluster",
            )
        )

        # Geometric placement
        trace.add(
            Decision(
                phase=DecisionPhase.GEOMETRIC,
                decision_type=DecisionType.INITIAL_POSITION,
                subject="Q1",
                value=(50, 10),
                reason="Power stage cluster placed at top edge for thermal dissipation",
                constraint_refs=["thermal.edge_placement"],
                epoch=0,
            )
        )

        # Position refined during optimization
        alt = Alternative(
            value=(45, 10),
            rejection_reason="Would violate 5mm edge keepout",
            constraint_violated="keepout.board_edge",
            loss_if_chosen=0.95,
        )
        trace.add(
            Decision(
                phase=DecisionPhase.GEOMETRIC,
                decision_type=DecisionType.POSITION_UPDATE,
                subject="Q1",
                value=(52, 12),
                previous_value=(50, 10),
                reason="Gradient descent moved for better wire length",
                alternatives=[alt],
                epoch=500,
                loss_contribution=-0.02,
            )
        )

        # Finalize
        trace.finalize(
            positions={"Q1": (52, 12), "U_MCU": (80, 50)},
            metrics={"hpwl": 234.5, "overlap": 0.0, "thermal_score": 0.95},
        )

        # Query the trace
        assert len(trace) == 4
        assert (
            trace.why("Q1")
            == "Q1 is at (52, 12) because: Gradient descent moved for better wire length"
        )
        assert "edge keepout" in trace.why_not("Q1", (45, 10))

        # Check summary
        summary = trace.summary()
        assert summary["unique_subjects"] == 2
        assert summary["by_phase"]["semantic"] == 2
        assert summary["by_phase"]["geometric"] == 2
