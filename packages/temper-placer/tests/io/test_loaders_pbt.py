"""Property-based + metamorphic tests for the Rust YAML loaders.

Wave 4, Phase 3 — candidate 2 of
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``
(program gates R1c/R1d). These properties exercise the migrated
``temper_placer.io.netclass_loader`` and ``temper_placer.io.loop_loader``
modules (pure-delegation re-exports of the ``temper_design_bundle_python``
loaders); bit-identical parity against the pinned pre-migration Python is
asserted separately by ``test_loaders_rust_differential.py``.

The candidate covers TWO modules, so the R1c/R1d minima are met per module:
five properties and three metamorphic relations each.

``netclass_loader`` — properties:

- N1. Class-set totality: the loaded ``net_classes`` keys are exactly the
  document's ``classes`` keys, for any generated document.
- N2. Default fall-through is bit-exact: a class omitting an optional key
  receives the corresponding ``DesignRules`` default, and ``clearance``
  specifically receives the document's ``default_clearance_mm`` — the
  *overwritten* value, not the constructor default.
- N3. Explicit values win: a class that supplies a key receives exactly
  that value (bit-exact), whatever the defaults are.
- N4. ``class_pairs`` key canonicity: every key is a 2-tuple in sorted
  order, and the key set is exactly the sort-normalized set of well-formed
  document keys (malformed keys contribute nothing).
- N5. Aliasing and assignment invariants: ``result.class_pairs`` IS
  ``result.design_rules.class_pairs``, and ``net_class_assignments``
  contains every entry of ``TEMPER_NET_ASSIGNMENTS``.

``netclass_loader`` — metamorphic relations:

- MN1. Mapping-order permutation invariance (exact for CONTENT): permuting
  the document's ``classes`` and ``class_pairs`` mapping order leaves every
  loaded value identical. Honestly bounded: ``net_classes`` *insertion
  order* follows the document and is NOT claimed invariant — the relation
  is asserted on sorted items.
- MN2. Pair-key reversal invariance (exact): writing ``B-A`` instead of
  ``A-B`` yields the identical canonical key and the identical value.
- MN3. Unmapped-key inertness (exact): adding top-level or per-class keys
  the loader does not read leaves the result identical.

``loop_loader`` — properties:

- L1. Enum resolution totality: every ``LoopType``/``LoopPriority`` value,
  in any letter casing, resolves to that member and never raises.
- L2. Defaults: an omitted ``max_area_mm2`` is exactly 100.0, an omitted
  ``priority`` is ``MEDIUM``, and an omitted ``events`` block yields a
  ``LoopEvent`` whose six fields are all ``None``.
- L3. Field passthrough is bit-exact: name/description/components/nets and
  every supplied event float arrive unmodified (``float.hex()`` compared).
- L4. Save→load round trip preserves every field bit-exactly.
- L5. Collection assembly: a directory of N uniquely-named templates yields
  a collection of exactly those N loops, ordered by sorted filename.

``loop_loader`` — metamorphic relations:

- ML1. Dict-key-order permutation invariance (exact): the loader reads by
  key, so shuffling the input mapping changes nothing.
- ML2. Unrecognized-key inertness (exact).
- ML3. Emitter idempotence (exact, byte-level): ``save(load(save(x)))``
  produces byte-identical output to ``save(x)``. Honestly bounded: the
  claim is on the emitted BYTES for loops whose fields survive the format
  (the emitter drops falsy ``components``/``nets``/``return_*``, so the
  relation is stated over the re-loaded loop, not over the original).

Every property carries a G4 vacuity mutant: a degenerate kernel is swapped
in via the ``_kernels`` indirection and the property's inner test is
re-run, asserting it fails. A property no mutant can break is not a
property.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
from temper_placer.core.loop import Loop, LoopEvent, LoopPin, LoopPriority, LoopType
from temper_placer.io.loop_loader import (
    LoopLoadError,
    load_loop_collection,
    load_loop_from_dict,
    load_loop_template,
    save_loop_to_yaml,
)
from temper_placer.io.netclass_loader import load_netclass_rules

MAX_EXAMPLES = 60
SETTINGS = settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

_LOOP_TYPE_VALUES = [t.value for t in LoopType.members()]
_LOOP_PRIORITY_VALUES = [p.value for p in LoopPriority.members()]

_EVENT_FIELDS = (
    "di_dt",
    "dv_dt",
    "frequency_hz",
    "peak_current_a",
    "rms_current_a",
    "ringing_freq_hz",
)

# Identifier-ish names: no "-" (it is the class_pairs key separator) and no
# leading/trailing whitespace, so the generated documents stay well-formed.
_NAME = st.text(alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=8)
_FINITE = st.floats(allow_nan=False, allow_infinity=False, width=64)
_CLEARANCE = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)

# Free text that survives a PyYAML dump→load cycle.
#
# YAML's *reader* normalizes line breaks: U+000A, U+000D, U+0085 (NEL),
# U+2028 (LS) and U+2029 (PS) are all line-break characters, so a scalar
# containing one is not recovered verbatim by ``safe_load`` even though
# ``dump(allow_unicode=True)`` emits it. That is a property of PyYAML — the
# tokenizer/emitter this migration deliberately KEEPS (see the loaders'
# module docstring) — not of the loaders, and it held identically before the
# migration: ``test_loaders_rust_differential.py::
# test_yaml_line_break_characters_are_equally_lossy_on_both_sides`` pins the
# two implementations agreeing on such input. The round-trip relations below
# are therefore bounded to text without those characters, which is the
# honest statement of what round-trip parity can claim.
#
# Lone surrogates (Unicode category Cs) are excluded for the same reason:
# they cannot survive the format either — ``yaml.dump`` cannot encode them
# when writing, and the Rust ``Loop`` pyclass's ``String`` fields raise
# ``UnicodeEncodeError`` at the pyo3 boundary when extracting them (a Phase-2
# boundary property, pre-existing and unrelated to the loaders migration).
# ``st.characters()`` in current Hypothesis does NOT exclude Cs by default,
# so it must be blacklisted explicitly or the round-trip properties
# occasionally draw a surrogate and fail on input the format cannot hold.
_YAML_LINE_BREAKS = "\n\r\x85\u2028\u2029"
_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters=_YAML_LINE_BREAKS,
    ),
    max_size=16,
)


def _hex(value):
    """Bit-exact float key (``None`` passes through)."""
    return None if value is None else float(value).hex()


@st.composite
def _netclass_docs(draw, min_classes=0, min_pairs=0):
    """A netclass_rules.yaml-shaped document (already parsed)."""
    default_clearance = draw(_CLEARANCE)
    class_names = draw(
        st.lists(_NAME, min_size=min_classes, max_size=4, unique=True)
    )
    classes = {}
    for name in class_names:
        body = {}
        for key in ("trace_width", "clearance", "via_diameter", "via_drill"):
            if draw(st.booleans()):
                body[key] = draw(_CLEARANCE)
        if draw(st.booleans()):
            body["safety_category"] = draw(st.sampled_from(["HV", "LV", "AC"]))
        classes[name] = body

    pair_names = draw(st.lists(_NAME, min_size=min_pairs * 2, max_size=6, unique=True))
    class_pairs = {}
    for left, right in zip(pair_names[::2], pair_names[1::2]):
        class_pairs[f"{left}-{right}"] = {
            "clearance": draw(_CLEARANCE),
            "because": draw(_TEXT),
        }
    return {
        "default_clearance_mm": default_clearance,
        "classes": classes,
        "class_pairs": class_pairs,
    }


@st.composite
def _loop_dicts(draw):
    """A loop-template-shaped document (already parsed)."""
    data = {
        "name": draw(_NAME),
        "loop_type": draw(st.sampled_from(_LOOP_TYPE_VALUES)),
    }
    if draw(st.booleans()):
        data["description"] = draw(_TEXT)
    if draw(st.booleans()):
        data["priority"] = draw(st.sampled_from(_LOOP_PRIORITY_VALUES))
    if draw(st.booleans()):
        data["components"] = draw(st.lists(_NAME, max_size=3))
    if draw(st.booleans()):
        data["nets"] = draw(st.lists(_NAME, max_size=3))
    if draw(st.booleans()):
        data["max_area_mm2"] = draw(_FINITE)
    if draw(st.booleans()):
        data["events"] = {
            field: draw(_FINITE)
            for field in _EVENT_FIELDS
            if draw(st.booleans())
        }
    if draw(st.booleans()):
        data["pins"] = [
            {"component": draw(_NAME), "pin": draw(_NAME)}
            for _ in range(draw(st.integers(min_value=1, max_value=3)))
        ]
    if draw(st.booleans()):
        data["return_layer"] = draw(_NAME)
    if draw(st.booleans()):
        data["return_net"] = draw(_NAME)
    return data


def _write_yaml(path, document):
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, allow_unicode=True))
    return path


def _loop_fields(loop):
    return (
        loop.name,
        loop.loop_type,
        loop.description,
        tuple((p.component_ref, p.pin_name, p.net_name) for p in loop.pins),
        tuple(loop.components),
        tuple(loop.nets),
        _hex(loop.max_area_mm2),
        loop.priority,
        tuple(_hex(getattr(loop.events, f)) for f in _EVENT_FIELDS),
        loop.return_layer,
        loop.return_net,
    )


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _Kernels:
    """Every kernel a property depends on, swappable for mutation testing."""

    load_netclass = staticmethod(lambda path: load_netclass_rules(path))
    load_loop = staticmethod(lambda data: load_loop_from_dict(data))
    load_template = staticmethod(lambda path: load_loop_template(path))
    load_collection = staticmethod(lambda directory: load_loop_collection(directory))
    save_loop = staticmethod(lambda loop, path: save_loop_to_yaml(loop, path))


_kernels = _Kernels()

_KERNEL_NAMES = (
    "load_netclass",
    "load_loop",
    "load_template",
    "load_collection",
    "save_loop",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _assert_property_fails(property_fn, *args):
    """Run a hypothesis-wrapped property's inner test and require a failure.

    A mutant that the property tolerates means the property is vacuous.
    """
    with pytest.raises((AssertionError, KeyError, AttributeError, TypeError)):
        property_fn.hypothesis.inner_test(*args)


# ---------------------------------------------------------------------------
# netclass_loader — properties
# ---------------------------------------------------------------------------


@SETTINGS
@given(document=_netclass_docs())
def test_n1_class_set_totality(document, tmp_path_factory):
    """N1: loaded net_classes keys == the document's classes keys."""
    path = _write_yaml(tmp_path_factory.mktemp("n1") / "r.yaml", document)
    result = _kernels.load_netclass(path)
    assert set(result.design_rules.net_classes) == set(document["classes"])


