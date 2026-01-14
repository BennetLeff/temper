import json
import sys
from pathlib import Path
from temper_placer.deterministic.feedback.drc_runner import run_drc_check


def main():
    pcb_path = "pcb/temper_router_v6_output.kicad_pcb"
    output_dir = "drc_results"

    if not Path(pcb_path).exists():
        print(f"Error: {pcb_path} not found")
        sys.exit(1)

    print(f"Running DRC on {pcb_path}...")
    try:
        report_path = run_drc_check(pcb_path, output_dir)
        print(f"Report generated: {report_path}")

        with open(report_path) as f:
            data = json.load(f)

        violations = data.get("violations", [])
        unconnected = data.get("unconnected_items", [])

        print(f"\nDRC SUMMARY")
        print(f"===========")
        print(f"Total Violations: {len(violations)}")
        print(f"Unconnected Items: {len(unconnected)}")

        if violations:
            print("\nViolation Types:")
            from collections import Counter

            counts = Counter(v.get("description", "Unknown") for v in violations)
            for desc, count in counts.most_common():
                print(f"  {desc}: {count}")

    except Exception as e:
        print(f"DRC Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
