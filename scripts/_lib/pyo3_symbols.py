"""Derive, from Rust source, the symbol set a pyo3 ``#[pymodule]`` registers.

Why this exists
---------------
``scripts/check_stale_extensions.py`` used to answer only two questions about
an installed extension: "is it newer than its sources" (mtime / content stamp)
and "does it export an init function" (byte scan for ``PyInit_<module>``).
Neither is the question an agent actually asks before trusting a number, which
is: **does this ``.so`` contain the function I am about to call?**

Measured failures with the gate green (AGENTS.md, "Measurement Instruments
That Lie", and the ``docs/evidence/`` files it cites):

* ``stale=0`` reported against a ``.so`` missing a function its own Rust
  source registers -- the timestamp said "rebuilt", the artifact disagreed.
  Downstream cost: ``is_hv_net("hb-gnd")`` returned ``False`` where the
  rebuilt artifact returns ``True``, and an agent spent hours on the wrong
  hypothesis.
* ``fresh 10/10`` *and* all ten modules importing cleanly, while
  ``temper_design_bundle_python`` lacked ``resolve_insulation_declaration``.
  Found only because someone happened to call the missing function.

The expected set has to be *derived*, never hand-maintained: a checked-in list
of symbols is the same defect one level up and goes stale exactly the way the
timestamps did. So this module reads the crate's own Rust source and computes
what the module must export.

What "must export" means here (and why it is registration-driven)
-----------------------------------------------------------------
The authority is the ``#[pymodule]`` function body, followed transitively
through the ``register(m)``-style helpers it calls. A ``#[pyfunction]`` that
is *defined* but never registered is not a module attribute and must not be
demanded of the artifact; conversely every ``wrap_pyfunction!`` /
``add_class::<>`` / ``m.add("NAME", ...)`` reachable from the entry point is a
name ``dir(module)`` is required to contain. Enumerating every
``#[pyfunction]`` in the crate instead would over-demand (911 declared vs 774
registered across ``packages/``) and produce exactly the kind of false red
that gets a gate switched off.

``#[pyfunction]``/``#[pyclass]`` items are still parsed -- that is where the
*exported* name comes from, since ``#[pyo3(name = "...")]`` renames it (54
items in this repo do).

Four source shapes this must survive, all present in this repo
--------------------------------------------------------------
1. **Submodules.** ``temper-design-bundle`` registers 20 of its contract
   groups as child modules (``let sub = PyModule::new(py, "board_contracts")``
   ... ``module.add_submodule(&sub)``), so ``Board`` is
   ``temper_design_bundle_python.board_contracts.Board``, not a top-level
   name. Registration is therefore tracked *per receiver*, and expected
   symbols carry the dotted path the artifact is checked against. Ignoring
   this produced 122 phantom "missing" symbols on a known-good build.
2. **``#[cfg_attr(feature = "python", pyfunction)]``** (17 sites) -- the item
   is a pyfunction only when the feature is on, so the ``cfg_attr`` condition
   becomes a gate on the item rather than being ignored.
3. **``macro_rules!``-generated pyfunctions** -- ``netclass_fn!(is_hv_net,
   ...)`` expands to ``#[pyfunction] pub fn is_hv_net``, which no source scan
   can see as an item. A ``wrap_pyfunction!`` target that resolves to no
   visible item is still demanded, under pyo3's default name (the identifier
   itself); such symbols are counted separately as INFERRED so the assumption
   is visible rather than buried.
4. **Local path dependencies that are themselves pyo3 crates.** The source
   set a freshness digest covers includes them, and several carry their own
   ``#[pymodule]``. Only files under the crate root are parsed, and the entry
   point is matched by *name* against the crate's declared module, so the
   walk can never start from another crate's module. Ignoring this made
   ``temper-orchestration`` resolve to ``temper_geometry``'s pymodule.

Feature gating
--------------
The feature set the artifact was actually built with is ``[tool.maturin]
features`` from the crate's ``pyproject.toml`` (plus ``default``, expanded
transitively through ``[features]`` in ``Cargo.toml``), because that is the
exact list maturin passes to cargo. A predicate this module cannot decide is
reported as UNRESOLVED rather than guessed in either direction -- guessing
"enabled" manufactures false failures, guessing "disabled" silently shrinks
the gate -- and the count is printed so it cannot drift upward unnoticed.

Relationship to the other Rust-reading gates
--------------------------------------------
``check_unwired_kernels.py`` and ``check_pyo3_duplicate_registration.py``
also read ``wrap_pyfunction!``/``add_class::<>`` out of ``packages/**/*.rs``,
and this module deliberately does NOT replace either. Both of those ask a
repo-wide question ("is this kernel wired to anything at all", "is any name
registered twice") over a flat glob, where a miss is a soft signal reconciled
by hand and a per-crate boundary is irrelevant. This module answers a
per-artifact question whose answer decides a hard CI failure, so it needs
things they can afford to skip: reachability from one crate's ``#[pymodule]``,
feature-gate evaluation, submodule nesting, and a refusal to guess. A shared
"good enough for a ledger" parser used to decide a hard gate is how false reds
get a gate disabled; the two live side by side on purpose.

Parsing strategy
----------------
Rust is not parsed with a real grammar (no ``syn`` from Python). The source is
*masked*: comments and string/char literals are blanked to spaces of the same
length, so offsets stay valid. Structure (attribute clusters, brace-matched
bodies, generic arguments) is matched on the masked text; literal values are
read back out of the original at the matched offsets. The anti-vacuity
backstop in the caller -- zero expected symbols for a crate is a TOOL ERROR,
never a pass -- is what keeps a parser regression from silently turning this
into a no-op.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ExpectedSymbol",
    "Extraction",
    "enabled_features",
    "extract_expected_symbols",
    "load_crate_toml",
    "mask_rust",
]


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


_RAW_STR_OPEN = re.compile(r'(?:b?r)(?P<hashes>#*)"')
_CHAR_LIT = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F]+\}|x[0-9a-fA-F]{2}|.)|[^\\'])'")


def mask_rust(text: str) -> str:
    """Return *text* with comments and literals blanked to spaces.

    Length and newline positions are preserved, so an offset into the mask is
    the same offset into the original.

    Handles ``//`` and (nested) ``/* */`` comments, ``"..."`` with escapes,
    raw strings ``r"..."``/``r#"..."#``, byte strings, and char literals --
    while leaving lifetimes (``&'a str``) alone, since a lifetime is an
    apostrophe that is not followed by a closing quote.
    """
    out = list(text)
    n = len(text)
    i = 0

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j == -1 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            depth = 1
            j = i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth += 1
                    j += 2
                elif text.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            blank(i, j)
            i = j
            continue
        if c in "rb" and (m := _RAW_STR_OPEN.match(text, i)):
            close = '"' + m.group("hashes")
            j = text.find(close, m.end())
            j = n if j == -1 else j + len(close)
            blank(i, j)
            i = j
            continue
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    j += 1
                    break
                j += 1
            blank(i, j)
            i = j
            continue
        if c == "'":
            if m := _CHAR_LIT.match(text, i):
                blank(i, m.end())
                i = m.end()
                continue
            i += 1  # a lifetime, not a literal
            continue
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Bracket matching
# ---------------------------------------------------------------------------


def _match_forward(masked: str, open_idx: int, opener: str, closer: str) -> int:
    """Index of the bracket closing the one at *open_idx*, or -1."""
    depth = 0
    for i in range(open_idx, len(masked)):
        ch = masked[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _match_backward(masked: str, close_idx: int, opener: str, closer: str) -> int:
    depth = 0
    for i in range(close_idx, -1, -1):
        ch = masked[i]
        if ch == closer:
            depth += 1
        elif ch == opener:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level(text: str, masked: str, sep: str = ",") -> list[str]:
    """Split *text* on *sep* at bracket depth 0."""
    pieces: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(masked):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == sep and depth == 0:
            pieces.append(text[start:i])
            start = i + 1
    pieces.append(text[start:])
    return pieces


# ---------------------------------------------------------------------------
# cfg evaluation
# ---------------------------------------------------------------------------


class Undecidable(Exception):
    """A ``cfg`` predicate this module refuses to guess at."""


def eval_cfg(pred: str, features: frozenset[str]) -> bool:
    """Evaluate a ``cfg`` predicate against *features*.

    Raises :class:`Undecidable` for anything not decidable from the feature
    set plus "this is a native CPython extension built by maturin" -- never a
    silent True or False.
    """
    pred = pred.strip()
    masked = mask_rust(pred)

    for combinator in ("any", "all", "not"):
        head = masked[: len(combinator)]
        if head == combinator and masked[len(combinator) :].lstrip().startswith("("):
            open_idx = masked.index("(", len(combinator))
            close_idx = _match_forward(masked, open_idx, "(", ")")
            if close_idx == -1:
                raise Undecidable(pred)
            inner = pred[open_idx + 1 : close_idx]
            inner_masked = masked[open_idx + 1 : close_idx]
            parts = [p.strip() for p in _split_top_level(inner, inner_masked) if p.strip()]
            if combinator == "not":
                if len(parts) != 1:
                    raise Undecidable(pred)
                return not eval_cfg(parts[0], features)
            results = [eval_cfg(p, features) for p in parts]
            return any(results) if combinator == "any" else all(results)

    if m := re.fullmatch(r'feature\s*=\s*"([^"]*)"', pred):
        return m.group(1) in features
    if pred in {"test", "doctest"}:
        # A maturin-built cdylib is never compiled under `cfg(test)`.
        return False
    if m := re.fullmatch(r'target_arch\s*=\s*"([^"]*)"', pred):
        # The gate only ever inspects an artifact loadable by the interpreter
        # running it, so a wasm target is decidably absent. Naming any other
        # architecture is not something this repo does, and guessing would be
        # a lie -- hence Undecidable rather than a default.
        if m.group(1) in {"wasm32", "wasm64"}:
            return False
        raise Undecidable(pred)
    if m := re.fullmatch(r'target_family\s*=\s*"([^"]*)"', pred):
        if m.group(1) == "wasm":
            return False
        raise Undecidable(pred)
    raise Undecidable(pred)


# ---------------------------------------------------------------------------
# Feature resolution
# ---------------------------------------------------------------------------


def enabled_features(pyproject: dict, cargo: dict) -> frozenset[str]:
    """The feature set maturin builds this crate's cdylib with.

    ``[tool.maturin] features`` is what maturin passes to cargo verbatim, so
    it -- not a guess from the crate name -- is the source of truth. Entries
    of the form ``pyo3/extension-module`` select a feature of a *dependency*
    and are dropped: they never gate this crate's own ``#[cfg]``. ``default``
    is included unless ``no-default-features`` says otherwise, matching cargo.
    Everything is then expanded transitively through ``[features]``.
    """
    maturin = pyproject.get("tool", {}).get("maturin", {})
    seeds = {f for f in maturin.get("features", []) if "/" not in f}
    if not maturin.get("no-default-features", False):
        seeds.add("default")

    feature_table = cargo.get("features", {})
    optional_deps = {
        name
        for section in ("dependencies", "build-dependencies")
        for name, spec in cargo.get(section, {}).items()
        if isinstance(spec, dict) and spec.get("optional")
    }

    resolved: set[str] = set()
    queue = list(seeds)
    while queue:
        feat = queue.pop()
        if feat in resolved:
            continue
        resolved.add(feat)
        if feat in optional_deps:
            continue
        for dep in feature_table.get(feat, []):
            if "/" in dep:
                continue
            queue.append(dep.removeprefix("dep:"))
    if "default" not in feature_table:
        resolved.discard("default")
    return frozenset(resolved)


# ---------------------------------------------------------------------------
# Attribute scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Attr:
    head: str  # e.g. "pyfunction", "cfg", "pyo3"
    args: str  # raw text between the parentheses ("" if none)
    args_masked: str
    start: int  # offset of the enclosing `#`
    end: int  # offset just past the enclosing `]`
    #: cfg predicates from an enclosing ``cfg_attr`` -- the attribute applies
    #: only when all of them hold. Empty for a plain attribute.
    guard: tuple[str, ...] = ()


def _parse_attr_body(body: str, body_masked: str, start: int, end: int, guard: tuple[str, ...]):
    """Yield the attribute(s) inside one ``#[...]``, flattening ``cfg_attr``."""
    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_:]*)", body_masked)
    if not m:
        return
    head = m.group(1).rsplit("::", 1)[-1]
    args = args_masked = ""
    rest = body_masked[m.end() :].lstrip()
    if rest.startswith("("):
        open_rel = body_masked.index("(", m.end())
        close_rel = _match_forward(body_masked, open_rel, "(", ")")
        if close_rel != -1:
            args = body[open_rel + 1 : close_rel]
            args_masked = body_masked[open_rel + 1 : close_rel]

    if head == "cfg_attr" and args_masked:
        pieces = _split_top_level(args, args_masked)
        pieces_masked = _split_top_level(args_masked, args_masked)
        condition = pieces[0].strip()
        inner_guard = guard + ((condition,) if condition else ())
        for piece, piece_masked in zip(pieces[1:], pieces_masked[1:], strict=True):
            if piece.strip():
                yield from _parse_attr_body(
                    piece, piece_masked, start, end, inner_guard
                )
        return

    yield _Attr(head, args, args_masked, start, end, guard)


