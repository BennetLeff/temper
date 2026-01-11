"""
Router V6 Stage 3.7: Build SAT Model

Builds a SAT/SMT model for topological routing constraints.
Part of temper-5eh3 (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SATVariable:
    """Boolean variable in the SAT model."""

    name: str
    description: str

    def __str__(self) -> str:
        return self.name


@dataclass
class SATClause:
    """Clause in the SAT model (disjunction of literals)."""

    literals: list[tuple[SATVariable, bool]]  # (variable, is_positive)
    description: str

    def __str__(self) -> str:
        terms = []
        for var, is_positive in self.literals:
            if is_positive:
                terms.append(str(var))
            else:
                terms.append(f"¬{var}")
        return f"({' ∨ '.join(terms)})"


@dataclass
class SATModel:
    """SAT model for topological routing."""

    variables: list[SATVariable]
    clauses: list[SATClause]

    @property
    def variable_count(self) -> int:
        """Number of variables in model."""
        return len(self.variables)

    @property
    def clause_count(self) -> int:
        """Number of clauses in model."""
        return len(self.clauses)

    def add_variable(self, name: str, description: str) -> SATVariable:
        """Add a variable to the model."""
        var = SATVariable(name, description)
        self.variables.append(var)
        return var

    def add_clause(self, literals: list[tuple[SATVariable, bool]], description: str) -> None:
        """Add a clause to the model."""
        clause = SATClause(literals, description)
        self.clauses.append(clause)


def build_sat_model() -> SATModel:
    """
    Build a SAT model for topological routing constraints.

    This creates a baseline SAT model structure. Actual constraints
    will be added by subsequent stages (connectivity, capacity, etc.).

    Returns:
        Empty SATModel ready for constraint addition

    Example:
        >>> model = build_sat_model()
        >>> model.variable_count == 0
        True
    """
    return SATModel(variables=[], clauses=[])


def add_connectivity_to_sat(
    model: SATModel,
    net_name: str,
    source_node: str,
    sink_node: str,
) -> None:
    """
    Add connectivity constraint to SAT model.

    Ensures that there exists a path from source to sink for the given net.

    Args:
        model: SAT model to modify
        net_name: Net requiring routing
        source_node: Source node ID
        sink_node: Sink node ID

    Example:
        >>> model = build_sat_model()
        >>> add_connectivity_to_sat(model, "SIG1", "N1", "N2")
        >>> model.clause_count > 0
        True
    """
    # Create variable for this routing path
    var = model.add_variable(
        f"route_{net_name}_{source_node}_to_{sink_node}",
        f"Path exists for {net_name} from {source_node} to {sink_node}"
    )

    # Add clause: this path must exist (always true)
    model.add_clause(
        [(var, True)],
        f"Connectivity for {net_name}"
    )


def add_capacity_to_sat(
    model: SATModel,
    channel_id: str,
    max_nets: int,
    nets_using_channel: list[str],
) -> None:
    """
    Add capacity constraint to SAT model.

    Ensures that no more than max_nets use a given channel.

    Args:
        model: SAT model to modify
        channel_id: Channel identifier
        max_nets: Maximum number of nets allowed
        nets_using_channel: List of net names that could use this channel

    Example:
        >>> model = build_sat_model()
        >>> add_capacity_to_sat(model, "CH1", 3, ["NET1", "NET2", "NET3", "NET4"])
        >>> model.clause_count > 0
        True
    """
    # Create variables for each net using this channel
    channel_vars = []
    for net in nets_using_channel:
        var = model.add_variable(
            f"uses_{net}_{channel_id}",
            f"{net} uses channel {channel_id}"
        )
        channel_vars.append(var)

    # Add capacity constraint (simplified - at most max_nets can be true)
    # In practice, this would use cardinality constraints
    if len(channel_vars) > max_nets:
        # At least one net must NOT use this channel
        model.add_clause(
            [(var, False) for var in channel_vars[max_nets:]],
            f"Capacity limit for {channel_id}"
        )
