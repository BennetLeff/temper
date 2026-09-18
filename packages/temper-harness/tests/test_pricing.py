"""The price table: transcription, window arithmetic, and refusals.

Two of these tests are worth their weight. ``test_off_peak_is_exactly_half_of_peak`` pins
the relationship the documentation states, so a transcription slip in one of six numbers
fails rather than halving a bill silently. And every ``unpriced`` test exists to keep a
missing number from becoming the number zero, which is the failure this repo has been bitten
by before and the reason R4 is a requirement rather than a style note.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from temper_harness.canary import probe_fanout
from temper_harness.ledger import LedgerStore
from temper_harness.pricing import (
    OFF_PEAK,
    PEAK,
    PRICING_DIR,
    PriceTableError,
    available_tables,
    latest_table_id,
    load_table,
    window_for,
)
from temper_harness.provider.interface import Request, Terminal
from temper_harness.provider.messages import ChatMessage
from temper_harness.schema_registry import build_validator

#: A Monday, inside the documented peak window (01:00-04:00 UTC, weekdays).
PEAK_MOMENT = dt.datetime(2026, 9, 14, 2, 0, tzinfo=dt.UTC)
#: The same Monday, outside both windows.
OFF_PEAK_MOMENT = dt.datetime(2026, 9, 14, 11, 0, tzinfo=dt.UTC)


def test_every_committed_table_is_schema_valid() -> None:
    tables = available_tables()
    assert tables, f"no price tables under {PRICING_DIR}"
    for table_id in tables:
        build_validator("pricing.schema.json").validate(load_table(table_id).raw)


def test_the_latest_table_is_the_newest_by_name() -> None:
    """No version constant in Python: adding a file is the whole change (KTD7)."""
    assert latest_table_id() == available_tables()[-1]
    assert load_table().table_id == latest_table_id()


def test_an_unknown_table_id_is_refused() -> None:
    with pytest.raises(PriceTableError, match="no price table"):
        load_table("1999-01-01")


def test_off_peak_is_exactly_half_of_peak() -> None:
    """The documented relationship, asserted rather than assumed.

    This is the test that catches a transcription slip. Six numbers were copied from a
    published table; if one of them is wrong the relationship breaks, and without this the
    only symptom would be a bill that is wrong by a factor of two for part of every day.
    """
    table = load_table()
    for model in table.raw["models"]:
        for kind in ("input_cache_hit", "input_cache_miss", "output"):
            peak = table.rate(model, PEAK, kind)
            off_peak = table.rate(model, OFF_PEAK, kind)
            assert peak == off_peak * 2, f"{model}/{kind}: {peak} vs {off_peak}"


def test_the_documented_flash_rates_are_the_numbers_transcribed() -> None:
    """Pinned against the published table, so an edit is a deliberate act."""
    table = load_table()
    assert table.raw["source"] == "https://api-docs.deepseek.com/quick_start/pricing"
    assert table.model_version("deepseek-flash") == "DeepSeek-V4.1-Flash"
    assert table.rate("deepseek-flash", OFF_PEAK, "input_cache_hit") == Decimal("0.003")
    assert table.rate("deepseek-flash", OFF_PEAK, "input_cache_miss") == Decimal("0.15")
    assert table.rate("deepseek-flash", OFF_PEAK, "output") == Decimal("0.60")


def test_the_table_says_whether_its_rates_are_measured_or_inherited() -> None:
    """Documentation is an inherited figure. The table says which it is, and a
    `measured` claim has to come with something that was actually measured."""
    table = load_table()
    verification = table.raw["verification"]
    assert verification["status"] in ("measured", "unverified")
    if table.is_verified:
        assert verification["method"]
        assert verification["observed"], "a measured claim with no observation is a claim"
        assert verification["tolerance_usd"] is not None
    else:
        assert verification["observed"] is None


def test_a_measured_verification_still_holds_against_the_current_rates() -> None:
    """The ratchet: the cost is DERIVED from the recorded usage, not restated.

    An observation records what a call consumed and what the account's balance moved by.
    This recomputes the cost from those tokens and the table as it stands now, and compares
    it to the delta. So editing a rate breaks the verification rather than leaving a stale
    `measured` badge on numbers nobody re-checked -- which is the whole reason the
    observation stores usage instead of a pre-computed figure.

    What the comparison is worth is bounded by the instrument, and the tolerance says so:
    the balance is quoted to two decimals, so the delta is only known to about +/-0.01. That
    is enough to exclude the peak/off-peak and cache-hit/miss transpositions, which are 2x
    and 50x, and not enough to catch a small typo.
    """
    table = load_table()
    assert table.is_verified, "this test is about a measured table; see #1602"
    tolerance = Decimal(str(table.raw["verification"]["tolerance_usd"]))

    for entry in table.raw["verification"]["observed"]:
        at = dt.datetime.fromisoformat(entry["at"])
        assert window_for(table.raw, at) == entry["window"], entry["at"]
        computed = table.estimate_usd(entry["usage"], model=entry["model"], at=at)
        assert computed is not None, entry["at"]
        observed = Decimal(str(entry["observed_usd"]))
        assert abs(computed - observed) <= tolerance, (
            f"{entry['at']}: recomputed {computed} is more than {tolerance} from the "
            f"observed balance delta {observed}; the rates disagree with the measurement"
        )
        assert entry["note"]


def test_the_two_measured_observations_cover_input_and_output() -> None:
    """One rate each, so the verification is not two readings of the same number."""
    table = load_table()
    observed = table.raw["verification"]["observed"]
    if not observed:
        pytest.skip("the table is not measured; see #1602")
    assert len(observed) >= 2
    kinds = [max(entry["usage"], key=lambda k: entry["usage"][k] or 0) for entry in observed]
    assert "prompt_tokens" in kinds
    assert "completion_tokens" in kinds


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (dt.datetime(2026, 9, 14, 1, 0, tzinfo=dt.UTC), PEAK),  # window opens
        (dt.datetime(2026, 9, 14, 3, 59, tzinfo=dt.UTC), PEAK),
        (dt.datetime(2026, 9, 14, 4, 0, tzinfo=dt.UTC), OFF_PEAK),  # half-open: 04:00 is out
        (dt.datetime(2026, 9, 14, 6, 0, tzinfo=dt.UTC), PEAK),  # second window opens
        (dt.datetime(2026, 9, 14, 9, 59, tzinfo=dt.UTC), PEAK),
        (dt.datetime(2026, 9, 14, 10, 0, tzinfo=dt.UTC), OFF_PEAK),
        (dt.datetime(2026, 9, 14, 5, 0, tzinfo=dt.UTC), OFF_PEAK),  # between windows
        (dt.datetime(2026, 9, 14, 0, 30, tzinfo=dt.UTC), OFF_PEAK),  # before the first
        (dt.datetime(2026, 9, 19, 2, 0, tzinfo=dt.UTC), OFF_PEAK),  # Saturday
        (dt.datetime(2026, 9, 13, 2, 0, tzinfo=dt.UTC), OFF_PEAK),  # Sunday
    ],
)
def test_the_window_is_peak_only_on_weekday_mornings_utc(
    moment: dt.datetime, expected: str
) -> None:
    assert window_for(load_table().raw, moment) == expected


def test_a_non_utc_timestamp_is_converted_before_the_window_is_chosen() -> None:
    """03:00 in UTC+2 is 01:00 UTC, which is peak -- the window is defined in UTC."""
    elsewhere = dt.datetime(2026, 9, 14, 3, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    assert window_for(load_table().raw, elsewhere) == PEAK


def test_the_window_does_not_consult_a_locale_formatted_weekday_name() -> None:
    """The always-runnable half of the locale guard.

    `strftime("%A")` returns a *localised* weekday name, and relying on it made the peak
    window depend on `LC_TIME` -- measured: `de_DE` and `fr_FR` both moved a Monday 02:00 UTC
    call from `peak` to `off_peak`, halving every weekday bill. The behavioural test below is
    the real instrument and needs a non-English locale installed, which a bare CI container
    does not have.

    This asserts the property that made the bug possible, and it is a *source scan*, which is
    the weaker kind: a locale-independent bug would pass it. It is here because it always runs,
    and because this particular defect is syntactically visible -- the money path must not call
    a date formatter at all.

    It parses the module rather than searching its text. The first version searched the text
    and immediately tripped on the docstring that *documents* the anti-pattern, which is the
    same lesson the schema suite records for its inline-version scan: a substring scan matches
    the sentence explaining why the thing is forbidden.
    """
    import ast

    source = (
        Path(__file__).resolve().parents[1] / "src" / "temper_harness" / "pricing.py"
    ).read_text(encoding="utf-8")
    formatter_calls = [
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr in ("strftime", "strptime")
    ]
    assert not formatter_calls, (
        "the peak window must not format a date: a locale-formatted value in the money path "
        f"is how a weekday bill got halved (found {formatter_calls})"
    )


def test_a_locale_change_does_not_move_the_window() -> None:
    """The money path must not depend on the ambient locale.

    `strftime("%A")` returns a *localised* weekday name. Measured before the fix, for a
    Monday 02:00 UTC that is inside the peak window: `LC_TIME=C` gave "Monday" and `peak`,
    while `LC_TIME=de_DE` gave "Montag" and `off_peak` and `fr_FR` gave "lundi" and
    `off_peak`. So a process that set a locale halved every weekday bill, with no error and a
    perfectly well-formed figure. The window now compares `weekday()` indices, which no
    locale can move.
    """
    import locale

    moments = {
        "monday 02:00 UTC (peak)": dt.datetime(2026, 9, 14, 2, 0, tzinfo=dt.UTC),
        "monday 11:00 UTC (off-peak)": dt.datetime(2026, 9, 14, 11, 0, tzinfo=dt.UTC),
        "saturday 02:00 UTC (off-peak)": dt.datetime(2026, 9, 19, 2, 0, tzinfo=dt.UTC),
    }
    table = load_table()
    baseline = {label: window_for(table.raw, at) for label, at in moments.items()}
    assert baseline == {
        "monday 02:00 UTC (peak)": PEAK,
        "monday 11:00 UTC (off-peak)": OFF_PEAK,
        "saturday 02:00 UTC (off-peak)": OFF_PEAK,
    }, "the baseline is wrong, so this test would not be measuring the locale"

    original = locale.setlocale(locale.LC_TIME)
    compared = 0
    try:
        for candidate in ("de_DE.UTF-8", "fr_FR.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, candidate)
            except locale.Error:
                continue  # this machine does not have the locale; nothing to compare
            compared += 1
            moved = {label: window_for(table.raw, at) for label, at in moments.items()}
            assert moved == baseline, f"{candidate} moved the window: {moved} != {baseline}"
    finally:
        locale.setlocale(locale.LC_TIME, original)
    if not compared:
        # A reasoned skip, not a pass: this test cannot measure the property without a
        # non-English LC_TIME, and a bare CI container has none. The first version of this
        # asserted `compared` and so turned "the platform cannot run this test" into a
        # *failure* -- which is how CI found it. The always-runnable half is
        # `test_the_window_does_not_consult_a_locale_formatted_weekday_name`.
        pytest.skip(
            "no non-English LC_TIME locale is installed, so this test cannot measure the "
            "locale independence it exists for"
        )


def test_an_unrecognised_weekday_name_is_refused_rather_than_skipped() -> None:
    """Skipping one would move that day's calls to the cheaper window."""
    import copy

    raw = copy.deepcopy(load_table().raw)
    raw["peak_windows"]["weekdays"] = ["funday"]
    with pytest.raises(PriceTableError, match="not weekdays"):
        window_for(raw, dt.datetime(2026, 9, 14, 2, 0, tzinfo=dt.UTC))


