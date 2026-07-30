"""Typed, deterministic evidence model for the creepage campaign queue."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Literal

from temper_placer.validation._drc_api import DrcError

FixClass = Literal["layout_routing", "same_package_bom", "rule_policy"]

_NUMBER = r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_LABELLED_DISTANCE_RE = re.compile(
    rf"\bactual\s*[:=]?\s*(?P<actual>{_NUMBER})\s*mm\b.*?"
    rf"\brequired\s*[:=]?\s*(?P<required>{_NUMBER})\s*mm\b",
    re.IGNORECASE,
)
_INEQUALITY_DISTANCE_RE = re.compile(
    r"(?P<actual>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*mm\s*<\s*"
    r"(?P<required>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*mm",
    re.IGNORECASE,
)


def _normalize_labels(values: Iterable[str]) -> tuple[str, ...]:
    """Normalize evidence labels while preserving a deterministic order."""
    labels = {value.strip() for value in values}
    if any(not value for value in labels):
        raise ValueError("evidence labels must not be empty")
    return tuple(sorted(labels))


@dataclass(frozen=True, slots=True)
class CreepageObservation:
    """One canonical creepage observation, including incomplete evidence."""

    rule: str
    location: tuple[float, float]
    message: str
    components: tuple[str, ...] = ()
    nets: tuple[str, ...] = ()
    actual_distance_mm: float | None = None
    required_distance_mm: float | None = None

    def __post_init__(self) -> None:
        rule = self.rule.strip().lower()
        message = self.message.strip()
        if not rule:
            raise ValueError("rule must not be empty")
        if not message:
            raise ValueError("message must not be empty")
        if len(self.location) != 2 or any(
            not math.isfinite(value) for value in self.location
        ):
            raise ValueError("location must contain two finite coordinates")

        actual = self.actual_distance_mm
        required = self.required_distance_mm
        if actual is not None and (not math.isfinite(actual) or actual < 0):
            raise ValueError("actual distance must be finite and non-negative")
        if required is not None and (not math.isfinite(required) or required <= 0):
            raise ValueError("required distance must be finite and positive")
        if actual is not None and required is not None and actual >= required:
            raise ValueError("actual distance must be below required distance")

        object.__setattr__(self, "rule", rule)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "components", _normalize_labels(self.components))
        object.__setattr__(self, "nets", _normalize_labels(self.nets))

    @property
    def stable_identity(self) -> str:
        """Return an identity stable across reference-designator renumbering."""
        # Component references are deliberately excluded: they are useful
        # evidence for a reviewer but are not stable physical identity.
        payload = {
            "location_mm": [round(value, 3) for value in self.location],
            "nets": self.nets,
            "rule": self.rule,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CreepageQueueItem:
    """A classified observation with an auditable reason for its class."""

    observation: CreepageObservation
    fix_class: FixClass
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("rationale must not be empty")

    @property
    def stable_identity(self) -> str:
        return self.observation.stable_identity


def _classify(
    observation: CreepageObservation,
    rule_policy_identities: Collection[str],
) -> tuple[FixClass, str]:
    if observation.stable_identity in rule_policy_identities:
        return "rule_policy", "explicit rule/policy investigation disposition"
    if (
        not observation.components
        or not observation.nets
        or observation.actual_distance_mm is None
        or observation.required_distance_mm is None
    ):
        return "rule_policy", "insufficient structured evidence; investigate before fixing"
    if len(observation.components) == 1:
        return "same_package_bom", "single-component geometry requires layout-first BOM review"
    return "layout_routing", "multi-component violation is a layout/routing candidate"


def classify_creepage(
    observations: Iterable[CreepageObservation],
    *,
    rule_policy_identities: Collection[str] = (),
) -> tuple[CreepageQueueItem, ...]:
    """Normalize, deduplicate, classify, and sort creepage observations.

    Duplicate reports for one physical observation are collapsed by stable
    identity. If reruns provide different human-readable details for that
    identity, the lexicographically smallest representation is retained so
    the result remains deterministic and never depends on input order.
    """
    by_identity: dict[str, CreepageObservation] = {}
    for observation in observations:
        identity = observation.stable_identity
        previous = by_identity.get(identity)
        if previous is None or _observation_sort_key(observation) < _observation_sort_key(
            previous
        ):
            by_identity[identity] = observation

    policy_ids = frozenset(rule_policy_identities)
    items = []
    for identity in sorted(by_identity):
        observation = by_identity[identity]
        fix_class, rationale = _classify(observation, policy_ids)
        items.append(CreepageQueueItem(observation, fix_class, rationale))
    return tuple(items)


def observation_from_drc_error(error: DrcError) -> CreepageObservation:
    """Convert one KiCad creepage error into queue evidence.

    Only the creepage rule is accepted. Distance fields are parsed when the
    message uses explicit labels or a strict ``actual mm < required mm``
    inequality; unknown message formats deliberately produce incomplete
    evidence so the classifier sends them to investigation.
    """
    if error.rule.strip().casefold() != "creepage":
        raise ValueError(f"expected a creepage DRC error, got {error.rule!r}")

    actual, required = _parse_distances(error.message)
    return CreepageObservation(
        rule=error.rule,
        location=error.location,
        message=error.message,
        components=tuple(error.components),
        nets=tuple(error.nets),
        actual_distance_mm=actual,
        required_distance_mm=required,
    )


def creepage_observations_from_errors(
    errors: Iterable[DrcError],
) -> tuple[CreepageObservation, ...]:
    """Extract creepage observations without mixing in other DRC rules."""
    return tuple(
        observation_from_drc_error(error)
        for error in errors
        if error.rule.strip().casefold() == "creepage"
    )


def _parse_distances(message: str) -> tuple[float | None, float | None]:
    match = _LABELLED_DISTANCE_RE.search(message)
    if match:
        return _valid_distance_pair(
            float(match.group("actual")), float(match.group("required"))
        )

    match = _INEQUALITY_DISTANCE_RE.search(message)
    if match:
        return _valid_distance_pair(float(match.group("actual")), float(match.group("required")))
    return None, None


def _valid_distance_pair(actual: float, required: float) -> tuple[float | None, float | None]:
    if math.isfinite(actual) and math.isfinite(required) and 0 <= actual < required:
        return actual, required
    return None, None


def _observation_sort_key(
    observation: CreepageObservation,
) -> tuple[object, ...]:
    """Return a total ordering key for duplicate observations."""
    return (
        observation.message,
        observation.components,
        observation.nets,
        observation.actual_distance_mm,
        observation.required_distance_mm,
    )
