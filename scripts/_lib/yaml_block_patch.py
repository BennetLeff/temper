"""Replace one top-level block of a YAML document without touching the rest.

Why this exists
---------------
``power_pcb_dataset/baselines/temper_production_baseline.yaml`` is 350 lines,
of which roughly 250 are comments: a ~200-line header recording why
``component_count``/``net_count`` were removed on 2026-07-29 (after five
hand-edits chased absolutes against a mutable board and went red on ``main``
four times in three days), plus per-block provenance notes explaining what
each number means and which measurement produced it. That rationale is the
most valuable content in the file -- it is what stops the next person
repeating the mistake.

The routine this replaces did::

    doc = yaml.safe_load(f)
    doc["router_v6_routing"] = {...}
    yaml.safe_dump(doc, f, ...)

``yaml.safe_dump`` serialises a plain ``dict``. A ``dict`` has no comments.
So the round trip deleted all ~250 of them -- an observed ``-292/+91`` diff --
while looking, in code, like it only assigned one key.

Approach: textual splice, not a round-tripping loader
------------------------------------------------------
Three options were weighed:

1. **A round-tripping loader** (``ruamel.yaml`` in ``rt`` mode). Preserves
   most comments, but adds a dependency the repo does not currently have, and
   still re-emits the *entire* document -- so quoting style, line wrapping and
   block-scalar formatting can shift anywhere in the file. A baseline diff
   should show the numbers that changed and nothing else; a reformat of 350
   lines is not reviewable.
2. **Splitting rationale into a sibling document.** Rejected: it separates the
   reasoning from the number it explains, which is precisely the coupling that
   makes the header work. The header is read *because* it is adjacent to
   ``drc_errors``.
3. **Replace only the target block's lines, textually.** Chosen. Every byte
   outside the replaced block is preserved exactly -- not "preserved by a
   serialiser that tries hard", but literally the same bytes. The resulting
   diff is minimal and reviewable by construction.

The splice fails closed rather than guessing: an ambiguous or missing target
key, or a comment *inside* the block being replaced (which a splice would
destroy -- the same failure mode in miniature), raises
:exc:`YamlBlockPatchError` and writes nothing.
"""

from __future__ import annotations

from typing import Any

import yaml


class YamlBlockPatchError(RuntimeError):
    """Raised when a block cannot be replaced safely. Nothing is written."""


def _block_bounds(lines: list[str], key: str) -> tuple[int, int]:
    """Return ``(start, end)`` line indices of top-level *key*'s block.

    ``start`` is the ``key:`` line; ``end`` is exclusive and excludes any
    blank lines trailing the block, so those stay outside the replaced region
    and survive verbatim.
    """
    header = f"{key}:"
    starts = [i for i, line in enumerate(lines) if line == header or line.startswith(header + " ")]
    if not starts:
        raise YamlBlockPatchError(f"top-level key {key!r} not found at column 0")
    if len(starts) > 1:
        raise YamlBlockPatchError(
            f"top-level key {key!r} appears {len(starts)} times at column 0 "
            f"(lines {[i + 1 for i in starts]}); refusing to guess which to replace"
        )
    start = starts[0]

    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line and not line[0].isspace():
            # A new top-level construct: another key, or a comment column 0.
            end = i
            break

    while end > start + 1 and not lines[end - 1].strip():
        end -= 1

    return start, end


def render_block(key: str, data: Any) -> list[str]:
    """Render ``{key: data}`` as YAML lines, in insertion order."""
    text = yaml.safe_dump({key: data}, default_flow_style=False, sort_keys=False)
    return text.rstrip("\n").split("\n")


def patch_yaml_block(original: str, key: str, data: Any) -> str:
    """Return *original* with top-level *key*'s block replaced by *data*.

    Every byte outside the block is preserved exactly. Raises
    :exc:`YamlBlockPatchError` -- writing nothing -- if the target is missing,
    ambiguous, or contains comments that a splice would destroy, or if the
    result fails the post-conditions below.
    """
    lines = original.split("\n")
    start, end = _block_bounds(lines, key)

    comment_lines = [
        (i + 1, lines[i]) for i in range(start, end) if lines[i].lstrip().startswith("#")
    ]
    if comment_lines:
        rendered = "\n".join(f"    line {n}: {text.strip()}" for n, text in comment_lines)
        raise YamlBlockPatchError(
            f"block {key!r} contains {len(comment_lines)} comment line(s) that a "
            f"textual splice would delete:\n{rendered}\n"
            "Move them above the block (where they are preserved) or extend this "
            "patcher to carry them. Refusing to write."
        )

    patched_lines = lines[:start] + render_block(key, data) + lines[end:]
    patched = "\n".join(patched_lines)

    _verify(original, patched, key, start, end)
    return patched


def _verify(original: str, patched: str, key: str, start: int, end: int) -> None:
    """Post-conditions. A patcher that can silently corrupt evidence is worse
    than no patcher, so the result is checked before the caller may write it.
    """
    try:
        before = yaml.safe_load(original) or {}
        after = yaml.safe_load(patched) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise YamlBlockPatchError(f"patched document does not parse as YAML: {exc}") from exc

    if list(after) != list(before):
        raise YamlBlockPatchError(
            f"top-level keys changed: {list(before)!r} -> {list(after)!r}. Refusing to write."
        )

    for other in before:
        if other == key:
            continue
        if before[other] != after[other]:
            raise YamlBlockPatchError(
                f"patching {key!r} also changed unrelated top-level key {other!r}. "
                "Refusing to write."
            )

    original_lines = original.split("\n")
    patched_lines = patched.split("\n")
    if original_lines[:start] != patched_lines[:start]:
        raise YamlBlockPatchError("content before the patched block changed. Refusing to write.")
    if original_lines[end:] != patched_lines[len(patched_lines) - (len(original_lines) - end) :]:
        raise YamlBlockPatchError("content after the patched block changed. Refusing to write.")

    def comment_count(text: str) -> int:
        return sum(1 for line in text.split("\n") if line.lstrip().startswith("#"))

    if comment_count(patched) != comment_count(original):
        raise YamlBlockPatchError(
            f"comment count changed {comment_count(original)} -> {comment_count(patched)}. "
            "This patcher exists specifically to prevent that. Refusing to write."
        )