def test_a_naive_timestamp_is_refused() -> None:
    """Because `datetime.hour` on a naive value reads the local clock.

    The error from getting this wrong is a factor of two, and it would be invisible: the
    figure would look perfectly well-formed.
    """
    with pytest.raises(PriceTableError, match="must carry a timezone"):
        window_for(load_table().raw, dt.datetime(2026, 9, 14, 2, 0))


def test_a_cost_splits_input_by_cache_status() -> None:
    """Hand-computed from the documented rates, so the arithmetic is checked not asserted.

    peak: (200 x 0.006 + 800 x 0.30 + 100 x 1.20) / 1e6 = 361.2 / 1e6
    """
    table = load_table()
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "reasoning_tokens": 37,
        "cached_input_tokens": 200,
        "total_tokens": 1100,
    }
    assert table.estimate_usd(usage, model="deepseek-flash", at=PEAK_MOMENT) == Decimal("0.0003612")
    assert table.estimate_usd(usage, model="deepseek-flash", at=OFF_PEAK_MOMENT) == Decimal(
        "0.0001806"
    )


def test_a_fully_cached_input_is_fifty_times_cheaper() -> None:
    """The cache-hit rate is 0.006 against 0.30, and that ratio is the whole reason
    `cached_input_tokens` is a field rather than a curiosity."""
    table = load_table()
    cached = {"prompt_tokens": 1000, "completion_tokens": 0, "cached_input_tokens": 1000}
    uncached = {"prompt_tokens": 1000, "completion_tokens": 0, "cached_input_tokens": 0}
    hit = table.estimate_usd(cached, model="deepseek-flash", at=PEAK_MOMENT)
    miss = table.estimate_usd(uncached, model="deepseek-flash", at=PEAK_MOMENT)
    assert hit is not None and miss is not None
    assert miss == hit * 50


