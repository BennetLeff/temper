"""Turning a token count into USD, and being honest about when it cannot.

KTD7 asks for a versioned price table with its schema committed, so a rate change adds a
version rather than re-pricing history. This module is the loader and the arithmetic. Two
things about this provider made the design more than a lookup:

* **Every rate is quoted at two prices.** Off-peak is exactly half of peak, and peak is a
  wall-clock window in UTC (weekdays, 01:00-04:00 and 06:00-10:00). A cost is therefore a
  function of *when* a call happened, so :meth:`PriceTable.estimate_usd` requires a
  timestamp that carries a timezone and refuses a naive one -- `datetime.hour` on a naive
  value silently reads the local clock, which would pick the wrong window by an unknown
  number of hours, and the error would be a factor of two on the bill.
* **An unknown quantity is not zero.** A usage block with a missing field cannot be priced,
  and this returns ``None`` rather than a partial sum, because a partial sum is quotable and
  a missing number is not (R4). The same applies to a block whose own numbers contradict each
  other: a cached count larger than the prompt count means the split between cache-hit and
  cache-miss input is unknowable, and the honest answer is a gap.

Money is `Decimal`, not `float`. The rates are exact decimals and the token counts are
integers, so the product is exact; a float introduces representation error into a figure
whose whole purpose is comparison between experiment arms. It is converted to a number only
at the ledger boundary, where JSON has no decimal type -- and the conversion is the only
place a rounding could occur.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from temper_harness.schema_registry import build_validator

PRICING_SCHEMA = "pricing.schema.json"

#: The tables live beside the package with the schemas: committed data, reviewed as a diff.
PRICING_DIR = Path(__file__).resolve().parents[2] / "pricing"

PEAK = "peak"
OFF_PEAK = "off_peak"

#: A million, because the provider quotes per million tokens and an implicit unit is how a
#: figure ends up six orders of magnitude wrong.
_PER_MILLION = Decimal(1_000_000)

#: Weekday name to `datetime.weekday()` index, because `strftime("%A")` is **localised**.
#:
#: Measured, and it is the money path: with `LC_TIME=de_DE` a Monday 02:00 UTC reports
#: ``"Montag"``, matched no name in the table's English list, and the window came back
#: ``off_peak`` -- halving every weekday bill, with no error and a perfectly well-formed
#: figure. Same under ``fr_FR`` (``"lundi"``). The table stores names because a human reads
#: it; the code compares indices, which no locale can move.
_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class PriceTableError(ValueError):
    """A price table that cannot be used, or a question it cannot answer."""


def available_tables() -> tuple[str, ...]:
    """Every committed table id, newest last. A date-named file sorts by its date."""
    return tuple(sorted(path.stem for path in PRICING_DIR.glob("*.json")))


def latest_table_id() -> str:
    """The newest committed table, without naming a version in Python.

    KTD7's shape: a rate change is a new file. Picking the newest by name rather than by a
    constant means adding a table is the whole change, and no code has to be edited to
    start charging the new rates.
    """
    tables = available_tables()
    if not tables:
        raise PriceTableError(
            f"no price tables under {PRICING_DIR}; a ledger row cannot claim a price_table_id"
        )
    return tables[-1]


def load_table(table_id: str | None = None) -> PriceTable:
    """Load and validate one committed table."""
    resolved = table_id or latest_table_id()
    path = PRICING_DIR / f"{resolved}.json"
    if not path.exists():
        raise PriceTableError(f"no price table {resolved!r}; available: {list(available_tables())}")
    document = json.loads(path.read_text(encoding="utf-8"))
    build_validator(PRICING_SCHEMA).validate(document)
    return PriceTable(table_id=resolved, raw=document)


def window_for(raw: Mapping[str, Any], at: dt.datetime) -> str:
    """Which of the two windows a moment falls in, or raises on a naive timestamp."""
    if at.tzinfo is None:  # noqa: SIM102 - kept as its own guard for the message
        raise PriceTableError(
            "a cost depends on the peak window, so the timestamp must carry a timezone; "
            "a naive one would be read as local time and pick the wrong rate"
        )
    peak = raw["peak_windows"]
    moment = at.astimezone(dt.UTC)
    unknown = [name for name in peak["weekdays"] if name.lower() not in _WEEKDAY_INDEX]
    if unknown:
        # Fail closed rather than skipping an unrecognised day, which would silently move
        # that day's calls to the cheaper window.
        raise PriceTableError(f"peak_windows.weekdays names {unknown}, which are not weekdays")
    allowed = {_WEEKDAY_INDEX[name.lower()] for name in peak["weekdays"]}
    if moment.weekday() not in allowed:
        return OFF_PEAK
    for start, end in peak["hours"]:
        # Half-open, so a boundary belongs to exactly one window. The provider writes the
        # windows as "01:00 - 04:00" and does not say whether the endpoints are inclusive;
        # see the plan's unknowns -- getting this wrong is a factor of two.
        if start <= moment.hour < end:
            return PEAK
    return OFF_PEAK


@dataclass(frozen=True, slots=True)
class PriceTable:
    """One loaded table. Immutable, so a row's figure cannot change under it."""

    table_id: str
    raw: Mapping[str, Any]

    @property
    def source(self) -> str:
        return str(self.raw["source"])

    @property
    def retrieved_at(self) -> str:
        return str(self.raw["retrieved_at"])

    @property
    def verification_status(self) -> str:
        return str(self.raw["verification"]["status"])

    @property
    def is_verified(self) -> bool:
        """Whether these rates were checked against the provider's own accounting.

        False means the numbers are *transcribed from documentation* -- an inherited figure,
        not a measurement. Anything that quotes a USD total should say which of the two it
        is resting on, which is why this is a property and not a comment.
        """
        return self.verification_status == "measured"

    def model_version(self, model: str) -> str | None:
        entry = self.raw["models"].get(model)
        return str(entry["model_version"]) if entry else None

    def rate(self, model: str, window: str, kind: str) -> Decimal:
        entry = self.raw["models"].get(model)
        if entry is None:
            raise PriceTableError(f"{model!r} is not in price table {self.table_id!r}")
        if window not in (PEAK, OFF_PEAK):
            raise PriceTableError(f"unknown window {window!r}")
        return Decimal(str(entry["rates"][window][kind]))

    def estimate_usd(
        self, usage: Mapping[str, int | None] | None, *, model: str, at: dt.datetime
    ) -> Decimal | None:
        """The cost of one call, or ``None`` when it cannot be known.

        ``None`` and not zero: a usage block the provider did not fully report cannot be
        priced, and returning the sum of the parts it did report would produce a figure that
        looks measured and is not.

        Reasoning tokens are deliberately *not* priced separately. They are billed as output
        and are a subset of ``completion_tokens``, so pricing them again would double the
        output half of the bill -- the same trap the aggregate documents for token counts.
        """
        if usage is None:
            return None
        entry = self.raw["models"].get(model)
        if entry is None:
            return None

        prompt = _as_count(usage.get("prompt_tokens"))
        completion = _as_count(usage.get("completion_tokens"))
        cached = _as_count(usage.get("cached_input_tokens"))
        if prompt is None or completion is None or cached is None:
            return None
        if cached > prompt:
            # The split between cache-hit and cache-miss input is unknowable, and the two
            # rates differ by a factor of fifty, so a figure derived from this would be
            # arbitrary. Refuse rather than clamp.
            return None

        window = window_for(self.raw, at)
        rates = entry["rates"][window]
        uncached = prompt - cached
        cost = (
            Decimal(cached) * Decimal(str(rates["input_cache_hit"]))
            + Decimal(uncached) * Decimal(str(rates["input_cache_miss"]))
            + Decimal(completion) * Decimal(str(rates["output"]))
        ) / _PER_MILLION
        return cost


def _as_count(value: Any) -> int | None:
    """A non-negative int, or ``None``. ``bool`` excluded: ``True`` is an ``int`` here."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return int(value)
