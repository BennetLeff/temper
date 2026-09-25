#!/usr/bin/env python3
"""Build zapote-rtd.v1 from native KiCad measurements and source identity.

This is transport only. Expected RTD topology and geometry policy come from
the serialized authored policy and source manifest; they are never inferred
from native names or footprints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def observed_nets(native: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for key in ("connections", "traces", "vias", "connectivity_clusters"):
        for item in native.get(key, []):
            net = item.get("net")
            if isinstance(net, str) and net:
                names.add(net)
    return sorted(names)


def load_policy(path: Path) -> dict[str, Any]:
    policy = load(path)
    if policy.get("schema") != "zapote.rtd.authored-policy.v1":
        raise ValueError(f"{path} has unsupported authored-policy schema")
    if not isinstance(policy.get("net_domains"), dict):
        raise ValueError("authored policy must contain net_domains")
    if not isinstance(policy.get("geometry"), dict) or not isinstance(policy.get("topology"), dict):
        raise ValueError("authored policy must contain geometry and topology")
    return policy


def source_component(source: dict[str, Any], instance_path: str) -> dict[str, Any]:
    # The generated source section keeps sensing components in `components`
    # and the retained buck/half-bridge census in `full_bridge.components`.
    # Both are source identity, so resolve either section by stable instance
    # path rather than by a native reference or substring.
    candidates = list(source.get("components", []))
    candidates.extend(source.get("bridge", {}).get("components", []))
    candidates.extend(source.get("full_bridge", {}).get("components", []))
    for component in candidates:
        if component.get("instance_path") == instance_path:
            return component
    raise ValueError(f"source manifest has no component for {instance_path}")


def source_reference(source: dict[str, Any], instance_path: str) -> str:
    reference = source_component(source, instance_path).get("reference")
    if not isinstance(reference, str) or not reference:
        raise ValueError(f"source manifest has no reference for {instance_path}")
    return reference


def source_quantity(source: dict[str, Any], instance_path: str, unit: str) -> float:
    value = source_component(source, instance_path).get("value")
    if not isinstance(value, str):
        raise ValueError(f"source manifest has no value for {instance_path}")
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(k|M|m|u|n)?" + re.escape(unit), value, re.I)
    if not match:
        raise ValueError(f"source value {value!r} for {instance_path} is not a {unit} quantity")
    amount = float(match.group(1))
    prefix = (match.group(2) or "").lower()
    scale = {"k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9}.get(prefix, 1.0)
    return amount * scale


def source_tolerance_pct(source: dict[str, Any], instance_path: str) -> float:
    value = source_component(source, instance_path).get("value")
    if not isinstance(value, str):
        raise ValueError(f"source manifest has no value for {instance_path}")
    match = re.search(r"\+/-\s*(\d+(?:\.\d+)?)\s*%", value)
    if not match:
        raise ValueError(f"source value {value!r} for {instance_path} has no tolerance")
    return float(match.group(1))


def authored_geometry(native: dict[str, Any], source: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Combine serialized policy with measured regions from source-bound IDs."""
    components = {item["id"]: item for item in native.get("components", [])}
    reference_to_instance = native.get("reference_to_instance", {})
    aggressors = []
    for authored in policy["geometry"]["aggressors"]:
        instance_path = authored.get("source_instance")
        component_id = source_reference(source, instance_path)
        # Native exports may key a component by its stable instance path or
        # by its KiCad reference. Accept the extractor's explicit mapping;
        # never guess this relationship from names.
        native_id = reference_to_instance.get(component_id, component_id)
        component = components.get(native_id)
        if component is None:
            raise ValueError(f"native snapshot is missing source-bound aggressor {instance_path} ({component_id} -> {native_id})")
        points = [pad["position_mm"] for pad in component.get("footprint_pads", []) if len(pad.get("position_mm", [])) == 2]
        if not points:
            points = [component["position_mm"]]
        xs, ys = zip(*points)
        margin = float(authored["margin_mm"])
        aggressors.append({"net": authored["net"], "region_mm": [min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin], "min_distance_mm": float(authored["min_distance_mm"])})
    geometry = policy["geometry"]
    return {"sensitive_nets": list(geometry["sensitive_nets"]), "aggressors": aggressors, "prohibited_connections": list(geometry["prohibited_connections"]), "required_locality_mm": float(geometry["required_locality_mm"])}


def macros(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*#define\s+(\w+)\s+([^/\s]+)", line)
        if match:
            values[match.group(1)] = match.group(2).rstrip("fF")
    return values


def number(values: dict[str, str], key: str) -> int:
    try:
        return int(values[key], 0)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"firmware pins missing numeric macro {key}") from exc


