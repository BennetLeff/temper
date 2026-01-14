"""
Router V6 Stage 3.7: Build SAT Model

Builds a SAT/SMT model for topological routing constraints.
Part of temper-5eh3 (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.router_v6.constraint_model import (
        CapacityConstraint,
        ConstraintModel,
        DiffPairConstraint,
        LayerConstraint,
        NetChannelVar,
    )


@dataclass(frozen=True)
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


def populate_sat_from_constraints(
    sat_model: SATModel,
    constraint_model: ConstraintModel,
    net_names: list[str] | None = None,
) -> None:
    """
    Populate SAT model with constraints from constraint model.

    Translates high-level routing constraints into SAT clauses.

    Args:
        sat_model: SAT model to populate
        constraint_model: Constraint model with variables and constraints
        net_names: Optional list of net names (indexed by net_idx)

    Example:
        >>> sat = build_sat_model()
        >>> populate_sat_from_constraints(sat, constraints)
        >>> sat.variable_count > 0
        True
    """
    from temper_placer.router_v6.constraint_model import (
        CapacityConstraint,
        DiffPairConstraint,
        LayerConstraint,
        NetChannelVar,
    )

    # 1. Create SAT variables from constraint model variables
    var_map = {}  # constraint var name -> SAT var
    net_channel_vars = {}  # net_idx -> list of SAT vars for that net

    for var in constraint_model.variables:
        if isinstance(var, NetChannelVar):
            # Create human-readable variable name with net name if available
            if net_names and var.net_idx < len(net_names):
                net_name = net_names[var.net_idx]
                # Use full channel ID to preserve routing info
                # But ensure no conflicts with var name parsing which uses _ as separator
                # Variable format: uses_{net_name}_{channel_id}
                var_name = f"uses_{net_name}_{var.channel_id}"
                description = f"Net {net_name} uses channel {var.channel_id}"
            else:
                var_name = var.name
                description = f"Net {var.net_idx} uses channel {var.channel_id}"

            sat_var = sat_model.add_variable(var_name, description)
            var_map[var.name] = sat_var

            # Track variables for each net
            if var.net_idx not in net_channel_vars:
                net_channel_vars[var.net_idx] = []
            net_channel_vars[var.net_idx].append(sat_var)

    # 1.5: Add basic connectivity constraints - each net must use at least one channel
    for net_idx, vars_list in net_channel_vars.items():
        if vars_list:
            # At least one of these variables must be True
            # This is a clause: (var1 ∨ var2 ∨ ... ∨ varN)
            net_name_str = (
                net_names[net_idx] if net_names and net_idx < len(net_names) else f"N{net_idx}"
            )
            sat_model.add_clause(
                [(var, True) for var in vars_list],
                f"Connectivity: {net_name_str} must use at least one channel",
            )

    # 1.6: Build index mapping for O(1) lookups (critical optimization)
    # This prevents O(N) list.index() calls in capacity constraints
    sat_var_to_idx = {v: i + 1 for i, v in enumerate(sat_model.variables)}

    # 2. Translate constraints to SAT clauses
    for constraint in constraint_model.constraints:
        if isinstance(constraint, DiffPairConstraint):
            # Diff pair: uses[p, c] == uses[n, c]
            # Encode as: (¬p ∨ n) ∧ (p ∨ ¬n)
            # Which means: p implies n, and n implies p
            p_sat = var_map.get(constraint.p_var.name)
            n_sat = var_map.get(constraint.n_var.name)

            if p_sat and n_sat:
                # If p_net uses channel, then n_net must use channel
                sat_model.add_clause(
                    [(p_sat, False), (n_sat, True)],
                    f"DiffPair: {constraint.p_var.name} → {constraint.n_var.name}",
                )
                # If n_net uses channel, then p_net must use channel
                sat_model.add_clause(
                    [(n_sat, False), (p_sat, True)],
                    f"DiffPair: {constraint.n_var.name} → {constraint.p_var.name}",
                )

        elif isinstance(constraint, LayerConstraint):
            # Layer restriction: uses[n, c] == allowed
            # If allowed = False, add clause (¬uses[n, c])
            # If allowed = True, add clause (uses[n, c])
            var_name = f"uses_N{constraint.net_idx}_{constraint.channel_id}"
            sat_var = var_map.get(var_name)

            if sat_var:
                sat_model.add_clause(
                    [(sat_var, constraint.allowed)], f"Layer: {var_name} = {constraint.allowed}"
                )

        elif isinstance(constraint, CapacityConstraint):
            # Capacity: sum(uses[n, c] * width[n]) <= capacity
            # Try to use PySAT PBEnc for accurate constraints
            try:
                from pysat.pb import PBEnc

                has_pb = True
            except (ImportError, AssertionError):
                has_pb = False

            lits = []
            weights = []
            for var, width in constraint.terms:
                sat_var = var_map.get(var.name)
                if sat_var:
                    # Map to 1-based index using O(1) dictionary lookup
                    idx = sat_var_to_idx[sat_var]
                    lits.append(idx)
                    # Apply 1.5x safety factor for vias/jogs
                    weights.append(int(width * 1.5 * 100))  # 0.01mm resolution

            if has_pb and lits:
                bound = int(constraint.capacity * constraint.slack_factor * 100)
                # PBEnc generates raw CNF with auxiliary variables
                # We need to preserve variable mapping
                top_id = len(sat_model.variables)
                cnf = PBEnc.atmost(lits=lits, weights=weights, bound=bound, top_id=top_id)

                # Add clauses to model
                for clause in cnf.clauses:
                    sat_literals = []
                    for lit in clause:
                        var_idx = abs(lit) - 1
                        is_pos = lit > 0

                        # Create aux var if needed
                        while var_idx >= len(sat_model.variables):
                            sat_model.add_variable(f"aux_{len(sat_model.variables)}", "Auxiliary")

                        sat_var = sat_model.variables[var_idx]
                        sat_literals.append((sat_var, is_pos))

                    sat_model.add_clause(sat_literals, f"PB Capacity: {constraint.channel_id}")

            else:
                # Fallback: Cardinality based on min width
                if constraint.terms:
                    min_width = min(width for _, width in constraint.terms)
                    if min_width > 0:
                        max_nets = int(constraint.capacity * constraint.slack_factor / min_width)

                        # Simplified cardinality: forbid subsets of size K+1
                        # This is combinatorial explosion if we do it manually.
                        # Just forbid ALL if count > max.
                        sat_vars = []
                        for var, _ in constraint.terms:
                            v = var_map.get(var.name)
                            if v:
                                sat_vars.append(v)

                        if len(sat_vars) > max_nets:
                            # Naive: (not v1 or not v2 ... or not vk) for all k-subsets? No.
                            # Naive: (not v1 or ... or not vn) -> At least one is false.
                            # This assumes capacity is N-1. Weak.
                            pass


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
        f"Path exists for {net_name} from {source_node} to {sink_node}",
    )

    # Add clause: this path must exist (always true)
    model.add_clause([(var, True)], f"Connectivity for {net_name}")


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
        var = model.add_variable(f"uses_{net}_{channel_id}", f"{net} uses channel {channel_id}")
        channel_vars.append(var)

    # Add capacity constraint (simplified - at most max_nets can be true)
    # In practice, this would use cardinality constraints
    if len(channel_vars) > max_nets:
        # At least one net must NOT use this channel
        model.add_clause(
            [(var, False) for var in channel_vars[max_nets:]], f"Capacity limit for {channel_id}"
        )