def _attrs_in(text: str, masked: str, lo: int, hi: int) -> list[_Attr]:
    """Every attribute (``cfg_attr`` flattened) whose ``#`` lies in [lo, hi)."""
    out: list[_Attr] = []
    pos = lo
    while True:
        idx = masked.find("#", pos)
        if idx == -1 or idx >= hi:
            return out
        q = idx + 1
        if q < len(masked) and masked[q] == "!":
            q += 1
        if q >= len(masked) or masked[q] != "[":
            pos = idx + 1
            continue
        close = _match_forward(masked, q, "[", "]")
        if close == -1:
            return out
        out.extend(
            _parse_attr_body(
                text[q + 1 : close], masked[q + 1 : close], idx, close + 1, ()
            )
        )
        pos = close + 1


# ---------------------------------------------------------------------------
# Item scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Item:
    kind: str  # "function" | "class"
    rust_name: str
    export_name: str
    cfgs: tuple[str, ...]
    path: Path
    line: int


_ITEM_DECL = re.compile(
    r"(?:pub\s*(?:\([^)]*\)\s*)?)?"
    r"(?:default\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?"
    r'(?:extern\s*(?:"[^"]*")?\s+)?'
    r"(fn|struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
)

_MOD_DECL = re.compile(r"\bmod\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{")


