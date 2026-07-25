"""Supersession sweep over docs/plans/.

Paths stay stable: 105 code/config references and `Origin: U5 of docs/plans/...`
provenance breadcrumbs depend on them. Only frontmatter `status` changes.

Classification is evidence-based and conservative. Anything without clear
evidence becomes `stale` (needs human triage) rather than being guessed at.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
from collections import Counter

REPO = pathlib.Path("/Users/bennet/Desktop/temper")
PLANS = REPO / "docs" / "plans"
SWEEP_DATE = "2026-07-25"

# Pinned active by live @req annotations with a registry entry (check_traceability.py:215).
PINNED = {"2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md"}

# Explicitly superseded by STRATEGY v2.0 / METHODOLOGY.md.
SUPERSEDED = {
    "2026-07-24-001-fix-forced-segment-fail-closed-plan.md":
        "fix was correct; framing was not - the gate was reporting an invalid board",
    "2026-07-24-002-feat-pivot-to-fab-ready-board-verdict-plan.md":
        "verdict layer superseded by the provenance-tiered check corpus",
    "2026-07-24-001-feat-close-honesty-tangent-pivot-to-fab-ready-plan.md":
        "premised on the router-capacity reading of the outline failure",
    "2026-07-24-003-feat-firmware-hardware-validation-track-plan.md":
        "re-sequenced under STRATEGY v2 build order",
}

PATH_RE = re.compile(r"`([a-zA-Z0-9_./-]+\.(?:py|rs|c|h|yaml|yml|toml|ato|kicad_pcb))`")
FM_RE = re.compile(r"^---$(.*?)^---$", re.S | re.M)


def classify(name: str, text: str, in_log: bool) -> tuple[str, str]:
    fm = FM_RE.search(text)
    cur = "NONE"
    if fm:
        m = re.search(r"^status:\s*(\S+)", fm.group(1), re.M)
        if m:
            cur = m.group(1)

    if name in PINNED:
        return "active", "pinned by live @req annotations"
    if name in SUPERSEDED:
        return "superseded", SUPERSEDED[name]
    if cur in ("completed", "superseded"):
        return cur, "already declared"

    paths = {q for q in PATH_RE.findall(text) if "/" in q}
    exist = [q for q in paths if (REPO / q).exists()]
    frac = len(exist) / len(paths) if paths else None

    if in_log and (frac is None or frac >= 0.6):
        return "completed", f"referenced in git history; {len(exist)}/{len(paths)} paths exist"
    if frac is not None and frac >= 0.8:
        return "completed", f"{len(exist)}/{len(paths)} named paths exist"
    if frac is not None and len(paths) >= 3 and frac <= 0.25:
        return "abandoned", f"only {len(exist)}/{len(paths)} named paths exist"
    return "stale", "insufficient evidence - needs human triage"


def apply(text: str, status: str, basis: str) -> str:
    fm = FM_RE.search(text)
    block = fm.group(1)
    block = re.sub(r"^status:.*$", f"status: {status}", block, count=1, flags=re.M)
    if "status:" not in block:
        block = f"status: {status}\n" + block.lstrip("\n")
    block = re.sub(r"^swept.*$\n?", "", block, flags=re.M)
    block = block.rstrip("\n") + f"\nswept: {SWEEP_DATE}\nswept_basis: \"{basis}\"\n"
    return text[: fm.start(1)] + block + text[fm.end(1) :]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    log = subprocess.run(
        ["git", "log", "--all", "--pretty=%s%x02%b"], capture_output=True, text=True, cwd=REPO
    ).stdout

    counts: Counter[str] = Counter()
    skipped: list[str] = []
    for p in sorted(PLANS.glob("*.md")):
        text = p.read_text(errors="ignore")
        if not FM_RE.search(text):
            skipped.append(p.name)
            continue
        stem = p.stem
        in_log = stem in log or (re.match(r"^2026-\d\d-\d\d-\d\d\d", stem) and stem[:14] in log)
        status, basis = classify(p.name, text, bool(in_log))
        counts[status] += 1
        if args.write:
            p.write_text(apply(text, status, basis))

    print(f"{'WROTE' if args.write else 'DRY RUN'} — {sum(counts.values())} plans")
    for s, n in counts.most_common():
        print(f"  {s:12} {n}")
    if skipped:
        print(f"  no frontmatter, skipped: {len(skipped)}")
        for s in skipped:
            print(f"    {s}")


if __name__ == "__main__":
    main()
