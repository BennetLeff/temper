"""Property-based + metamorphic tests for the migrated trace_commands
compute.

Wave 4, Phase 5 (cli/adapters/temper-workflow slice). These properties
exercise the migrated ``temper_orchestration.filter_decisions`` and
``temper_orchestration.find_rejected_alternative`` (the delegation shim
``temper_placer/cli/trace_commands.py`` calls them); bit-identical parity
against the pinned pre-migration Python is asserted separately by
``test_trace_commands_rust_differential.py``.

Five properties (R1c), all non-vacuously guarded:

- F1. Exact-match: ``filter_decisions`` returns exactly the indices whose
  decision's ``d.get("subject") == subject``.
- F2. Order preservation: the returned indices are strictly increasing.
- F3. Subject partition: for two distinct non-None subjects, the filtered
  index sets are disjoint.
- F4. Empty input: ``filter_decisions([], s) == []`` and, for an all-match
  list, the filter returns every index.
- F6. ``find_rejected_alternative`` validity: a non-None result ``(di, ai)``
  satisfies ``decisions[di].get("subject") == subject`` AND
  ``str(decisions[di]["alternatives_considered"][ai].get("value")) ==
  value``.
- F7. First-match: the returned ``(di, ai)`` is the lexicographically first
  match (no earlier decision/alternative matches).

Three metamorphic relations (R1d):

- MF1. Permutation: permuting the decisions list permutes the result
  indices consistently (original index i maps to its permuted position).
- MF2. Append-inertness: appending a decision whose subject does not match
  leaves the filtered index set unchanged.
- MF3. Unrelated-key inertness: adding extra keys to decisions and
  alternatives (``phase``, ``reason``, ``constraint_refs``,
  ``loss_if_chosen``) does not change either function's result.

Every property carries a G4 vacuity mutant: a degenerate kernel is swapped
in via the ``_kernels`` indirection and the property's inner test is
re-run, asserting it fails. A property no mutant can break is not a
property.
"""

from __future__ import annotations

import pytest
import temper_orchestration as _to
from hypothesis import assume, given, settings
from hypothesis import strategies as st

_SUBJECTS = st.one_of(st.text(min_size=0, max_size=8), st.integers(min_value=-5, max_value=5))
_VALUES = st.one_of(st.text(min_size=0, max_size=8), st.integers(min_value=-5, max_value=5))

_SETTINGS = settings(max_examples=100, deadline=None)


def _alt_strategy():
    return st.one_of(
        st.fixed_dictionaries(
            {"value": _VALUES, "rejection_reason": st.text(min_size=1, max_size=8)}
        ),
        st.fixed_dictionaries(
            {
                "value": _VALUES,
                "rejection_reason": st.text(min_size=1, max_size=8),
                "constraint_violated": st.text(min_size=1, max_size=8),
            }
        ),
    )


def _decision_strategy():
    return st.one_of(
        st.fixed_dictionaries({"subject": _SUBJECTS, "value": _VALUES}),
        st.fixed_dictionaries(
            {
                "subject": _SUBJECTS,
                "value": _VALUES,
                "alternatives_considered": st.lists(_alt_strategy(), max_size=4),
            }
        ),
    )


_DECISIONS = st.lists(_decision_strategy(), max_size=8)


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _Kernels:
    filter_decisions = staticmethod(lambda d, s: _to.filter_decisions(d, s))
    find_rejected = staticmethod(lambda d, s, v: _to.find_rejected_alternative(d, s, v))


_kernels = _Kernels()
_KERNEL_NAMES = ("filter_decisions", "find_rejected")


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _assert_property_fails(property_fn, *args):
    with pytest.raises(
        (AssertionError, KeyError, AttributeError, TypeError, pytest.fail.Exception)
    ):
        property_fn.hypothesis.inner_test(*args)


