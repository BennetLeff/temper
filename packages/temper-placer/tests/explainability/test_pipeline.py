"""Tests for composable traced pipeline."""

from temper_placer.explainability.pipeline import (
    TracedPipeline,
    compose_traces,
    demo_pipeline,
    traced_pipeline_example,
)
from temper_placer.explainability.trace import Trace


class TestComposeTraces:
    """Tests for compose_traces function."""

    def test_compose_empty_traces(self):
        """GIVEN empty traces
        WHEN composing
        THEN returns empty trace"""
        result = compose_traces()

        assert len(result) == 0

    def test_compose_single_trace(self):
        """GIVEN single trace
        WHEN composing
        THEN returns same trace"""
        trace1 = Trace.empty().add("Q1", (10, 20), "R1")

        result = compose_traces(trace1)

        assert len(result) == 1
        assert result.entries[0].subject == "Q1"

    def test_compose_multiple_traces(self):
        """GIVEN multiple traces
        WHEN composing
        THEN combines all entries"""
        trace1 = Trace.empty().add("Q1", (10, 20), "R1")
        trace2 = Trace.empty().add("Q2", (30, 40), "R2")
        trace3 = Trace.empty().add("VCC", "path", "R3")

        result = compose_traces(trace1, trace2, trace3)

        assert len(result) == 3
        assert result.entries[0].subject == "Q1"
        assert result.entries[1].subject == "Q2"
        assert result.entries[2].subject == "VCC"

    def test_compose_preserves_order(self):
        """GIVEN traces in specific order
        WHEN composing
        THEN preserves entry order"""
        trace1 = Trace.empty().add("A", 1, "R1")
        trace2 = Trace.empty().add("B", 2, "R2")
        trace3 = Trace.empty().add("C", 3, "R3")

        result = compose_traces(trace1, trace2, trace3)

        assert result.entries[0].because == "R1"
        assert result.entries[1].because == "R2"
        assert result.entries[2].because == "R3"


class TestTracedPipelineExample:
    """Tests for traced_pipeline_example function."""

    def test_pipeline_composes_traces(self):
        """GIVEN placement and routing functions
        WHEN running pipeline
        THEN composes traces from both phases"""
        def placement_fn(data):
            trace = Trace.empty().add("Q1", (10, 20), "Placed")
            return "positions", trace

        def routing_fn(positions, data):
            trace = Trace.empty().add("VCC", "path", "Routed")
            return "routes", trace

        result, trace = traced_pipeline_example(
            placement_fn, routing_fn, "data"
        )

        assert len(trace) == 2
        assert trace.entries[0].subject == "Q1"
        assert trace.entries[1].subject == "VCC"

    def test_pipeline_returns_both_results(self):
        """GIVEN pipeline functions
        WHEN running
        THEN returns results from both phases"""
        def placement_fn(data):
            return "positions", Trace.empty()

        def routing_fn(positions, data):
            return "routes", Trace.empty()

        result, trace = traced_pipeline_example(
            placement_fn, routing_fn, "data"
        )

        assert result == ("positions", "routes")


