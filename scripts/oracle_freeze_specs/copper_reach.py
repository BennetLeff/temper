"""FREEZE spec: ``io/real_board.py::_copper_reach_mm`` (U5 first retiree).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/io/_copper_reach_py_oracle.py
  Pinned verbatim at commit ``d7a22b5d16d4db7d47be39f9d7580921eb9e5263``
  (the file's own header). Unchanged for 863 commits as of the freeze
  (measured 2026-08-11 against ``HEAD``) -- far past the plan's 10-
  consecutive-commit R19-shaped bar.

Kernel:
  packages/temper-geometry/src/copper_reach.rs :: copper_reach_mm
  Unchanged for 182 commits over the same span. Already partially covered
  by 3 hand-written unit tests in that file's own ``mod tests`` (the exact
  NaN/Infinity cases this spec's corpus also carries) -- this FREEZE
  formalizes and extends that ad hoc coverage into a measured, non-vacuous
  golden-vector corpus, it does not invent coverage from nothing.

Differential (retired by this same change):
  packages/temper-placer/tests/io/test_copper_reach_rust_differential.py
  16/16 passed at freeze time (`pytest tests/io/test_copper_reach_rust_
  differential.py -q`, 2026-08-11). The `test_shipped_module_delegates_to_
  rust` wiring check in that file is NOT part of the oracle differential
  (it asserts production wiring, Stage 7 concern) and is intentionally
  left in place after this freeze -- only the oracle-comparison tests are
  removed, because their job is now done by the Rust golden-vector test.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: this is a bounding-box/reach computation for
    router hot-path sizing, not creepage/clearance/via-keepout geometry
    (those live in creepage_check.rs / via_clearance.rs / clearance_geometry.rs
    and are explicitly excluded from this batch).
  - No host-facility or entropy dependency: pure arithmetic (`math.hypot`,
    a `max` reduction) plus `pad_bounding_radius`, which is itself already
    a portable Rust kernel with no dlsym/libm boundary crossing.
  - Input domain (a short list of pads, each a fixed-shape numeric tuple)
    is small and well enumerable -- exactly FREEZE's "enumerable or
    samplable" criterion.

Reproduction / regeneration note: ``run_oracle`` below imports the pinned
oracle module directly so the corpus generation step is byte-for-byte the
oracle's own output, not a re-transcription of it (transcribing it here
would risk the exact "two copies of the same bug" failure the plan's
oracle-disposition table warns against). Once this spec has been run and
the oracle file deleted (which happens in the same commit), re-running
this generator will fail with an import error by design -- the frozen
corpus is meant to be extended, if ever, by reviving the oracle from git
history (`git show d7a22b5d16d4db7d47be39f9d7580921eb9e5263:packages/
temper-placer/tests/io/_copper_reach_py_oracle.py`) for that one session,
not by leaving a live copy around indefinitely (which would defeat the
retirement).
"""

from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib.oracle_freeze import (  # noqa: E402
    FreezeCase,
    FreezeSpec,
    NonVacuityCheck,
    SplitMix64,
    rust_f64_literal,
)

_PLACER_TESTS_ROOT = Path(__file__).resolve().parent.parent.parent / "packages" / "temper-placer"


def _pad_geometry():
    from temper_placer.core.pad_geometry import pad_bounding_radius, shape_code

    return pad_bounding_radius, shape_code


