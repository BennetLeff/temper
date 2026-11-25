"""Tests for firmware/tools/check_idf_waits.py.

ESP-IDF 5.3 (CI: espressif/idf:release-v5.3) rejects any wait but portMAX_DELAY on the SPI bus lock:
spi_device_acquire_bus (spi_master.c "acquire finite time not supported now."), spi_device_polling_start
("currently timeout is not available for polling transactions") and spi_bus_lock_acquire_start. The call
returns ESP_ERR_INVALID_ARG every time, so code built on it fails on hardware while every host test,
which stubs the transport, passes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_idf_waits as gate  # noqa: E402


def _bad(src: str) -> list[str]:
    return gate.check_source("x.c", src)


def test_finite_acquire_is_caught():
    assert _bad("if (spi_device_acquire_bus(h, pdMS_TO_TICKS(2)) != ESP_OK) return false;")


def test_portmax_acquire_passes():
    assert not _bad("spi_device_acquire_bus(h, portMAX_DELAY);")


def test_polling_start_and_bus_lock_are_checked():
    assert _bad("spi_device_polling_start(h, &t, 10);")
    assert _bad("spi_bus_lock_acquire_start(lock, ticks);")
    assert not _bad("spi_device_polling_start(h, &t, portMAX_DELAY);")


def test_call_split_over_lines_with_nested_parens():
    assert _bad("e = spi_device_acquire_bus(dev_of(a, b),\n        pdMS_TO_TICKS(5));")
    assert not _bad("e = spi_device_acquire_bus(dev_of(a, b),\n        portMAX_DELAY);")


def test_comments_and_declarations_are_ignored():
    assert not _bad("/* spi_device_acquire_bus(h, pdMS_TO_TICKS(2)) is rejected by IDF */")
    assert not _bad("// spi_device_acquire_bus(h, 2);")
    assert not _bad("esp_err_t spi_device_acquire_bus(spi_device_handle_t device, TickType_t wait);")


def test_firmware_tree_passes():
    problems = gate.check_tree()
    assert problems == [], "\n".join(problems)
    assert gate.files_scanned() > 20  # the scan reaches the sources