@SETTINGS
@given(document=_netclass_docs(min_classes=1))
def test_n2_defaults_fall_through_bit_exactly(document, tmp_path_factory):
    """N2: an omitted key falls through to the DesignRules default, and an
    omitted ``clearance`` falls through to the document's
    ``default_clearance_mm`` (the value assigned before the classes loop)."""
    for body in document["classes"].values():
        body.pop("clearance", None)
        body.pop("trace_width", None)
    path = _write_yaml(tmp_path_factory.mktemp("n2") / "r.yaml", document)
    result = _kernels.load_netclass(path)
    dr = result.design_rules
    for name in document["classes"]:
        nc = dr.net_classes[name]
        assert _hex(nc.clearance) == _hex(document["default_clearance_mm"])
        assert _hex(nc.trace_width) == _hex(dr.default_trace_width)


@SETTINGS
@given(document=_netclass_docs(min_classes=1), explicit=_CLEARANCE)
def test_n3_explicit_values_win_bit_exactly(document, explicit, tmp_path_factory):
    """N3: a class that supplies ``clearance`` gets exactly that value."""
    for body in document["classes"].values():
        body["clearance"] = explicit
    path = _write_yaml(tmp_path_factory.mktemp("n3") / "r.yaml", document)
    result = _kernels.load_netclass(path)
    for name in document["classes"]:
        assert _hex(result.design_rules.net_classes[name].clearance) == _hex(explicit)


