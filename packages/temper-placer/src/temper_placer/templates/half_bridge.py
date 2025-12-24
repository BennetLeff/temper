from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from temper_placer.core.loop import Loop
    from temper_placer.core.netlist import Netlist

@dataclass
class ComponentRole:
    name: str
    type: str
    ref_pattern: str
    thermal: str | None = None

@dataclass
class LoopDefinition:
    name: str
    type: str
    path: list[str]
    max_area_mm2: float
    priority: str

@dataclass
class HalfBridgeTemplate:
    """Loaded half-bridge template."""
    name: str
    components: dict[str, ComponentRole]
    loops: dict[str, LoopDefinition]
    constraints: list[dict]
    zones: dict[str, dict]
    guidelines: list[str]

    @classmethod
    def load(cls, path: Path | None = None) -> HalfBridgeTemplate:
        """Load half-bridge template from YAML."""
        if path is None:
            path = Path(__file__).parent / "half_bridge.yaml"

        with open(path) as f:
            data = yaml.safe_load(f)

        components = {
            name: ComponentRole(
                name=name,
                type=comp["type"],
                ref_pattern=comp["ref_pattern"],
                thermal=comp.get("thermal")
            )
            for name, comp in data.get("components", {}).items()
        }

        loops = {
            name: LoopDefinition(
                name=name,
                type=loop["type"],
                path=loop["path"],
                max_area_mm2=loop["max_area_mm2"],
                priority=loop["priority"]
            )
            for name, loop in data.get("loops", {}).items()
        }

        return cls(
            name=data.get("name", "half_bridge"),
            components=components,
            loops=loops,
            constraints=data.get("constraints", []),
            zones=data.get("zones", {}),
            guidelines=data.get("guidelines", [])
        )

    def match_components(self, netlist: Netlist) -> dict[str, str]:
        """Match netlist components to template roles."""

        matches = {}
        for role_name, role in self.components.items():
            pattern = re.compile(role.ref_pattern)
            for comp in netlist.components:
                if pattern.match(comp.ref):
                    matches[role_name] = comp.ref
                    break

        return matches

    def generate_constraints(self, component_map: dict[str, str]) -> list[dict]:
        """Generate PCL constraints with actual component refs."""
        constraints = []

        for c in self.constraints:
            new_c = c.copy()
            # Replace placeholder names with actual refs
            if "a" in new_c and new_c["a"] in component_map:
                new_c["a"] = component_map[new_c["a"]]
            if "b" in new_c and new_c["b"] in component_map:
                new_c["b"] = component_map[new_c["b"]]
            if "inner" in new_c:
                new_c["inner"] = [
                    component_map.get(ref, ref) for ref in new_c["inner"]
                ]
            constraints.append(new_c)

        return constraints

    def generate_loops(self, component_map: dict[str, str]) -> list[Loop]:
        """Generate Loop objects with actual component refs."""
        from temper_placer.core.loop import Loop
        result = []
        for name, loop_def in self.loops.items():
            # Substitute component references in path
            path = []
            for step in loop_def.path:
                if "." in step:
                    comp_role, pin = step.split(".")
                    if comp_role in component_map:
                        path.append(f"{component_map[comp_role]}.{pin}")
                    else:
                        path.append(step)
                else:
                    path.append(step)

            loop = Loop(
                name=loop_def.name,
                type=loop_def.type,
                # Note: Loop implementation might need more parsing
                # This is a simplification
                priority=loop_def.priority,
                max_area_mm2=loop_def.max_area_mm2
            )
            result.append(loop)

        return result
