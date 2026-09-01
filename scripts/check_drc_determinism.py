#!/usr/bin/env python3
"""Measure whether the KiCad DRC measurement is reproducible on an unchanged board.

Runs the ratchet's exact measurement path -- ``temper_placer.validation._drc_api.run_drc``
with ``--all-track-errors``, after regenerating ``pcb/temper.kicad_dru`` from
``scripts/generate_kicad_dru.py`` -- N times over a byte-identical board, and reports
per violation category:

* the observed **count** distribution, and
* whether the Rust-owned engineering-semantic **multiset** agrees, and
* the raw provider-item fringe KiCad changed between samples.

The semantic check matters independently of the count: two runs can agree on
"199 shorting_items" while disagreeing about which 199.  Identity, multiset
digests, intersections, unions, and fringes are all computed by
``temper_drc_rs``; this script only transports raw KiCad records and renders
the resulting evidence.

Exit codes: 0 = every category reproducible, 1 = at least one category is not,
2 = the measurement could not be taken (no kicad-cli, no board).

Anti-vacuity: ``--inject-variance`` deliberately makes the measurement unstable, so
that "reproducible" is a result this tool can fail to produce rather than its only
possible output. See ``scripts/tests/test_check_drc_determinism.py``.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

_NET_IN_BRACKETS = re.compile(r"\[[^\]]*\]")

INJECT_NONE = "none"
INJECT_UNPIN = "unpin"
INJECT_SYNTHETIC = "synthetic"


def _repo_root() -> Path:
    path = Path(__file__).resolve().parent
    while not (path / ".git").exists() and path != path.parent:
        path = path.parent
    return path


def _evidence_envelope(samples: list[list[dict]]) -> dict:
    """Thin transport shim to the Rust-owned identity/envelope kernel."""
    import temper_drc_rs  # type: ignore[import-untyped]

    return json.loads(
        temper_drc_rs.drc_evidence_envelope_json(json.dumps(samples, separators=(",", ":")))
    )


def _group_raw_findings(raw_findings: list[dict]) -> dict[str, list[dict]]:
    """Group lossless raw records; severity is part of the category namespace."""
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for finding in raw_findings:
        category = str(finding.get("type", "unknown"))
        if finding.get("severity") == "warning":
            category = "W:" + category
        transported = dict(finding)
        transported["type"] = category
        grouped[category].append(transported)
    return grouped


def _sample(pcb_path: Path, *, inject: str, sample_index: int) -> dict[str, list[dict]]:
    """One DRC measurement, grouped by category."""
    from temper_placer.validation._drc_api import run_drc_measurement

    measurement = run_drc_measurement(pcb_path, strict=True)
    by_category = _group_raw_findings(measurement.raw_findings)

    if inject == INJECT_SYNTHETIC and sample_index % 2 == 1:
        # Deliberate, obviously-fake variance: drop one violation from a category
        # on every other sample. If the harness still reports "reproducible", the
        # harness is broken and every clean result it has ever produced is void.
        for _category, violations in sorted(by_category.items()):
            if violations:
                violations.pop()
                break
    return by_category


def measure(pcb_path: Path, samples: int, *, inject: str = INJECT_NONE) -> list[dict]:
    runs = []
    for index in range(samples):
        runs.append(_sample(pcb_path, inject=inject, sample_index=index))
        print(f"  sample {index + 1}/{samples}", file=sys.stderr, flush=True)
    return runs


def analyse(runs: list[dict]) -> list[dict]:
    from temper_placer.validation._drc_api import drc_cap_for

    categories = sorted({category for run in runs for category in run})
    report = []
    for category in categories:
        counts = collections.Counter(len(run.get(category, [])) for run in runs)
        samples = []
        for run in runs:
            sample = []
            for finding in run.get(category, []):
                transported = dict(finding)
                transported["type"] = category
                sample.append(transported)
            samples.append(sample)
        envelope = _evidence_envelope(samples)
        digests = collections.Counter(
            sample["observation_digest"][:12] for sample in envelope["samples"]
        )
        # Cap-saturation annotation: a measured count at exactly its
        # category's KiCad reporting cap (ERROR_LIMIT 199 /
        # EXTENDED_ERROR_LIMIT 499 -- see temper_drc_rs.drc_count) is a
        # FLOOR, not a count. "Reproducible" for such a category means
        # "reproducibly saturated", which is a different (and weaker)
        # statement than "the truth is known" -- the caller must not read a
        # stable 199 as "exactly 199 violations". The "W:" prefix the
        # warning arm uses is a display convention, not a violation type.
        bare_category = category[2:] if category.startswith("W:") else category
        cap = drc_cap_for(bare_category)
        at_cap = cap is not None and any(c == cap for c in counts)
        report.append(
            {
                "category": category,
                "counts": dict(sorted(counts.items())),
                "count_stable": len(counts) == 1,
                "set_stable": envelope["observation"]["stable"],
                "digests": dict(digests),
                "intersection_size": envelope["observation"]["intersection_size"],
                "union_size": envelope["observation"]["union_size"],
                "unstable_fringe": envelope["observation"]["unstable_fringe"],
                "raw_set_stable": envelope["raw"]["stable"],
                "raw_digests": [sample["raw_digest"] for sample in envelope["samples"]],
                "raw_intersection_size": envelope["raw"]["intersection_size"],
                "raw_union_size": envelope["raw"]["union_size"],
                "raw_unstable_fringe": envelope["raw"]["unstable_fringe"],
                "at_cap": at_cap,
            }
        )
    return report


def net_churn(runs: list[dict]) -> dict[str, list[str]]:
    """Copper items whose reported net NAME differed between runs, keyed by the
    item description with the net blinded out."""
    seen: dict[str, set[str]] = collections.defaultdict(set)
    for run in runs:
        for violations in run.values():
            for violation in violations:
                for item in violation["items"]:
                    description = item.get("description", "")
                    match = _NET_IN_BRACKETS.search(description)
                    if match:
                        seen[_NET_IN_BRACKETS.sub("[]", description)].add(match.group(0)[1:-1])
    return {item: sorted(nets) for item, nets in sorted(seen.items()) if len(nets) > 1}


def render(report: list[dict], runs: list[dict]) -> bool:
    print(f"\n{len(runs)} samples\n")
    print(f"{'category':26s} {'counts':30s} {'semantic':>10s} {'raw':>10s}")
    unstable = []
    for row in report:
        verdict = "stable" if row["set_stable"] else "UNSTABLE"
        if not row["count_stable"] or not row["set_stable"]:
            unstable.append(row["category"])
        counts_cell = str(row["counts"])
        if row["at_cap"]:
            counts_cell += "  [at cap — floor, not a count]"
        raw_verdict = "stable" if row["raw_set_stable"] else "CHURN"
        print(f"{row['category']:26s} {counts_cell:30s} {verdict:>10s} {raw_verdict:>10s}")
    if unstable:
        print(f"\nNOT REPRODUCIBLE: {', '.join(unstable)}")
    else:
        print("\nREPRODUCIBLE: every category identical across all samples.")
    return not unstable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pcb", default="pcb/temper.kicad_pcb")
    parser.add_argument("-n", "--samples", type=int, default=120)
    parser.add_argument(
        "--inject-variance",
        choices=[INJECT_NONE, INJECT_UNPIN, INJECT_SYNTHETIC],
        default=INJECT_NONE,
        help=(
            "anti-vacuity self-test: 'unpin' removes the single-thread pin from the "
            "real measurement, 'synthetic' drops a violation on every other sample. "
            "Both MUST make this tool report NOT REPRODUCIBLE."
        ),
    )
    parser.add_argument("--show-net-churn", action="store_true")
    parser.add_argument(
        "--no-regen-dru",
        action="store_true",
        help="skip regenerating pcb/temper.kicad_dru (the CI gate always regenerates)",
    )
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))
    sys.path.insert(0, str(repo_root / "scripts"))

    pcb_path = Path(args.pcb)
    if not pcb_path.is_absolute():
        pcb_path = repo_root / pcb_path
    if not pcb_path.exists():
        print(f"board not found: {pcb_path}", file=sys.stderr)
        return 2

    if not args.no_regen_dru:
        import generate_kicad_dru

        generate_kicad_dru.OUTPUT_PATH.write_text(
            generate_kicad_dru.generate_dru(), encoding="utf-8"
        )
        print(f"regenerated {generate_kicad_dru.OUTPUT_PATH} from scripts/generate_kicad_dru.py")

    from temper_placer.validation._drc_api import get_kicad_cli_version, is_kicad_cli_available

    if not is_kicad_cli_available():
        print("kicad-cli not available -- cannot measure", file=sys.stderr)
        return 2
    print(f"platform={sys.platform} kicad-cli={get_kicad_cli_version()}")

    if args.inject_variance == INJECT_UNPIN:
        os.environ["TEMPER_DRC_THREAD_PIN"] = "0"
        print("INJECTED VARIANCE: single-thread pin disabled")
    elif args.inject_variance == INJECT_SYNTHETIC:
        print("INJECTED VARIANCE: one violation dropped on every other sample")

    runs = measure(pcb_path, args.samples, inject=args.inject_variance)
    reproducible = render(analyse(runs), runs)

    if args.show_net_churn:
        churn = net_churn(runs)
        print(f"\ncopper items whose reported net NAME changed between samples: {len(churn)}")
        for item, nets in list(churn.items())[:20]:
            print(f"  {item}  ->  {nets}")

    return 0 if reproducible else 1


if __name__ == "__main__":
    sys.exit(main())
