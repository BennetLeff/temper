#!/usr/bin/env python3
"""Bind a source-derived native RTDUnit export to an immutable Rust input.

This is deliberately a transport adapter. It does not invent net roles or
turn file presence into an engineering verdict. Rust checks observed board data.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED_NATIVE = (
    "board_sha256", "extractor_sha256", "copper_layer_count", "components",
    "connections", "connectivity_clusters", "traces", "vias", "zones",
)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--board-file", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True,
                        help="generated firmware/config.h (and pin macros)")
    parser.add_argument("--firmware-pins", type=Path, required=True,
                        help="source-derived firmware/components/hal/include/temper_pins.h")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile_bytes = args.profile.read_bytes()
    native_bytes = args.native.read_bytes()
    profile = json.loads(profile_bytes)
    native = json.loads(native_bytes)
    missing = [key for key in REQUIRED_NATIVE if key not in native]
    if missing:
        raise SystemExit("native export missing required transport fields: " + ", ".join(missing))
    source_manifest = json.loads(args.source_manifest.read_text())
    source_components = {
        item.get("instance_path", item.get("address", "")).split("::")[-1]: item
        for item in source_manifest.get("components", [])
        if isinstance(item, dict)
    }
    if not source_components:
        raise SystemExit("source manifest has no compiled component census")
    expected_source = {
        binding["instance_id"]: binding["mpn"]
        for binding in profile.get("component_bindings", [])
    }
    expected_source.update({
        profile["probe"]["component"]: profile["probe"]["mpn"],
        profile["local"]["reference_component"]: profile["local"]["reference_mpn"],
        profile["local"]["ferrite_component"]: profile["local"]["ferrite_mpn"],
        "unit_io": profile["interface"]["connector_mpn"],
    })
    for instance, expected_mpn in expected_source.items():
        source = source_components.get(instance)
        if source is None:
            raise SystemExit("source manifest missing required compiled component " + instance)
        observed_mpn = source.get("mpn", source.get("attributes", {}).get("mpn"))
        if observed_mpn != expected_mpn:
            raise SystemExit(f"source manifest MPN mismatch for {instance}: {observed_mpn!r} != {expected_mpn!r}")
    ref_to_instance = {c.get("reference"): c.get("instance_path") for c in source_manifest.get("bridge", {}).get("components", [])}
    pin_to_pad = {(p.get("instance_path"), p.get("pin")): str(p.get("pad")) for p in source_manifest.get("strict_pin_map", [])}
    source_components_out = []
    for component in source_manifest.get("components", []):
        instance = component.get("instance_path", component.get("address", "")).split("::")[-1]
        pads = sum(1 for pin in source_manifest.get("strict_pin_map", []) if pin.get("instance_path") == instance)
        if instance and pads:
            source_components_out.append({"instance_id": instance, "mpn": component.get("mpn", component.get("attributes", {}).get("mpn", "")), "pad_count": pads})
    if not source_components_out:
        raise SystemExit("source manifest has no complete compiled component/pad census")
    expected_components = {
        item["instance_id"]: item["mpn"] for item in source_components_out
    }
    native_components = {
        item.get("id"): item.get("mpn") for item in native.get("components", [])
    }
    if native_components != expected_components:
        raise SystemExit(
            "native/source compiled component census differs: "
            + json.dumps(
                {
                    "missing": sorted(set(expected_components) - set(native_components)),
                    "extra": sorted(set(native_components) - set(expected_components)),
                    "mpn_mismatch": sorted(
                        key for key in set(expected_components) & set(native_components)
                        if expected_components[key] != native_components[key]
                    ),
                },
                sort_keys=True,
            )
        )
    source_bindings = []
    for net in source_manifest.get("bridge", {}).get("nets", []):
        for ref, pin in net.get("nodes", []):
            instance = ref_to_instance.get(ref)
            pad = pin_to_pad.get((instance, pin))
            if not instance or not pad:
                raise SystemExit(
                    "source manifest bridge node is not in strict component/pin map: "
                    + json.dumps({"ref": ref, "pin": pin, "instance": instance, "pad": pad})
                )
            source_bindings.append({"instance_id": instance, "pad": pad, "net": net["name"]})
    if not source_bindings:
        raise SystemExit("source manifest has no strict compiled pad/net bindings")
    expected = {(b["instance_id"], b["pad"]): b["net"] for b in source_bindings}
    if len(expected) != len(source_bindings):
        raise SystemExit("compiled source bridge contains duplicate instance/pad bindings")
    observed = {
        (c["id"], str(p["pad"])): p["net"]
        for c in native["components"] for p in c.get("footprint_pads", [])
    }
    observed_source = observed
    if observed_source.keys() != expected.keys():
        missing_pads = sorted(expected.keys() - observed_source.keys())
        extra_pads = sorted(observed_source.keys() - expected.keys())
        raise SystemExit(
            "native/source compiled pad set differs: "
            + json.dumps({"missing": missing_pads, "extra": extra_pads}, sort_keys=True)
        )
    for key, expected_net in expected.items():
        if observed_source[key] != expected_net:
            raise SystemExit("native pad/net does not match compiled source binding: " + json.dumps({"instance_id": key[0], "pad": key[1], "net": expected_net}, sort_keys=True))
    model = json.loads(args.model.read_text())
    board_hash = sha256(args.board_file)
    if native["board_sha256"].lower() != board_hash:
        raise SystemExit(f"native board_sha256 does not match board-file bytes: native={native['board_sha256']} current={board_hash}")
    extractor_hash = sha256(args.extractor)
    if native["extractor_sha256"].lower() != extractor_hash:
        raise SystemExit(f"native extractor_sha256 does not match extractor bytes: native={native['extractor_sha256']} current={extractor_hash}")
    firmware_text = args.firmware.read_text()
    firmware_pins_text = args.firmware_pins.read_text()
    def macro(name: str, text: str) -> float:
        match = re.search(r"^\s*#define\s+" + re.escape(name) + r"\s+([0-9]+(?:\.[0-9]+)?)(?:f)?", text, re.MULTILINE)
        if not match:
            raise SystemExit("firmware header missing required macro " + name)
        return float(match.group(1))
    firmware = {
        "cs_gpio": int(macro("PIN_SPI_CS_RTD1", firmware_pins_text)),
        "drdy_gpio": int(macro("PIN_RTD_DRDY", firmware_pins_text)),
        "low_threshold_word": int(macro("MAX31865_LOW_THRESHOLD_WORD", firmware_text)),
        "high_threshold_word": int(macro("MAX31865_HIGH_THRESHOLD_WORD", firmware_text)),
        "short_fault_ohm": macro("RTD_SHORT_FAULT_OHM", firmware_text),
        "open_fault_ohm": macro("RTD_OPEN_FAULT_OHM", firmware_text),
    }
    identity = {
        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "native_export_sha256": hashlib.sha256(native_bytes).hexdigest(),
        "source_manifest_sha256": sha256(args.source_manifest),
        "extractor_sha256": extractor_hash,
        "model_sha256": sha256(args.model),
        "firmware_sha256": sha256(args.firmware),
        "firmware_pins_sha256": sha256(args.firmware_pins),
        "board_sha256": board_hash,
    }
    if args.binary:
        identity["binary_sha256"] = sha256(args.binary)
    envelope = {"schema": "zapote.rtd.unit-input.v1", "profile": profile, "native": native,
                "identity": identity, "firmware": firmware, "model": model,
                "source_bindings": source_bindings,
                "source_components": source_components_out}
    args.output.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")

if __name__ == "__main__":
    main()
