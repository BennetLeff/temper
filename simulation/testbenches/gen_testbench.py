"""
SPICE testbench generator from templates.
"""

from __future__ import annotations

import argparse
from pathlib import Path

TESTBENCH_TEMPLATES = Path(__file__).parent / "templates"


def generate_testbench(
    test_name: str,
    task_id: str,
    purpose: str,
    title: str,
    component_lib: str | list[str],
    circuit_definition: str,
    analysis: str,
    control_commands: str,
    outputs: list[str] | None = None,
    measurements: list[str] | None = None,
    output_path: Path | None = None,
) -> str:
    """Generate SPICE testbench from templates."""
    content = []

    # 1. Header
    header_template = (TESTBENCH_TEMPLATES / "template_header.spice").read_text()
    
    libs = [component_lib] if isinstance(component_lib, str) else component_lib
    lib_includes = "\n".join([f".INCLUDE {lib}" for lib in libs])
    
    content.append(
        header_template.format(
            test_name=test_name,
            task_id=task_id,
            purpose=purpose,
            title=title,
            component_library=lib_includes,
        )
    )

    # 2. Options (standardized)
    content.append(".INCLUDE common_options.spice\n")

    # 3. Circuit Definition
    content.append("*------------------------------------------------------------------------------")
    content.append("* Circuit Definition")
    content.append("*------------------------------------------------------------------------------")
    content.append(circuit_definition)
    content.append("")

    # 4. Analysis
    content.append("*------------------------------------------------------------------------------")
    content.append("* Analysis")
    content.append("*------------------------------------------------------------------------------")
    content.append(analysis)
    content.append("")

    # 5. Control block
    control_template = (TESTBENCH_TEMPLATES / "template_control.spice").read_text()
    
    meas_str = "\n".join(measurements) if measurements else ""
    out_str = " ".join(outputs) if outputs else ""
    
    content.append(
        control_template.format(
            analysis_commands=control_commands,
            outputs=out_str,
            measurements=meas_str,
        )
    )

    # 6. Trailer
    content.append(".END\n")

    final_text = "\n".join(content)
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_text)
        print(f"✓ Generated testbench: {output_path}")
        
    return final_text


def main():
    parser = argparse.ArgumentParser(description="Generate SPICE testbenches from templates.")
    parser.add_argument("--name", required=True, help="Test circuit name")
    parser.add_argument("--task", default="general", help="Task ID")
    parser.add_argument("--purpose", required=True, help="Purpose of the test")
    parser.add_argument("--title", required=True, help="SPICE .TITLE field")
    parser.add_argument("--lib", required=True, help="Path to component library")
    parser.add_argument("--output", required=True, type=Path, help="Output file path")
    
    args = parser.parse_args()
    
    generate_testbench(
        test_name=args.name,
        task_id=args.task,
        purpose=args.purpose,
        title=args.title,
        component_lib=args.lib,
        circuit_definition="* [Custom circuit components go here]",
        analysis=".op",
        control_commands="run",
        outputs=["v(1)"],
        measurements=["meas op v1_val FIND v(1) AT=0"],
        output_path=args.output
    )


if __name__ == "__main__":
    main()
