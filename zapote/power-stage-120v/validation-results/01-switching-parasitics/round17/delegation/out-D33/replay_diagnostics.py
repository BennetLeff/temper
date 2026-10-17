"""Replay preserved rail/solver experiments; retain indeterminate outcomes.

Each deck has a captured parameter dictionary and content hash. Licensed
model paths are resolved locally. This does not regenerate the canonical
full campaign or silently replace its recorded results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import rail_campaign as campaign

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="default: all captured experiments")
    args = parser.parse_args()
    records = json.loads((HERE / "diagnostics/records.json").read_text())
    known = {r["name"] for r in records}
    if set(args.names) - known:
        parser.error("unknown experiment name")
    rows = []
    for record in records:
        if args.names and record["name"] not in args.names:
            continue
        original = HERE / "diagnostics" / record["deck"]
        data = original.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["deck_sha256"]:
            raise ValueError(f"deck hash mismatch: {original}")
        text = data.decode().replace("@PMEG@", str(campaign.f6.PMEG))
        text = text.replace("@TLVH431@", str(campaign.model()))
        folder = HERE / "runs/diagnostics" / record["name"]
        folder.mkdir(parents=True, exist_ok=True)
        deck = folder / "input.cir"
        deck.write_text(text)
        result = campaign.f6.run_d2.run(deck, record["params"], keep=folder)
        (folder / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
        rows.append({"name": record["name"], "aborted": result["aborted"],
                     "failed": result["failed"], "measurements": result["meas"]})
        print(json.dumps(rows[-1]), flush=True)
    (HERE / "diagnostic-reruns.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