def test_reasoning_tokens_are_not_priced_twice() -> None:
    """They are billed as output and are a subset of completion_tokens.

    Pricing them again would double the output half of the bill, which is the same trap the
    aggregate documents for token counts -- and here it would be a 2x error in the figure a
    fixed-expenditure comparison is denominated in.
    """
    table = load_table()
    with_reasoning = {
        "prompt_tokens": 0,
        "completion_tokens": 18,
        "reasoning_tokens": 15,
        "cached_input_tokens": 0,
    }
    without = {"prompt_tokens": 0, "completion_tokens": 18, "cached_input_tokens": 0}
    assert table.estimate_usd(with_reasoning, model="deepseek-flash", at=PEAK_MOMENT) == Decimal(
        "0.0000216"
    )
    assert table.estimate_usd(with_reasoning, model="deepseek-flash", at=PEAK_MOMENT) == (
        table.estimate_usd(without, model="deepseek-flash", at=PEAK_MOMENT)
    )


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"prompt_tokens": None, "completion_tokens": 1, "cached_input_tokens": 0},
        {"prompt_tokens": 1, "completion_tokens": None, "cached_input_tokens": 0},
        {"prompt_tokens": 1, "completion_tokens": 1, "cached_input_tokens": None},
        {"prompt_tokens": 1, "completion_tokens": 1},
        {"prompt_tokens": True, "completion_tokens": 1, "cached_input_tokens": 0},
        {"prompt_tokens": -5, "completion_tokens": 1, "cached_input_tokens": 0},
        # A cache hit larger than the input: the hit/miss split is unknowable and the two
        # rates differ fiftyfold, so any figure would be arbitrary.
        {"prompt_tokens": 10, "completion_tokens": 1, "cached_input_tokens": 11},
    ],
)
def test_an_unknowable_cost_is_unpriced_and_never_zero(usage: object) -> None:
    """``None`` and not ``0``. Zero is a claim that the call was free (R4)."""
    assert load_table().estimate_usd(usage, model="deepseek-flash", at=PEAK_MOMENT) is None