@SETTINGS
@given(document=_netclass_docs())
def test_n4_class_pair_keys_are_canonical(document, tmp_path_factory):
    """N4: every key is a sorted 2-tuple, and the key set is exactly the
    sort-normalized set of the document's well-formed pair keys."""
    path = _write_yaml(tmp_path_factory.mktemp("n4") / "r.yaml", document)
    result = _kernels.load_netclass(path)
    expected = set()
    for raw_key in document["class_pairs"]:
        parts = raw_key.split("-")
        if len(parts) == 2:
            expected.add(tuple(sorted(parts)))
    assert set(result.class_pairs) == expected
    for key in result.class_pairs:
        assert isinstance(key, tuple) and len(key) == 2
        assert list(key) == sorted(key)


@SETTINGS
@given(document=_netclass_docs())
def test_n5_aliasing_and_assignments(document, tmp_path_factory):
    """N5: the returned class_pairs IS the one attached to design_rules, and
    every TEMPER_NET_ASSIGNMENTS entry is present."""
    path = _write_yaml(tmp_path_factory.mktemp("n5") / "r.yaml", document)
    result = _kernels.load_netclass(path)
    assert result.class_pairs is result.design_rules.class_pairs
    assignments = result.design_rules.net_class_assignments
    for net, cls in TEMPER_NET_ASSIGNMENTS.items():
        assert assignments[net] == cls