def _attr_cluster(masked: str, marker_idx: int) -> tuple[int, int]:
    """(cluster_start, item_decl_start) for the attribute at *marker_idx*.

    Comments were blanked by :func:`mask_rust`, so plain whitespace skipping
    walks over doc comments too.
    """
    start = marker_idx
    while True:
        j = start - 1
        while j >= 0 and masked[j].isspace():
            j -= 1
        if j >= 0 and masked[j] == "]":
            open_idx = _match_backward(masked, j, "[", "]")
            if open_idx > 0:
                p = open_idx - 1
                if p >= 0 and masked[p] == "!":
                    p -= 1
                if p >= 0 and masked[p] == "#":
                    start = p
                    continue
        break

    pos = marker_idx
    n = len(masked)
    while pos < n:
        while pos < n and masked[pos].isspace():
            pos += 1
        if pos < n and masked[pos] == "#":
            q = pos + 1
            if q < n and masked[q] == "!":
                q += 1
            if q < n and masked[q] == "[":
                close = _match_forward(masked, q, "[", "]")
                if close == -1:
                    break
                pos = close + 1
                continue
        break
    return start, pos


def _export_name_from(attrs: list[_Attr]) -> str | None:
    for attr in attrs:
        if attr.head not in {"pyo3", "pyclass", "pyfunction"} or not attr.args:
            continue
        for piece in _split_top_level(attr.args, attr.args_masked):
            if m := re.fullmatch(r'\s*name\s*=\s*"([^"]+)"\s*', piece):
                return m.group(1)
    return None