def test_a_model_absent_from_the_table_is_unpriced() -> None:
    table = load_table()
    assert (
        table.estimate_usd(
            {"prompt_tokens": 1, "completion_tokens": 1, "cached_input_tokens": 0},
            model="a-model-that-does-not-exist",
            at=PEAK_MOMENT,
        )
        is None
    )
    with pytest.raises(PriceTableError, match="is not in price table"):
        table.rate("a-model-that-does-not-exist", PEAK, "output")


# -- integration: a ledger row carries the identity that priced it -------------


class _Scripted:
    """One priced call per invocation."""

    def __init__(self, *, prompt: int, completion: int, cached: int) -> None:
        self.prompt, self.completion, self.cached = prompt, completion, cached

    def stream(self, request: Request):
        yield Terminal(
            {
                "id": "msg",
                "model": request.model,
                "finish_reason": "stop",
                "content": "done",
                "reasoning_content": "",
                "system_fingerprint": None,
                "tool_calls": [],
                "usage": {
                    "prompt_tokens": self.prompt,
                    "completion_tokens": self.completion,
                    "reasoning_tokens": 0,
                    "cached_input_tokens": self.cached,
                    "total_tokens": self.prompt + self.completion,
                },
                "served_from": "live",
            }
        )


def test_a_priced_run_records_the_table_identity_and_sums_its_usd(tmp_path: Path) -> None:
    """A row says which table priced it, and the aggregate adds the figures up.

    KTD7's point: a rate change adds a version, and existing rows keep the identity that
    produced them. Without the id on the row, a later reader cannot tell which rates a
    historical figure came from -- which is exactly how a rate change silently re-prices
    history.
    """
    table = load_table()
    store = LedgerStore(tmp_path / "ledger")
    result = probe_fanout(
        store=store,
        transport=_Scripted(prompt=1000, completion=100, cached=200),
        request=Request(
            model="deepseek-flash",
            messages=[ChatMessage(role="user", content="place it")],
            served_from="live",
        ),
        sessions=["worker-0"],
        priced_by=table,
        at=PEAK_MOMENT,
    )

    [outcome] = result.outcomes
    assert outcome.price_table_id == table.table_id
    assert outcome.estimated_usd == pytest.approx(0.0003612)
    row = store.call_rows()[0]
    assert row["price_table_id"] == table.table_id
    assert row["estimated_usd"] == pytest.approx(0.0003612)
    assert result.aggregate.inclusive_usd == pytest.approx(0.0003612)
    assert result.aggregate.priced_rows == 1
    assert result.aggregate.usd_is_complete is True
    # D4: the row records WHICH window priced it. Off-peak is exactly half of peak, so
    # without this the figure carries a factor-of-two ambiguity nothing can resolve later.
    assert row["price_window"] == "peak"
    assert outcome.price_window == "peak"