# ---------------------------------------------------------------------------
# netclass_loader — G4 vacuity mutants
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, design_rules, class_pairs):
        self.design_rules = design_rules
        self.class_pairs = class_pairs


class _FakeRules:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _empty_netclass_kernel(path):
    """Degenerate: loads nothing at all."""
    pairs = {}
    return _FakeResult(
        _FakeRules(
            net_classes={},
            net_class_assignments={},
            class_pairs=pairs,
            default_trace_width=0.2,
        ),
        pairs,
    )


def test_n1_fails_for_empty_loader(_restore_kernels, tmp_path_factory):
    _kernels.load_netclass = _empty_netclass_kernel
    doc = {"default_clearance_mm": 0.2, "classes": {"A": {}}, "class_pairs": {}}
    _assert_property_fails(test_n1_class_set_totality, doc, tmp_path_factory)


def test_n2_fails_for_constant_default_kernel(_restore_kernels, tmp_path_factory):
    """A loader that ignores ``default_clearance_mm`` and always uses 0.2."""

    def constant_kernel(path):
        real = load_netclass_rules(path)
        for nc in list(real.design_rules.net_classes):
            real.design_rules.net_classes[nc] = real.design_rules.net_classes[nc].model_copy(
                update={"clearance": 0.2}
            )
        return real

    _kernels.load_netclass = constant_kernel
    doc = {"default_clearance_mm": 7.5, "classes": {"A": {}}, "class_pairs": {}}
    _assert_property_fails(test_n2_defaults_fall_through_bit_exactly, doc, tmp_path_factory)


def test_n3_fails_for_defaults_only_kernel(_restore_kernels, tmp_path_factory):
    """A loader that ignores explicit per-class values."""

    def defaults_only(path):
        real = load_netclass_rules(path)
        for name in list(real.design_rules.net_classes):
            real.design_rules.net_classes[name] = real.design_rules.net_classes[
                name
            ].model_copy(update={"clearance": 0.0})
        return real

    _kernels.load_netclass = defaults_only
    doc = {"default_clearance_mm": 0.2, "classes": {"A": {}}, "class_pairs": {}}
    _assert_property_fails(test_n3_explicit_values_win_bit_exactly, doc, 3.5, tmp_path_factory)


