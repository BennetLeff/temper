import temper_ipc as _tipc


def estimate_trace_current(
    width_mm: float,
    thickness_oz: float = 1.0,
    temp_rise_c: float = 10.0,
    internal_layer: bool = False,
) -> float:
    return _tipc.estimate_trace_current(width_mm, thickness_oz, temp_rise_c, internal_layer)


def estimate_current_from_net_class(
    trace_width_mm: float,
    thickness_oz: float = 1.0,
    temp_rise_c: float = 10.0,
) -> float:
    return _tipc.estimate_current_from_net_class(trace_width_mm, thickness_oz, temp_rise_c)

TRACE_CURRENT_TABLE_1OZ = {
    0.15: 0.7, 0.2: 1.0, 0.25: 1.2, 0.4: 2.0, 0.5: 2.5,
    1.0: 5.0, 2.0: 9.5, 3.0: 14.0, 5.0: 22.0, 10.0: 42.0,
}