def test_pricing_needs_both_a_table_and_a_moment(tmp_path: Path) -> None:
    """A cost is a function of the window, so one without the other prices nothing."""
    store = LedgerStore(tmp_path / "ledger")
    transport = _Scripted(prompt=1, completion=1, cached=0)
    sessions = ["worker-0"]
    request = Request(
        model="deepseek-flash",
        messages=[ChatMessage(role="user", content="x")],
        served_from="live",
    )
    with pytest.raises(ValueError, match="both a table and the timestamp"):
        probe_fanout(
            store=store, transport=transport, request=request, sessions=sessions, at=PEAK_MOMENT
        )
    with pytest.raises(ValueError, match="both a table and the timestamp"):
        probe_fanout(
            store=store,
            transport=transport,
            request=request,
            sessions=sessions,
            priced_by=load_table(),
        )


def test_an_unpriced_run_says_unpriced_and_never_zero(tmp_path: Path) -> None:
    """The state the harness was in before this table existed, kept honest."""
    store = LedgerStore(tmp_path / "ledger")
    result = probe_fanout(
        store=store,
        transport=_Scripted(prompt=1000, completion=100, cached=0),
        request=Request(
            model="deepseek-flash",
            messages=[ChatMessage(role="user", content="x")],
            served_from="live",
        ),
        sessions=["worker-0"],
    )
    [outcome] = result.outcomes
    assert outcome.price_table_id == "unpriced"
    assert outcome.estimated_usd is None
    assert store.call_rows()[0]["estimated_usd"] is None
    # The row says unpriced, and the aggregate says how much of it was priced. It used to
    # report `inclusive_usd == 0.0` with no flag at all, which reads as a free run -- and a
    # test asserted that, calling it "labelled as such" when nothing labelled it.
    assert result.aggregate.priced_rows == 0
    assert result.aggregate.usd_is_complete is False
    assert result.aggregate.inclusive_usd == 0.0, "the sum of no figures"
