"""
End-to-End Explainability Demo.

This test demonstrates what the system produces when running on different design scenarios.
"""

from temper_placer.core.board import LayerStackup
from temper_placer.explainability import Trace
from temper_placer.explainability.pipeline import TracedPipeline


def test_demo_explainability_scenarios():
    def run_design_scenario(name, components, net_configs):
        print(f"\n{'='*60}")
        print(f"DESIGN SCENARIO: {name}")
        print(f"{'='*60}")

        stackup = LayerStackup.default_4layer()

        def placement_stage(_data):
            trace = Trace.empty()
            for comp, reason in components.items():
                trace = trace.add(comp, (50.0, 50.0), reason)
            return {"positions": "optimized_data"}, trace

        def routing_stage(_placement_data):
            trace = Trace.empty()
            for net_name, config in net_configs.items():
                net_class = config['class']
                allowed = stackup.routable_layers(net_class)

                if net_class == "HighVoltage":
                    msg = "Restricted to L1 (2oz copper) for high current capacity. " \
                          "Path avoids logic area to maintain creepage."
                else:
                    msg = f"Routed on signal layers {allowed} to minimize via count. " \
                          f"Layer L4 used for cross-talk reduction."

                trace = trace.add(net_name, "PATH_DATA", msg)
            return {"routes": "routed_data"}, trace

        pipeline = TracedPipeline()
        pipeline.add_stage("placement", placement_stage)
        pipeline.add_stage("routing", routing_stage)

        result, combined_trace = pipeline.run(None)

        print("\n[EXPLANATIONS]")
        subjects = list(components.keys()) + list(net_configs.keys())
        for subject in subjects:
            print(f"\n> why('{subject}')?")
            print(combined_trace.why(subject))

    # --- DESIGN A: Power Module ---
    power_module_components = {
        "Q1": "Placed near DC link capacitor to minimize parasitic inductance.",
        "C_DC": "Fixed position near power input terminals.",
    }
    power_module_nets = {
        "HV_BUS": {"class": "HighVoltage"},
        "VCC": {"class": "Power"}
    }

    # --- DESIGN B: Signal Processor ---
    signal_processor_components = {
        "U1": "Central position to balance wirelength for peripheral connectors.",
    }
    signal_processor_nets = {
        "SIG_HIGH_SPEED": {"class": "Signal"},
    }

    run_design_scenario("POWER CONVERTER (Safety Critical)", power_module_components, power_module_nets)
    run_design_scenario("SIGNAL PROCESSOR (High Density)", signal_processor_components, signal_processor_nets)
