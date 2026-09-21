"""The provider's usage block, mapped onto the committed usage record.

This is the one place the provider's nesting becomes our field names, and the
mapping was frozen against captured bytes rather than inferred. That mattered:

* ``reasoning_tokens`` is one level deeper than the rest, inside
  ``completion_tokens_details``. A flat read of the top level would have found
  nothing and reported ``null`` for a quantity the provider does report.
* ``cached_input_tokens`` comes from ``prompt_tokens_details.cached_tokens``,
  not from the ``prompt_cache_hit_tokens`` that sits beside it at the top level.
  Both carry the same fact; normalizing both would be two homes for one number.
* ``reasoning_tokens`` is a SUBSET of ``completion_tokens``, so the record's
  fields are not all addends -- see ``temper_harness.ledger.aggregate``, which
  sums only the additive pair and would otherwise over-report by the majority of
  the output tokens.

The field list is read from the committed schema rather than restated here, and
:func:`normalize_usage` fails closed if the schema grows a field this module does
not know how to fill. A silent ``None`` for a new field would look exactly like a
provider that stopped reporting it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from temper_harness.schema_registry import load_schema

USAGE_SCHEMA = "usage.schema.json"

#: One field's source in the provider's block, or ``None`` when it is absent.
Extractor = Callable[[Mapping[str, Any]], "int | None"]


def usage_fields() -> tuple[str, ...]:
    """The committed record's fields, in schema order."""
    required: list[str] = load_schema(USAGE_SCHEMA)["required"]
    return tuple(required)


def _as_int(value: Any) -> int | None:
    """An integer, or ``None``.

    ``bool`` is excluded explicitly: ``True`` is an ``int`` in Python, so a
    provider (or a corrupt fixture) reporting a boolean would otherwise be
    recorded as the token count 1 -- a fabricated measurement from a type error.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _nested(block: Mapping[str, Any], outer: str, inner: str) -> int | None:
    section = block.get(outer)
    if not isinstance(section, Mapping):
        return None
    return _as_int(section.get(inner))


def _extractors() -> dict[str, Extractor]:
    return {
        "prompt_tokens": lambda block: _as_int(block.get("prompt_tokens")),
        "completion_tokens": lambda block: _as_int(block.get("completion_tokens")),
        "reasoning_tokens": lambda block: _nested(
            block, "completion_tokens_details", "reasoning_tokens"
        ),
        "cached_input_tokens": lambda block: _nested(
            block, "prompt_tokens_details", "cached_tokens"
        ),
        "total_tokens": lambda block: _as_int(block.get("total_tokens")),
    }


def normalize_usage(block: Any) -> dict[str, int | None]:
    """Map a provider usage block onto the committed usage record.

    A field the provider does not report becomes ``None``, never ``0`` (R4): a
    missing count and a measured zero are different facts, and this package
    exists partly because the prior attempt published one as the other. Absent
    input yields an all-``null`` record rather than an exception, because "the
    provider said nothing about usage" is a state a ledger row has to be able to
    record honestly.
    """
    extractors = _extractors()
    expected = set(usage_fields())
    if set(extractors) != expected:
        missing = sorted(expected - set(extractors))
        extra = sorted(set(extractors) - expected)
        raise AssertionError(
            f"{USAGE_SCHEMA} and this mapping disagree (unfilled: {missing}, unknown: {extra}); "
            "a new field would otherwise be recorded as null, which reads as a provider "
            "that stopped reporting it"
        )
    if not isinstance(block, Mapping):
        return dict.fromkeys(usage_fields())
    return {field: extractors[field](block) for field in usage_fields()}
