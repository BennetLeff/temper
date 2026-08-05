"""Type-carrying value signatures for Wave-4 differential comparisons.

The R1a rule for this program is that an A/B comparison must not be able to
pass when the two arms produce *different types* that happen to compare
equal, nor when they produce floats that differ in the last bit.  ``==`` in
Python fails both ways: ``True == 1``, ``0.0 == -0.0``, and
``np.float32(0.1) == 0.1`` is False but ``np.float64(0.1) == 0.1`` is True
while both print identically.

:func:`sig` canonicalizes a value into a nested tuple that carries, at every
leaf:

* the **concrete type name** (``type(v).__name__``) -- so ``float`` vs
  ``float64``, ``int`` vs ``bool``, ``tuple`` vs ``list`` all separate;
* for floats, ``float.hex()`` -- an exact, lossless decimal-free rendering,
  so ``0.0``/``-0.0`` and 1-ulp neighbours separate;
* for arrays, ``dtype`` and ``shape`` in addition to the per-element hex --
  so an ``f32`` array never matches an ``f64`` array even when the values
  round-trip.

There is **no tolerance anywhere**.  ``test_signature_self_test.py`` is the
self-test that proves each of those discriminations actually fires; it is
what stops this module from silently degrading into ``==``.

Provenance
----------
Every executable statement in this file is **byte-identical** to
``tests/router_v6/_signature.py`` as it stands on PR #732 (branch
``feat/wave4-router-v6-core-rust``, head ``9c30918b7``), which is still OPEN
at the time this slice was written; only this docstring differs.
The survey (``docs/evidence/2026-08-04-router-v6-migration-survey.md`` §5)
records this module and its self-test as the program's *only* genuinely
one-time, package-wide scaffolding -- so it is copied rather than rewritten,
and whichever of the two PRs lands second contributes nothing here.  The
self-test is deliberately NOT duplicated: #732 owns it, and two copies of
the same test ids in one package is worse than one.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

import numpy as np

__all__ = ["sig", "sigs_equal"]


def _float_hex(x: object) -> str:
    """``float.hex()`` of ``x`` widened to f64.

    Widening f32 -> f64 is exact, so the hex still separates any two
    distinct f32 values; the *dtype* recorded alongside separates f32 from
    f64.  NaN renders as ``'nan'`` and infinities as ``'inf'``/``'-inf'``,
    matching CPython's own ``float.hex`` contract.
    """
    f = float(x)  # type: ignore[arg-type]
    if f != f:
        return "nan"
    if f in (float("inf"), float("-inf")):
        return repr(f)
    return f.hex()


def sig(v: object) -> object:
    """Canonical, type-carrying signature of ``v``.

    Raises ``TypeError`` for any value shape this comparator does not know
    how to render.  That is deliberate: an unknown type must fail loudly
    rather than fall through to a weaker comparison.
    """
    if v is None:
        return ("NoneType",)
    tn = type(v).__name__
    if isinstance(v, (bool, np.bool_)):
        return (tn, bool(v))
    if isinstance(v, np.ndarray):
        return (
            tn,
            str(v.dtype),
            tuple(int(d) for d in v.shape),
            tuple(sig(x) for x in v.ravel()),
        )
    if isinstance(v, (float, np.floating)):
        return (tn, _float_hex(v))
    if isinstance(v, (int, np.integer)):
        return (tn, int(v))
    if isinstance(v, str):
        return (tn, v)
    if isinstance(v, bytes):
        return (tn, v.hex())
    if isinstance(v, (tuple, list)):
        return (tn, len(v), tuple(sig(x) for x in v))
    if isinstance(v, dict):
        # Iteration order is part of the value: it is NOT sorted here.
        # Sorting would hide an ordering divergence, which this program
        # treats as an undetectable behaviour change.
        return (tn, tuple((sig(k), sig(val)) for k, val in v.items()))
    if is_dataclass(v) and not isinstance(v, type):
        return (tn, tuple((f.name, sig(getattr(v, f.name))) for f in fields(v)))
    if isinstance(v, BaseException):
        return (tn, str(v))
    raise TypeError(f"sig() has no rendering for {tn!r}: {v!r}")


def sigs_equal(a: object, b: object) -> bool:
    """``sig(a) == sig(b)`` -- exact, no tolerance."""
    return sig(a) == sig(b)