def _matches(d: dict, subject) -> bool:
    return d.get("subject") == subject


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@_SETTINGS
@given(_DECISIONS, _SUBJECTS)
def test_f1_exact_match(decisions, subject):
    """F1: the filtered indices are exactly the matching indices."""
    got = _kernels.filter_decisions(decisions, subject)
    assert got == [i for i, d in enumerate(decisions) if _matches(d, subject)]


@_SETTINGS
@given(_DECISIONS, _SUBJECTS)
def test_f2_order_preserved(decisions, subject):
    """F2: returned indices are strictly increasing (no reordering)."""
    got = _kernels.filter_decisions(decisions, subject)
    assert got == sorted(got)
    assert len(got) == len(set(got))


@_SETTINGS
@given(_DECISIONS, _SUBJECTS, _SUBJECTS)
def test_f3_subject_partition(decisions, s1, s2):
    """F3: distinct non-None subjects filter to disjoint index sets."""
    assume(s1 != s2 and s1 is not None and s2 is not None)
    i1 = set(_kernels.filter_decisions(decisions, s1))
    i2 = set(_kernels.filter_decisions(decisions, s2))
    assert i1.isdisjoint(i2)


@_SETTINGS
@given(_SUBJECTS)
def test_f4_empty_and_all_match(subject):
    """F4: empty input filters to [], and an all-match list filters to
    every index."""
    assert _kernels.filter_decisions([], subject) == []
    n = 5
    all_match = [{"subject": subject, "value": i} for i in range(n)]
    assert _kernels.filter_decisions(all_match, subject) == list(range(n))


@_SETTINGS
@given(_DECISIONS, _SUBJECTS, _VALUES)
def test_f6_find_rejected_validity(decisions, subject, value):
    """F6: a non-None find result is a valid (decision, alternative) match."""
    hit = _kernels.find_rejected(decisions, subject, value)
    if hit is None:
        return
    di, ai = hit
    assert 0 <= di < len(decisions)
    d = decisions[di]
    assert d.get("subject") == subject
    alts = d.get("alternatives_considered", [])
    assert 0 <= ai < len(alts)
    assert str(alts[ai].get("value")) == value


@_SETTINGS
@given(_DECISIONS, _SUBJECTS, _VALUES)
def test_f7_first_match(decisions, subject, value):
    """F7: the result is the LEXICOGRAPHICALLY FIRST match — no earlier
    (decision, alternative) pair satisfies the match conditions."""
    hit = _kernels.find_rejected(decisions, subject, value)
    first = None
    for di, d in enumerate(decisions):
        if d.get("subject") != subject:
            continue
        for ai, alt in enumerate(d.get("alternatives_considered", [])):
            if str(alt.get("value")) == value:
                first = (di, ai)
                break
        if first is not None:
            break
    assert hit == first


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@_SETTINGS
@given(_DECISIONS, _SUBJECTS, st.integers(min_value=0, max_value=5))
def test_mf1_permutation(decisions, subject, seed):
    """MF1: permuting the decisions permutes the result indices."""
    import random

    if not decisions:
        return
    perm = list(range(len(decisions)))
    rng = random.Random(seed)
    rng.shuffle(perm)
    permuted = [decisions[i] for i in perm]
    got = _kernels.filter_decisions(permuted, subject)
    # original index i appears in the permuted list at position perm.index(i)
    expected = sorted(perm.index(i) for i in _kernels.filter_decisions(decisions, subject))
    assert got == expected


@_SETTINGS
@given(_DECISIONS, _SUBJECTS, _SUBJECTS)
def test_mf2_append_inertness(decisions, subject, other_subject):
    """MF2: appending a non-matching decision leaves the filtered index set
    unchanged (existing indices are stable; the new element never matches)."""
    # the appended element must never match `subject` (even for empty input)
    assume(other_subject != subject)
    appended = decisions + [{"subject": other_subject, "value": 0}]
    got = _kernels.filter_decisions(appended, subject)
    assert got == _kernels.filter_decisions(decisions, subject)


