"""JSON serialization for decision traces.

This module provides functions to save and load DecisionTrace objects as JSON,
enabling persistent storage, analysis, and sharing of placement decision history.

Example:
    >>> from temper_placer.explainability.decision import DecisionTrace, Decision
    >>> from temper_placer.explainability.serialization import save_trace, load_trace
    >>>
    >>> trace = DecisionTrace()
    >>> trace.add(Decision(subject='Q1', value=(10, 20), reason='Initial'))
    >>>
    >>> save_trace(trace, Path('decisions.json'))
    >>> loaded = load_trace(Path('decisions.json'))
    >>> assert loaded.run_id == trace.run_id
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)


def _serialize_value(value: Any) -> Any:
    """Handle special types (numpy arrays, tuples, JAX arrays, etc).

    Args:
        value: Any value that needs to be serialized

    Returns:
        JSON-serializable version of the value
    """
    if value is None:
        return None
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "tolist"):  # numpy/jax array
        return value.tolist()
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _deserialize_value(value: Any, as_tuple: bool = False) -> Any:
    """Convert JSON values back to appropriate Python types.

    Args:
        value: JSON value to deserialize
        as_tuple: If True, convert lists to tuples (for positions)

    Returns:
        Deserialized Python value
    """
    if value is None:
        return None
    if isinstance(value, list) and as_tuple:
        return tuple(value)
    return value


def serialize_alternative(alt: Alternative) -> dict[str, Any]:
    """Convert Alternative to JSON-serializable dict.

    Args:
        alt: Alternative to serialize

    Returns:
        JSON-serializable dictionary
    """
    return {
        "value": _serialize_value(alt.value),
        "rejection_reason": alt.rejection_reason,
        "constraint_violated": alt.constraint_violated,
        "loss_if_chosen": alt.loss_if_chosen,
    }


def deserialize_alternative(data: dict[str, Any]) -> Alternative:
    """Convert JSON dict back to Alternative.

    Args:
        data: JSON dictionary

    Returns:
        Alternative instance
    """
    return Alternative(
        value=_deserialize_value(data.get("value")),
        rejection_reason=data.get("rejection_reason", ""),
        constraint_violated=data.get("constraint_violated"),
        loss_if_chosen=data.get("loss_if_chosen"),
    )


def serialize_decision(decision: Decision) -> dict[str, Any]:
    """Convert Decision to JSON-serializable dict.

    Args:
        decision: Decision to serialize

    Returns:
        JSON-serializable dictionary
    """
    return {
        "id": decision.id,
        "timestamp": decision.timestamp.isoformat(),
        "phase": decision.phase.value,
        "decision_type": decision.decision_type.value,
        "subject": decision.subject,
        "value": _serialize_value(decision.value),
        "previous_value": _serialize_value(decision.previous_value),
        "reason": decision.reason,
        "constraint_refs": decision.constraint_refs,
        "loss_contribution": decision.loss_contribution,
        "alternatives": [serialize_alternative(alt) for alt in decision.alternatives],
        "epoch": decision.epoch,
        "iteration": decision.iteration,
    }


def deserialize_decision(data: dict[str, Any]) -> Decision:
    """Convert JSON dict back to Decision.

    Args:
        data: JSON dictionary

    Returns:
        Decision instance
    """
    # Parse phase enum
    phase_str = data.get("phase", "geometric")
    try:
        phase = DecisionPhase(phase_str)
    except ValueError:
        phase = DecisionPhase.GEOMETRIC

    # Parse decision type enum
    dtype_str = data.get("decision_type", "position_update")
    try:
        dtype = DecisionType(dtype_str)
    except ValueError:
        dtype = DecisionType.POSITION_UPDATE

    # Parse timestamp
    timestamp_str = data.get("timestamp")
    if timestamp_str:
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()
    else:
        timestamp = datetime.now()

    # Parse alternatives
    alternatives = [deserialize_alternative(alt) for alt in data.get("alternatives", [])]

    return Decision(
        id=data.get("id", ""),
        timestamp=timestamp,
        phase=phase,
        decision_type=dtype,
        subject=data.get("subject", ""),
        value=_deserialize_value(data.get("value")),
        previous_value=_deserialize_value(data.get("previous_value")),
        reason=data.get("reason", ""),
        constraint_refs=data.get("constraint_refs", []),
        loss_contribution=data.get("loss_contribution", 0.0),
        alternatives=alternatives,
        epoch=data.get("epoch"),
        iteration=data.get("iteration"),
    )


def serialize_trace(trace: DecisionTrace) -> dict[str, Any]:
    """Convert DecisionTrace to JSON-serializable dict.

    Args:
        trace: DecisionTrace to serialize

    Returns:
        JSON-serializable dictionary with all trace data
    """
    return {
        "run_id": trace.run_id,
        "start_time": trace.start_time.isoformat(),
        "end_time": trace.end_time.isoformat() if trace.end_time else None,
        "config_snapshot": trace.config_snapshot,
        "decisions": [serialize_decision(d) for d in trace.decisions],
        "final_positions": {k: list(v) for k, v in trace.final_positions.items()},
        "final_metrics": trace.final_metrics,
    }


def deserialize_trace(data: dict[str, Any]) -> DecisionTrace:
    """Convert JSON dict back to DecisionTrace.

    Args:
        data: JSON dictionary

    Returns:
        DecisionTrace instance with all decisions restored
    """
    # Parse start time
    start_time_str = data.get("start_time")
    if start_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str)
        except ValueError:
            start_time = datetime.now()
    else:
        start_time = datetime.now()

    # Parse end time
    end_time = None
    end_time_str = data.get("end_time")
    if end_time_str:
        try:
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError:
            pass

    # Parse final positions (convert lists to tuples)
    final_positions: dict[str, tuple[float, float]] = {}
    for k, v in data.get("final_positions", {}).items():
        if isinstance(v, list) and len(v) >= 2:
            final_positions[k] = (float(v[0]), float(v[1]))

    # Create trace with basic attributes
    trace = DecisionTrace(
        run_id=data.get("run_id", ""),
        start_time=start_time,
        end_time=end_time,
        config_snapshot=data.get("config_snapshot", {}),
        final_positions=final_positions,
        final_metrics=data.get("final_metrics", {}),
    )

    # Add all decisions
    for d in data.get("decisions", []):
        trace.add(deserialize_decision(d))

    return trace


def save_trace(trace: DecisionTrace, path: Path | str) -> None:
    """Save trace to JSON file.

    Args:
        trace: DecisionTrace to save
        path: Path to output file

    Raises:
        IOError: If file cannot be written
    """
    path = Path(path)
    with open(path, "w") as f:
        json.dump(serialize_trace(trace), f, indent=2)


def load_trace(path: Path | str) -> DecisionTrace:
    """Load trace from JSON file.

    Args:
        path: Path to JSON file

    Returns:
        Loaded DecisionTrace instance

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)
    return deserialize_trace(data)


def trace_to_json(trace: DecisionTrace, indent: int | None = 2) -> str:
    """Serialize trace to JSON string.

    Args:
        trace: DecisionTrace to serialize
        indent: JSON indentation (None for compact)

    Returns:
        JSON string representation
    """
    return json.dumps(serialize_trace(trace), indent=indent)


def trace_from_json(json_str: str) -> DecisionTrace:
    """Deserialize trace from JSON string.

    Args:
        json_str: JSON string

    Returns:
        DecisionTrace instance
    """
    data = json.loads(json_str)
    return deserialize_trace(data)
