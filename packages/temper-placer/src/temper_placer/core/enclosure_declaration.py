"""Load ``elec/enclosure_manifest.yaml`` and derive this board's pollution
degree and reinforced HV<->SELV creepage requirement from it.

This module is the *thin* half of the mechanism. Every rule that matters --
the schema, the placeholder checks, the staleness (content-digest) check, the
PD2-exception precondition, the Table 17 lookup and the clause-29.2.3
doubling -- lives in Rust, in
``packages/temper-design-bundle/src/enclosure.rs``, and is reached through
``temper_design_bundle_python.resolve_enclosure_declaration``. Read that
module's docstring for the derivation, the standards citations, and the
argument for each check. Nothing here re-implements any of it: a second
Python home for a safety rule is exactly what AGENTS.md forbids, and this
particular rule already had three homes' worth of drift behind it.

What this module *does* own, because Rust deliberately does not:

* **Finding the declaration.** One repo-relative path, resolved from this
  file's own location, with no environment-variable override -- an env var
  that can redirect a safety declaration is a hole, not a feature.
* **Resolving the verification commit.** Rust takes ``evidence_resolved`` as
  an *input* because resolving it needs a git object store, which does not
  exist on the ``wasm32`` tier and must not be assumed by a library import.

Fail-closed contract
--------------------
Every failure raises :class:`EnclosureDeclarationError` (a ``RuntimeError``).
There is no fallback value, no default classification, and no "warn and
continue" path -- the only thing a silent fallback could produce is a safety
number chosen by something other than the declaration. Concretely, all of
these are hard errors:

* the declaration file is missing, empty, unparseable, or has an unknown
  schema version;
* it carries an unknown key (including a hand-written ``pollution_degree``:
  declaring the answer next to the evidence is the defect this replaces);
* a verification field is blank or a placeholder;
* ``measured_at_commit`` is not 40 lowercase hex characters;
* the declared facts do not match ``declared_state_sha256`` -- i.e. the
  physical claim was edited after the verification that backs it;
* the declaration claims the PD2 exception and its verification commit does
  not resolve in this repository.

Cost, and why the git call is conditional
-----------------------------------------
The commit is resolved **only when the declared facts claim the PD2
exception**, because that is the only case in which its resolvability changes
the answer. Under the current (PD3) declaration nothing shells out to git, so
importing :mod:`temper_placer.core.isolation_constants` stays a pure file
read and is safe in a shallow clone, a container without git, or a test
tmpdir. When PD2 *is* claimed the git call is mandatory and any failure --
git missing, a shallow clone, a timeout, a non-commit object -- is treated as
"not resolved", which makes PD2 unselectable. Failing in the conservative
direction is the whole point; a checker that cannot tell a fake SHA from a
real one must not be allowed to grant the smaller creepage figure.

``scripts/check_enclosure_declaration.py`` re-checks resolvability
*unconditionally* (via ``check_evidence_provenance.verify_commits_exist``, the
repo's canonical batch mechanism, which fails closed on a shallow clone), so a
dangling commit under PD3 is still caught in CI -- it just does not wedge an
import.

What this cannot do
-------------------
No gate makes a physical enclosure real. See
``EnclosureResolution.limitation()``, which every consumer of the number can
reach in one call, and the declaration file's own header.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import temper_design_bundle_python as _tdb

__all__ = [
    "DECLARATION_PATH",
    "EnclosureDeclarationError",
    "EnclosureResolution",
    "resolve_declaration",
    "reinforced_barrier_width_mm",
]


class EnclosureDeclarationError(RuntimeError):
    """The enclosure declaration is missing, malformed, stale, or unbacked.

    Deliberately a subclass of ``RuntimeError`` rather than a bare
    ``ValueError``: it is raised at import time by
    :mod:`temper_placer.core.isolation_constants`, and a distinct type lets a
    caller (or a test) tell "the declaration is broken" apart from any other
    ``ValueError`` crossing the pyo3 boundary.
    """


# The declaration lives beside elec/domain_manifest.yaml -- the working
# precedent this file's shape follows, and where a reader looking for "what
# does this design declare about itself" already looks.
#
# Resolved from this module's own location, never from the cwd and never from
# an environment variable: an env var that can redirect a safety declaration
# is a hole, not a feature, and a cwd-relative path would make the enforced
# creepage figure depend on where a script happened to be invoked from.
#
# Five parents up from
# packages/temper-placer/src/temper_placer/core/enclosure_declaration.py is
# the repo root under this repo's editable install. The ancestor walk is a
# robustness measure for any layout where that arithmetic does not hold (a
# non-editable install, a vendored copy) -- it does NOT weaken anything: if
# no ancestor carries the declaration, the fixed arithmetic still supplies a
# path, and reading it fails closed with EnclosureDeclarationError. There is
# no branch here that yields a classification without a declaration.
_RELATIVE = Path("elec") / "enclosure_manifest.yaml"


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / _RELATIVE).is_file():
            return candidate
    return here.parents[5]


_REPO_ROOT = _discover_repo_root()
DECLARATION_PATH = _REPO_ROOT / _RELATIVE

_FORTY_HEX = 40


@dataclass(frozen=True)
class EnclosureResolution:
    """The declaration's verdict: the classification and the number it implies.

    Every field is derived. Nothing here is written down anywhere as a
    literal, and there is deliberately no constructor that takes a width.
    """

    pollution_degree: int
    barrier_width_mm: float
    provenance: str
    """Full provenance chain of ``barrier_width_mm``, back to the recovered
    Table 17 cell and the clause that doubles it."""
    sealed: bool
    gasketed: bool
    outside_forced_air_path: bool
    verified_on: str
    measured_at_commit: str
    pd2_exception_claimed: bool
    """True when the declared facts made the verification commit's
    resolvability load-bearing."""
    source_path: Path

    def limitation(self) -> str:
        """The honest limit on what any of this proves.

        Sourced from the Rust constant so the sentence has exactly one home
        and cannot drift between the declaration, the gate and this module.
        """
        return _tdb.enclosure_mechanism_limitation()


def _commit_resolves(sha: str, repo_root: Path) -> bool:
    """Whether *sha* names a real commit object in *repo_root*'s object store.

    Conservative by construction: **every** failure mode -- git absent, a
    timeout, a non-zero exit, a shallow clone, an object that resolves to a
    blob/tree/tag rather than a commit -- returns ``False``, which makes the
    PD2 exception unselectable. A resolvability check that cannot distinguish
    a fabricated SHA from a real one must never answer "resolved".

    The gate uses ``check_evidence_provenance.verify_commits_exist`` instead,
    which batches and raises (rather than returning False) on a shallow clone
    so CI reports a tool error rather than a silent PD3 pin. This function is
    the strict, import-safe subset of that behaviour; the two agree on every
    input where the batch version does not raise, and
    ``scripts/tests/test_check_enclosure_declaration.py`` pins that agreement.
    """
    if len(sha) != _FORTY_HEX or any(c not in "0123456789abcdef" for c in sha):
        return False
    if (repo_root / ".git" / "shallow").exists():
        return False
    try:
        completed = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and completed.stdout.strip() == "commit"


def resolve_declaration(
    path: Path | None = None, repo_root: Path | None = None
) -> EnclosureResolution:
    """Read, validate and evaluate the enclosure declaration at *path*.

    *path* defaults to :data:`DECLARATION_PATH`; *repo_root* (the git
    repository whose object store a PD2 claim's verification commit must
    resolve in) defaults to this checkout. Both are explicit parameters rather
    than environment lookups so a test can point at a fixture without any
    global switch existing that production could also be flipped by.

    Raises :class:`EnclosureDeclarationError` on every failure; never returns
    a fallback.
    """
    declaration_path = DECLARATION_PATH if path is None else Path(path)
    resolved_root = _REPO_ROOT if repo_root is None else Path(repo_root)

    try:
        yaml_text = declaration_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise EnclosureDeclarationError(
            f"enclosure declaration not found at {declaration_path}. This file "
            "is what selects the board's pollution degree, and therefore its "
            "reinforced HV<->SELV creepage requirement; without it no "
            "classification can be derived and none is assumed. See "
            "packages/temper-design-bundle/src/enclosure.rs."
        ) from exc
    except OSError as exc:
        raise EnclosureDeclarationError(
            f"enclosure declaration at {declaration_path} could not be read: {exc}"
        ) from exc

    # Two-phase on purpose. The first call passes evidence_resolved=False,
    # which is safe for any declaration and *sufficient* for a PD3 one -- so
    # the common path never shells out to git. Only a declaration that
    # actually claims the PD2 exception reaches the second call, and it does
    # so having already been told, by the Rust rule itself, that the exception
    # is what it is claiming. Python never decides that; it only supplies the
    # git answer the Rust rule asked for.
    try:
        resolution = _tdb.resolve_enclosure_declaration(yaml_text, False)
    except ValueError as exc:
        message = str(exc)
        if "does not resolve to a commit" not in message:
            raise EnclosureDeclarationError(
                f"{declaration_path}: {message}"
            ) from exc
        # PD2 is claimed. Resolvability is now load-bearing -- go and check it.
        sha = _extract_commit(yaml_text)
        if not _commit_resolves(sha, resolved_root):
            raise EnclosureDeclarationError(
                f"{declaration_path}: {message}"
            ) from exc
        try:
            resolution = _tdb.resolve_enclosure_declaration(yaml_text, True)
        except ValueError as exc2:  # pragma: no cover - defensive
            raise EnclosureDeclarationError(
                f"{declaration_path}: {exc2}"
            ) from exc2

    return EnclosureResolution(
        pollution_degree=resolution.pollution_degree(),
        barrier_width_mm=resolution.barrier_width_mm(),
        provenance=resolution.provenance_debug(),
        sealed=resolution.sealed(),
        gasketed=resolution.gasketed(),
        outside_forced_air_path=resolution.outside_forced_air_path(),
        verified_on=resolution.verified_on(),
        measured_at_commit=resolution.measured_at_commit(),
        pd2_exception_claimed=resolution.pd2_exception_claimed(),
        source_path=declaration_path,
    )


def _extract_commit(yaml_text: str) -> str:
    """Pull ``measured_at_commit`` out of a declaration Rust already accepted
    the *shape* of.

    Only ever called after ``resolve_enclosure_declaration`` has parsed the
    document and validated that field, so this is a lookup, not a parser: it
    cannot admit a value the Rust schema would have rejected. Returning ``""``
    on a miss is safe -- :func:`_commit_resolves` rejects it, PD2 stays
    unselectable, and the original Rust error is what surfaces.
    """
    for raw in yaml_text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("measured_at_commit:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return ""


@lru_cache(maxsize=1)
def reinforced_barrier_width_mm() -> float:
    """The derived reinforced HV<->SELV creepage requirement, in millimetres.

    This is the single call ``MIN_BARRIER_WIDTH_MM`` is assigned from. Cached
    because it is read at import time by several modules and the declaration
    cannot change within a process; the cache is keyed on nothing because the
    path is fixed -- pass an explicit path to :func:`resolve_declaration` for
    any other file (tests do exactly that, and are therefore uncached).
    """
    return resolve_declaration().barrier_width_mm
