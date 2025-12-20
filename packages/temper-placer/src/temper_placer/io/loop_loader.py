"""
Loop definition loader for YAML-based loop templates.

This module provides functions to load loop definitions from YAML files,
supporting both individual loop templates and collections of loops.

Example usage:
    >>> from temper_placer.io.loop_loader import load_loop_template, load_loop_collection
    >>>
    >>> # Load a single loop template
    >>> loop = load_loop_template("configs/templates/loops/commutation.yaml")
    >>> print(loop.name, loop.priority)
    commutation LoopPriority.CRITICAL
    >>>
    >>> # Load all loops in a directory
    >>> collection = load_loop_collection("configs/templates/loops/")
    >>> print(len(collection))
    5
"""

from pathlib import Path
from typing import Any

import yaml

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)


class LoopLoadError(Exception):
    """Error loading a loop definition."""

    pass


def _parse_events(events_data: dict[str, Any] | None) -> LoopEvent:
    """Parse LoopEvent from YAML data."""
    if events_data is None:
        return LoopEvent()

    return LoopEvent(
        di_dt=events_data.get("di_dt"),
        dv_dt=events_data.get("dv_dt"),
        frequency_hz=events_data.get("frequency_hz"),
        peak_current_a=events_data.get("peak_current_a"),
        rms_current_a=events_data.get("rms_current_a"),
        ringing_freq_hz=events_data.get("ringing_freq_hz"),
    )


def _parse_pins(pins_data: list[dict[str, Any]] | None) -> list[LoopPin]:
    """Parse list of LoopPin from YAML data."""
    if pins_data is None:
        return []

    pins = []
    for pin_data in pins_data:
        pins.append(
            LoopPin(
                component_ref=str(pin_data["component"]),
                pin_name=str(pin_data["pin"]),
                net_name=pin_data.get("net"),
            )
        )
    return pins


def _parse_loop_type(type_str: str) -> LoopType:
    """Parse LoopType from string, with case-insensitive matching."""
    type_str_lower = type_str.lower()
    for lt in LoopType:
        if lt.value == type_str_lower:
            return lt
    raise LoopLoadError(
        f"Unknown loop type: {type_str}. Valid types: {[t.value for t in LoopType]}"
    )


def _parse_priority(priority_str: str | None) -> LoopPriority:
    """Parse LoopPriority from string, with case-insensitive matching."""
    if priority_str is None:
        return LoopPriority.MEDIUM

    priority_lower = priority_str.lower()
    for lp in LoopPriority:
        if lp.value == priority_lower:
            return lp
    raise LoopLoadError(
        f"Unknown priority: {priority_str}. Valid priorities: {[p.value for p in LoopPriority]}"
    )


def load_loop_from_dict(data: dict[str, Any], source: str = "yaml") -> Loop:
    """Load a Loop from a dictionary (parsed YAML or JSON).

    Args:
        data: Dictionary containing loop definition.
        source: Source identifier for tracking where the loop came from.

    Returns:
        Loop object populated from the dictionary.

    Raises:
        LoopLoadError: If required fields are missing or invalid.
    """
    # Required fields
    try:
        name = data["name"]
        loop_type_str = data["loop_type"]
        description = data.get("description", "")
    except KeyError as e:
        raise LoopLoadError(f"Missing required field: {e}")

    # Parse loop type
    loop_type = _parse_loop_type(loop_type_str)

    # Parse optional fields
    pins = _parse_pins(data.get("pins"))
    components = data.get("components", [])
    nets = data.get("nets", [])
    max_area_mm2 = float(data.get("max_area_mm2", 100.0))
    priority = _parse_priority(data.get("priority"))
    events = _parse_events(data.get("events"))
    return_layer = data.get("return_layer")
    return_net = data.get("return_net")

    return Loop(
        name=name,
        loop_type=loop_type,
        description=description,
        pins=pins,
        components=components,
        nets=nets,
        max_area_mm2=max_area_mm2,
        priority=priority,
        events=events,
        return_layer=return_layer,
        return_net=return_net,
        source=source,
    )


