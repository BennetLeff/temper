"""Shape summarisation: structural enough to compare, blind enough to survive sampling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from temper_harness.canary.shapes import (
    VOLATILE_SHAPE_KEYS,
    compare_shapes,
    shape_digest,
    shape_of_exchange,
)
from tests import corpus


def shape_for(name: str) -> dict[str, Any]:
    return shape_of_exchange(
        http_status=corpus.ENTRIES[name]["http_status"],
        raw=corpus.response_bytes(name),
        content_type=corpus.headers_of(name).get("content-type"),
    )


def test_a_completion_summarises_without_any_of_its_text() -> None:
    """The property that lets the evidence be committed at all."""
    shape = shape_for("plain")
    payload = json.loads(corpus.response_bytes("plain"))
    reasoning = payload["choices"][0]["message"]["reasoning_content"]
    assert reasoning, "this fixture is supposed to carry reasoning; the test needs it"
    assert reasoning not in json.dumps(shape)
    assert shape["kind"] == "completion"


def test_a_completion_shape_records_the_structural_facts() -> None:
    shape = shape_for("parallel_tools")
    assert shape["system_fingerprint_present"] is True
    assert "usage" in shape["top_level_keys"]
    assert shape["tool_calls_present"] is True
    assert shape["finish_reasons"] == ["tool_calls"]
    assert shape["usage_total_reconciles"] is True
    assert shape["reasoning_present"] is True


def test_a_streamed_shape_records_where_usage_and_the_finish_reason_land() -> None:
    shape = shape_for("stream_plain")
    assert shape["kind"] == "stream"
    assert shape["sentinel_present"] is True
    assert shape["usage_event_count"] == 1
    assert shape["usage_on_final_event"] is True
    assert shape["finish_reason_on_final_event"] is True


def test_a_streamed_shape_does_not_record_an_event_count() -> None:
    """The deliberate omission: output length varies run to run.

    A canary that compared event counts would go red every time the model wrote a
    longer answer, which is a false alarm about the provider and would train whoever
    reads it to ignore the instrument.
    """
    shape = shape_for("stream_plain")
    assert "event_count" not in shape
    assert "content_is_empty" not in json.dumps(shape)


def test_a_refusal_summarises_as_its_error_envelope() -> None:
    shape = shape_for("invalid_model")
    assert shape["kind"] == "error_body"
    assert shape["error_type"] == "invalid_request_error"
    assert shape["error_keys"] == ["code", "message", "param", "type"]


@pytest.mark.parametrize("name", sorted(corpus.ENTRIES))
def test_every_recorded_exchange_summarises(name: str) -> None:
    """Anti-vacuity, and coverage: no probe may be silently unsummarisable."""
    shape = shape_for(name)
    assert shape["kind"] != "unparseable"
    assert shape["kind"] != "unparseable_stream"
    assert shape["response_bytes"] == len(corpus.response_bytes(name))
    assert len(shape["response_sha256"]) == 64


# -- comparison --------------------------------------------------------------


def test_a_missing_field_is_a_shape_change() -> None:
    recorded = shape_for("plain")
    live = dict(recorded)
    live["system_fingerprint_present"] = False
    differences = compare_shapes(recorded, live)
    assert len(differences) == 1
    assert "system_fingerprint_present" in differences[0]


def test_a_renamed_usage_field_is_a_shape_change() -> None:
    recorded = shape_for("plain")
    live = dict(recorded)
    live["usage_keys"] = [key for key in recorded["usage_keys"] if key != "total_tokens"]
    assert compare_shapes(recorded, live)


def test_usage_moving_off_the_final_chunk_is_a_shape_change() -> None:
    recorded = shape_for("stream_plain")
    live = dict(recorded)
    live["usage_on_final_event"] = False
    assert compare_shapes(recorded, live)


def test_a_refusal_becoming_a_success_is_a_shape_change() -> None:
    recorded = shape_for("invalid_model")
    live = shape_for("plain")
    assert compare_shapes(recorded, live)


def test_a_wholly_new_shape_key_is_reported() -> None:
    """Iterating only the recorded keys would silently ignore one.

    The docstring used to claim forward compatibility and was wrong in both directions:
    it reported an addition *inside* a compared list while missing a brand-new
    top-level key. Union iteration reports every structural difference, and a human
    decides whether it matters.
    """
    recorded = shape_for("plain")
    live = dict(recorded)
    live["a_field_the_recorder_never_knew_about"] = True
    differences = compare_shapes(recorded, live)
    assert len(differences) == 1
    assert "a_never_knew_about" in differences[0] or "never_knew_about" in differences[0]


def test_the_shapes_record_exact_key_lists(tmp_path: Path) -> None:
    """An addition is reported too, and that is deliberate.

    It is tempting to treat "the provider added a field" as compatible -- nothing the
    client reads changed. But the fields most likely to be added are exactly the ones
    that matter: a cost field, or a new usage breakdown. A canary that shrugged at
    those would be silent about a change to what a call costs to compute. So an
    addition turns it red and a human decides, which is the conservative direction for
    an instrument whose whole output is a claim about the provider.
    """
    recorded = shape_for("plain")
    live = dict(recorded)
    live["top_level_keys"] = [*recorded["top_level_keys"], "a_brand_new_field"]
    differences = compare_shapes(recorded, live)
    assert len(differences) == 1
    assert "a_brand_new_field" in differences[0]


def test_the_volatile_facts_never_affect_a_comparison() -> None:
    """Two runs of a sampled model cannot produce the same bytes."""
    recorded = shape_for("plain")
    live = dict(recorded)
    for key in VOLATILE_SHAPE_KEYS:
        live[key] = "different" if isinstance(recorded[key], str) else recorded[key] + 1
    assert compare_shapes(recorded, live) == []
    assert shape_digest(recorded) == shape_digest(live)


def test_the_shape_digest_tracks_behaviour() -> None:
    recorded = shape_for("plain")
    changed = dict(recorded)
    changed["reasoning_present"] = False
    assert shape_digest(recorded) != shape_digest(changed)


def test_recorded_shapes_agree_across_two_reads_of_the_corpus() -> None:
    """Determinism: the same bytes must summarise to the same anything."""
    from temper_harness.canary import recorded_shapes

    captured = Path(corpus.CAPTURED)
    first = recorded_shapes(captured)
    second = recorded_shapes(captured)
    assert first == second
    assert len(first) == len(corpus.ENTRIES)