def test_n4_fails_for_unsorted_key_kernel(_restore_kernels, tmp_path_factory):
    """A loader that keeps the raw (unsorted) pair order."""

    def unsorted_keys(path):
        real = load_netclass_rules(path)
        real.class_pairs = {tuple(reversed(k)): v for k, v in real.class_pairs.items()}
        real.design_rules.class_pairs = real.class_pairs
        return real

    _kernels.load_netclass = unsorted_keys
    doc = {
        "default_clearance_mm": 0.2,
        "classes": {},
        "class_pairs": {"Zeta-Alpha": {"clearance": 1.0, "because": "x"}},
    }
    _assert_property_fails(test_n4_class_pair_keys_are_canonical, doc, tmp_path_factory)


def test_n5_fails_for_unaliased_kernel(_restore_kernels, tmp_path_factory):
    """A loader that returns a COPY of class_pairs instead of the same dict,
    and skips the TEMPER_NET_ASSIGNMENTS update."""

    def unaliased(path):
        real = load_netclass_rules(path)
        real.class_pairs = dict(real.class_pairs)
        real.design_rules.net_class_assignments = {}
        return real

    _kernels.load_netclass = unaliased
    doc = {"default_clearance_mm": 0.2, "classes": {}, "class_pairs": {}}
    _assert_property_fails(test_n5_aliasing_and_assignments, doc, tmp_path_factory)


# ---------------------------------------------------------------------------
# netclass_loader — metamorphic relations
# ---------------------------------------------------------------------------


@SETTINGS
@given(document=_netclass_docs(), seed=st.integers(min_value=0, max_value=10**6))
def test_mn1_mapping_order_permutation_invariance(document, seed, tmp_path_factory):
    """MN1 (exact for content): permuting the document's mapping order leaves
    every loaded value identical. Bounded: ``net_classes`` INSERTION ORDER
    follows the document and is not claimed invariant, so the comparison is
    on sorted items."""
    import random

    rng = random.Random(seed)

    def shuffled(mapping):
        items = list(mapping.items())
        rng.shuffle(items)
        return dict(items)

    permuted = {
        "default_clearance_mm": document["default_clearance_mm"],
        "classes": shuffled(document["classes"]),
        "class_pairs": shuffled(document["class_pairs"]),
    }
    base_dir = tmp_path_factory.mktemp("mn1")
    a = _kernels.load_netclass(_write_yaml(base_dir / "a.yaml", document))
    b = _kernels.load_netclass(_write_yaml(base_dir / "b.yaml", permuted))
    assert sorted(a.design_rules.net_classes.items()) == sorted(
        b.design_rules.net_classes.items()
    )
    assert sorted(a.class_pairs.items()) == sorted(b.class_pairs.items())


@SETTINGS
@given(left=_NAME, right=_NAME, clearance=_CLEARANCE, because=_TEXT)
def test_mn2_pair_key_reversal_invariance(left, right, clearance, because, tmp_path_factory):
    """MN2 (exact): ``A-B`` and ``B-A`` canonicalize to the identical key
    with the identical value."""
    assume(left != right)
    base = {"default_clearance_mm": 0.2, "classes": {}}
    forward = dict(base, class_pairs={f"{left}-{right}": {"clearance": clearance, "because": because}})
    reverse = dict(base, class_pairs={f"{right}-{left}": {"clearance": clearance, "because": because}})
    base_dir = tmp_path_factory.mktemp("mn2")
    a = _kernels.load_netclass(_write_yaml(base_dir / "f.yaml", forward))
    b = _kernels.load_netclass(_write_yaml(base_dir / "r.yaml", reverse))
    assert list(a.class_pairs) == list(b.class_pairs)
    assert a.class_pairs == b.class_pairs


