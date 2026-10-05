"""Check the copied native source against the audited compilation exports."""

from pathlib import Path

EXPORT_NAMES = ("default.net", "default.csv", "resolved-components.json")


def verify_source_snapshot(unit: Path) -> None:
    """Reject missing or different exports before either CAD builder writes."""
    for name in EXPORT_NAMES:
        audited = unit / "frozen" / name
        native = unit / "native-19" / "frozen" / name
        if audited.read_bytes() != native.read_bytes():
            raise ValueError(f"native19 source snapshot differs from audited export: {name}")
