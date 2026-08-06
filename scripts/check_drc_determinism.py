#!/usr/bin/env python3
"""Measure whether the KiCad DRC measurement is reproducible on an unchanged board.

Runs the ratchet's exact measurement path -- ``temper_placer.validation._drc_api.run_drc``
with ``--all-track-errors``, after regenerating ``pcb/temper.kicad_dru`` from
``scripts/generate_kicad_dru.py`` -- N times over a byte-identical board, and reports
per violation category:

* the observed **count** distribution, and
* whether the **set** of violations was identical run to run.

The set check matters independently of the count: two runs can agree on "199
shorting_items" while disagreeing about which 199, and a ceiling that only watches
counts calls that stable. Violation identity is compared with net *names* normalised
away, because KiCad assigns an arbitrary member net to each shorted copper cluster and
that choice is itself unstable -- a cosmetic difference that would otherwise drown out
the real ones. ``--show-net-churn`` reports it separately.

Exit codes: 0 = every category reproducible, 1 = at least one category is not,
2 = the measurement could not be taken (no kicad-cli, no board).

Anti-vacuity: ``--inject-variance`` deliberately makes the measurement unstable, so
that "reproducible" is a result this tool can fail to produce rather than its only
possible output. See ``scripts/tests/test_check_drc_determinism.py``.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import re
import sys
from pathlib import Path

_NET_IN_BRACKETS = re.compile(r"\[[^\]]*\]")
_NETS_IN_MESSAGE = re.compile(r"\(nets [^)]*\)")

INJECT_NONE = "none"
INJECT_UNPIN = "unpin"
INJECT_SYNTHETIC = "synthetic"


def _repo_root() -> Path:
    path = Path(__file__).resolve().parent
    while not (path / ".git").exists() and path != path.parent:
        path = path.parent
    return path


def violation_identity(rule: str, message: str, items: list[str], *, blind_nets: bool) -> str:
    """A stable identity for one violation, independent of report order.

    ``items`` are kicad-cli's raw item descriptions. They are sorted, because the
    order of the two sides of a pairwise violation is not guaranteed; when nets are
    blinded they must be blinded *before* sorting, or a renamed net silently reorders
    the pair and looks like a different violation.
    """
    if blind_nets:
        message = _NETS_IN_MESSAGE.sub("(nets ..)", message)
        items = [_NET_IN_BRACKETS.sub("[]", item) for item in items]
    return "|".join([rule, message, *sorted(items)])


def set_digest(identities: list[str]) -> str:
    digest = hashlib.sha256()
    for identity in sorted(identities):
        digest.update(identity.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def _sample(pcb_path: Path, *, inject: str, sample_index: int) -> dict[str, list[dict]]:
    """One DRC measurement, grouped by category."""
    from temper_placer.validation._drc_api import run_drc

    result = run_drc(pcb_path)
    by_category: dict[str, list[dict]] = collections.defaultdict(list)
    for violation in result.errors:
        by_category[violation.rule].append(
            {"message": violation.message, "items": list(violation.items)}
        )
    for warning in result.warnings:
        by_category["W:" + warning.rule].append({"message": warning.message, "items": []})

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


def analyse(runs: list[dict], *, blind_nets: bool = True) -> list[dict]:
    categories = sorted({category for run in runs for category in run})
    report = []
    for category in categories:
        counts = collections.Counter(len(run.get(category, [])) for run in runs)
        digests = collections.Counter(
            set_digest(
                [
                    violation_identity(category, v["message"], v["items"], blind_nets=blind_nets)
                    for v in run.get(category, [])
                ]
            )
            for run in runs
        )
        report.append(
            {
                "category": category,
                "counts": dict(sorted(counts.items())),
                "count_stable": len(counts) == 1,
                "set_stable": len(digests) == 1,
                "digests": dict(digests),
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
                    match = _NET_IN_BRACKETS.search(item)
                    if match:
                        seen[_NET_IN_BRACKETS.sub("[]", item)].add(match.group(0)[1:-1])
    return {item: sorted(nets) for item, nets in sorted(seen.items()) if len(nets) > 1}


def render(report: list[dict], runs: list[dict]) -> bool:
    print(f"\n{len(runs)} samples\n")
    print(f"{'category':26s} {'counts':30s} {'set':>10s}")
    unstable = []
    for row in report:
        verdict = "stable" if row["set_stable"] else "UNSTABLE"
        if not row["count_stable"] or not row["set_stable"]:
            unstable.append(row["category"])
        print(f"{row['category']:26s} {str(row['counts']):30s} {verdict:>10s}")
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