def real(values: dict[str, str], key: str) -> float:
    try:
        return float(values[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"firmware config missing numeric macro {key}") from exc


def source_mpn(source: dict[str, Any], instance_path: str) -> str:
    mpn = source_component(source, instance_path).get("mpn")
    if not isinstance(mpn, str) or not mpn:
        raise ValueError(f"source manifest has no resolved MPN for {instance_path}")
    return mpn


def source_mcu_pads(source: dict[str, Any], policy: dict[str, Any]) -> dict[str, str]:
    pads: dict[str, str] = {}
    mcu_reference = source_reference(source, policy["topology"]["adc"]["mcu_instance"])
    signals = policy["topology"]["spi"]
    for net in source.get("bridge", {}).get("nets", []):
        name = net.get("name")
        if name not in {signal["signal"] for signal in signals}:
            continue
        for node in net.get("nodes", []):
            if isinstance(node, list) and len(node) == 2 and node[0] == mcu_reference:
                pads[name] = str(node[1])
                break
    if set(pads) != {signal["signal"] for signal in signals}:
        raise ValueError("source manifest lacks complete MCU RTD pad map")
    return pads


def make_input(native: dict[str, Any], native_hash: str, source_manifest: Path, board_file: Path, suite_file: Path, model_file: Path, firmware_config: Path, firmware_pins: Path, policy_file: Path) -> dict[str, Any]:
    components = []
    for item in native.get("components", []):
        pads = []
        for pad in item.get("footprint_pads", []):
            if "size_mm" in pad and "layers" in pad:
                pads.append({key: pad[key] for key in ("pad", "net", "position_mm", "size_mm", "layers")})
        components.append({"id": item["id"], "mpn": item["mpn"], "kind": item["kind"], "position_mm": item["position_mm"], "footprint_pads": pads})
    source = load(source_manifest)
    policy = load_policy(policy_file)
    domains = policy["net_domains"]
    roles = policy.get("net_roles", {})
    nets = [{"name": name, "domain": domains.get(name, "UNCLASSIFIED"), "role": roles.get(name, "observed")} for name in observed_nets(native)]
    # The native extractor can report the same component/pad/net tuple once
    # per source object.  The Zapote boundary deliberately rejects duplicate
    # pin assignments, so collapse only exact duplicates while preserving all
    # distinct observed assignments.
    connections = []
    seen_connections: set[tuple[str, str, str]] = set()
    for item in native.get("connections", []):
        key = (item.get("component", ""), item.get("pin", ""), item.get("net", ""))
        if key in seen_connections:
            continue
        seen_connections.add(key)
        connections.append(item)
    source_hash = sha256(source_manifest)
    board_hash = sha256(board_file)
    suite_hash = sha256(suite_file)
    model_hash = sha256(model_file)
    firmware = macros(firmware_config)
    pins = macros(firmware_pins)
    mcu_pads = source_mcu_pads(source, policy)
    native_board_hash = native.get("board_sha256", "")
    if not isinstance(native_board_hash, str) or not native_board_hash:
        raise ValueError("native export must carry its own board_sha256")
    if native_board_hash != board_hash:
        raise ValueError(
            "native extraction board_sha256 does not match the board bytes supplied to the binder"
        )
    native_extractor_hash = native.get("extractor_sha256", "")
    if not isinstance(native_extractor_hash, str) or not native_extractor_hash:
        raise ValueError("native export must carry its own extractor_sha256")
    topology = policy["topology"]
    required_local_ics = [{key: value for key, value in item.items() if key != "capacitor"} for item in topology["required_local_ics"]]
    decoupling = []
    for required in topology["required_local_ics"]:
        ic, cap, rail, ground = required["component"], required["capacitor"], required["rail"], required["ground"]
        component = next((item for item in components if item["id"] == cap), None)
        if component is None:
            raise ValueError(f"native snapshot is missing required capacitor {cap}")
        decoupling.append({"component": cap, "ic": ic, "rail": rail, "ground": ground, "capacitance_uf": source_quantity(source, cap, "F") * 1e6, "position_mm": component["position_mm"]})
    adc_pins = dict(topology["adc"]["pins"])
    connector = dict(topology["connector"])
    rref = dict(topology["rref"])
    reference = dict(topology["reference"])
    local_rail = dict(topology["local_rail"])
    fault_output = dict(topology["fault_output"])
    spi = []
    for signal in topology["spi"]:
        firmware_key = {
            "RTD_SCK": "PIN_SPI_CLK",
            "RTD_SDI": "PIN_SPI_MOSI",
            "RTD_SDO": "PIN_SPI_MISO",
            "RTD_CS_N": "PIN_SPI_CS_RTD1",
            "RTD_DRDY": "PIN_RTD_DRDY",
        }[signal["signal"]]
        spi.append({"signal": signal["signal"], "mcu_pin": number(pins, firmware_key), "adc_pin": signal["adc_pin"], "series_component": signal["series_component"]})
    expected_rref_mpn = source_mpn(source, rref["component"])
    if expected_rref_mpn != rref["mpn"]:
        raise ValueError(f"authored RREF MPN {rref['mpn']} disagrees with source {expected_rref_mpn}")
    rref["mpn"] = expected_rref_mpn
    rref["resistance_ohm"] = source_quantity(source, rref["component"], "ohm")
    rref["tolerance_pct"] = source_tolerance_pct(source, rref["component"])
    expected_reference_mpn = source_mpn(source, reference["component"])
    if expected_reference_mpn != reference["mpn"]:
        raise ValueError(f"authored reference MPN {reference['mpn']} disagrees with source {expected_reference_mpn}")
    reference["mpn"] = expected_reference_mpn
    downstream_reference_consumers = list(topology["downstream_reference_consumers"])
    return {
        "schema_version": 1,
        "identity": {"source_revision": source.get("generator_sha256", "source-manifest"), "source_hash": source_hash, "board_revision": native.get("kicad_version", "unknown"), "board_hash": board_hash, "suite_revision": "zapote-rtd-v1", "suite_hash": suite_hash, "model_revision": "RTD_SAFETY_DUAL_PATH", "model_hash": model_hash, "observed_source_hash": source_hash, "observed_board_hash": board_hash, "observed_suite_hash": suite_hash, "observed_model_hash": model_hash, "native_export_sha256": native_hash, "native_board_sha256": native_board_hash, "native_extractor_sha256": native_extractor_hash, "native_binding_required": True, "runtime": "rust-native", "provider": "local"},
        "board": {"components": components, "nets": nets, "connections": connections, "traces": native.get("traces", []), "connectivity_clusters": native.get("connectivity_clusters", []), "vias": native.get("vias", []), "paths": [], "geometry": authored_geometry(native, source, policy)},
        "rtd": {"connector": connector, "adc": {"component": topology["adc"]["component"], "mpn": source_mpn(source, topology["adc"]["component"]), "pins": adc_pins}, "rref": rref, "reference": reference, "local_rail": local_rail, "required_local_ics": required_local_ics, "decoupling": decoupling, "mcu_pads": mcu_pads, "spi": spi, "fault_output": fault_output, "downstream_reference_consumers": downstream_reference_consumers},
        "firmware": {"gpio": {"RTD_SCK": number(pins, "PIN_SPI_CLK"), "RTD_SDI": number(pins, "PIN_SPI_MOSI"), "RTD_SDO": number(pins, "PIN_SPI_MISO"), "RTD_CS_N": number(pins, "PIN_SPI_CS_RTD1"), "RTD_DRDY": number(pins, "PIN_RTD_DRDY")}, "thresholds": {"short_ohm": real(firmware, "RTD_SHORT_FAULT_OHM"), "open_ohm": real(firmware, "RTD_OPEN_FAULT_OHM"), "low_word": number(firmware, "MAX31865_LOW_THRESHOLD_WORD"), "high_word": number(firmware, "MAX31865_HIGH_THRESHOLD_WORD"), **policy["firmware"]["thresholds"]}, "config_revision": str(firmware_config)},
        "scenarios": [{"name": "short_at_boundary", "resistance_ohm": 10.0, "conductor_open": None, "rail_loss": None, "expected_class": "covered_short", "expected_detected": True}, {"name": "open_at_boundary", "resistance_ohm": 300.0, "conductor_open": None, "rail_loss": None, "expected_class": "covered_open", "expected_detected": True}, {"name": "valid_hot_pt100", "resistance_ohm": 194.1, "conductor_open": None, "rail_loss": None, "expected_class": "valid_measurement", "expected_detected": False}, {"name": "post_ferrite_loss", "resistance_ohm": None, "conductor_open": None, "rail_loss": "post_ferrite", "expected_class": "local_rail_loss", "expected_detected": True}, {"name": "upstream_loss", "resistance_ohm": None, "conductor_open": None, "rail_loss": "upstream", "expected_class": "upstream_loss_system_disable_required", "expected_detected": False}, {"name": "force_plus_open", "resistance_ohm": None, "conductor_open": "FORCE+", "rail_loss": None, "expected_class": "covered_cable_open", "expected_detected": True}, {"name": "force_minus_open", "resistance_ohm": None, "conductor_open": "FORCE-", "rail_loss": None, "expected_class": "covered_cable_open", "expected_detected": True}, {"name": "sense_plus_open", "resistance_ohm": None, "conductor_open": "SENSE+", "rail_loss": None, "expected_class": "blind_spot_open_sense_plus", "expected_detected": False}, {"name": "sense_minus_open", "resistance_ohm": None, "conductor_open": "SENSE-", "rail_loss": None, "expected_class": "indeterminate_fault", "expected_detected": False}],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--board-file", type=Path, required=True)
    parser.add_argument("--suite-file", type=Path, required=True)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--firmware-config", type=Path, default=Path("firmware/config.h"))
    parser.add_argument("--firmware-pins", type=Path, default=Path("firmware/components/hal/include/temper_pins.h"))
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "rtd" / "authored-policy.json",
    )
    args = parser.parse_args()
    for path in (args.native, args.source_manifest, args.board_file, args.suite_file, args.model_file, args.firmware_config, args.firmware_pins, args.policy):
        if not path.is_file():
            raise SystemExit(f"required input is missing: {path}")
    payload = make_input(load(args.native), sha256(args.native), args.source_manifest, args.board_file, args.suite_file, args.model_file, args.firmware_config, args.firmware_pins, args.policy)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