@SETTINGS
@given(document=_netclass_docs(), noise_key=_NAME, noise_value=_TEXT)
def test_mn3_unmapped_keys_are_inert(document, noise_key, noise_value, tmp_path_factory):
    """MN3 (exact): keys the loader does not read change nothing."""
    assume(noise_key not in {"default_clearance_mm", "classes", "class_pairs"})
    noisy = dict(document)
    noisy[noise_key] = noise_value
    noisy["classes"] = {
        name: dict(body, unmapped_note=noise_value)
        for name, body in document["classes"].items()
    }
    base_dir = tmp_path_factory.mktemp("mn3")
    a = _kernels.load_netclass(_write_yaml(base_dir / "a.yaml", document))
    b = _kernels.load_netclass(_write_yaml(base_dir / "b.yaml", noisy))
    assert list(a.design_rules.net_classes.items()) == list(b.design_rules.net_classes.items())
    assert a.class_pairs == b.class_pairs


def test_mn_relations_are_discriminating(tmp_path_factory):
    """Vacuity sanity: the MN input space really does produce differing
    results for differing documents (otherwise the invariances are trivial)."""
    base_dir = tmp_path_factory.mktemp("mn_sanity")
    a = load_netclass_rules(
        _write_yaml(
            base_dir / "a.yaml",
            {"default_clearance_mm": 0.2, "classes": {"A": {"clearance": 1.0}}, "class_pairs": {}},
        )
    )
    b = load_netclass_rules(
        _write_yaml(
            base_dir / "b.yaml",
            {"default_clearance_mm": 0.2, "classes": {"A": {"clearance": 2.0}}, "class_pairs": {}},
        )
    )
    assert a.design_rules.net_classes["A"] != b.design_rules.net_classes["A"]


# ---------------------------------------------------------------------------
# loop_loader — properties
# ---------------------------------------------------------------------------


@SETTINGS
@given(
    loop_type=st.sampled_from(_LOOP_TYPE_VALUES),
    priority=st.sampled_from(_LOOP_PRIORITY_VALUES),
    flips=st.lists(st.booleans(), min_size=24, max_size=24),
)
def test_l1_enum_resolution_is_case_insensitive_and_total(loop_type, priority, flips):
    """L1: every enum value, in any casing, resolves to that member."""

    def recase(text, mask):
        return "".join(c.upper() if bit else c.lower() for c, bit in zip(text, mask))

    data = {
        "name": "n",
        "loop_type": recase(loop_type, flips),
        "priority": recase(priority, flips[::-1]),
    }
    loop = _kernels.load_loop(data)
    assert loop.loop_type.value == loop_type
    assert loop.priority.value == priority


@SETTINGS
@given(name=_NAME, loop_type=st.sampled_from(_LOOP_TYPE_VALUES))
def test_l2_omitted_optionals_take_the_documented_defaults(name, loop_type):
    """L2: max_area_mm2 == 100.0 exactly, priority == MEDIUM, events all None."""
    loop = _kernels.load_loop({"name": name, "loop_type": loop_type})
    assert _hex(loop.max_area_mm2) == _hex(100.0)
    assert loop.priority == LoopPriority.MEDIUM
    assert all(getattr(loop.events, field) is None for field in _EVENT_FIELDS)
    assert loop.description == ""
    assert loop.pins == []
    assert loop.components == []
    assert loop.nets == []


@SETTINGS
@given(data=_loop_dicts())
def test_l3_field_passthrough_is_bit_exact(data):
    """L3: supplied fields arrive unmodified, floats compared bit-for-bit."""
    loop = _kernels.load_loop(dict(data))
    assert loop.name == data["name"]
    assert loop.loop_type.value == data["loop_type"]
    assert loop.description == data.get("description", "")
    assert loop.components == data.get("components", [])
    assert loop.nets == data.get("nets", [])
    assert _hex(loop.max_area_mm2) == _hex(float(data.get("max_area_mm2", 100.0)))
    for field in _EVENT_FIELDS:
        expected = data.get("events", {}).get(field)
        assert _hex(getattr(loop.events, field)) == _hex(expected)
    assert loop.return_layer == data.get("return_layer")
    assert loop.return_net == data.get("return_net")


