#!/usr/bin/env python3
"""Recompute every completed binary capture; optionally rerun final AC decks."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import tarfile
import numpy as np
from periodic import analyze, read_binary
from filter_stage import MODEL

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ac", action="store_true")
    args = parser.parse_args()
    verified = []
    for path in sorted((HERE / "periodic-runs").glob("*/result.json")):
        original = json.loads(path.read_text())
        if original["status"] not in ("complete", "not_settled"):
            continue
        waves = read_binary(gzip.decompress((path.parent / "waves.raw.gz").read_bytes()))
        with tempfile.TemporaryDirectory(prefix="d22-replay-") as directory:
            temp = Path(directory)
            actual = analyze(waves, original["identity"]["params"], temp)
            assert actual["status"] == original["status"], path
            for file in ("fft.npz", "prior-fft.npz"):
                with np.load(temp / file) as a, np.load(path.parent / file) as b:
                    assert set(a.files) == set(b.files)
                    for key in a.files:
                        np.testing.assert_allclose(
                            a[key], b[key], rtol=1e-11, atol=1e-12, err_msg=str(path)
                        )
        verified.append(str(path.parent.relative_to(HERE)))
    ac = []
    if args.ac:
        for path in sorted((HERE / "harmonic-transfer-v3").glob("*.cir")):
            with tempfile.TemporaryDirectory(prefix="d22-ac-replay-") as directory:
                temp = Path(directory)
                (temp / "case.cir").write_text(path.read_text())
                (temp / ".spiceinit").write_text("set filetype=ascii\n")
                subprocess.run(
                    ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", "case.cir"],
                    cwd=temp,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
                waves = MODEL["read_raw"](temp / "waves.raw")
                with np.load(path.with_suffix(".npz")) as expected:
                    for key in expected.files:
                        np.testing.assert_allclose(
                            waves[key], expected[key], rtol=1e-9, atol=1e-12, err_msg=str(path)
                        )
            ac.append(str(path.relative_to(HERE)))
    if not verified or (args.ac and not ac):
        raise ValueError("no evidence found to replay")
    archive_records = json.loads((HERE / "exploratory-ac-archive.json").read_text())
    archived_count = 0
    for archive_manifest in archive_records:
        archive_path = HERE / archive_manifest["archive"]
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == archive_manifest["sha256"]
        expected_members = archive_manifest["members_sha256"]
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            assert len(members) == len(expected_members)
            assert {member.name for member in members} == set(expected_members)
            for member in members:
                assert member.isfile()
                assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == expected_members[member.name]
        archived_count += len(expected_members)
    report = {"completed_raw_captures_replayed": verified, "AC_decks_rerun": ac, "exploratory_AC_archive_members_verified": archived_count, "status": "PASS"}
    (HERE / "replay-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS:", len(verified), "raw captures;", len(ac), "AC decks;", archived_count, "archived AC files")


if __name__ == "__main__":
    main()
