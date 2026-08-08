#!/usr/bin/env python3
"""Deterministic component-value/MPN-defect mutations on a synthetic fixture
-- the mutation half of the component-defect corpus (STRATEGY.md build
order step 4, 2026-08-07). Mirrors ``board_defect_mutator.py``'s discipline
(mutate a copy, never the source; self-verify the mutation actually took
effect) for a different domain: a passive component's declared value and
MPN, checked by ``scripts/mpn_fabrication_gate.py``, instead of PCB
geometry checked by kicad-cli.

``scripts/component_defect_fixtures/clean.ato`` is the committed baseline
(real, verified-correct: 100 kOhm 1%, Yageo RC0603FR-07100KL -- the actual
replacement part from the real 2026-07-27 UVL-02 fix). It is NEVER modified
by anything in this module, and it is not under ``elec/`` -- nothing in
this corpus touches ``elec/src`` (task rule: do not modify elec/). Every
mutation function reads the clean fixture, replaces one named ref's
``.value``/``.mpn`` line pair with a real historical fabricated-part
incident's values, and writes a NEW file to ``out_path``.

The two defect classes, both real incidents (docs/STRATEGY.md, "Two more
bad parts, both in protection circuits" / "Tempco was never analysed, and a
fourth part is fabricated", 2026-07-27):

  fabricated-mpn: r_target's value+mpn replaced with 61.3 kOhm /
    ``ERA-3AEB6132V`` -- not an E96/E192 value, and the MPN is internally
    consistent with that invented value but appears at no real distributor.
  mpn-value-mismatch: r_target's mpn replaced with ``RC0603FR-0710KL`` (a
    REAL, orderable Yageo part whose own encoding is 10 kOhm) while the
    declared value stays 100 kOhm -- a 10x mismatch between a real part
    number and the value the design assumes it has (the real UVL-02 bug).

Usage:
    python scripts/component_defect_mutator.py --mutation fabricated-mpn \\
        --out /tmp/m.ato
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CLEAN_FIXTURE = Path(__file__).resolve().parent / "component_defect_fixtures" / "clean.ato"

MUTATIONS = ("fabricated-mpn", "mpn-value-mismatch")

# mutation name -> (ref, new value line body (without the "ref.value = "
# prefix), new mpn string). Both real historical incidents -- see module
# docstring and docs/STRATEGY.md's 2026-07-27 entries.
_MUTATION_PARAMS: dict[str, dict[str, str]] = {
    "fabricated-mpn": {
        "ref": "r_target",
        "value_body": "61.3kohm +/- 0.1%",
        "mpn": "ERA-3AEB6132V",
    },
    "mpn-value-mismatch": {
        "ref": "r_target",
        "value_body": "100.0kohm +/- 1.0%",
        "mpn": "RC0603FR-0710KL",
    },
}


class MutationError(RuntimeError):
    """Raised when a mutation's target ref does not resolve against the
    clean fixture, or when the written file fails to differ from the clean
    fixture in the expected way. Fail-closed: a mutation that cannot prove
    it changed anything must never silently report a mutated board."""


@dataclass
class MutationResult:
    mutation: str
    seed: int
    clean_sha256: str
    mutated_sha256: str
    seed_content_sha256: str
    summary: dict[str, Any]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _value_line_re(ref: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(ref)}\.value\s*=.*$", re.MULTILINE)


def _mpn_line_re(ref: str) -> re.Pattern[str]:
    return re.compile(rf'^{re.escape(ref)}\.mpn\s*=\s*".*"$', re.MULTILINE)


def mutate_value_mpn(
    clean_path: Path,
    out_path: Path,
    ref: str,
    value_body: str,
    mpn: str,
    seed: int,
    mutation_name: str,
) -> MutationResult:
    """Replace *ref*'s ``.value``/``.mpn`` lines in *clean_path* with
    *value_body*/*mpn*, writing the result to *out_path*. Fails closed
    (raises :class:`MutationError`) if either line is not found in the
    clean fixture, or if the written file is not both (a) different from
    the clean fixture and (b) contains the exact new lines -- the same
    "prove the injected artifact differs, independently of the gate under
    test" discipline ``board_defect_mutator.py`` follows (METHODOLOGY.md
    Sec. 5).
    """
    clean_text = clean_path.read_text(encoding="utf-8")
    clean_hash = sha256_text(clean_text)

    value_re = _value_line_re(ref)
    mpn_re = _mpn_line_re(ref)
    if not value_re.search(clean_text):
        raise MutationError(f"clean fixture has no {ref}.value line to replace")
    if not mpn_re.search(clean_text):
        raise MutationError(f"clean fixture has no {ref}.mpn line to replace")

    new_value_line = f"{ref}.value = {value_body}"
    new_mpn_line = f'{ref}.mpn = "{mpn}"'
    mutated_text = value_re.sub(new_value_line, clean_text, count=1)
    mutated_text = mpn_re.sub(new_mpn_line, mutated_text, count=1)

    if mutated_text == clean_text:
        raise MutationError(
            f"mutation {mutation_name!r} produced byte-identical output -- "
            "the injector is a no-op (this is exactly the failure class "
            "docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md "
            "documents: a seeded defect that did not change anything)"
        )
    if new_value_line not in mutated_text or new_mpn_line not in mutated_text:
        raise MutationError(
            f"mutation {mutation_name!r} did not land the expected lines "
            f"({new_value_line!r} / {new_mpn_line!r}) in the written file"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(mutated_text, encoding="utf-8")
    mutated_hash = sha256_text(mutated_text)

    return MutationResult(
        mutation=mutation_name,
        seed=seed,
        clean_sha256=clean_hash,
        mutated_sha256=mutated_hash,
        seed_content_sha256=sha256_text(f"{seed}:{mutated_hash}"),
        summary={
            "ref": ref,
            "new_value_line": new_value_line,
            "new_mpn_line": new_mpn_line,
        },
    )


def apply_mutation(mutation: str, out_path: Path, seed: int) -> MutationResult:
    if mutation not in _MUTATION_PARAMS:
        raise MutationError(
            f"unknown mutation {mutation!r} (known: {sorted(_MUTATION_PARAMS)})"
        )
    params = _MUTATION_PARAMS[mutation]
    return mutate_value_mpn(
        CLEAN_FIXTURE,
        out_path,
        params["ref"],
        params["value_body"],
        params["mpn"],
        seed,
        mutation,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutation", choices=sorted(_MUTATION_PARAMS), required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        result = apply_mutation(args.mutation, args.out, args.seed)
    except MutationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    import json

    print(json.dumps(result.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
