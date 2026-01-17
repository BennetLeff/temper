"""
Footprint library for PCB component bounds and properties.

This module provides a centralized footprint library that stores accurate
component bounds extracted from KiCad footprint files. This ensures consistent
and accurate component sizing across all tests and optimizations.

Implements temper-1my.1.2: Footprint Library for Temper Components
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class FootprintSpec:
    """
    Specification for a PCB footprint.

    Attributes:
        name: Footprint name (e.g., "TO-247-3", "0805").
        bounds: (width, height) bounding box in mm.
        courtyard_margin: Additional margin for courtyard in mm.
        thermal_pad: True if footprint has an exposed thermal pad.
        pin_1_offset: Optional (x, y) offset of pin 1 from component center.
    """

    name: str
    bounds: tuple[float, float]
    courtyard_margin: float = 0.0
    thermal_pad: bool = False
    pin_1_offset: tuple[float, float] | None = None

    @property
    def width(self) -> float:
        """Footprint width in mm."""
        return self.bounds[0]

    @property
    def height(self) -> float:
        """Footprint height in mm."""
        return self.bounds[1]

    def __repr__(self) -> str:
        return (
            f"FootprintSpec({self.name!r}, bounds={self.bounds}, "
            f"thermal_pad={self.thermal_pad})"
        )


class FootprintLibrary:
    """
    Library of footprint specifications.

    Provides a centralized registry of component footprints with accurate
    bounds and properties. Footprints can be loaded from YAML files.

    Example:
        >>> lib = load_footprint_library("footprints.yaml")
        >>> spec = lib["TO-247-3"]
        >>> print(spec.bounds)
        (16.0, 21.0)
    """

    def __init__(self):
        """Initialize an empty footprint library."""
        self.footprints: dict[str, FootprintSpec] = {}

    def add(self, spec: FootprintSpec) -> None:
        """
        Add a footprint specification to the library.

        Args:
            spec: FootprintSpec to add.
        """
        self.footprints[spec.name] = spec

    def get(
        self,
        name: str,
        default: FootprintSpec | None = None,
    ) -> FootprintSpec:
        """
        Get a footprint specification by name.

        Args:
            name: Footprint name.
            default: Optional default value if not found.

        Returns:
            FootprintSpec for the given name.

        Raises:
            KeyError: If footprint not found and no default provided.
        """
        if name in self.footprints:
            return self.footprints[name]
        elif default is not None:
            return default
        else:
            raise KeyError(f"Footprint not found: {name}")

    def __contains__(self, name: str) -> bool:
        """Check if footprint exists in library."""
        return name in self.footprints

    def __getitem__(self, name: str) -> FootprintSpec:
        """Get footprint by name (dict-like access)."""
        return self.get(name)

    def __len__(self) -> int:
        """Number of footprints in library."""
        return len(self.footprints)

    @classmethod
    def from_yaml_string(cls, yaml_content: str) -> FootprintLibrary:
        """
        Load library from YAML string.

        Args:
            yaml_content: YAML string containing footprint definitions.

        Returns:
            FootprintLibrary with loaded footprints.

        Raises:
            yaml.YAMLError: If YAML is malformed.
            ValueError: If footprint data is invalid.
        """
        lib = cls()
        data = yaml.safe_load(yaml_content)

        if not data or "footprints" not in data:
            return lib  # Empty library

        footprints_data = data["footprints"]

        for name, fp_data in footprints_data.items():
            # Validate required fields
            if "bounds" not in fp_data:
                raise ValueError(f"Footprint '{name}' missing required 'bounds' field")

            bounds = fp_data["bounds"]
            if not isinstance(bounds, list) or len(bounds) != 2:
                raise ValueError(
                    f"Footprint '{name}' has invalid bounds format. "
                    f"Expected [width, height], got {bounds}"
                )

            # Extract optional fields
            courtyard_margin = fp_data.get("courtyard_margin", 0.0)
            thermal_pad = fp_data.get("thermal_pad", False)
            pin_1_offset = fp_data.get("pin_1_offset")

            # Convert pin_1_offset from list to tuple if present
            if pin_1_offset is not None:
                if isinstance(pin_1_offset, list) and len(pin_1_offset) == 2:
                    pin_1_offset = tuple(pin_1_offset)
                else:
                    raise ValueError(
                        f"Footprint '{name}' has invalid pin_1_offset format. "
                        f"Expected [x, y], got {pin_1_offset}"
                    )

            # Create spec
            spec = FootprintSpec(
                name=name,
                bounds=tuple(bounds),
                courtyard_margin=float(courtyard_margin),
                thermal_pad=bool(thermal_pad),
                pin_1_offset=pin_1_offset,
            )

            lib.add(spec)

        return lib


def load_footprint_library(path: Path | str) -> FootprintLibrary:
    """
    Load footprint library from a YAML file.

    Args:
        path: Path to YAML file containing footprint definitions.

    Returns:
        FootprintLibrary with loaded footprints.

    Raises:
        FileNotFoundError: If file doesn't exist.
        yaml.YAMLError: If YAML is malformed.
        ValueError: If footprint data is invalid.

    Example YAML format:
        footprints:
          TO-247-3:
            bounds: [16.0, 21.0]
            courtyard_margin: 0.25
            thermal_pad: true
            pin_1_offset: [-5.08, 0]

          "0805":
            bounds: [2.0, 1.25]
            courtyard_margin: 0.15
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Footprint library not found: {path}")

    yaml_content = path.read_text()
    return FootprintLibrary.from_yaml_string(yaml_content)
