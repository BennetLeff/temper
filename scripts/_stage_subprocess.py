#!/usr/bin/env python3
"""Single-stage subprocess for the temper Rust driver (Option E).

The Rust CLI driver (`temper pipeline-run`, crates/temper-cli) owns the
pipeline loop over ``PipelineRunner<NativeBoardState>``; each stage shells
out to THIS script:

    echo '<state JSON>' | python _stage_subprocess.py --stage <name> > out.json

The script materializes the wire-JSON schema (see
``packages/temper-orchestration/src/state_ser.rs`` -- the codec both sides
agree on) into a Python ``deterministic.state.BoardState``, runs the
already-migrated Rust pyfunction ``temper_orchestration.run_<stage>``, and
serializes the mutated state back to stdout in the same schema.

Errors go to stderr with a non-zero exit code:
  2  usage error (unknown stage name)
  1  stage failure (the pyfunction raised) or a serialization violation

Opaque fields are plain JSON values on this boundary: they are decoded into
plain Python objects on input and re-encoded verbatim on output. An opaque
holding a non-JSON-native Python object (a real Board, a numpy array, ...)
is a LOUD serialization error naming the field -- never a silent drop --
mirroring the Rust codec's rule.

Extra pyfunction arguments: stages whose adapters thread constructor state
(``config_attach(config)``, ``zone_geometry(zone_config)``, ...) take it as
positional args after the state. Pass them here with repeatable ``--arg``:

    ... --arg '[[{"placer": {...}}]]'        # one JSON value per --arg
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

SCHEMA = 1


# ---------------------------------------------------------------------------
# Val canon -- the int-vs-float tags ({\"int\": i} / {\"float\": f})
# ---------------------------------------------------------------------------

def _val_to_py(v):
    if isinstance(v, dict):
        if "int" in v:
            return int(v["int"])
        if "float" in v:
            return float(v["float"])
    raise ValueError(f"expected a tagged {{\"int\": ..}}/{{\"float\": ..}}, got {v!r}")


def _val_to_json(x):
    # bool is an int subclass in CPython -- test it first.
    if isinstance(x, bool):
        raise ValueError(f"bool where an int-or-float Val was expected: {x!r}")
    if isinstance(x, int):
        return {"int": x}
    if isinstance(x, float):
        return {"float": x}
    raise ValueError(f"not an int-or-float Val: {x!r}")


def _f64_to_json(x, what):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{what}: expected a float, got {type(x).__name__}")
    f = float(x)
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"{what}: non-finite float {f} is not JSON-representable")
    return f


# ---------------------------------------------------------------------------
# Element builders -- shapes mirror netlist_owned.rs's Marshal impls 1:1
# ---------------------------------------------------------------------------

def _zone_from_json(v):
    from temper_placer.deterministic.stages.zone_geometry import Zone

    def corner(c):
        (x, y) = c
        return (_val_to_py(x), _val_to_py(y))

    ((lo), (hi)) = v["bounds"]
    return Zone(v["name"], (corner(lo), corner(hi)))


def _route_from_json(v):
    from temper_design_bundle_python import board_contracts

    Trace = board_contracts.Trace

    start, end = v["start"], v["end"]
    return Trace((start[0], start[1]), (end[0], end[1]), float(v["width"]),
                 v["layer"], v["net"])


def _via_from_json(v):
    from temper_design_bundle_python import board_contracts

    Via = board_contracts.Via

    pos = v["position"]
    l0, l1 = v["layers"]
    return Via((pos[0], pos[1]), float(v["drill"]), float(v["width"]),
               (l0, l1), v["net"], v["is_diff_pair"])


def _layer_assignment_from_json(v):
    from temper_design_bundle_python import LayerAssignment

    return LayerAssignment(v["net_name"], _val_to_py(v["layer"]),
                           v["allow_layer_change"], v["is_plane"])


def _drc_violation_from_json(v):
    from temper_placer.router_v6.constraints_drc_oracle import Violation
    from temper_placer.router_v6.constraints_geometry import Point

    loc = v["location"]
    return Violation(
        type=v["type"], geometry_a_id=v["geometry_a_id"],
        geometry_b_id=v["geometry_b_id"], net_a=v["net_a"], net_b=v["net_b"],
        clearance_actual=float(v["clearance_actual"]),
        clearance_required=float(v["clearance_required"]),
        location=Point(loc[0], loc[1]),
    )


def _connectivity_violation_from_json(v):
    from temper_placer.deterministic.stages.connectivity_validation import (
        ConnectivityViolation,
    )
    from temper_placer.router_v6.constraints_geometry import Point

    loc = v["location"]
    return ConnectivityViolation(
        type=v["type"], net=v["net"], location=Point(loc[0], loc[1]),
        description=v["description"],
    )


def _placement_violation_from_json(v):
    from temper_placer.deterministic.stages.placement_validation import (
        PlacementViolation,
    )

    return PlacementViolation(
        constraint_name=v["constraint_name"],
        violation_type=v["violation_type"],
        message=v["message"], severity=v["severity"],
        component_a=v["component_a"], component_b=v["component_b"],
        actual_distance_mm=v["actual_distance_mm"],
        required_distance_mm=v["required_distance_mm"],
    )


def _placement_from_json(v):
    pos = v["position"]
    return (v["ref"], (pos[0], pos[1]))


def _slot_from_json(pair):
    return (pair[0], pair[1])


def _zone_slots_from_json(v):
    return (v["zone"], tuple(_slot_from_json(s) for s in v["slots"]))


# ---------------------------------------------------------------------------
# State <-> JSON
# ---------------------------------------------------------------------------

def _opt_list(doc_typed, key, build):
    """null -> None; array -> list of built elements."""
    v = doc_typed.get(key)
    if v is None:
        return None
    return tuple(build(item) for item in v)


def _opt_set(doc_typed, key, build=None):
    v = doc_typed.get(key)
    if v is None:
        return None
    if build is None:
        return frozenset(tuple(item) for item in v)
    return frozenset(build(item) for item in v)


def state_from_json(text: str):
    from temper_placer.deterministic.state import BoardState

    doc = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError("state document: expected a JSON object")
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"state document: schema must be {SCHEMA}, got {doc.get('schema')!r}")
    typed = doc.get("typed")
    if not isinstance(typed, dict):
        raise ValueError('state document: missing "typed" object')

    kwargs = {}
    kwargs["net_order"] = tuple(doc.get("net_order") or ())
    opaque = doc.get("opaque") or {}
    for name, value in opaque.items():
        kwargs[name] = json.loads(json.dumps(value))  # plain objects only
    kwargs["drc_violations"] = _opt_list(typed, "drc_violations", _drc_violation_from_json)
    kwargs["connectivity_violations"] = _opt_list(
        typed, "connectivity_violations", _connectivity_violation_from_json)
    kwargs["placement_violations"] = _opt_list(
        typed, "placement_violations", _placement_violation_from_json)
    kwargs["placements"] = _opt_set(typed, "placements", _placement_from_json)
    kwargs["used_slots"] = _opt_set(typed, "used_slots")
    kwargs["routes"] = _opt_set(typed, "routes", _route_from_json)
    kwargs["vias"] = _opt_set(typed, "vias", _via_from_json)
    kwargs["zones"] = _opt_set(typed, "zones", _zone_from_json)
    kwargs["component_zone_map"] = _opt_set(typed, "component_zone_map")
    kwargs["zone_slots"] = _opt_set(typed, "zone_slots", _zone_slots_from_json)
    kwargs["layer_assignments"] = _opt_set(
        typed, "layer_assignments", _layer_assignment_from_json)
    return BoardState(**kwargs)


def _point_to_json(loc):
    return [_f64_to_json(loc.x, "location.x"), _f64_to_json(loc.y, "location.y")]


def _drc_violation_to_json(v):
    return {
        "type": v.type,
        "geometry_a_id": v.geometry_a_id,
        "geometry_b_id": v.geometry_b_id,
        "net_a": v.net_a,
        "net_b": v.net_b,
        "clearance_actual": _f64_to_json(v.clearance_actual, "clearance_actual"),
        "clearance_required": _f64_to_json(v.clearance_required, "clearance_required"),
        "location": _point_to_json(v.location),
    }


def _connectivity_violation_to_json(v):
    return {
        "type": v.type,
        "net": v.net,
        "location": _point_to_json(v.location),
        "description": v.description,
    }


def _placement_violation_to_json(v):
    return {
        "constraint_name": v.constraint_name,
        "violation_type": v.violation_type,
        "message": v.message,
        "severity": v.severity,
        "component_a": v.component_a,
        "component_b": v.component_b,
        "actual_distance_mm": (
            None if v.actual_distance_mm is None
            else _f64_to_json(v.actual_distance_mm, "actual_distance_mm")),
        "required_distance_mm": (
            None if v.required_distance_mm is None
            else _f64_to_json(v.required_distance_mm, "required_distance_mm")),
    }


def _route_to_json(r):
    sx, sy = r.start
    ex, ey = r.end
    return {
        "start": [_f64_to_json(sx, "route.start"), _f64_to_json(sy, "route.start")],
        "end": [_f64_to_json(ex, "route.end"), _f64_to_json(ey, "route.end")],
        "width": _f64_to_json(r.width, "route.width"),
        "layer": r.layer,
        "net": r.net,
    }


def _via_to_json(via):
    px, py = via.position
    return {
        "position": [_f64_to_json(px, "via.position"), _f64_to_json(py, "via.position")],
        "drill": _f64_to_json(via.drill, "via.drill"),
        "width": _f64_to_json(via.width, "via.width"),
        "layers": [via.layers[0], via.layers[1]],
        "net": via.net,
        "is_diff_pair": via.is_diff_pair,
    }


def _zone_to_json(z):
    (x0, y0), (x1, y1) = z.bounds
    return {
        "name": z.name,
        "bounds": [
            [_val_to_json(x0), _val_to_json(y0)],
            [_val_to_json(x1), _val_to_json(y1)],
        ],
    }


def _layer_assignment_to_json(la):
    return {
        "net_name": la.net_name,
        "layer": _val_to_json(la.layer),
        "allow_layer_change": la.allow_layer_change,
        "is_plane": la.is_plane,
    }


_OPAQUE_FIELDS = (
    "board", "netlist", "loops", "grid", "drc_oracle", "design_rules",
    "config", "component_domain_map", "routing_corridors", "domain_regions",
    "violations", "reclaim_by_pin_pair",
)

_JSON_NATIVE = (dict, list, str, bool, int, float, type(None))


def _encode_opaque(name, value):
    """Plain JSON values verbatim; plain collections element-wise.

    ``component_domain_map`` / ``routing_corridors`` / ``domain_regions`` /
    ``violations`` are plain frozenset/tuple *data* fields on the Python
    BoardState (their NativeBoardState counterparts are opaque only because
    their owned types have not landed yet), so a set/tuple of JSON-native
    leaves encodes as an array. Anything else (a real Board, a numpy array,
    a shapely geometry) is a LOUD error naming the field -- never a silent
    drop -- mirroring the Rust codec's rule.
    """
    if isinstance(value, _JSON_NATIVE):
        return value
    if isinstance(value, (frozenset, set, tuple, list)):
        items = [_encode_opaque(name, v) for v in value]
        # Sets sort by their encoded rendering -- the same deterministic
        # function-of-the-values convention state_ser.rs's set_to_json uses.
        return sorted(items, key=repr) if isinstance(value, (frozenset, set)) else items
    raise ValueError(
        f"opaque field {name!r} holds a non-JSON-native "
        f"{type(value).__module__}.{type(value).__qualname__}; opaque fields "
        "cross this boundary only as plain JSON values"
    )


def _opaque_to_doc(state) -> dict:
    out = {}
    for name in _OPAQUE_FIELDS:
        value = getattr(state, name)
        if value is None or value == () or value == frozenset():
            continue
        out[name] = _encode_opaque(name, value)
    return out


def state_to_json(state) -> str:
    doc = {
        "schema": SCHEMA,
        "net_order": list(state.net_order),
        "opaque": _opaque_to_doc(state),
        "typed": {
            "drc_violations":
                None if state.drc_violations is None
                else [_drc_violation_to_json(v) for v in state.drc_violations],
            "connectivity_violations":
                None if state.connectivity_violations is None
                else [_connectivity_violation_to_json(v) for v in state.connectivity_violations],
            "placement_violations":
                None if state.placement_violations is None
                else [_placement_violation_to_json(v) for v in state.placement_violations],
            "placements":
                None if state.placements is None
                else [{"ref": ref, "position": [pos[0], pos[1]]}
                      for (ref, pos) in sorted(state.placements)],
            "used_slots":
                None if state.used_slots is None
                else [[s[0], s[1]] for s in sorted(state.used_slots)],
            "routes":
                None if state.routes is None
                else [_route_to_json(r) for r in sorted(state.routes, key=_route_to_json_sort)],
            "vias":
                None if state.vias is None
                else [_via_to_json(v) for v in sorted(state.vias, key=lambda v: v.position)],
            "zones":
                None if state.zones is None
                else [_zone_to_json(z) for z in sorted(state.zones, key=lambda z: z.name)],
            "component_zone_map":
                None if state.component_zone_map is None
                else [[ref, zone] for (ref, zone) in sorted(state.component_zone_map)],
            "zone_slots":
                None if state.zone_slots is None
                else [{"zone": zone, "slots": [[s[0], s[1]] for s in slots]}
                      for (zone, slots) in sorted(state.zone_slots)],
            "layer_assignments":
                None if state.layer_assignments is None
                else [_layer_assignment_to_json(la)
                      for la in sorted(state.layer_assignments, key=lambda la: la.net_name)],
        },
    }
    return json.dumps(doc, allow_nan=False)


def _route_to_json_sort(r):
    return (r.layer, r.net or "", r.start[0], r.start[1], r.end[0], r.end[1])


# ---------------------------------------------------------------------------
# Stage dispatch
# ---------------------------------------------------------------------------

def stage_fn(stage_name: str):
    import temper_orchestration as to

    fn_name = "run_clearance_grid_stage" if stage_name == "clearance_grid" \
        else f"run_{stage_name}"
    fn = getattr(to, fn_name, None)
    if fn is None or not callable(fn):
        raise KeyError(stage_name)
    return fn


# Constructor-state defaults mirroring what the deterministic stage adapters
# (``deterministic/stages/__init__.py``) thread into the same pyfunctions --
# the real pipeline constructs these stages with exactly these values, so a
# subprocess run without explicit --arg extras matches production behavior.
# Stages NOT listed here either need nothing (run_<name>(state)) or need
# state that does not survive the JSON boundary yet (a config block, a
# parsed-pads list, a live Stage instance) -- those fail loudly instead.
DEFAULT_STAGE_ARGS = {
    "track_deduplication": [0.05],
    "short_circuit_detection": [0.1],
    "via_deduplication": [0.05],
    "via_validation": [0.1, True],
    # The validation stages' constructor defaults (fail-on-violations off --
    # the pipeline's fence threading decides severity, the stage only
    # reports).
    "drc_validation": [False, 0],
    "connectivity_validation": [False],
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", required=True, help="pipeline stage name")
    parser.add_argument(
        "--arg", action="append", default=[], metavar="JSON",
        help="extra positional argument for the stage pyfunction (repeatable)")
    args = parser.parse_args(argv)

    try:
        fn = stage_fn(args.stage)
    except KeyError:
        print(f"_stage_subprocess: unknown stage {args.stage!r}", file=sys.stderr)
        return 2

    try:
        extra = [json.loads(a) for a in args.arg] if args.arg \
            else DEFAULT_STAGE_ARGS.get(args.stage, [])
    except json.JSONDecodeError as e:
        print(f"_stage_subprocess: bad --arg JSON: {e}", file=sys.stderr)
        return 2

    try:
        state = state_from_json(sys.stdin.read())
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"_stage_subprocess: [{args.stage}] cannot materialize state: {e}",
              file=sys.stderr)
        return 1

    try:
        result = fn(state, *extra)
    except Exception as e:  # noqa: BLE001 -- the boundary reports ANY stage failure
        print(f"_stage_subprocess: [{args.stage}] stage failed: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # The D6 validation pyfunctions surface their raise decision as a
    # ``(state, message)`` tuple (the Python shims raise on a non-None
    # message); every other stage returns the state directly.
    message = None
    if isinstance(result, tuple) and len(result) == 2:
        out_state, message = result
    else:
        out_state = result

    try:
        fields = {f.name for f in dataclasses.fields(out_state)}
    except TypeError:
        print(f"_stage_subprocess: [{args.stage}] stage returned an unexpected "
              f"{type(out_state).__name__} (not a BoardState)", file=sys.stderr)
        return 1
    missing = {"net_order"} - fields
    if missing:
        print(f"_stage_subprocess: [{args.stage}] stage returned an unexpected "
              f"object (missing fields {sorted(missing)})", file=sys.stderr)
        return 1

    if message is not None:
        print(f"_stage_subprocess: [{args.stage}] stage reported: {message}",
              file=sys.stderr)
        return 1

    try:
        sys.stdout.write(state_to_json(out_state))
        sys.stdout.write("\n")
    except (ValueError, TypeError, AttributeError) as e:
        print(f"_stage_subprocess: [{args.stage}] cannot serialize mutated state: {e}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