def _oracle_module():
    """Import the pinned oracle.

    Expected to fail once the oracle has been retired (this spec's own
    first run deletes it in the same commit) -- see the module docstring's
    "Reproduction / regeneration note". Raises a clear, actionable error
    rather than a bare ``ModuleNotFoundError`` so `--check`/regeneration
    attempts after retirement fail with an explanation instead of a stack
    trace.
    """
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    try:
        return importlib.import_module("tests.io._copper_reach_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show d7a22b5d16d4db7d47be39f9d7580921eb9e5263:packages/temper-placer/"
            "tests/io/_copper_reach_py_oracle.py > packages/temper-placer/tests/io/"
            "_copper_reach_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


SHAPES = ("circle", "oval", "rect", "roundrect", "thru_hole")
SHAPE_TAG = {s: f"shape_{s}" for s in SHAPES}
UNKNOWN_SHAPE_TAG = "shape_unknown"


def _pad(ox, oy, w=1.0, h=2.0, shape="rect", ratio=0.25):
    return {"offset": (ox, oy), "width": w, "height": h, "shape": shape, "roundrect_ratio": ratio}


def _tags_for(pads: list[dict]) -> frozenset[str]:
    pad_bounding_radius, shape_code = _pad_geometry()
    tags: set[str] = set()
    if not pads:
        tags.add("empty")
        return frozenset(tags)
    tags.add("single_pad" if len(pads) == 1 else "multi_pad")

    reaches: list[float] = []
    for p in pads:
        ox, oy = p["offset"]
        if any(isinstance(v, float) and math.isnan(v) for v in (ox, oy)):
            tags.add("nan_present")
        if any(isinstance(v, float) and math.isinf(v) for v in (ox, oy)):
            tags.add("inf_present")
        if (isinstance(ox, float) and ox < 0) or (isinstance(oy, float) and oy < 0):
            tags.add("negative_offset")
        shape = p["shape"]
        tags.add(SHAPE_TAG.get(shape, UNKNOWN_SHAPE_TAG))
        try:
            reach = math.hypot(ox, oy) + pad_bounding_radius(
                p["width"], p["height"], shape, p["roundrect_ratio"]
            )
        except (ValueError, OverflowError):
            reach = float("nan")
        if not math.isnan(reach):
            reaches.append(reach)

    if len(reaches) >= 2:
        reaches.sort()
        for a, b in zip(reaches, reaches[1:], strict=False):
            if abs(a - b) < 1e-3 * max(1.0, abs(a)):
                tags.add("near_tie")
                break

    return frozenset(tags)


def _curated_cases() -> list[FreezeCase]:
    cases: list[tuple[str, list[dict]]] = [
        ("empty", []),
        ("single_at_origin", [_pad(0.0, 0.0)]),
        ("single_offset", [_pad(3.0, 4.0)]),
        ("two_pads_second_further", [_pad(1.0, 0.0), _pad(10.0, 0.0)]),
        ("two_pads_first_further", [_pad(10.0, 0.0), _pad(1.0, 0.0)]),
        ("negative_offsets", [_pad(-3.0, -4.0)]),
        ("circle_shape", [_pad(1.0, 1.0, shape="circle")]),
        ("oval_shape", [_pad(1.0, 1.0, shape="oval")]),
        ("roundrect_shape", [_pad(1.0, 1.0, shape="roundrect", ratio=0.4)]),
        ("thru_hole_shape", [_pad(1.0, 1.0, shape="thru_hole")]),
        ("unknown_shape_falls_back", [_pad(1.0, 1.0, shape="not-a-shape")]),
        ("zero_size_pad", [_pad(2.0, 0.0, w=0.0, h=0.0)]),
        ("tie_between_pads", [_pad(3.0, 4.0), _pad(4.0, 3.0)]),
        ("nan_offset_kept_not_discarded", [_pad(math.nan, 0.0), _pad(10.0, 0.0)]),
        ("nan_second_does_not_displace_finite_max", [_pad(10.0, 0.0), _pad(math.nan, 0.0)]),
        ("infinity_beats_nan", [_pad(math.inf, math.nan)]),
    ]
    out = []
    for name, pads in cases:
        out.append(FreezeCase(input=pads, tags=_tags_for(pads) | {f"named:{name}"}))
    return out


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    shapes = SHAPES + ("not-a-shape",)
    out: list[FreezeCase] = []
    for _ in range(n):
        n_pads = 1 + rng.index(4)
        pads = []
        for _p in range(n_pads):
            ox = rng.range(-50.0, 50.0)
            oy = rng.range(-50.0, 50.0)
            special_roll = rng.index(100)
            if special_roll < 18:
                # inject a NaN into one coordinate -- this is the entire
                # point of this corpus (the module docstring's NaN
                # contract), so it must be common, not a rare fluke.
                if rng.boolean():
                    ox = math.nan
                else:
                    oy = math.nan
            elif special_roll < 24:
                if rng.boolean():
                    ox = math.inf if rng.boolean() else -math.inf
                else:
                    oy = math.inf if rng.boolean() else -math.inf
            w = rng.range(0.05, 5.0)
            h = rng.range(0.05, 5.0)
            shape = shapes[rng.index(len(shapes))]
            ratio = rng.range(0.0, 0.5)
            pads.append(_pad(ox, oy, w=w, h=h, shape=shape, ratio=ratio))
        out.append(FreezeCase(input=pads, tags=_tags_for(pads)))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(40, seed=0xC0FFEE_C0117EA)


def run_oracle(pads: list[dict]):
    oracle = _oracle_module()
    return oracle.copper_reach_mm(pads, 0.0)


def _render_pad_tuple(p: dict) -> str:
    _pad_bounding_radius, shape_code = _pad_geometry()
    ox, oy = p["offset"]
    code = shape_code(p["shape"])
    return (
        f"({rust_f64_literal(ox)}, {rust_f64_literal(oy)}, "
        f"{rust_f64_literal(p['width'])}, {rust_f64_literal(p['height'])}, "
        f"{code}i64, {rust_f64_literal(p['roundrect_ratio'])})"
    )


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `copper_reach_mm` (FREEZE, U4/U5).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec copper_reach`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/copper_reach.py's module docstring).")
    lines.append("    struct FrozenCopperReachCase {")
    lines.append("        pads: &'static [PadRow],")
    lines.append("        expected_bits: u64,")
    lines.append("        tags: &'static [&'static str],")
    lines.append("    }")
    lines.append("")
    lines.append("    const FROZEN_COPPER_REACH_GOLDEN: &[FrozenCopperReachCase] = &[")
    for case, output in results:
        pads_rs = ", ".join(_render_pad_tuple(p) for p in case.input)
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("        FrozenCopperReachCase {")
        lines.append(f"            pads: &[{pads_rs}],")
        lines.append(f"            expected_bits: {_bits(output):#018x}_u64,")
        lines.append(f"            tags: &[{tags_rs}],")
        lines.append("        },")
    lines.append("    ];")
    lines.append("")
    lines.append("    #[cfg_attr(test, test)]")
    lines.append("    fn frozen_copper_reach_matches_golden_corpus() {")
    lines.append("        for case in FROZEN_COPPER_REACH_GOLDEN {")
    lines.append("            let got = copper_reach_mm(case.pads);")
    lines.append("            let want = f64::from_bits(case.expected_bits);")
    lines.append(
        "            let ok = (got.is_nan() && want.is_nan()) || got.to_bits() == want.to_bits();"
    )
    lines.append('            assert!(ok, "tags={:?}: got {:?} want {:?}", case.tags, got, want);')
    lines.append("        }")
    lines.append("    }")
    lines.append("")
    lines.append("    /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("    /// ever hand-edited down to something trivially satisfiable. Mirrors the")
    lines.append("    /// coverage-guard convention in creepage_check.rs / via_clearance.rs (PR")
    lines.append("    /// #1007) and property_campaigns.rs's IPC-2221 bracket guard.")
    lines.append("    #[cfg_attr(test, test)]")
    lines.append("    fn frozen_copper_reach_corpus_is_non_vacuous() {")
    lines.append("        let n = FROZEN_COPPER_REACH_GOLDEN.len() as u32;")
    lines.append(
        "        let count = |tag: &str| FROZEN_COPPER_REACH_GOLDEN.iter()."
        "filter(|c| c.tags.contains(&tag)).count() as u32;"
    )
    for nvc in _NON_VACUITY:
        if nvc.min_count:
            lines.append(
                f'        assert!(count("{nvc.tag}") >= {nvc.min_count}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {nvc.min_count}) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
        else:
            pct = int(round(nvc.min_fraction * 100))
            lines.append(
                f'        assert!(count("{nvc.tag}") * 100 >= n * {pct}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {pct}%) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
    lines.append("    }")
    return "\n".join(lines)


def _bits(x: float) -> int:
    import struct

    return struct.unpack(">Q", struct.pack(">d", x))[0]


_NON_VACUITY = [
    NonVacuityCheck(
        tag="nan_present",
        description="the NaN-is-kept-not-discarded contract is the entire point of this suite",
        min_fraction=0.10,
    ),
    NonVacuityCheck(
        tag="inf_present",
        description="infinity-beats-nan via py_hypot must be exercised at least once",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="multi_pad",
        description="max()-over-pads reduction only exercised with >=2 pads",
        min_fraction=0.40,
    ),
    NonVacuityCheck(
        tag="negative_offset",
        description="offsets must not be exclusively non-negative",
        min_fraction=0.15,
    ),
    NonVacuityCheck(
        tag="near_tie",
        description="tie-break direction (first pad wins ties, strict `>`) must be exercised",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="empty",
        description="the `if not pads: return 0.0` branch must be exercised",
        min_count=1,
    ),
] + [
    NonVacuityCheck(
        tag=tag,
        description=f"pad shape code coverage: {tag} must appear at least once",
        min_count=1,
    )
    for tag in (*SHAPE_TAG.values(), UNKNOWN_SHAPE_TAG)
]


SPEC = FreezeSpec(
    name="copper_reach",
    description="io/real_board.py::_copper_reach_mm -- max(|offset| + pad_bounding_radius) over pads.",
    oracle_provenance=(
        "packages/temper-placer/tests/io/_copper_reach_py_oracle.py, pinned at "
        "d7a22b5d16d4db7d47be39f9d7580921eb9e5263, unchanged 863 commits as of freeze"
    ),
    kernel_provenance="packages/temper-geometry/src/copper_reach.rs :: copper_reach_mm, unchanged 182 commits",
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-geometry/src/copper_reach.rs",
    insert_before_marker="// --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---",
)