@_SETTINGS
@given(_DECISIONS, _SUBJECTS, _VALUES)
def test_mf3_unrelated_key_inertness(decisions, subject, value):
    """MF3: extra keys on decisions/alternatives do not change results —
    the compute reads only subject/alternatives_considered/value."""
    decorated = [
        {
            **d,
            "phase": "place",
            "reason": "decorated",
            "constraint_refs": ["c1", "c2"],
            "decision_type": "choice",
        }
        | (
            {
                "alternatives_considered": [
                    {**a, "loss_if_chosen": 1.5, "constraint_violated": "v"}
                    for a in d["alternatives_considered"]
                ]
            }
            if "alternatives_considered" in d
            else {}
        )
        for d in decisions
    ]
    assert _kernels.filter_decisions(decorated, subject) == _kernels.filter_decisions(
        decisions, subject
    )
    assert _kernels.find_rejected(decorated, subject, value) == _kernels.find_rejected(
        decisions, subject, value
    )


# ---------------------------------------------------------------------------
# G4 vacuity mutants — one per property.
# ---------------------------------------------------------------------------


def test_f1_fails_for_all_indices_kernel(_restore_kernels):
    """A kernel returning every index (subject-blind) breaks F1."""

    def all_indices(d, s):
        return list(range(len(d)))

    _kernels.filter_decisions = all_indices
    _assert_property_fails(test_f1_exact_match, [{"subject": "A", "value": 1}], "B")


def test_f2_fails_for_reversed_kernel(_restore_kernels):
    """A kernel returning matches in reverse breaks F2."""

    def reversed_indices(d, s):
        return list(reversed([i for i, x in enumerate(d) if x.get("subject") == s]))

    _kernels.filter_decisions = reversed_indices
    _assert_property_fails(
        test_f2_order_preserved, [{"subject": "A"}, {"subject": "A"}, {"subject": "A"}], "A"
    )


def test_f3_fails_for_subject_blind_kernel(_restore_kernels):
    """A kernel that ignores the subject (returns even-indexed) breaks F3."""

    def even_indices(d, s):
        return [i for i in range(len(d)) if i % 2 == 0]

    _kernels.filter_decisions = even_indices
    _assert_property_fails(
        test_f3_subject_partition, [{"subject": "A"}, {"subject": "B"}], "A", "B"
    )


def test_f4_fails_for_nonempty_on_empty_kernel(_restore_kernels):
    """A kernel returning a phantom index for an empty input breaks F4."""

    def phantom(d, s):
        return [0] if not d else [i for i, x in enumerate(d) if x.get("subject") == s]

    _kernels.filter_decisions = phantom
    _assert_property_fails(test_f4_empty_and_all_match, "A")


def test_f6_fails_for_wrong_subject_kernel(_restore_kernels):
    """A kernel that matches on a different subject breaks F6."""

    def wrong_subject(d, s, v):
        for di, x in enumerate(d):
            if x.get("subject") != s:
                continue
            for ai, alt in enumerate(x.get("alternatives_considered", [])):
                if str(alt.get("value")) == v:
                    return (di, ai)
        return (0, 0) if d else None

    _kernels.find_rejected = wrong_subject
    _assert_property_fails(
        test_f6_find_rejected_validity, [{"subject": "A", "value": 1}], "A", "1"
    )


def test_f7_fails_for_last_match_kernel(_restore_kernels):
    """A kernel returning the LAST match instead of the first breaks F7."""

    def last_match(d, s, v):
        result = None
        for di, x in enumerate(d):
            if x.get("subject") != s:
                continue
            for ai, alt in enumerate(x.get("alternatives_considered", [])):
                if str(alt.get("value")) == v:
                    result = (di, ai)
        return result

    _kernels.find_rejected = last_match
    _assert_property_fails(
        test_f7_first_match,
        [{"subject": "A", "alternatives_considered": [{"value": 1}, {"value": 1}]}],
        "A",
        "1",
    )
