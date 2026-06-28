"""
End-to-End Explainability Demo Script.

This script demonstrates what the system produces when running on different design scenarios:
1. Power Converter (HV safety, commutation loops)
2. Signal Processor (Dense routing, layer transitions)
"""

from temper_placer.explainability import Trace
from temper_placer.explainability.pipeline import TracedPipeline
from temper_placer.core.board import LayerStackup
from temper_placer.router_v6.adapter import MazeRouter
import jax.numpy as jnp

def run_design_scenario(name, components, net_configs):
    print(f"\n{'='*60}")
    print(f"DESIGN SCENARIO: {name}")
    print(f"{'='*60}")

    stackup = LayerStackup.default_4layer()
    router = MazeRouter(grid_size=(100, 100), num_layers=4, layer_stackup=stackup)

    def placement_stage(data):
        trace = Trace.empty()
        # Mocking the output of a traced optimizer
        for comp, reason in components.items():
            trace = trace.add(comp, (50.0, 50.0), reason)
        return {"positions": "optimized_data"}, trace

    def routing_stage(placement_data):
        trace = Trace.empty()
        # Mocking the output of route_all_with_trace
        for net_name, config in net_configs.items():
            net_class = config['class']
            allowed = stackup.routable_layers(net_class)
            
            # Simulate a routing decision
            if net_class == "HighVoltage":
                msg = f"Restricted to L1 (2oz copper) for high current capacity. " \
                      f"Path avoids logic area to maintain creepage."
            else:
                msg = f"Routed on signal layers {allowed} to minimize via count. " \
                      f"Layer L4 used for cross-talk reduction."
            
            trace = trace.add(net_name, "PATH_DATA", msg)
        return {"routes": "routed_data"}, trace

    # Build and run pipeline
    pipeline = TracedPipeline()
    pipeline.add_stage("placement", placement_stage)
    pipeline.add_stage("routing", routing_stage)

    result, combined_trace = pipeline.run(None)

    # Show the "Explainability Output"
    print("\n[EXPLANATIONS]")
    subjects = list(components.keys()) + list(net_configs.keys())
    for subject in subjects:
        print(f"\n> why('{subject}')?")
        print(combined_trace.why(subject))

# --- DESIGN A: Power Module ---
power_module_components = {
    "Q1": "Placed near DC link capacitor to minimize parasitic inductance.",
    "C_DC": "Fixed position near power input terminals.",
    "T1": "Placed at board edge to optimize thermal dissipation and airflow."
}
power_module_nets = {
    "HV_BUS": {"class": "HighVoltage"},
    "GATE_DRIVE": {"class": "Signal"},
    "VCC": {"class": "Power"}
}

# --- DESIGN B: Signal Processor ---
signal_processor_components = {
    "U1": "Central position to balance wirelength for peripheral connectors.",
    "OSC1": "Placed adjacent to U1.XTAL pins with short, symmetric traces.",
}
signal_processor_nets = {
    "SIG_HIGH_SPEED": {"class": "Signal"},
    "DEBUG_UART": {"class": "Signal"},
}

if __name__ == "__main__":
    run_design_scenario("POWER CONVERTER (Safety Critical)", power_module_components, power_module_nets)
    run_design_scenario("SIGNAL PROCESSOR (High Density)", signal_processor_components, signal_processor_nets)
