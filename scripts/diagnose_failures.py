import sys
from pathlib import Path
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6


def diagnose():
    pcb_path = Path("pcb/temper_fixed.kicad_pcb")
    if not pcb_path.exists():
        print(f"Error: {pcb_path} does not exist.")
        return

    print(f"Loading {pcb_path}...")
    pipeline = RouterV6Pipeline(verbose=True)

    # We run the pipeline but we want to capture the result object
    # The pipeline.run() method returns RouterV6Result

    try:
        result = pipeline.run(pcb_path)
    except Exception as e:
        print(f"Pipeline failed with error: {e}")
        import traceback

        traceback.print_exc()
        return

    print("\n" + "=" * 50)
    print("DIAGNOSTIC REPORT")
    print("=" * 50)

    stage4 = result.stage4
    pf_result = stage4.pathfinding_result

    print(f"Total Nets: {len(pf_result.routed_paths) + len(pf_result.failed_nets)}")
    print(f"Routed: {len(pf_result.routed_paths)}")
    print(f"Failed: {len(pf_result.failed_nets)}")

    if pf_result.failed_nets:
        print("\nFailed Nets Details:")
        for net_name in pf_result.failed_nets:
            print(f"- {net_name}")
            if net_name in pf_result.failure_reports:
                report = pf_result.failure_reports[net_name]
                print(f"  Reason: {report.failure_reason}")
                if report.blocking_nets:
                    print(f"  Blockers: {report.blocking_nets}")
                if report.congestion_region:
                    print(f"  Region: {report.congestion_region}")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    diagnose()
