"""Test board catalog for Router V6 benchmark suite.

This module defines the multi-board test suite used to validate Router V6.
Per the plan, we need diverse boards across domains:
- 2+ digital boards
- 1+ mixed-signal boards
- 3+ power electronics boards
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestBoard:
    """Metadata for a test board in the benchmark suite.

    Attributes:
        name: Short name for the board
        path: Path to .kicad_pcb file
        domain: Board domain (digital, power, mixed)
        layers: Number of copper layers
        expected_net_count: Approximate number of nets (for validation)
        description: What makes this board interesting for testing
        source: Where the design came from
        license: License of the design files
    """
    name: str
    path: Path
    domain: str
    layers: int
    expected_net_count: int
    description: str
    source: str
    license: str

    def exists(self) -> bool:
        """Check if PCB file exists."""
        return self.path.exists()

    def __str__(self) -> str:
        status = "✓" if self.exists() else "✗"
        return f"{status} {self.name}: {self.domain}, {self.layers}L, ~{self.expected_net_count} nets"


# Standard test suite locations
# NOTE: Using unrouted versions from test fixtures for benchmarking
BASE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "external" / ".cache"

PIANTOR_PATH = BASE_PATH / "piantor_right" / "piantor_right_unrouted.kicad_pcb"
LIBRESOLAR_BMS_PATH = BASE_PATH / "libresolar_bms" / "libresolar_bms_unrouted.kicad_pcb"
RP2040_PATH = BASE_PATH / "rp2040_designguide" / "rp2040_designguide_unrouted.kicad_pcb"
BITAXE_PATH = BASE_PATH / "bitaxe_ultra" / "bitaxe_ultra_unrouted.kicad_pcb"


# Test board definitions (using unrouted versions)
TEST_BOARDS: list[TestBoard] = [
    TestBoard(
        name="Piantor_Right",
        path=PIANTOR_PATH,
        domain="digital",
        layers=2,
        expected_net_count=33,
        description="Split keyboard, regular grid of switches",
        source="https://github.com/beekeeb/piantor",
        license="CC-BY-SA-4.0"
    ),
    TestBoard(
        name="LibreSolar_BMS",
        path=LIBRESOLAR_BMS_PATH,
        domain="power",
        layers=4,
        expected_net_count=200,
        description="8S 50A battery management system, multiple voltage domains",
        source="https://github.com/LibreSolar/bms-8s50-ic",
        license="Apache-2.0"
    ),
    TestBoard(
        name="RP2040_DesignGuide",
        path=RP2040_PATH,
        domain="mixed",
        layers=4,
        expected_net_count=120,
        description="RP2040 reference design, mixed digital/power",
        source="Raspberry Pi Foundation",
        license="CC-BY-SA-4.0"
    ),
    TestBoard(
        name="BitAxe_Ultra",
        path=BITAXE_PATH,
        domain="mixed",
        layers=2,
        expected_net_count=80,
        description="Bitcoin ASIC miner, high-speed digital + power",
        source="https://github.com/skot/bitaxe",
        license="GPL-3.0"
    ),
]


def get_available_boards() -> list[TestBoard]:
    """Get list of test boards that actually exist on disk.

    Returns:
        List of TestBoard instances where path exists
    """
    return [board for board in TEST_BOARDS if board.exists()]


def get_board_by_name(name: str) -> TestBoard | None:
    """Look up a test board by name.

    Args:
        name: Board name (case-insensitive)

    Returns:
        TestBoard if found, None otherwise
    """
    name_lower = name.lower()
    for board in TEST_BOARDS:
        if board.name.lower() == name_lower:
            return board
    return None


def print_test_suite_status():
    """Print status of test suite boards."""
    print("Router V6 Test Suite Status")
    print("=" * 60)

    available = get_available_boards()
    print(f"\nAvailable: {len(available)}/{len(TEST_BOARDS)} boards\n")

    # Group by domain
    digital = [b for b in TEST_BOARDS if b.domain == "digital"]
    power = [b for b in TEST_BOARDS if b.domain == "power"]
    mixed = [b for b in TEST_BOARDS if b.domain == "mixed"]

    print("Digital Boards:")
    for board in digital:
        print(f"  {board}")

    print("\nPower Boards:")
    for board in power:
        print(f"  {board}")

    print("\nMixed-Signal Boards:")
    for board in mixed:
        print(f"  {board}")

    print("\n" + "=" * 60)
    print(f"READY: {len(available)} boards available for benchmarking")

    if len(available) < 4:
        print("WARNING: Need at least 4 boards for meaningful benchmarking")


if __name__ == "__main__":
    print_test_suite_status()