def load_loop_template(path: str | Path) -> Loop:
    """Load a loop definition from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Loop object loaded from the file.

    Raises:
        LoopLoadError: If the file cannot be loaded or parsed.
        FileNotFoundError: If the file doesn't exist.

    Example:
        >>> loop = load_loop_template("configs/templates/loops/commutation.yaml")
        >>> loop.name
        'commutation'
        >>> loop.priority
        <LoopPriority.CRITICAL: 'critical'>
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Loop template not found: {path}")

    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise LoopLoadError(f"Invalid YAML in {path}: {e}")

    if data is None:
        raise LoopLoadError(f"Empty YAML file: {path}")

    return load_loop_from_dict(data, source=f"template:{path.name}")


def load_loop_collection(
    directory: str | Path,
    pattern: str = "*.yaml",
    name: str = "",
    description: str = "",
) -> LoopCollection:
    """Load all loop templates from a directory.

    Args:
        directory: Path to directory containing YAML loop templates.
        pattern: Glob pattern for finding template files (default: "*.yaml").
        name: Optional name for the collection.
        description: Optional description for the collection.

    Returns:
        LoopCollection containing all loaded loops.

    Raises:
        FileNotFoundError: If the directory doesn't exist.
        LoopLoadError: If any template fails to load.

    Example:
        >>> collection = load_loop_collection("configs/templates/loops/")
        >>> len(collection)
        5
        >>> collection.get_critical_loops()
        [Loop(name='commutation', ...), Loop(name='gate_drive_high', ...), ...]
    """
    directory = Path(directory)

    if not directory.exists():
        raise FileNotFoundError(f"Loop template directory not found: {directory}")

    if not directory.is_dir():
        raise LoopLoadError(f"Path is not a directory: {directory}")

    collection = LoopCollection(
        name=name or directory.name,
        description=description,
    )

    # Load all matching files
    template_files = sorted(directory.glob(pattern))

    for template_path in template_files:
        # Skip README and non-template files
        if template_path.name.lower() in ("readme.md", "readme.yaml", "readme.txt"):
            continue

        try:
            loop = load_loop_template(template_path)
            collection.add_loop(loop)
        except Exception as e:
            raise LoopLoadError(f"Failed to load {template_path}: {e}")

    return collection


def save_loop_to_yaml(loop: Loop, path: str | Path) -> None:
    """Save a Loop to a YAML file.

    Args:
        loop: Loop object to save.
        path: Output file path.

    Example:
        >>> save_loop_to_yaml(my_loop, "output/my_loop.yaml")
    """
    path = Path(path)

    # Build dictionary representation
    data: dict[str, Any] = {
        "name": loop.name,
        "loop_type": loop.loop_type.value,
        "description": loop.description,
    }

    # Components list
    if loop.components:
        data["components"] = loop.components

    # Pins (if defined)
    if loop.pins:
        data["pins"] = [
            {
                "component": pin.component_ref,
                "pin": pin.pin_name,
                **({"net": pin.net_name} if pin.net_name else {}),
            }
            for pin in loop.pins
        ]

    # Nets
    if loop.nets:
        data["nets"] = loop.nets

    # Constraints
    data["max_area_mm2"] = loop.max_area_mm2
    data["priority"] = loop.priority.value

    # Events (only include non-None values)
    events = {}
    if loop.events.di_dt is not None:
        events["di_dt"] = loop.events.di_dt
    if loop.events.dv_dt is not None:
        events["dv_dt"] = loop.events.dv_dt
    if loop.events.frequency_hz is not None:
        events["frequency_hz"] = loop.events.frequency_hz
    if loop.events.peak_current_a is not None:
        events["peak_current_a"] = loop.events.peak_current_a
    if loop.events.rms_current_a is not None:
        events["rms_current_a"] = loop.events.rms_current_a
    if loop.events.ringing_freq_hz is not None:
        events["ringing_freq_hz"] = loop.events.ringing_freq_hz
    if events:
        data["events"] = events

    # Return path info
    if loop.return_layer:
        data["return_layer"] = loop.return_layer
    if loop.return_net:
        data["return_net"] = loop.return_net

    # Write to file
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
