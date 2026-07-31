#!/usr/bin/env python3
"""Known-failure-reason pinning: make a known-red test's failure *reason*
falsifiable, so a *different* failure absorbed by the same red status is loud.

Motivation
----------
PR #460 nearly merged a destructive HV short (``DC_BUS+`` shorted to
``SW_NODE`` across the half-bridge IGBTs on the golden board). CI missed it
because ``test_golden_board_drc_regression`` was already failing for an
unrelated, pre-existing reason (a writer that drops solved rotation --
``docs/evidence/2026-07-30-placement-writer-rotation.md``). Standard triage
discipline in this repo is "reproduce on ``origin/main`` before attributing a
failure to your change" -- which compares *which tests fail*, not *why they
fail*. A test red for reason A silently absorbed a new, far worse reason B.

This module lets a test declare, in a checked-in registry
(``known-failure-pins.yaml``), the *signature* of a failure it is already
known to have -- not just its name. When the test's assertions fail, it
compares the observed failure signature against the declared one and
annotates the ``AssertionError`` message:

* signature matches the pin  -> ``[KNOWN-FAILURE, pinned]`` prefix, citing
  the linked evidence doc. Still a FAILING test (red in CI) -- this is
  deliberately not xfail (see "Why not xfail" below) -- but the message says
  unambiguously "this is the known issue."
* signature differs from the pin -> a loud, visually distinct
  ``KNOWN-FAILURE PIN MISMATCH`` block showing both signatures side by side,
  explicitly warning that this may be a *new* regression hiding behind a
  stale pin.
* no pin declared for this test at all -> the message is returned completely
  unchanged. This is the anti-suppression guarantee: a test with no
  declaration gets zero help from this module, in either direction.

Why not xfail
--------------
This repo's standing rule forbids ``pytest.xfail``/``skipif`` as a way to
resolve a failure: ``xfail`` reports the test as expected-to-fail, which
removes it from the set of things CI treats as red. That is exactly the
signal this mechanism exists to preserve -- a pinned test still fails, still
shows red, still requires a human to look at it. All this module changes is
*what the failure message says*, not whether the test failed.

Anti-suppression design (why this cannot become an xfail list)
----------------------------------------------------------------
1. **A pin cannot mask an undeclared failure.** ``annotate_failure`` for a
   nodeid with no registry entry is the identity function on the message.
   There is no "declare everything known" shortcut -- each pin names one
   test and one exact signature.
2. **Pins expire.** Each entry carries ``declared``/``expires`` dates. Past
   expiry, ``check_signature`` treats the pin as absent (status
   ``"expired"``, itself reported loudly) -- an expired pin does not keep
   matching forever by default.
3. **Pins require a paper trail.** ``issue`` must point at a real,
   checked-in ``docs/evidence/`` or ``docs/solutions/`` file. No bare claims.
4. **The registry is a ratchet, not a wishlist.** ``main()`` below is the CI
   gate (``uv run python scripts/known_failure_pins.py``): it fails the
   build if the live-pin count exceeds ``MAX_LIVE_PINS``, if any pin is
   past its expiry (renew-or-delete, forced), if any pin's total lifetime
   exceeds ``MAX_PIN_LIFETIME_DAYS`` (no permanent waivers), if an
   ``issue`` link is dangling, or if a pinned nodeid no longer resolves to
   a real test (a pin cannot outlive the test it was written for). This is
   the same shape as ``tools/loc_cap_check.py``'s allowlist ratchet
   (baseline + required justification + stale-entry detection), applied to
   failure *reasons* instead of line counts.

Registry format (``known-failure-pins.yaml``, repo root)
----------------------------------------------------------
::

    <pytest nodeid>:
      issue: docs/evidence/<file>.md   # must exist on disk
      declared: YYYY-MM-DD
      expires: YYYY-MM-DD              # <= MAX_PIN_LIFETIME_DAYS after declared
      reason: >
        Human-readable explanation of the known defect.
      signature:
        <violation-type>: <count>      # exact, comparable-by-equality dict
        ...

Usage from a test
------------------
::

    signature = dict(sorted(fixable_counts.items()))
    try:
        assert shorting == 0, "..."
        ...
    except AssertionError as exc:
        raise AssertionError(
            annotate_failure(request.node.nodeid, signature, str(exc))
        ) from exc

CI gate
-------
::

    uv run python scripts/known_failure_pins.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_REGISTRY_PATH = REPO_ROOT / "known-failure-pins.yaml"

# Ratchet caps -- deliberately small. This mechanism pins ONE test's failure
# reason at a time with full scrutiny; it is not a general xfail list. Raise
# either constant only in the same PR that adds the pin justifying it, so a
# reviewer sees the cap move in the diff.
MAX_LIVE_PINS = 3
MAX_PIN_LIFETIME_DAYS = 21


class PinRegistryError(ValueError):
    """The registry file itself is structurally invalid."""


@dataclass(frozen=True)
class KnownFailurePin:
    nodeid: str
    issue: str
    declared: dt.date
    expires: dt.date
    reason: str
    signature: dict[str, Any]


@dataclass(frozen=True)
class PinVerdict:
    status: str  # "unpinned" | "known" | "changed" | "expired"
    message: str


def _parse_date(value: Any, *, field_name: str, nodeid: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except (ValueError, TypeError) as e:
        raise PinRegistryError(
            f"pin {nodeid!r}: {field_name} {value!r} is not an ISO date (YYYY-MM-DD)"
        ) from e


def load_pins(path: Path = PIN_REGISTRY_PATH) -> dict[str, KnownFailurePin]:
    """Load and validate the pin registry. Missing file == no pins (not an error:
    a repo with nothing pinned is the common, healthy state)."""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise PinRegistryError(f"{path}: top-level YAML must be a mapping of nodeid -> pin")

    pins: dict[str, KnownFailurePin] = {}
    for nodeid, entry in raw.items():
        if not isinstance(entry, dict):
            raise PinRegistryError(f"pin {nodeid!r}: entry must be a mapping")
        required = ("issue", "declared", "expires", "reason", "signature")
        missing = [k for k in required if k not in entry]
        if missing:
            raise PinRegistryError(f"pin {nodeid!r}: missing required field(s) {missing}")
        signature = entry["signature"]
        if not isinstance(signature, dict) or not signature:
            raise PinRegistryError(
                f"pin {nodeid!r}: signature must be a non-empty mapping of "
                f"violation-type -> count. An empty/missing signature would match "
                f"any failure, which is exactly the suppression hole this format "
                f"exists to close."
            )
        pins[nodeid] = KnownFailurePin(
            nodeid=nodeid,
            issue=str(entry["issue"]),
            declared=_parse_date(entry["declared"], field_name="declared", nodeid=nodeid),
            expires=_parse_date(entry["expires"], field_name="expires", nodeid=nodeid),
            reason=str(entry["reason"]),
            signature=dict(signature),
        )
    return pins


def check_signature(
    nodeid: str,
    actual_signature: dict[str, Any],
    *,
    pins: dict[str, KnownFailurePin] | None = None,
    today: dt.date | None = None,
) -> PinVerdict:
    """Compare an observed failure signature against the registry.

    Pure function of (nodeid, signature, pins, today) -- no I/O beyond the
    optional ``load_pins()`` default, so it is trivial to unit-test with
    synthetic pins and dates (see scripts/tests/test_known_failure_pins.py).
    """
    if pins is None:
        pins = load_pins()
    if today is None:
        today = dt.date.today()

    pin = pins.get(nodeid)
    if pin is None:
        return PinVerdict(status="unpinned", message="")

    if today > pin.expires:
        return PinVerdict(
            status="expired",
            message=(
                f"[KNOWN-FAILURE PIN EXPIRED] {nodeid} was pinned to {pin.issue} "
                f"(declared {pin.declared}) but the pin expired {pin.expires} "
                f"(today {today}) and was never renewed. Treating this failure as "
                f"UNPINNED -- an expired pin does not count as a known reason. "
                f"Re-verify the failure and either renew the pin (fresh expiry, "
                f"re-confirmed signature) in known-failure-pins.yaml, or delete it "
                f"if the underlying issue is resolved."
            ),
        )

    if actual_signature == pin.signature:
        return PinVerdict(
            status="known",
            message=(
                f"[KNOWN-FAILURE, pinned] {nodeid} is pinned as known-failing "
                f"(issue: {pin.issue}, declared {pin.declared}, expires "
                f"{pin.expires}). Reason: {pin.reason.strip()} Observed failure "
                f"signature matches the pinned signature exactly: "
                f"{actual_signature}. This is the pinned failure, not a new one."
            ),
        )

    changed_keys = sorted(set(actual_signature) | set(pin.signature))
    diff = {
        k: (pin.signature.get(k, "<absent>"), actual_signature.get(k, "<absent>"))
        for k in changed_keys
        if pin.signature.get(k) != actual_signature.get(k)
    }
    return PinVerdict(
        status="changed",
        message=(
            "\n"
            "################################################################\n"
            f"# KNOWN-FAILURE PIN MISMATCH -- {nodeid}\n"
            "################################################################\n"
            f"This test is pinned as known-failing for a SPECIFIC reason "
            f"(issue: {pin.issue}, declared {pin.declared}):\n"
            f"    {pin.reason.strip()}\n"
            f"    pinned signature:   {pin.signature}\n"
            f"but it just failed with a DIFFERENT signature:\n"
            f"    observed signature: {actual_signature}\n"
            f"    changed entries (pinned -> observed): {diff}\n"
            "Do NOT assume this is the pinned issue. This is exactly the shape "
            "of the PR #460 near-miss: a test already red for reason A silently "
            "absorbed a new, unrelated reason B. Investigate this as a fresh, "
            "potentially more serious failure before dismissing it as "
            "'pre-existing, matches origin/main.'\n"
            "################################################################\n"
        ),
    )


def annotate_failure(
    nodeid: str,
    actual_signature: dict[str, Any],
    base_message: str,
    *,
    pins: dict[str, KnownFailurePin] | None = None,
    today: dt.date | None = None,
) -> str:
    """Return ``base_message``, prefixed with a pin verdict when one applies.

    Unpinned tests get ``base_message`` back byte-for-byte -- the mechanism
    is fully inert for any test with no registry entry.
    """
    verdict = check_signature(nodeid, actual_signature, pins=pins, today=today)
    if verdict.status == "unpinned":
        return base_message
    return f"{verdict.message}\n{base_message}"


# --------------------------------------------------------------------------
# CI gate: validate the registry itself (the ratchet).
# --------------------------------------------------------------------------


def _nodeid_resolves(nodeid: str) -> bool:
    """Cheap, dependency-free check that a pinned nodeid still names a real
    test: the file exists and defines a function/method with that name.

    Not a full pytest collection (that would require spinning up the target
    package's environment from a generic repo-root script) -- a regex-level
    check is enough to catch the common decay case (test deleted or renamed)
    without adding a subprocess dependency to this gate.
    """
    file_part, _, test_part = nodeid.partition("::")
    path = REPO_ROOT / file_part
    if not path.is_file():
        return False
    # Last segment after any further "::" (class::method) is the def name.
    def_name = test_part.rsplit("::", 1)[-1]
    if not def_name:
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return f"def {def_name}(" in text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=PIN_REGISTRY_PATH)
    args = parser.parse_args(argv)

    try:
        pins = load_pins(args.registry)
    except PinRegistryError as e:
        print(f"[KNOWN-FAILURE-PINS FAIL] registry is malformed: {e}", file=sys.stderr)
        return 1

    errors: list[str] = []
    today = dt.date.today()

    if len(pins) > MAX_LIVE_PINS:
        errors.append(
            f"TOO_MANY_PINS: {len(pins)} live pin(s) exceeds the ratchet cap "
            f"({MAX_LIVE_PINS}). Raise MAX_LIVE_PINS in scripts/known_failure_pins.py "
            f"only in the same PR that adds the pin justifying it."
        )

    for nodeid, pin in sorted(pins.items()):
        issue_path = REPO_ROOT / pin.issue
        if not issue_path.exists():
            errors.append(
                f"ORPHAN_ISSUE_LINK: pin {nodeid!r} links to {pin.issue!r}, which "
                f"does not exist on disk. Every pin must cite a real, checked-in "
                f"docs/evidence/ or docs/solutions/ file, not a bare claim."
            )
        if pin.expires < today:
            errors.append(
                f"EXPIRED_PIN: pin {nodeid!r} expired {pin.expires} (today {today}) "
                f"and was never renewed or removed. An expired pin is inert at test "
                f"time (treated as unpinned there) but must not linger unattended "
                f"in the registry -- renew with fresh evidence or delete it."
            )
        lifetime = pin.expires - pin.declared
        if lifetime.days > MAX_PIN_LIFETIME_DAYS or lifetime.days < 0:
            errors.append(
                f"PIN_LIFETIME_OUT_OF_RANGE: pin {nodeid!r} spans {pin.declared} -> "
                f"{pin.expires} ({lifetime.days}d), outside the allowed "
                f"0-{MAX_PIN_LIFETIME_DAYS}d range. A known-failure pin is a triage "
                f"aid with a forced renewal cadence, not a permanent waiver."
            )
        if not _nodeid_resolves(nodeid):
            errors.append(
                f"ORPHAN_PIN: pin {nodeid!r} does not resolve to a real test on "
                f"disk (file missing, or no matching `def`). Remove pins for tests "
                f"that were deleted, renamed, or moved."
            )

    if errors:
        print(f"[KNOWN-FAILURE-PINS FAIL] {len(errors)} violation(s) in {args.registry}:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"[KNOWN-FAILURE-PINS OK] {len(pins)} live pin(s), all within policy "
        f"(cap {MAX_LIVE_PINS}, max lifetime {MAX_PIN_LIFETIME_DAYS}d)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