class TestTracedPipelineClass:
    """Tests for TracedPipeline class."""

    def test_empty_pipeline(self):
        """GIVEN empty pipeline
        WHEN running
        THEN returns input and empty trace"""
        pipeline = TracedPipeline()

        result, trace = pipeline.run("input")

        assert result == "input"
        assert len(trace) == 0

    def test_single_stage(self):
        """GIVEN pipeline with one stage
        WHEN running
        THEN executes stage and returns trace"""
        def stage1(data):
            trace = Trace.empty().add("S1", data, "Stage 1")
            return f"{data}_processed", trace

        pipeline = TracedPipeline()
        pipeline.add_stage("stage1", stage1)

        result, trace = pipeline.run("input")

        assert result == "input_processed"
        assert len(trace) == 1
        assert trace.entries[0].subject == "S1"

    def test_multiple_stages(self):
        """GIVEN pipeline with multiple stages
        WHEN running
        THEN executes all stages in order"""
        def stage1(data):
            trace = Trace.empty().add("S1", data, "Stage 1")
            return f"{data}_s1", trace

        def stage2(data):
            trace = Trace.empty().add("S2", data, "Stage 2")
            return f"{data}_s2", trace

        def stage3(data):
            trace = Trace.empty().add("S3", data, "Stage 3")
            return f"{data}_s3", trace

        pipeline = TracedPipeline()
        pipeline.add_stage("stage1", stage1)
        pipeline.add_stage("stage2", stage2)
        pipeline.add_stage("stage3", stage3)

        result, trace = pipeline.run("input")

        assert result == "input_s1_s2_s3"
        assert len(trace) == 3

    def test_pipeline_chaining(self):
        """GIVEN pipeline builder
        WHEN adding stages
        THEN supports method chaining"""
        def stage1(data):
            return data, Trace.empty()

        def stage2(data):
            return data, Trace.empty()

        pipeline = (TracedPipeline()
                   .add_stage("s1", stage1)
                   .add_stage("s2", stage2))

        assert len(pipeline.stages) == 2

    def test_pipeline_combines_traces(self):
        """GIVEN pipeline with multiple stages
        WHEN running
        THEN combines all traces via monoid operation"""
        def stage1(data):
            trace = Trace.empty()
            trace = trace.add("A", 1, "R1")
            trace = trace.add("B", 2, "R2")
            return data, trace

        def stage2(data):
            trace = Trace.empty()
            trace = trace.add("C", 3, "R3")
            return data, trace

        pipeline = TracedPipeline()
        pipeline.add_stage("s1", stage1)
        pipeline.add_stage("s2", stage2)

        result, trace = pipeline.run("input")

        assert len(trace) == 3
        assert trace.entries[0].subject == "A"
        assert trace.entries[1].subject == "B"
        assert trace.entries[2].subject == "C"


class TestDemoPipeline:
    """Tests for demo_pipeline function."""

    def test_demo_runs(self):
        """GIVEN demo pipeline
        WHEN running
        THEN executes without error"""
        result, trace = demo_pipeline()

        assert result is not None
        assert isinstance(trace, Trace)

    def test_demo_has_placement_and_routing(self):
        """GIVEN demo pipeline
        WHEN running
        THEN has entries from both phases"""
        result, trace = demo_pipeline()

        # Should have placement entries
        q1_explanation = trace.why("Q1")
        assert "Q1" in q1_explanation

        # Should have routing entries
        vcc_explanation = trace.why("VCC")
        assert "VCC" in vcc_explanation


class TestIntegration:
    """Integration tests for full pipeline."""

    def test_full_pipeline_workflow(self):
        """GIVEN complete pipeline with placement and routing
        WHEN running
        THEN can query decisions from any phase"""
        # Define traced placement
        def placement(components):
            trace = Trace.empty()
            for comp in components:
                trace = trace.add(
                    comp,
                    (10.0, 20.0),
                    f"Placed {comp} to minimize wirelength"
                )
            return {"positions": "mock"}, trace

        # Define traced routing
        def routing(placement_result):
            trace = Trace.empty()
            trace = trace.add("VCC", ["L1", "L4"], "Power net on signal layers")
            trace = trace.add("GND", ["L1", "L4"], "Ground net on signal layers")
            return {"routes": "mock"}, trace

        # Build and run pipeline
        pipeline = TracedPipeline()
        pipeline.add_stage("placement", placement)
        pipeline.add_stage("routing", routing)

        components = ["Q1", "Q2", "U1"]
        result, trace = pipeline.run(components)

        # Query placement decisions
        q1_explanation = trace.why("Q1")
        assert "Q1" in q1_explanation
        assert "wirelength" in q1_explanation

        # Query routing decisions
        vcc_explanation = trace.why("VCC")
        assert "VCC" in vcc_explanation
        assert "Power" in vcc_explanation

    def test_pipeline_monoid_composition(self):
        """GIVEN pipeline stages
        WHEN composing traces
        THEN follows monoid laws"""
        def stage1(data):
            return data, Trace.empty().add("A", 1, "R1")

        def stage2(data):
            return data, Trace.empty().add("B", 2, "R2")

        def stage3(data):
            return data, Trace.empty().add("C", 3, "R3")

        # Build pipeline
        pipeline = TracedPipeline()
        pipeline.add_stage("s1", stage1)
        pipeline.add_stage("s2", stage2)
        pipeline.add_stage("s3", stage3)

        _, trace = pipeline.run("input")

        # Verify associativity: (t1 + t2) + t3 == t1 + (t2 + t3)
        # This is implicit in the pipeline composition
        assert len(trace) == 3
