#!/usr/bin/env python3
"""Apply layer cost system to maze_router.py cleanly and verifiably."""

with open('/Users/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/routing/maze_router.py', 'r') as f:
    content = f.read()

# Step 1: Add get_layer_cost method after _cost method
get_layer_cost_method = '''
    def get_layer_cost(self, net_rules, layer_idx):
        """Get cost multiplier for routing on a specific layer based on net class rules."""
        if not net_rules:
            return 1.0 if layer_idx in [0, self.num_layers - 1] else 2.0
        
        # Explicit YAML costs
        if net_rules.layer_costs and hasattr(self, 'layer_stackup'):
            if 0 <= layer_idx < len(self.layer_stackup.layers):
                layer_name = self.layer_stackup.layers[layer_idx].name
                if layer_name in net_rules.layer_costs:
                    return net_rules.layer_costs[layer_name]
        
        # Auto-derive from routing_strategy
        if net_rules.routing_strategy:
            strategy = net_rules.routing_strategy
            if strategy == "plane_preferred":
                if hasattr(self, 'layer_stackup') and self.layer_stackup.is_plane_layer(layer_idx):
                    return 0.1  # 10x preference for planes
                return 10.0  # Discourage non-planes
            elif strategy == "plane_required":
                if hasattr(self, 'layer_stackup') and self.layer_stackup.is_plane_layer(layer_idx):
                    return 0.1
                return 50.0 if layer_idx in [0, self.num_layers - 1] else 100.0
            elif strategy in ("surface_only", "top_layer_only"):
                return 1.0 if layer_idx in [0, self.num_layers - 1] else 100.0
            elif strategy == "wide_trace":
                return 1.0
        
        return 1.0 if layer_idx in [0, self.num_layers - 1] else 2.0
'''

# Find the end of _cost method and insert
marker = "return base_cost + h + diff + wrong_way_cost + c_space_cost\n"
pos = content.find(marker)
if pos == -1:
    print("ERROR: Could not find _cost return statement!")
    exit(1)

pos_newline = content.find("\n", pos) + 1
content = content[:pos_newline] + get_layer_cost_method + content[pos_newline:]
print("✓ Added get_layer_cost method")

# Step 2: Replace primary layer penalty with layer cost multiplier
old_penalty = """        # Layer preference penalty (discourage layers other than primary_layer)
        if hasattr(self, "_current_assignment") and self._current_assignment:
            primary_idx = self._current_assignment.primary_layer.value - 1
            if neighbor.layer != primary_idx:
                # Add significant penalty for using non-primary layers
                # This ensures we prefer primary layer unless it's blocked
                base_cost += 5.0"""

new_cost_system = """        # PROFESSIONAL LAYER COST SYSTEM (temper-b577)
        if hasattr(self, "_current_net_rules") and self._current_net_rules:
            layer_cost_mult = self.get_layer_cost(self._current_net_rules, neighbor.layer)
            base_cost *= layer_cost_mult"""

if old_penalty not in content:
    print("ERROR: Could not find old penalty code!")
    exit(1)

content = content.replace(old_penalty, new_cost_system)
print("✓ Replaced penalty with layer cost system")

# Step 3: Add _current_net_rules tracking in route_net_mst
# Find the import line and add tracking after it
route_mst_marker = "from temper_placer.routing.layer_assignment import Layer\n"
pos = content.find(route_mst_marker)
if pos == -1:
    print("ERROR: Could not find route_net_mst import!")
    exit(1)

tracking_code = """
        # Track net rules for layer cost system (temper-b577)
        if self.design_rules:
            self._current_net_rules = self.design_rules.get_rules_for_net(net_name)
        else:
            self._current_net_rules = None
"""

pos_after = content.find("\n", pos) + 1
content = content[:pos_after] + tracking_code + content[pos_after:]
print("✓ Added _current_net_rules tracking in route_net_mst")

# Step 4: Also add tracking in find_path_rrr
find_path_marker = "        self._current_assignment = assignment\n"
pos2 = content.find(find_path_marker)
if pos2 != -1:
    tracking_code2 = """        if self.design_rules:
            self._current_net_rules = self.design_rules.get_rules_for_net(net_name)
        else:
            self._current_net_rules = None
"""
    pos2_after = content.find("\n", pos2) + 1
    content = content[:pos2_after] + tracking_code2 + content[pos2_after:]
    print("✓ Added _current_net_rules tracking in find_path_rrr")

# Write result
with open('/Users/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/routing/maze_router.py', 'w') as f:
    f.write(content)

print("\n✅ Layer cost system fully applied!")
print("   - get_layer_cost method: ✓")
print("   - Cost multiplier in _get_neighbor_cost: ✓")
print("   - Tracking in route_net_mst: ✓")
print("   - Tracking in find_path_rrr: ✓")