def _plain_cfgs(attrs: list[_Attr]) -> list[str]:
    return [a.args.strip() for a in attrs if a.head == "cfg" and a.args.strip()]


def _module_cfg_spans(text: str, masked: str) -> list[tuple[int, int, tuple[str, ...]]]:
    """Spans of ``#[cfg(...)] mod name { ... }`` blocks and their predicates.

    An item inside such a block inherits the block's cfg -- which is how
    ``#[cfg(feature = "python")] mod pymodule_def { ... }`` (four crates here)
    gates everything it contains without repeating itself.
    """
    spans: list[tuple[int, int, tuple[str, ...]]] = []
    for m in _MOD_DECL.finditer(masked):
        brace = masked.index("{", m.start())
        close = _match_forward(masked, brace, "{", "}")
        if close == -1:
            continue
        cluster_start, _decl = _attr_cluster(masked, m.start())
        cfgs = _plain_cfgs(_attrs_in(text, masked, cluster_start, m.start()))
        if cfgs:
            spans.append((brace, close, tuple(cfgs)))
    return spans


def scan_items(path: Path, text: str, masked: str) -> list[_Item]:
    """Every ``#[pyfunction]``/``#[pyclass]`` item declared in one file.

    ``#[cfg_attr(<cond>, pyfunction)]`` counts as a pyfunction gated on
    ``<cond>``; that form is how ``temper-orchestration`` and
    ``temper-drc-rs`` keep their kernels compilable for wasm.
    """
    mod_spans = _module_cfg_spans(text, masked)
    seen: set[int] = set()
    items: list[_Item] = []

    for attr in _attrs_in(text, masked, 0, len(masked)):
        if attr.head not in {"pyfunction", "pyclass"}:
            continue
        cluster_start, decl_start = _attr_cluster(masked, attr.start)
        if decl_start in seen:
            continue
        decl = _ITEM_DECL.match(masked, decl_start)
        if not decl:
            continue
        seen.add(decl_start)
        cluster = _attrs_in(text, masked, cluster_start, decl_start)
        cfgs = _plain_cfgs(cluster) + list(attr.guard)
        for lo, hi, mod_cfgs in mod_spans:
            if lo < attr.start < hi:
                cfgs.extend(mod_cfgs)
        rust_name = decl.group(2)
        items.append(
            _Item(
                kind="function" if attr.head == "pyfunction" else "class",
                rust_name=rust_name,
                export_name=_export_name_from(cluster) or rust_name,
                cfgs=tuple(cfgs),
                path=path,
                line=text.count("\n", 0, decl_start) + 1,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Function bodies
# ---------------------------------------------------------------------------


def _find_fn_body(masked: str, name: str) -> tuple[int, int] | None:
    """(open_brace, close_brace) of ``fn <name>``'s body, or None."""
    for m in re.finditer(rf"\bfn\s+{re.escape(name)}\s*[<(]", masked):
        depth = 0
        i = m.end() - 1
        n = len(masked)
        while i < n:
            ch = masked[i]
            if ch in "(<[":
                depth += 1
            elif ch in ")>]":
                depth -= 1
            elif ch == "{" and depth <= 0:
                close = _match_forward(masked, i, "{", "}")
                return None if close == -1 else (i, close)
            elif ch == ";" and depth <= 0:
                break  # a trait method declaration, no body
            i += 1
    return None


def _fn_first_param(masked: str, name: str) -> str | None:
    for m in re.finditer(rf"\bfn\s+{re.escape(name)}\s*\(", masked):
        open_idx = masked.index("(", m.end() - 1)
        close = _match_forward(masked, open_idx, "(", ")")
        if close == -1:
            continue
        first = masked[open_idx + 1 : close].split(",")[0]
        if pm := re.match(r"\s*(?:mut\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*:", first):
            return pm.group(1)
    return None


# ---------------------------------------------------------------------------
# Registration walk
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedSymbol:
    """One name the built module is required to expose.

    *name* may be dotted (``board_contracts.Board``) when the symbol lives in
    a child module created with ``PyModule::new`` and attached with
    ``add_submodule``.
    """

    name: str
    kind: str  # "function" | "class" | "attribute" | "submodule"
    origin: str  # "<file>:<line>" of the registering statement
    #: True when the target could not be matched to a visible ``#[pyfunction]``
    #: item (typically ``macro_rules!``-generated) and pyo3's default name --
    #: the identifier itself -- was assumed.
    inferred: bool = False


@dataclass
class Extraction:
    """What the source says the module must export, plus honest caveats."""

    #: Rust name of the ``#[pymodule]`` function the walk started from.
    entry_point: str
    symbols: dict[str, ExpectedSymbol] = field(default_factory=dict)
    #: cfg predicates this module refused to guess at; the items they gate are
    #: NOT demanded of the artifact. Surfaced so the number cannot drift.
    unresolved_cfgs: list[str] = field(default_factory=list)
    #: registration sites whose target could not be resolved at all.
    unresolved_targets: list[str] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def inferred_count(self) -> int:
        return sum(1 for s in self.symbols.values() if s.inferred)


_ADD_FUNCTION = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*add_(?:function|wrapped)\s*\(")
_ADD_CLASS = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*add_class\s*::\s*<\s*([A-Za-z_][A-Za-z0-9_:]*)"
)
_ADD_ATTR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*add\s*\(")
_ADD_SUBMODULE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*add_submodule\s*\(\s*&?\s*([A-Za-z_][A-Za-z0-9_]*)"
)
_WRAP = re.compile(r"wrap_pyfunction!\s*\(\s*([A-Za-z_][A-Za-z0-9_:]*)")
_SUBMODULE_NEW = re.compile(
    r"\blet\s+(?:mut\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*PyModule\s*::\s*new[A-Za-z0-9_]*\s*\("
)
_STRING_ARG = re.compile(r'\s*"([^"]*)"\s*\Z')


def _call_args(text: str, masked: str, open_paren: int) -> tuple[list[str], list[str]] | None:
    """Top-level argument list of the call whose ``(`` is at *open_paren*.

    Returned from the ORIGINAL text, not the mask: a string-literal argument
    is blanked in the mask, so a regex like ``\\(\\s*"`` written against the
    mask silently skips *over* the literal it meant to capture. That mistake
    cost 134 registrations on the first pass here, all of them reported as
    "unknown receiver" rather than as symbols.
    """
    close = _match_forward(masked, open_paren, "(", ")")
    if close == -1:
        return None
    args = text[open_paren + 1 : close]
    args_masked = masked[open_paren + 1 : close]
    return _split_top_level(args, args_masked), _split_top_level(args_masked, args_masked)


class _Walker:
    def __init__(
        self,
        files: dict[Path, tuple[str, str]],
        items: dict[str, list[_Item]],
        crate_root: Path,
        features: frozenset[str],
        result: Extraction,
    ) -> None:
        self._files = files
        self._items = items
        self._crate_root = crate_root
        self._features = features
        self._result = result
        self._visited: set[tuple[Path, str, str]] = set()

    # -- cfg -------------------------------------------------------------

    def _enabled(self, cfgs, where: str) -> bool:
        for pred in cfgs:
            try:
                if not eval_cfg(pred, self._features):
                    return False
            except Undecidable:
                entry = f"cfg({pred}) at {where}"
                if entry not in self._result.unresolved_cfgs:
                    self._result.unresolved_cfgs.append(entry)
                return False
        return True

    # -- resolution ------------------------------------------------------

    def _module_files(self, module_path: list[str]) -> set[Path]:
        """Files a Rust module path could live in (``a::b`` -> ``a/b.rs``)."""
        segs = [s for s in module_path if s not in {"crate", "self", "super"}]
        if not segs:
            return {self._crate_root / "src" / "lib.rs"}
        base = self._crate_root / "src" / Path(*segs)
        return {base.with_suffix(".rs"), base / "mod.rs", self._crate_root / "src" / "lib.rs"}

    def _resolve_item(self, path_expr: str, kind: str, here: Path) -> _Item | None:
        segments = path_expr.split("::")
        candidates = [it for it in self._items.get(segments[-1], []) if it.kind == kind]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        if len(segments) > 1:
            narrowed = [it for it in candidates if it.path in self._module_files(segments[:-1])]
            if len(narrowed) == 1:
                return narrowed[0]
            if narrowed:
                candidates = narrowed
        same_file = [it for it in candidates if it.path == here]
        if len(same_file) == 1:
            return same_file[0]
        if len({it.export_name for it in candidates}) == 1:
            return candidates[0]  # ambiguous origin, unambiguous export name
        return None

    # -- walk ------------------------------------------------------------

    def walk_fn(self, path: Path, fn_name: str, prefix: str = "") -> None:
        key = (path, fn_name, prefix)
        if key in self._visited:
            return
        self._visited.add(key)

        text, masked = self._files[path]
        span = _find_fn_body(masked, fn_name)
        if span is None:
            return
        lo, hi = span
        body = text[lo:hi]
        body_masked = masked[lo:hi]
        binding = _fn_first_param(masked, fn_name) or "m"

        def where(offset: int) -> str:
            return f"{path}:{text.count(chr(10), 0, lo + offset) + 1}"

        def stmt_cfgs(offset: int) -> list[str]:
            """``#[cfg(...)]`` attached to the statement at *offset*."""
            line_start = body_masked.rfind("\n", 0, offset) + 1
            prev_start = body_masked.rfind("\n", 0, max(line_start - 1, 0)) + 1
            prev = body[prev_start : max(line_start - 1, prev_start)]
            attrs = _attrs_in(prev, mask_rust(prev), 0, len(prev))
            return _plain_cfgs(attrs)

        # Child modules created in this body: `let sub = PyModule::new(py,
        # "board_contracts")`. Registrations on `sub` are attributes of the
        # child, not of the module under test.
        children: dict[str, str] = {}
        for m in _SUBMODULE_NEW.finditer(body_masked):
            parsed = _call_args(body, body_masked, m.end() - 1)
            if parsed is None or len(parsed[0]) < 2:
                continue
            if name := _STRING_ARG.match(parsed[0][1]):
                children[m.group(1)] = name.group(1)

        def prefix_for(receiver: str) -> str | None:
            if receiver == binding:
                return prefix
            if receiver in children:
                return f"{prefix}{children[receiver]}."
            return None

        for m in _ADD_SUBMODULE.finditer(body_masked):
            parent = prefix_for(m.group(1))
            child = children.get(m.group(2))
            if parent is None or child is None:
                continue
            site = where(m.start())
            if self._enabled(stmt_cfgs(m.start()), site):
                self._record(f"{parent}{child}", "submodule", site)

        for m in _ADD_FUNCTION.finditer(body_masked):
            recv = prefix_for(m.group(1))
            site = where(m.start())
            args_open = m.end() - 1
            args_close = _match_forward(body_masked, args_open, "(", ")")
            if args_close == -1:
                continue
            wrapped = _WRAP.search(body_masked, args_open, args_close)
            if wrapped is None:
                continue
            if recv is None:
                self._result.unresolved_targets.append(
                    f"{wrapped.group(1)}: unknown receiver {m.group(1)!r} at {site}"
                )
                continue
            if not self._enabled(stmt_cfgs(m.start()), site):
                continue
            target = wrapped.group(1)
            item = self._resolve_item(target, "function", path)
            if item is None:
                # macro_rules!-generated pyfunction: invisible as an item, so
                # pyo3's default name (the identifier) is assumed. Flagged.
                self._record(f"{recv}{target.split('::')[-1]}", "function", site, inferred=True)
                continue
            if not self._enabled(item.cfgs, f"{item.path}:{item.line}"):
                continue
            self._record(f"{recv}{item.export_name}", "function", site)

        for m in _ADD_CLASS.finditer(body_masked):
            recv = prefix_for(m.group(1))
            site = where(m.start())
            if recv is None:
                self._result.unresolved_targets.append(
                    f"{m.group(2)}: unknown receiver {m.group(1)!r} at {site}"
                )
                continue
            if not self._enabled(stmt_cfgs(m.start()), site):
                continue
            item = self._resolve_item(m.group(2), "class", path)
            if item is None:
                self._record(f"{recv}{m.group(2).split('::')[-1]}", "class", site, inferred=True)
                continue
            if not self._enabled(item.cfgs, f"{item.path}:{item.line}"):
                continue
            self._record(f"{recv}{item.export_name}", "class", site)

        for m in _ADD_ATTR.finditer(body_masked):
            parsed = _call_args(body, body_masked, m.end() - 1)
            if parsed is None or not parsed[0]:
                continue
            literal = _STRING_ARG.match(parsed[0][0])
            if literal is None:
                continue  # `.add(` with a computed name -- not resolvable
            recv = prefix_for(m.group(1))
            site = where(m.start())
            if recv is None:
                continue
            if self._enabled(stmt_cfgs(m.start()), site):
                self._record(f"{recv}{literal.group(1)}", "attribute", site)

        # Transitive `register(m)`-style helpers: a call whose first argument
        # is a module binding in scope. That is what makes the walk follow
        # `crate::congestion::register(m)?` (34 such calls in temper-geometry
        # alone) instead of stopping at lib.rs.
        bindings = "|".join(re.escape(b) for b in [binding, *children])
        call = re.compile(
            r"(?<![.\w])((?:[A-Za-z_][A-Za-z0-9_]*::)*[a-z_][A-Za-z0-9_]*)"
            rf"\s*\(\s*&?\s*({bindings})\s*[,)]"
        )
        for m in call.finditer(body_masked):
            target = m.group(1)
            if target.split("::")[-1] in {"wrap_pyfunction", "add_function", "add", "add_submodule"}:
                continue
            child_prefix = prefix_for(m.group(2))
            if child_prefix is None:
                continue
            site = where(m.start())
            if self._enabled(stmt_cfgs(m.start()), site):
                self._follow(target, path, child_prefix)

    def _follow(self, path_expr: str, here: Path, prefix: str) -> None:
        segments = path_expr.split("::")
        leaf = segments[-1]
        search: list[Path] = []
        if len(segments) > 1:
            search.extend(p for p in self._module_files(segments[:-1]) if p in self._files)
        search.append(here)
        for candidate in search:
            if candidate not in self._files:
                continue
            _text, masked = self._files[candidate]
            if _find_fn_body(masked, leaf) is None:
                continue
            if not self._enabled(self._fn_cfgs(candidate, leaf), f"{candidate}::{leaf}"):
                return
            self.walk_fn(candidate, leaf, prefix)
            return
        # Not a local function (a pyo3-generated method, a std call, a
        # closure). Silently ignored: demanding resolution here would flag
        # every `foo(m)` in the codebase.

    def _fn_cfgs(self, path: Path, fn_name: str) -> list[str]:
        text, masked = self._files[path]
        m = re.search(rf"\bfn\s+{re.escape(fn_name)}\s*[<(]", masked)
        if not m:
            return []
        decl_start = m.start()
        prefix = re.search(
            r"((?:pub\s*(?:\([^)]*\)\s*)?)?(?:async\s+)?(?:unsafe\s+)?"
            r'(?:extern\s*(?:"[^"]*")?\s+)?)$',
            masked[:decl_start],
        )
        if prefix:
            decl_start = prefix.start()
        cluster_start, _ = _attr_cluster(masked, decl_start)
        cfgs = _plain_cfgs(_attrs_in(text, masked, cluster_start, decl_start))
        for lo, hi, mod_cfgs in _module_cfg_spans(text, masked):
            if lo < m.start() < hi:
                cfgs.extend(mod_cfgs)
        return cfgs

    def _record(self, name: str, kind: str, origin: str, *, inferred: bool = False) -> None:
        self._result.symbols.setdefault(name, ExpectedSymbol(name, kind, origin, inferred))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def load_crate_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def extract_expected_symbols(
    crate_root: Path,
    source_files: list[Path],
    pyproject: dict,
    cargo: dict,
    module_name: str,
) -> Extraction:
    """Symbols the crate's ``#[pymodule]`` registers, per its own source.

    *source_files* is the caller's source set -- the same one the freshness
    digest is computed over, so the two halves of the gate can never disagree
    about which files they read. Only the entries under *crate_root* are
    parsed (see shape 4 in the module docstring).
    """
    crate_root = crate_root.resolve()
    files: dict[Path, tuple[str, str]] = {}
    for path in source_files:
        if path.suffix != ".rs":
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(crate_root):
            continue
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files[resolved] = (text, mask_rust(text))

    features = enabled_features(pyproject, cargo)

    items: dict[str, list[_Item]] = {}
    for path, (text, masked) in files.items():
        for item in scan_items(path, text, masked):
            items.setdefault(item.rust_name, []).append(item)

    entry: tuple[Path, str] | None = None
    fallback: tuple[Path, str] | None = None
    for path, (text, masked) in sorted(files.items()):
        for attr in _attrs_in(text, masked, 0, len(masked)):
            if attr.head != "pymodule":
                continue
            cluster_start, decl_start = _attr_cluster(masked, attr.start)
            decl = _ITEM_DECL.match(masked, decl_start)
            if not decl or decl.group(1) != "fn":
                continue
            fn_name = decl.group(2)
            cluster = _attrs_in(text, masked, cluster_start, decl_start)
            if (_export_name_from(cluster) or fn_name) == module_name:
                entry = (path, fn_name)
                break
            fallback = fallback or (path, fn_name)
        if entry:
            break
    entry = entry or fallback

    result = Extraction(entry_point=entry[1] if entry else "", files_scanned=len(files))
    if entry is None:
        return result

    _Walker(files, items, crate_root, features, result).walk_fn(*entry)
    return result
