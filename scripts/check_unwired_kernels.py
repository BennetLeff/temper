#!/usr/bin/env python3
"""Fail when a Rust kernel is registered into a Python module but nothing in production calls it.

WHY THIS EXISTS
---------------
On 2026-08-06 an audit found **4,096 LOC across 15 router_v6 files** whose Rust
kernels were fully built, registered, and proven bit-equivalent against pinned
oracles -- and never called by anything except their own differential:

    congestion cluster   1,300 LOC   23/23 symbols   PR #751
    DFM cluster          1,597 LOC   13/13 symbols   PR #749
    quality metrics        598 LOC   23/23 symbols   PR #750
    escape_via + net_ordering  601 LOC              PR #751

Every one of those PRs was correct by the documented process. That is the
problem this gate closes: `docs/migration-pipeline.md` stage 3 and the
discipline contract's G1-G8 checklist both END at "the differential is green".
No gate asked whether the Python call site changed, so a migration could be
complete, verified, merged -- and inert. The Rust existed; the Python still ran.

A differential cannot catch this. It compares the pinned ORACLE against the
Rust directly and passes whether or not the shipped module delegates. That is
by design and is not a flaw in the differential; it just means the wiring needs
its own check.

WHAT COUNTS AS WIRED
--------------------
A symbol registered with `m.add_function(wrap_pyfunction!(NAME, m)?)?` or
`m.add_class::<NAME>()` exists to be called from Python. It is WIRED if any
NON-TEST Python file references it -- `packages/*/src/**`, `scripts/`, `tools/`.
Test files prove equivalence; they do not put a kernel into production.

Both import spellings count, and this matters: the one correctly wired module
found during the audit (`heuristics/structural.py`) uses a function-local
`from temper_geometry import keepout_mask_flags_py`, which a naive
`import temper_geometry` scan misses entirely.

THE RATCHET
-----------
Some kernels are legitimately unwired for a while -- Phase B lands the Rust,
the shim follows. So this is a shrink-only inventory, exactly like
`.hash-order-inventory`:

    NEW_UNWIRED    a registered symbol with no production caller that is not in
                   the ledger. Hard fail. Either wire it or record it with a
                   reason.
    STALE_ENTRY    a ledger entry that IS now wired. Also a hard fail, because
                   paid-down debt that stays on the books hides the next
                   regression. Rerun with --write-inventory.

Failing on STALE_ENTRY is deliberate: it is the only mechanism that makes
progress visible in a diff.

USAGE
    uv run python scripts/check_unwired_kernels.py
    uv run python scripts/check_unwired_kernels.py --write-inventory

EXIT CODES
    0  every registered kernel is wired, or ledgered with a reason
    1  a new unwired kernel, or a stale ledger entry
    2  the scan itself failed (no symbols found, unreadable tree)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / ".unwired-kernel-inventory"

# Registration forms that mean "callable from Python".
# Registration is frequently PATH-QUALIFIED -- `wrap_pyfunction!(fdm::solve_py, m)`.
# Capturing the first identifier yields the Rust MODULE (`fdm`), not the function,
# which is wrong twice over: it invents a symbol that can never be "wired" (a module
# is not callable from Python), and it silently drops the real one. Measured on
# 2026-08-06: 113 of 572 registered functions were path-qualified, so the gate was
# not watching them AT ALL, while 18 Rust module names sat in the ledger being
# triaged as if they were kernels. Consume the `::` segments and keep the last.
ADD_FUNCTION = re.compile(
    r"wrap_pyfunction!\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)")
ADD_CLASS = re.compile(
    r"add_class::<\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)")
# `#[pyo3(name = "...")]` renames the Python-visible symbol.
PYO3_NAME = re.compile(r'#\[pyo3\([^)]*name\s*=\s*"([^"]+)"')
PYCLASS_NAME = re.compile(r'#\[pyclass\([^)]*name\s*=\s*"([^"]+)"')
# `#[pyfunction(name = "...")]` renames the Python-visible function.
PYFUNCTION_NAME = re.compile(r'#\[pyfunction\([^)]*name\s*=\s*"([^"]+)"')


def registered_symbols() -> dict[str, str]:
    """Python-visible symbol -> the .rs file that registers it."""
    return {
        name: detail[2]
        for name, detail in registered_symbol_details().items()
    }


def registered_symbol_details() -> dict[str, tuple[str, str, str]]:
    """Python name -> (Rust item name, kind, source file).

    ``registered_symbols`` deliberately keeps its small public result shape,
    while the liveness scan also needs the Rust item behind a registration in
    order to follow typed return/field edges.  ``kind`` is ``function`` or
    ``class``; this is registration-derived metadata, never a name allowlist.
    """
    sources: list[tuple[str, str]] = []
    for rs in REPO_ROOT.glob("packages/*/src/**/*.rs"):
        if "/target" in str(rs):
            continue
        try:
            sources.append((str(rs.relative_to(REPO_ROOT)), rs.read_text()))
        except OSError:
            continue

    # Renames are resolved REPO-WIDE, not per file. A `#[pyclass(name = "X")]`
    # is routinely declared in one module and registered in another --
    # `PyDsnCircle` is `#[pyclass(name = "DSNCircle")]` in dsn_types.rs but
    # registered from lib.rs. A per-file map cannot see across that boundary,
    # so it reports the Rust name, which no Python caller ever writes, and the
    # kernel looks unwired however thoroughly it is used.
    renames: dict[str, str] = {}
    for _rel, text in sources:
        renames.update(pyclass_renames(text))
        renames.update(pyfunction_renames(text))

    details: dict[str, tuple[str, str, str]] = {}
    for rel, text in sources:
        for m in ADD_FUNCTION.finditer(text):
            rust_name = m.group(1)
            py_name = renames.get(rust_name, rust_name)
            details.setdefault(py_name, (rust_name, "function", rel))
        for m in ADD_CLASS.finditer(text):
            rust_name = m.group(1)
            # A `#[pyclass(name = "X")]` is visible to Python as X, NOT as the
            # Rust struct name -- e.g. `PyFabPreset` is `FabPreset` to callers,
            # and `core/manufacturing.py` imports it under that name. Scanning
            # for the Rust name would report a wired kernel as unwired.
            py_name = renames.get(rust_name, rust_name)
            details.setdefault(py_name, (rust_name, "class", rel))
    return details


def registered_symbols_runtime() -> dict[str, str]:
    """AUDIT MODE: the symbols the built extensions actually export.

    `dir(module)` is the list Python callers really see, so it is immune to the
    ways a registered name diverges from its Python name -- path-qualified
    registration, `#[pyclass(name=...)]` declared in another file,
    `#[pyo3(name=...)]` on a function, and `use X as Y` aliases at the
    registration site. Every one of those has produced a wrong verdict here.

    It is NOT the default, and that is deliberate: it requires the extensions to
    be built, and the gate runs in trunk-health.yml under a bare `python3` with
    no venv. A ledger keyed to this view would report phantom STALE_ENTRYs in
    CI, which is a worse failure than the parser's -- noise that trains people
    to ignore the gate. Use it as a periodic audit:

        uv run --no-sync python scripts/check_unwired_kernels.py --runtime

    and reconcile anything it finds by hand.
    """
    import importlib
    import pkgutil

    out: dict[str, str] = {}
    for name in sorted({m.name for m in pkgutil.iter_modules() if m.name.startswith("temper_")}):
        mod = None
        try:
            mod = importlib.import_module(f"{name}.{name}")   # maturin layout
        except Exception:
            try:
                candidate = importlib.import_module(name)
                if str(getattr(candidate, "__file__", "")).endswith((".so", ".pyd")):
                    mod = candidate
            except Exception:
                mod = None
        if mod is None:
            continue          # pure-Python package: its names are not kernels
        for sym in dir(mod):
            if sym.startswith("_"):
                continue
            try:
                obj = getattr(mod, sym)
            except Exception:
                continue
            if callable(obj) or isinstance(obj, type):
                out.setdefault(sym, name)
    return out


def _logical_lines(text: str) -> list[str]:
    """Merge multi-line `#[...]` attributes into one logical line each.

    `#[pyo3(signature = (\n  name = "X",\n))]` puts the `name` on a continuation
    line; a line-by-line scan would either miss the rename or reset `pending`
    before the `fn` it applies to. Joining the attribute's lines keeps both
    rename regexes single-line.
    """
    out: list[str] = []
    buf = ""
    for line in text.splitlines():
        s = line.strip()
        if buf:
            buf += " " + s
            if line.rstrip().endswith("]"):
                out.append(buf)
                buf = ""
        elif s.startswith("#[") and not line.rstrip().endswith("]"):
            buf = s
        else:
            out.append(line)
    if buf:
        out.append(buf)
    return out


def pyclass_renames(text: str) -> dict[str, str]:
    """Rust type name -> Python-visible name, for `#[pyclass(name = "...")]`.

    Attribute-to-item binding, not first-match-in-file: the attribute applies to
    the `struct`/`enum` that immediately follows it, so an unrelated rename
    earlier in the same module must not be picked up.
    """
    renames: dict[str, str] = {}
    pending: str | None = None
    for line in _logical_lines(text):
        s = line.strip()
        hit = PYCLASS_NAME.search(s) or PYO3_NAME.search(s)
        if hit:
            pending = hit.group(1)
            continue
        m = re.match(r"(?:pub\s+)?(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", s)
        if m:
            if pending:
                renames[m.group(1)] = pending
            pending = None
        elif s and not s.startswith(("#[", "//", "///")):
            pending = None
    return renames


def pyfunction_renames(text: str) -> dict[str, str]:
    """Rust fn name -> Python-visible name, for `#[pyfunction(name = "...")]`.

    Mirrors `pyclass_renames` for functions: the name attribute applies to the
    `fn` that immediately follows it. Without this, the ledger keys an unwired
    kernel by its Rust name and reports it unwired even when production calls
    the renamed Python symbol -- measured 2026-08-08: 23 of 83 ledger entries
    were wired-in-disguise (e.g. `snap_to_grid_py` -> `snap_to_grid`,
    `validate_stackup_py` -> `validate_stackup`, the `parse_*`/`tag_*` ->
    `pcl_*` family, `py_load_loop_collection` -> `load_loop_collection`).
    """
    renames: dict[str, str] = {}
    pending: str | None = None
    for line in _logical_lines(text):
        s = line.strip()
        hit = PYFUNCTION_NAME.search(s) or PYO3_NAME.search(s)
        if hit:
            pending = hit.group(1)
            continue
        m = re.match(r"(?:pub\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)", s)
        if m:
            if pending:
                renames[m.group(1)] = pending
            pending = None
        elif s and not s.startswith(("#[", "//", "///")):
            pending = None
    return renames


def code_identifiers(src: str) -> set[str]:
    """Names REFERENCED BY CODE in one module -- not names merely mentioned.

    Text matching cannot tell a call from prose, and that is not a hypothetical
    distinction: `net_ordering.py`'s docstring named `net_priority_key_py` and
    `net_priority_lt_py` while explaining that nothing constructs a
    `NetPriority` any more. A raw substring scan read the explanation of their
    deadness as proof of their liveness and marked both wired (PR #839).

    That failure is silent and in the unsafe direction -- an unwired kernel
    reported as wired is exactly what this gate exists to catch -- so matching
    is done over the AST instead: attribute accesses, bare names, imported
    aliases, and string arguments to `getattr`/`importlib` (dynamic dispatch is
    a real call site; `dag_engine.py` resolves pipeline stages that way).

    Comments and docstrings contribute nothing, which is the point.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Unparseable file: fall back to raw text. Over-counting here can only
        # mark something wired that is not, so it is logged by the caller
        # rather than trusted silently.
        raise

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # WHOLE-string literals, never substrings.
            #
            # Restricting this to getattr/import_module arguments missed the
            # dispatch TABLES that are this repo's actual idiom: pcl/rust_bridge.py
            # lists its kernels as strings and resolves them later, and
            # scripts/bench_rust_constraints.py does the same. Ten
            # compute_*_loss_py kernels were being carried in the ledger as
            # unwired while production called every one of them.
            #
            # Exact equality is what keeps this safe. The failure that motivated
            # dropping strings entirely was a docstring containing "re-tokenize",
            # which a SUBSTRING scan matched against the `tokenize` kernel. As a
            # whole string it matches nothing, and neither does a mutation
            # description like "M7 is_via_position_valid: <= instead of <" --
            # verified against both.
            v = node.value.strip()
            if v:
                names.add(v)
                names.update(v.split("."))
    return names


def _rust_code_without_comments(src: str) -> str:
    """Remove Rust comments while preserving string/character literals.

    The unwired-kernel gate needs to inspect Rust-side dynamic Python calls,
    but a raw search would also read the migration comments that describe
    those calls.  This is intentionally a small lexical scanner rather than a
    Rust parser: it handles nested block comments, escaped literals, and raw
    strings, which is the syntax relevant to the literal-call patterns below.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    block_depth = 0
    while i < n:
        if block_depth:
            if src.startswith("/*", i):
                block_depth += 1
                i += 2
            elif src.startswith("*/", i):
                block_depth -= 1
                i += 2
            else:
                if src[i] == "\n":
                    out.append("\n")
                i += 1
            continue

        if src.startswith("//", i):
            i += 2
            while i < n and src[i] != "\n":
                i += 1
            continue
        if src.startswith("/*", i):
            block_depth = 1
            i += 2
            continue

        # Preserve raw strings, including any comment-looking text inside.
        raw = RUST_RAW_STRING_START.match(src, i) if src[i] == "r" else None
        if raw is not None:
            hashes = raw.group(1)
            end = '"' + hashes
            j = src.find(end, raw.end())
            if j < 0:
                out.append(src[i:])
                break
            j += len(end)
            out.append(src[i:j])
            i = j
            continue

        if src[i] == "'":
            # Rust lifetimes (`'a`) are not character literals. Only enter
            # literal mode when a closing quote is nearby; otherwise preserve
            # the apostrophe and continue scanning code normally.
            char_end = i + 1
            if char_end < n and src[char_end] == "\\":
                char_end += 2
            else:
                char_end += 1
            if char_end >= n or src[char_end] != "'":
                out.append(src[i])
                i += 1
                continue
            out.append(src[i : char_end + 1])
            i = char_end + 1
            continue

        if src[i] == '"':
            quote = src[i]
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                elif src[j] == quote:
                    j += 1
                    break
                else:
                    j += 1
            out.append(src[i:j])
            i = j
            continue

        out.append(src[i])
        i += 1
    return "".join(out)


RUST_GETATTR_LITERAL = re.compile(r"(?:\.\s*)?getattr\s*\(\s*\"([^\"]+)\"")
RUST_CALL_METHOD_LITERAL = re.compile(
    r"(?:\.\s*)?call_method\d*\s*\(\s*\"([^\"]+)\""
)
RUST_IMPORT_LITERAL = re.compile(
    r"(?:PyModule|[A-Za-z_][A-Za-z0-9_:]*)\s*::\s*import(?:_bound)?\s*"
    r"\([^,]+,\s*\"([^\"]+)\""
)
RUST_RAW_STRING_START = re.compile(r'r(#+)"')
RUST_RETURN_EDGE = re.compile(
    r"unwired-kernel-return-edge:\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*->\s*([A-Za-z_][A-Za-z0-9_]*)"
)


def rust_code_identifiers(src: str) -> set[str]:
    """Literal Python names reached by dynamic calls in Rust production code.

    Rust migrations commonly cross the extension boundary with
    ``module.getattr("kernel_py")``.  Those references are invisible to the
    Python AST scan, while registrations such as
    ``wrap_pyfunction!(kernel_py, module)`` are deliberately not matched.
    Only literal first arguments to ``getattr``, ``call_method*`` and
    ``PyModule::import`` are accepted; comments and docstrings are removed
    before matching.
    """
    code = _rust_code_without_comments(src)
    names: set[str] = set()
    for pattern in (
        RUST_GETATTR_LITERAL,
        RUST_CALL_METHOD_LITERAL,
        RUST_IMPORT_LITERAL,
    ):
        for match in pattern.finditer(code):
            value = match.group(1).strip()
            if value:
                names.add(value)
                names.update(value.split("."))
    names |= _rust_helper_dynamic_literals(code)
    return names


def _split_rust_arguments(text: str) -> list[str]:
    """Split one Rust call/signature argument list at top-level commas."""
    args: list[str] = []
    start = 0
    depth = {"(": 0, "[": 0, "{": 0, "<": 0}
    pairs = {")": "(", "]": "[", "}": "{",
    }
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in depth:
            depth[ch] += 1
        elif ch in pairs:
            opening = pairs[ch]
            depth[opening] = max(0, depth[opening] - 1)
        elif ch == ">":
            depth["<"] = max(0, depth["<"] - 1)
        elif ch == "," and not any(depth.values()):
            args.append(text[start:i].strip())
            start = i + 1
        i += 1
    tail = text[start:].strip()
    if tail:
        args.append(tail)
    return args


def _rust_call_argument_text(code: str, start: int) -> tuple[str, int] | None:
    """Return the balanced argument text beginning at an opening paren."""
    if start >= len(code) or code[start] != "(":
        return None
    depth = 0
    i = start
    while i < len(code):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return code[start + 1 : i], i
        i += 1
    return None


def _rust_helper_dynamic_literals(code: str) -> set[str]:
    """Follow a small, literal-only Rust helper dispatch pattern.

    The orchestration explainability bridge passes ``"explain_*"`` through
    ``io_types_call(..., name, ...)`` before calling ``m.getattr(name)``.
    Direct-literal matching cannot see that edge.  This recognises only a
    helper whose body calls ``getattr(<&str parameter>)`` on a ``PyModule``
    and only call sites whose corresponding argument is a string literal.
    It therefore cannot turn arbitrary prose or unrelated string arguments
    into liveness evidence.
    """
    helpers: list[tuple[str, int]] = []
    fn = re.compile(
        r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^{}]*>)?\s*\(([^{};]*)\)"
    )
    for match in fn.finditer(code):
        args = _split_rust_arguments(match.group(2))
        name_positions = [
            i for i, arg in enumerate(args)
            if re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\s*:\s*&(?:'[^']+\s*)?str\b", arg)
        ]
        if not name_positions:
            continue
        body_start = code.find("{", match.end())
        if body_start < 0:
            continue
        # Most functions cannot be dispatch helpers.  Avoid a full brace walk
        # unless a getattr call is nearby in the candidate body; the bound is
        # intentionally generous for this small adapter pattern.
        if code.find(".getattr", body_start, min(len(code), body_start + 2048)) < 0:
            continue
        # Find the matching function body with the same lexical brace walk
        # used below; this keeps a helper's proof local to its own body.
        depth = 0
        i = body_start
        while i < len(code):
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if depth != 0:
            continue
        body_text = code[body_start + 1 : i]
        for position in name_positions:
            param_name = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", args[position])
            if param_name and re.search(
                rf"\.\s*getattr\s*\(\s*{re.escape(param_name.group(1))}\s*\)",
                body_text,
            ):
                helpers.append((match.group(1), position))

    names: set[str] = set()
    for helper, position in helpers:
        for call in re.finditer(rf"\b{re.escape(helper)}\s*\(", code):
            # Skip the helper's own declaration; its parameter list cannot
            # contain a target string literal, but skipping is clearer and
            # avoids treating a string in a signature default-like construct.
            prefix = code[max(0, call.start() - 3) : call.start()]
            if re.search(r"\bfn\s*$", prefix):
                continue
            parsed = _rust_call_argument_text(code, call.end() - 1)
            if parsed is None:
                continue
            argument_text, _end = parsed
            args = _split_rust_arguments(argument_text)
            if position >= len(args):
                continue
            literal = re.fullmatch(r'"([^"]+)"', args[position].strip())
            if literal:
                value = literal.group(1).strip()
                if value:
                    names.add(value)
                    names.update(value.split("."))
    return names


def _rust_type_names(type_text: str, known_types: set[str]) -> set[str]:
    """Return known pyclass Rust names occurring in a Rust type expression."""
    return {
        name for name in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", type_text)
        if name in known_types
    }


def _rust_class_names(code: str) -> set[str]:
    """Find Rust names immediately following ``#[pyclass]`` attributes."""
    names: set[str] = set()
    pending = False
    for line in _logical_lines(code):
        s = line.strip()
        if s.startswith("#[pyclass"):
            pending = True
            continue
        if pending:
            match = re.match(
                r"(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum)\s+"
                r"([A-Za-z_][A-Za-z0-9_]*)",
                s,
            )
            if match:
                names.add(match.group(1))
                pending = False
                continue
            if s and not s.startswith("#["):
                pending = False
    return names


def _rust_brace_body(code: str, opening: int) -> str | None:
    if opening < 0 or opening >= len(code) or code[opening] != "{":
        return None
    depth = 0
    for i in range(opening, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[opening + 1 : i]
    return None


def _rust_function_returns(
    code: str,
    known_classes: set[str] | None = None,
) -> dict[str, set[str]]:
    """Rust function name -> pyclass names in its declared return type."""
    returns: dict[str, set[str]] = {}
    pyclasses = _rust_class_names(code) if known_classes is None else known_classes
    fn = re.compile(
        r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^{};]*>)?\s*"
        r"\([^{};]*\)([^{};]*)"
    )
    for match in fn.finditer(code):
        signature_tail = match.group(2)
        if "->" not in signature_tail:
            continue
        return_type = signature_tail.rsplit("->", 1)[1]
        returns.setdefault(match.group(1), set()).update(
            _rust_type_names(return_type, pyclasses)
        )
    return returns