@SETTINGS
@given(data=_loop_dicts())
def test_l4_save_load_round_trip_is_bit_exact(data, tmp_path_factory):
    """L4: every field survives save→load with identical bits."""
    original = _kernels.load_loop(dict(data))
    path = tmp_path_factory.mktemp("l4") / "loop.yaml"
    _kernels.save_loop(original, path)
    reloaded = _kernels.load_template(path)
    assert _loop_fields(reloaded) == _loop_fields(original)


@SETTINGS
@given(
    names=st.lists(_NAME, min_size=1, max_size=5, unique=True),
    loop_type=st.sampled_from(_LOOP_TYPE_VALUES),
)
def test_l5_collection_assembly_is_complete_and_sorted(names, loop_type, tmp_path_factory):
    """L5: N templates -> exactly those N loops, ordered by sorted filename.

    The property's documented bound is "N **uniquely-named** templates". On a
    case-insensitive filesystem (macOS APFS, the default for this repo's dev
    machines) names that differ only by case are NOT unique FILE names —
    ``E.yaml`` and ``e.yaml`` collapse to one directory entry — so such lists
    are excluded here; the loaders' traversal is ``sorted(directory.glob(
    pattern))`` and cannot conjure a file the filesystem does not store.
    """
    assume(len({n.lower() for n in names}) == len(names))
    directory = tmp_path_factory.mktemp("l5")
    for name in names:
        _write_yaml(directory / f"{name}.yaml", {"name": name, "loop_type": loop_type})
    collection = _kernels.load_collection(directory)
    assert [ln.name for ln in collection.loops] == sorted(names)


# ---------------------------------------------------------------------------
# loop_loader — G4 vacuity mutants
# ---------------------------------------------------------------------------


def test_l1_fails_for_case_sensitive_kernel(_restore_kernels):
    """A loader that only matches already-lowercase enum values."""

    def case_sensitive(data):
        if data.get("loop_type") not in _LOOP_TYPE_VALUES:
            raise LoopLoadError(f"Unknown loop type: {data.get('loop_type')}")
        return load_loop_from_dict(data)

    _kernels.load_loop = case_sensitive
    with pytest.raises(LoopLoadError):
        test_l1_enum_resolution_is_case_insensitive_and_total.hypothesis.inner_test(
            "commutation", "critical", [True] * 24
        )


def test_l2_fails_for_wrong_default_kernel(_restore_kernels):
    """A loader whose max_area default is 0.0 and whose priority default is LOW."""

    def wrong_defaults(data):
        payload = dict(data)
        payload.setdefault("max_area_mm2", 0.0)
        payload.setdefault("priority", "low")
        return load_loop_from_dict(payload)

    _kernels.load_loop = wrong_defaults
    _assert_property_fails(test_l2_omitted_optionals_take_the_documented_defaults, "n", "custom")


def test_l3_fails_for_rounding_kernel(_restore_kernels):
    """A loader that rounds max_area_mm2 — invisible to a tolerance-based
    assertion, caught by the bit-exact one."""

    def rounding(data):
        payload = dict(data)
        if "max_area_mm2" in payload:
            payload["max_area_mm2"] = round(float(payload["max_area_mm2"]), 6)
        return load_loop_from_dict(payload)

    _kernels.load_loop = rounding
    _assert_property_fails(
        test_l3_field_passthrough_is_bit_exact,
        {"name": "n", "loop_type": "custom", "max_area_mm2": 1.23456789012345},
    )


def test_l4_fails_for_lossy_emitter(_restore_kernels, tmp_path_factory):
    """An emitter that drops the events block loses fields across the trip."""

    def lossy_save(loop, path):
        stripped = Loop(
            name=loop.name,
            loop_type=loop.loop_type,
            description=loop.description,
            pins=list(loop.pins),
            components=list(loop.components),
            nets=list(loop.nets),
            max_area_mm2=loop.max_area_mm2,
            priority=loop.priority,
            events=LoopEvent(),
            return_layer=loop.return_layer,
            return_net=loop.return_net,
        )
        save_loop_to_yaml(stripped, path)

    _kernels.save_loop = lossy_save
    _assert_property_fails(
        test_l4_save_load_round_trip_is_bit_exact,
        {"name": "n", "loop_type": "custom", "events": {"di_dt": 1.5}},
        tmp_path_factory,
    )


