from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


class TemplateManager:
    """Manages loading and composition of domain-specific templates."""

    def __init__(self, template_dir: Path | None = None):
        self.template_dir = template_dir or Path(__file__).parent
        self.templates: dict[str, Any] = {}

    def load_all(self) -> None:
        """Load all templates in the directory."""
        for yaml_file in self.template_dir.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                self.templates[yaml_file.stem] = data

    def get_template(self, name: str) -> Any | None:
        """Get a specific template by name."""
        return self.templates.get(name)

    def compose(self, names: list[str]) -> dict[str, Any]:
        """Compose multiple templates into a single design specification."""
        composed: dict[str, Any] = {
            "components": {},
            "loops": {},
            "constraints": [],
            "zones": {},
            "guidelines": []
        }

        visited = set()

        def _compose_recursive(name_list):
            for name in name_list:
                if name in visited:
                    continue
                visited.add(name)

                tpl = self.get_template(name)
                if not tpl:
                    continue

                # Handle base templates first
                if "extends" in tpl:
                    _compose_recursive(tpl["extends"])

                # Merge components
                composed["components"].update(tpl.get("components", {}))
                # Merge loops
                composed["loops"].update(tpl.get("loops", {}))
                # Append constraints
                composed["constraints"].extend(tpl.get("constraints", []))
                # Merge zones
                composed["zones"].update(tpl.get("zones", {}))
                # Append guidelines
                composed["guidelines"].extend(tpl.get("guidelines", []))

        _compose_recursive(names)
        return composed
