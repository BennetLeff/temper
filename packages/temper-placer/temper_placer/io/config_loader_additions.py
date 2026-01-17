# Add this before "return constraints" line in load_constraints():

    # Parse placement_priority (priority-based placement)
    if "placement_priority" in config:
        constraints.placement_priority = config["placement_priority"]
    
    # Parse routing_priority (priority-based routing)
    if "routing_priority" in config:
        constraints.routing_priority = config["routing_priority"]
