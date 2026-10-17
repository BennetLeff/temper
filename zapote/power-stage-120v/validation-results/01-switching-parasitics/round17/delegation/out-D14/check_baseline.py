#!/usr/bin/env python3
"""Reject missing, duplicate, stale or changed fresh baseline evidence."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import summarize


def main() -> None:
    frozen = summarize.original_baseline()
    with tempfile.TemporaryDirectory(prefix="d14-baseline-") as directory:
        root = Path(directory)
        for name in ("qualify.json", "near-threshold-qualification.json"):
            (root / name).write_bytes((summarize.HERE / name).read_bytes())
        path = root / "original-reproduction.json"
        with patch.object(summarize, "HERE", root):
            assert summarize.original_baseline() == frozen
            rows = list(frozen.values())
            path.write_text(json.dumps(rows))
            assert summarize.original_baseline() == frozen
            malformed = [rows[:-1], rows + [rows[0]]]
            for key, value in (("complete", False), ("option", "itl100k")):
                changed = copy.deepcopy(rows)
                target = next(r for r in changed if r["complete"])
                target[key] = value
                malformed.append(changed)
            changed = copy.deepcopy(rows)
            next(r for r in changed if not r["complete"])["identity"]["common"] = "changed"
            malformed.append(changed)
            changed = copy.deepcopy(rows)
            next(r for r in changed if r["complete"])["meas"]["vds_ls_die_pk"] += 1
            malformed.append(changed)
            for changed in malformed:
                path.write_text(json.dumps(changed))
                try:
                    summarize.original_baseline()
                except AssertionError:
                    pass
                else:
                    raise AssertionError("Invalid fresh baseline was accepted")
    print(
        "PASS: frozen/fresh baseline parity; missing, duplicate, completion, option, identity and measurement mutations rejected"
    )


if __name__ == "__main__":
    main()
