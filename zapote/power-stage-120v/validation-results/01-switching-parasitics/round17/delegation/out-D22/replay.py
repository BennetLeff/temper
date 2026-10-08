#!/usr/bin/env python3
"""Recompute every completed binary capture; optionally rerun final AC decks."""

import argparse
import gzip
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from filter_stage import MODEL
from pack_spectra import verify_archive
from periodic import analyze, read_binary

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
    archived_count = sum(verify_archive(record) for record in archive_records)
    spectral_manifest = HERE / "receiver-spectra-archive.json"
    spectral_count = (
        sum(verify_archive(record) for record in json.loads(spectral_manifest.read_text()))
        if spectral_manifest.exists() else 0
    )
    report = {"completed_raw_captures_replayed": verified, "AC_decks_rerun": ac, "exploratory_AC_archive_members_verified": archived_count, "receiver_spectrum_archive_members_verified": spectral_count, "status": "PASS"}
    (HERE / "replay-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS:", len(verified), "raw captures;", len(ac), "AC decks;", archived_count, "archived AC files;", spectral_count, "archived receiver CSVs")


if __name__ == "__main__":
    main()
