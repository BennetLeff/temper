"""Deterministic progressive selection of replayable creepage cuts."""

from __future__ import annotations

from collections.abc import Iterable
from numbers import Integral

from temper_placer.placer.cp_sat.creepage_cut_replay import (
    ReplayCut,
    decode_creepage_cut_replay,
    encode_creepage_cut_replay,
)


def _canonical(cuts: Iterable[object]) -> tuple[ReplayCut, ...]:
    try:
        return decode_creepage_cut_replay(encode_creepage_cut_replay(cuts))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid creepage cuts: {exc}") from exc


def _nonnegative(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return int(value)


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _refs(refs: Iterable[object], label: str) -> frozenset[str]:
    try:
        values = tuple(refs)
    except TypeError as exc:
        raise ValueError(f"{label} must be an iterable of references") from exc
    if any(not isinstance(ref, str) or not ref or ref != ref.strip() for ref in values):
        raise ValueError(f"{label} must contain non-empty trimmed references")
    return frozenset(ref for ref in values if isinstance(ref, str))


def _pairs(pairs: Iterable[object], label: str) -> frozenset[tuple[str, str]]:
    try:
        values = tuple(pairs)
    except TypeError as exc:
        raise ValueError(f"{label} must be an iterable of reference pairs") from exc
    result: set[tuple[str, str]] = set()
    for index, pair in enumerate(values):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f"{label}[{index}] must contain exactly two references")
        a, b = pair
        if not all(isinstance(ref, str) and ref and ref == ref.strip() for ref in (a, b)) or a == b:
            raise ValueError(f"{label}[{index}] contains invalid references")
        result.add((a, b) if a < b else (b, a))
    return frozenset(result)


def select_progressive_creepage_cuts(
    cuts: Iterable[object], *, attempt_index: int, initial_batch_size: int = 32,
    growth_per_attempt: int = 32, max_active_cuts: int | None = None,
    always_active_refs: Iterable[object] = (), always_active_pairs: Iterable[object] = (),
) -> tuple[ReplayCut, ...]:
    """Select a strongest-first prefix; output stays canonical ref order."""
    attempt = _nonnegative(attempt_index, "attempt_index")
    initial = _positive(initial_batch_size, "initial_batch_size")
    growth = _nonnegative(growth_per_attempt, "growth_per_attempt")
    maximum = _positive(max_active_cuts, "max_active_cuts") if max_active_cuts is not None else None
    canonical = _canonical(cuts)
    available = {(a, b): mm for a, b, mm in canonical}
    active_refs, active_pairs = _refs(always_active_refs, "always_active_refs"), _pairs(always_active_pairs, "always_active_pairs")
    known_refs = {ref for a, b in available for ref in (a, b)}
    if active_refs - known_refs:
        raise ValueError(f"always_active_refs are absent from cuts: {sorted(active_refs - known_refs)!r}")
    if active_pairs - set(available):
        raise ValueError(f"always_active_pairs are absent from cuts: {sorted(active_pairs - set(available))!r}")
    ranked = sorted(canonical, key=lambda cut: (-cut[2], cut[0], cut[1]))
    prefix_size = initial + attempt * growth
    if maximum is not None:
        prefix_size = min(prefix_size, maximum)
    selected = set(active_pairs)
    selected.update((a, b) for a, b, _mm in canonical if a in active_refs or b in active_refs)
    for a, b, _mm in ranked[:prefix_size]:
        selected.add((a, b))
    if maximum is not None and len(selected) > maximum:
        raise ValueError("always-active cuts exceed max_active_cuts")
    return tuple((a, b, available[(a, b)]) for a, b in sorted(selected))


__all__ = ["select_progressive_creepage_cuts"]
