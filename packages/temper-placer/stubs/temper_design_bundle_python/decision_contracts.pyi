"""Type stubs for `temper_design_bundle_python.decision_contracts`.

Compiled from `packages/temper-design-bundle/src/decision_contracts.rs` --
the Wave C migration of `temper_placer/core/decision.py` (a separate
migration of the same original dataclass shape as `temper_orchestration`'s
own `explainability.rs` Decision/DecisionTrace/Alternative, consumed via
`temper_placer.explainability.decision` -- the two are distinct pyclasses in
distinct crates, not aliases of each other). Keep in sync with that file.
"""
from __future__ import annotations
from typing import Any

class Alternative:
    value: Any
    rejection_reason: Any
    constraint_violated: Any
    loss_if_chosen: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def to_dict(self) -> dict[str, Any]: ...

class Decision:
    id: Any
    subject: Any
    value: Any
    timestamp: Any
    phase: Any
    decision_type: Any
    reason: Any
    constraint_refs: Any
    loss_contribution: Any
    alternatives_considered: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class DecisionTrace:
    run_id: Any
    start_time: Any
    end_time: Any
    decisions: Any
    final_metrics: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def add_decision(self, decision: Decision) -> None: ...
    def query(self, subject: Any) -> list[Any]: ...
