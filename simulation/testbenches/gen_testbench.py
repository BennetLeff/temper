#!/usr/bin/env python3
"""SPICE testbench generator - eliminates boilerplate duplication."""

from pathlib import Path
from argparse import ArgumentParser

TEMPLATES = Path(__file__).parent / "templates"

def load(name: str) -> str:
    return (TEMPLATES / f"template_{name}.spice").read_text()

def generate(
    test_name: str,
    task_id: str,
    purpose: str,
    title: str,
    component_lib: str,
    sections: list[str],
    analysis_commands: str,
    outputs: str,
    measurements: str,
) -> str:
    return "".join([
        load("header").format(
            test_name=test_name,
            task_id=task_id,
            purpose=purpose,
            title=title,
            component_library=component_lib,
        ),
        load("options"),
        *sections,
        load("control").format(
            analysis_commands=analysis_commands,
            outputs=outputs,
            measurements=measurements,
        ),
    ])

def main() -> None:
    p = ArgumentParser(description="Generate SPICE testbenches from templates")
    p.add_argument("--test-name", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--purpose", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--component-lib", required=True)
    p.add_argument("--sections", nargs="+", default=[])
    p.add_argument("--analysis", default="run")
    p.add_argument("--outputs", default="")
    p.add_argument("--measurements", default="")
    p.add_argument("-o", "--output", required=True)
    args = p.parse_args()

    Path(args.output).write_text(generate(
        test_name=args.test_name,
        task_id=args.task_id,
        purpose=args.purpose,
        title=args.title,
        component_lib=args.component_lib,
        sections=args.sections,
        analysis_commands=args.analysis,
        outputs=args.outputs,
        measurements=args.measurements,
    ))
    print(f"Generated: {args.output}")

if __name__ == "__main__":
    main()
