"""Check a reviewed pin contract against the untouched source authority and header."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[4]


def main() -> None:
    if os.environ.get("CMSIS_DEVICE") and os.environ.get("CMSIS_CORE"):
        vendor = json.loads((HERE / "vendor-inputs.json").read_text())
        for header in vendor["headers"]:
            root = Path(os.environ["CMSIS_DEVICE" if header["kind"] == "device" else "CMSIS_CORE"])
            if hashlib.sha256((root / header["name"]).read_bytes()).hexdigest() != header["sha256"]:
                raise ValueError(f"Unreviewed compiler header bytes: {header['name']}")
    contract = json.loads((HERE / "pin-contract.json").read_text())
    authority = contract["stm32_authority"]
    source = REPO / authority["path"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != authority["sha256"]:
        raise ValueError("STM32 source pin export changed; reconcile binding before reuse")
    rows = [
        line.split("\t") for line in source.read_text().splitlines() if line.endswith("\t" + authority["source_ref"])
    ]
    actual = {(int(row[4]), row[5], row[7]) for row in rows}
    recorded = {(pin["package_pin"], pin["pad"], pin["net"]) for pin in contract["stm32"]}
    if recorded != actual or len(actual) != 64:
        raise ValueError("STM32 package pin contract does not match source")
    header = (HERE / "esp32/pins.h").read_text() + (HERE / "esp32/bench_pins.h").read_text()
    if contract["optional_bench"]["required_for_product"]:
        raise ValueError("Bench instrument became a product dependency")
    defines = dict(re.findall(r"^#define (R5_\w+) (\d+)$", header, re.MULTILINE))
    pin_map = {name: int(value) for name, value in defines.items()}
    if len(pin_map.values()) != len(set(pin_map.values())):
        raise ValueError("ESP32 GPIO collision")
    reserved = set(contract["esp32"]["reserved_gpio"])
    if set(pin_map.values()) & reserved:
        raise ValueError("ESP32 pin collides with flash, strap, USB, debug or console allocation")
    expected = set(contract["esp32"]["native4_pwm"].values())
    expected.update(row["gpio"] for row in contract["esp32"]["JCTRL"] if row["gpio"] is not None)
    expected.update(contract["optional_bench"]["JFAST"][net] for net in ("CS_N", "SCLK", "MISO", "MOSI", "RESET_N", "FAULT"))
    named = {
        "R5_PWM_AH": contract["esp32"]["native4_pwm"]["J4.5"],
        "R5_PWM_AL": contract["esp32"]["native4_pwm"]["J4.6"],
        "R5_PWM_BH": contract["esp32"]["native4_pwm"]["J4.7"],
        "R5_PWM_BL": contract["esp32"]["native4_pwm"]["J4.8"],
    }
    jctrl_names = {
        3: "SUP_RUN_OK",
        4: "REQUEST",
        5: "HEARTBEAT",
        6: "FAULT_HIGH",
        7: "UART_TX",
        8: "UART_RX",
        9: "RAIL_OK",
        10: "INTERLOCK_OK",
    }
    for row in contract["esp32"]["JCTRL"]:
        if row["pin"] in jctrl_names:
            named["R5_" + jctrl_names[row["pin"]]] = row["gpio"]
    for net, define in {"CS_N": "CS", "SCLK": "CLK", "MISO": "MISO", "MOSI": "MOSI", "RESET_N": "RESET_N", "FAULT": "FAULT"}.items():
        named["R5_FAST_" + define] = contract["optional_bench"]["JFAST"][net]
    if pin_map != named or set(pin_map.values()) != expected:
        raise ValueError("ESP32 header differs from connector contract")
    print(
        f"PASS: 64 STM32 source pins; {len(pin_map)} unique ESP32 GPIOs (12 product + 6 optional bench); reserved pins excluded"
    )
    print("New ESP carrier ECO only; this does not establish compatibility with legacy controller.")


if __name__ == "__main__":
    main()
