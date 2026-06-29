"""Report generator using Jinja2 templates."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

__all__ = ["ReportGenerator"]


class ReportGenerator:
    """Generates reports from Jinja2 templates."""

    def __init__(self, template_dir: Path | None = None):
        """
        Initialize the report generator.

        Args:
            template_dir: Path to directory containing templates.
                          Defaults to packages/temper-validation/templates.
        """
        if template_dir is None:
            # Assumes templates are in packages/temper-validation/templates/
            # relative to this file: src/temper_validation/reporting/generator.py
            # So: ../../../../templates
            # But nicer to find it relative to package root if installed.
            # For development, let's look relative to source root.
            # Or assume it's bundled with the package data?
            # For now, let's try to find it relative to the file location, assuming standard layout.
            current_file = Path(__file__).resolve()
            # Go up to packages/temper-validation/
            # src/temper_validation/reporting/generator.py -> src/temper_validation/reporting -> src/temper_validation -> src -> temper-validation
            package_root = current_file.parents[3]
            template_dir = package_root / "templates"

        if not template_dir.exists():
             # Fallback for installed package scenario where templates might be in package data
             # For now, just logging or relying on user to provide path might be safer if structure differs.
             # But let's assume the dev structure for now as per instructions.
             pass

        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    def generate(
        self,
        template_name: str,
        output_path: Path,
        **context: Any
    ) -> None:
        """
        Generate a report from a template.

        Args:
            template_name: Name of the template file (e.g., 'report.md.j2')
            output_path: Path where the generated report should be saved
            **context: Variables to pass to the template
        """
        template = self.env.get_template(template_name)
        content = template.render(**context)
        output_path.write_text(content, encoding="utf-8")
