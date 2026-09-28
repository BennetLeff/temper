"""Hash local-only raw evidence, excluding any licensed vendor model."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    paths = sorted(path for path in RAW.rglob("*") if path.is_file())
    if any(path.suffix.lower() in {".lib", ".ibs"} for path in paths):
        raise ValueError("licensed model candidate found in raw evidence")
    for path in paths:
        print(f"{sha256(path)}  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
