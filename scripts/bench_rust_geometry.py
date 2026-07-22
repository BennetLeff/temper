#!/usr/bin/env python3
"""Benchmark Rust-backed geometry functions vs pure-Python equivalents."""
import math
import time
import statistics
import temper_geometry as _tg

# Synthetic test data
P1 = (3.0, 4.0)
P2 = (7.0, 10.0)
SQUARE = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
A_VAL, B_VAL, ALPHA = 3.0, 7.0, 10.0
PX, PY, CX, CY, R = 5.0, 8.0, 2.0, 3.0, 4.0
RP_X, RP_Y, RP_ANGLE = 1.0, 0.0, 1.5707963267948966  # pi/2 rad


# ---- Pure-Python implementations ----

def _py_point_distance(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx * dx + dy * dy + 1e-12)


def _py_polygon_area(vertices):
    n = len(vertices) // 2
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        x_i, y_i = vertices[2 * i], vertices[2 * i + 1]
        x_j, y_j = vertices[2 * j], vertices[2 * j + 1]
        area += x_i * y_j - x_j * y_i
    return abs(area) * 0.5


def _py_smooth_max(a, b, alpha):
    c = max(a, b)
    return c + math.log(math.exp(alpha * (a - c)) + math.exp(alpha * (b - c))) / alpha


def _py_sdf_circle(px, py, cx, cy, r):
    dx = px - cx
    dy = py - cy
    return math.sqrt(dx * dx + dy * dy) - r


def _py_rotate_point(x, y, angle_rad, cx=0.0, cy=0.0):
    dx = x - cx
    dy = y - cy
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)


# ---- Benchmark harness ----

ITERS = 10_000
WARMUP = 1_000

BENCHMARKS = [
    ("point_distance", lambda: _py_point_distance(*P1, *P2),
                       lambda: _tg.point_distance(*P1, *P2)),
    ("polygon_area",   lambda: _py_polygon_area(SQUARE),
                       lambda: _tg.polygon_area(SQUARE)),
    ("smooth_max",     lambda: _py_smooth_max(A_VAL, B_VAL, ALPHA),
                       lambda: _tg.smooth_max(A_VAL, B_VAL, ALPHA)),
    ("sdf_circle",     lambda: _py_sdf_circle(PX, PY, CX, CY, R),
                       lambda: _tg.sdf_circle(PX, PY, CX, CY, R)),
    ("rotate_point",   lambda: _py_rotate_point(RP_X, RP_Y, RP_ANGLE),
                       lambda: _tg.rotate_point(RP_X, RP_Y, RP_ANGLE)),
]


def measure(name, py_fn, rs_fn):
    for _ in range(WARMUP):
        py_fn()
        rs_fn()

    py_times = []
    for _ in range(ITERS):
        t0 = time.perf_counter()
        py_fn()
        py_times.append(time.perf_counter() - t0)

    rs_times = []
    for _ in range(ITERS):
        t0 = time.perf_counter()
        rs_fn()
        rs_times.append(time.perf_counter() - t0)

    py_total = sum(py_times)
    rs_total = sum(rs_times)
    speedup = py_total / rs_total if rs_total > 0 else float("inf")
    return py_total, rs_total, speedup


def main():
    results = []
    for name, py_fn, rs_fn in BENCHMARKS:
        py_ms, rs_ms, speedup = measure(name, py_fn, rs_fn)
        results.append((name, py_ms * 1000, rs_ms * 1000, speedup))

    # Print table
    print(f"\n{'function':<18} {'Python (ms)':>12} {'Rust (ms)':>12} {'speedup':>10}")
    print("-" * 54)
    for name, py_ms, rs_ms, speedup in results:
        print(f"{name:<18} {py_ms:>10.3f}  {rs_ms:>10.3f}  {speedup:>8.1f}x")
    print()

    # Verify numerical agreement
    print("Numerical verification (max absolute error):")
    checks = [
        ("point_distance", _py_point_distance(*P1, *P2), _tg.point_distance(*P1, *P2)),
        ("polygon_area",   _py_polygon_area(SQUARE),     _tg.polygon_area(SQUARE)),
        ("smooth_max",     _py_smooth_max(A_VAL, B_VAL, ALPHA),
                          _tg.smooth_max(A_VAL, B_VAL, ALPHA)),
        ("sdf_circle",     _py_sdf_circle(PX, PY, CX, CY, R),
                          _tg.sdf_circle(PX, PY, CX, CY, R)),
        ("rotate_point",   _py_rotate_point(RP_X, RP_Y, RP_ANGLE),
                          _tg.rotate_point(RP_X, RP_Y, RP_ANGLE)),
    ]
    for name, py_val, rs_val in checks:
        if isinstance(py_val, tuple):
            err = max(abs(a - b) for a, b in zip(py_val, rs_val))
        else:
            err = abs(py_val - rs_val)
        print(f"  {name:<18} py={py_val!r}  rs={rs_val!r}  err={err:.2e}")
    print()


if __name__ == "__main__":
    main()