def test_l5_fails_for_first_file_only_kernel(_restore_kernels, tmp_path_factory):
    """A collection loader that stops after the first template."""

    def first_only(directory):
        collection = load_loop_collection(directory)
        collection.loops = collection.loops[:1]
        return collection

    _kernels.load_collection = first_only
    _assert_property_fails(
        test_l5_collection_assembly_is_complete_and_sorted, ["a", "b"], "custom", tmp_path_factory
    )


# ---------------------------------------------------------------------------
# loop_loader — metamorphic relations
# ---------------------------------------------------------------------------


@SETTINGS
@given(data=_loop_dicts(), seed=st.integers(min_value=0, max_value=10**6))
def test_ml1_key_order_permutation_invariance(data, seed):
    """ML1 (exact): the loader reads by key, so input order changes nothing."""
    import random

    items = list(data.items())
    random.Random(seed).shuffle(items)
    assert _loop_fields(_kernels.load_loop(dict(items))) == _loop_fields(
        _kernels.load_loop(dict(data))
    )


@SETTINGS
@given(data=_loop_dicts(), noise_key=_NAME, noise_value=_TEXT)
def test_ml2_unrecognized_keys_are_inert(data, noise_key, noise_value):
    """ML2 (exact): keys the loader never reads change nothing."""
    known = {
        "name",
        "loop_type",
        "description",
        "pins",
        "components",
        "nets",
        "max_area_mm2",
        "priority",
        "events",
        "return_layer",
        "return_net",
    }
    assume(noise_key not in known)
    noisy = dict(data)
    noisy[noise_key] = noise_value
    assert _loop_fields(_kernels.load_loop(noisy)) == _loop_fields(
        _kernels.load_loop(dict(data))
    )


@SETTINGS
@given(data=_loop_dicts())
def test_ml3_emitter_is_byte_idempotent(data, tmp_path_factory):
    """ML3 (exact, byte-level): re-emitting a loaded loop reproduces the same
    bytes. Bounded: the claim is over the RE-LOADED loop, because the emitter
    deliberately omits falsy ``components``/``nets``/``return_*``."""
    directory = tmp_path_factory.mktemp("ml3")
    once = directory / "once.yaml"
    twice = directory / "twice.yaml"
    _kernels.save_loop(_kernels.load_loop(dict(data)), once)
    _kernels.save_loop(_kernels.load_template(once), twice)
    assert twice.read_bytes() == once.read_bytes()


def test_ml_relations_are_discriminating(tmp_path_factory):
    """Vacuity sanity: the loop input space is genuinely discriminating —
    differing documents yield differing loops and differing bytes."""
    a = load_loop_from_dict({"name": "a", "loop_type": "custom"})
    b = load_loop_from_dict({"name": "b", "loop_type": "bootstrap", "priority": "critical"})
    assert _loop_fields(a) != _loop_fields(b)
    directory = tmp_path_factory.mktemp("ml_sanity")
    save_loop_to_yaml(a, directory / "a.yaml")
    save_loop_to_yaml(b, directory / "b.yaml")
    assert (directory / "a.yaml").read_bytes() != (directory / "b.yaml").read_bytes()


def test_pin_records_survive_the_round_trip(tmp_path_factory):
    """Named-pin coverage for L4/ML3 (the generated dicts carry netless pins,
    this pins the net-carrying branch of the emitter)."""
    loop = Loop(
        name="pins",
        loop_type=LoopType.COMMUTATION,
        description="",
        pins=[LoopPin("Q1", "G", "NET"), LoopPin("Q2", "S")],
    )
    path = tmp_path_factory.mktemp("pins") / "p.yaml"
    save_loop_to_yaml(loop, path)
    reloaded = load_loop_template(path)
    assert [(p.component_ref, p.pin_name, p.net_name) for p in reloaded.pins] == [
        ("Q1", "G", "NET"),
        ("Q2", "S", None),
    ]