def _rust_class_edges(code: str) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (field edges, inherent-method return edges) for pyclasses."""
    pyclasses = _rust_class_names(code)
    fields: dict[str, set[str]] = {name: set() for name in pyclasses}
    for match in re.finditer(
        r"\b(?:pub(?:\([^)]*\))?\s+)?struct\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)[^\{;]*\{",
        code,
    ):
        owner = match.group(1)
        if owner not in pyclasses:
            continue
        body = _rust_brace_body(code, match.end() - 1)
        if body is not None:
            fields[owner] |= _rust_type_names(body, pyclasses) - {owner}

    method_returns: dict[str, set[str]] = {name: set() for name in pyclasses}
    impl = re.compile(
        r"\bimpl\s+(?:[A-Za-z_][A-Za-z0-9_]*::)*"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\{"
    )
    for match in impl.finditer(code):
        owner = match.group(1)
        if owner not in pyclasses:
            continue
        body = _rust_brace_body(code, match.end() - 1)
        if body is None:
            continue
        for name, returned in _rust_function_returns(body, pyclasses).items():
            del name  # the class edge only needs the return type
            method_returns[owner] |= returned
    return fields, method_returns


def rust_type_flow_references(
    referenced: set[str],
    sources: list[tuple[str, str]] | None = None,
    details: dict[str, tuple[str, str, str]] | None = None,
) -> set[str]:
    """Infer anonymously consumed pyclasses from registered typed edges.

    A registered function is a root only when its Python-visible name occurs
    in production references.  Its declared return type, and the fields of
    any returned registered pyclass, are then followed transitively.  A
    registered class used directly by production is likewise a root and its
    inherent-method return/field edges are followed.  This is intentionally
    type-and-registration driven: no symbol-name allowlist can make an
    unrelated dead class look live.

    A small source-level ``unwired-kernel-return-edge: owner -> Type`` marker
    is also accepted for erased ``Py<PyAny>`` nested wires.  The marker is
    validated against a registered, production-called owner, so it is not a
    ledger exemption or a free-standing name allowlist.
    """
    if sources is None:
        sources = []
        for rs in REPO_ROOT.glob("packages/*/src/**/*.rs"):
            if "/target" in str(rs):
                continue
            try:
                sources.append((str(rs.relative_to(REPO_ROOT)), rs.read_text()))
            except OSError:
                continue

    if details is None:
        details = registered_symbol_details()
    registered_classes = {
        rust_name: py_name
        for py_name, (rust_name, kind, _rel) in details.items()
        if kind == "class"
    }
    if not registered_classes:
        return set()

    fields: dict[str, set[str]] = {name: set() for name in registered_classes}
    method_returns: dict[str, set[str]] = {name: set() for name in registered_classes}
    function_returns: dict[str, set[str]] = {}
    marked_edges: list[tuple[str, str]] = []
    registered_functions = {
        rust_name
        for rust_name, kind, _rel in details.values()
        if kind == "function"
    }
    for _rel, source in sources:
        # Most Rust files cannot contribute an edge.  Keep the source scan
        # cheap by looking for a pyclass attribute, a registered function
        # declaration, or an explicit erased-edge marker before stripping
        # comments and walking braces.
        if (
            "#[pyclass" not in source
            and "unwired-kernel-return-edge:" not in source
            and not any(f"fn {name}" in source for name in registered_functions)
        ):
            continue
        code = _rust_code_without_comments(source)
        source_classes = _rust_class_names(code)
        fields_local, methods_local = _rust_class_edges(code)
        for owner, targets in fields_local.items():
            if owner in fields:
                fields[owner] |= targets & set(registered_classes)
        for owner, targets in methods_local.items():
            if owner in method_returns:
                method_returns[owner] |= targets & set(registered_classes)
        for fn_name, targets in _rust_function_returns(code, source_classes).items():
            function_returns.setdefault(fn_name, set()).update(
                targets & set(registered_classes)
            )
        # Markers are read from the original source because they are comments;
        # the owner/target are still checked against parsed registrations.
        for owner, target in RUST_RETURN_EDGE.findall(source):
            if owner and target in source_classes:
                marked_edges.append((owner, target))

    roots: set[str] = set()
    for py_name, (rust_name, kind, _rel) in details.items():
        if py_name not in referenced:
            continue
        if kind == "class" and rust_name in registered_classes:
            roots.add(rust_name)
        elif kind == "function":
            roots |= function_returns.get(rust_name, set())

    # An erased nested field (currently Pin.drill) is represented by a
    # validated source marker.  Owner resolution accepts either the Rust name
    # or its Python-visible renamed name, but still requires a live function
    # registration before it can add a type edge.
    for owner, target in marked_edges:
        owner_details = next(
            (
                (rust_name, kind, py_name)
                for py_name, (rust_name, kind, _rel) in details.items()
                if rust_name == owner or py_name == owner
            ),
            None,
        )
        if owner_details is None:
            continue
        owner_rust, owner_kind, owner_py = owner_details
        if owner_kind == "function" and owner_py in referenced:
            roots.add(target)

    reachable = set(roots)
    pending = list(roots)
    while pending:
        owner = pending.pop()
        for target in fields.get(owner, set()) | method_returns.get(owner, set()):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    return {registered_classes[rust_name] for rust_name in reachable}


def rust_production_references() -> tuple[set[str], list[str]]:
    """Identifiers dynamically referenced by non-test Rust source files."""
    names: set[str] = set()
    unreadable: list[str] = []
    for rs in REPO_ROOT.glob("packages/*/src/**/*.rs"):
        if "/target" in str(rs) or "/tests/" in str(rs):
            continue
        try:
            names |= rust_code_identifiers(rs.read_text())
        except OSError:
            unreadable.append(str(rs.relative_to(REPO_ROOT)))
    return names, unreadable


def production_references() -> tuple[set[str], list[str]]:
    """Identifiers referenced by every non-test Python source, and unparseable files."""
    roots = ["packages", "scripts", "tools"]
    names: set[str] = set()
    unparseable: list[str] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            p = str(py)
            if "/tests/" in p or "/test_" in p:
                continue
            if "phase5_" in p and p.endswith("_mutations.py"):
                # Mutation-campaign drivers contain MUTATED copies of the
                # pre-migration kernels (to verify the Rust differential
                # catches behavior drift). They are adversarial harnesses,
                # not production callers -- counting them makes genuinely
                # unwired kernels look wired (measured 2026-08-08:
                # is_via_position_valid / place_via_with_clearance were
                # reported STALE_ENTRY via phase5_batch1_mutations.py).
                continue
            # NOTE: a bare `*_test.py` suffix is NOT a test-file marker on
            # its own -- production modules use it too
            # (regression/closure_test.py, scripts/ci_closure_test.py) and
            # DO call kernels. Real tests are excluded above by /tests/ and
            # /test_ alone; excluding `*_test.py` here previously hid a
            # production caller (measured 2026-08-08: closure_validate was
            # reported unwired while regression/closure_test.py:202 calls it).
            if "/.venv/" in p or "/target" in p or "/_py_oracle" in p:
                continue
            try:
                src = py.read_text()
            except OSError:
                continue
            try:
                names |= code_identifiers(src)
            except SyntaxError:
                unparseable.append(str(py.relative_to(REPO_ROOT)))
                names |= set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", src))
    rust_names, unreadable = rust_production_references()
    names |= rust_names
    # Some pyo3 classes are intentionally anonymous to Python callers: they
    # are nested in a live function/class return (for example DRC snapshot
    # rows and loop wires). Follow their Rust type edges after collecting the
    # ordinary Python and dynamic Rust references.
    names |= rust_type_flow_references(names)
    return names, unparseable + unreadable


def load_inventory() -> dict[str, str]:
    if not INVENTORY.exists():
        return {}
    entries: dict[str, str] = {}
    for line in INVENTORY.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sym, _, reason = line.partition("\t")
        entries[sym.strip()] = reason.strip()
    return entries


def write_inventory(unwired: dict[str, str], previous: dict[str, str]) -> None:
    lines = [
        "# Registered Rust kernels with no production caller.",
        "#",
        "# Shrink-only. A new entry is a hard failure -- wire the kernel or add it",
        "# here WITH A REASON. An entry that becomes wired is also a failure, so",
        "# paid-down debt shows up in a diff instead of rotting on the books.",
        "#",
        "# Generated by scripts/check_unwired_kernels.py --write-inventory",
        "# <symbol>\\t<reason>",
    ]
    for sym in sorted(unwired):
        reason = previous.get(sym, "").strip() or "unwired at time of recording; no reason given"
        lines.append(f"{sym}\t{reason}")
    INVENTORY.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runtime", action="store_true",
                    help="AUDIT: read symbols from the built extensions instead of "
                         "parsing Rust (exact, but needs `maturin develop`)")
    ap.add_argument("--write-inventory", action="store_true",
                    help="record the current unwired set (shrink-only ledger)")
    args = ap.parse_args()

    symbols = registered_symbols_runtime() if args.runtime else registered_symbols()
    if not symbols:
        print("FAIL: found zero registered pyo3 symbols -- the scan is broken, "
              "not the tree (a gate that inspects nothing passes vacuously).",
              file=sys.stderr)
        return 2

    referenced, unparseable = production_references()
    if not referenced:
        print("FAIL: found zero production Python sources to scan.", file=sys.stderr)
        return 2
    if unparseable:
        print(f"WARN: {len(unparseable)} file(s) did not parse; matched as raw text "
              f"(a mention in prose there can still mask an unwired kernel): "
              f"{', '.join(unparseable[:5])}", file=sys.stderr)

    unwired = {sym: where for sym, where in symbols.items() if sym not in referenced}

    ledger = load_inventory()

    if args.write_inventory:
        write_inventory(unwired, ledger)
        print(f"wrote {INVENTORY.name}: {len(unwired)} unwired kernel(s) "
              f"of {len(symbols)} registered")
        return 0

    new = sorted(set(unwired) - set(ledger))
    stale = sorted(set(ledger) - set(unwired))

    if not new and not stale:
        print(f"OK: {len(symbols)} registered kernel(s); "
              f"{len(unwired)} unwired, all ledgered.")
        return 0

    print("FAIL: unwired-kernel gate\n")
    for sym in new:
        print(f"NEW_UNWIRED   {sym}  ({unwired[sym]})")
        print("              registered into a Python module but no non-test caller.")
    for sym in stale:
        print(f"STALE_ENTRY   {sym} is now wired -- record the fix")
    print()
    if new:
        print("A registered kernel with no production caller is a migration that "
              "stopped at 'the differential is green'. The differential compares "
              "the ORACLE against the Rust and passes either way; it cannot see "
              "whether the shipped module delegates. Wire the Python call site, "
              "or add the symbol to the ledger with a reason.")
    if stale:
        print("STALE_ENTRY means debt was paid but the ledger was not updated: "
              "rerun with --write-inventory and commit the result.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
