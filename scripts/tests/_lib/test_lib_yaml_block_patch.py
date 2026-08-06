"""Tests for _lib/yaml_block_patch.py.

The property under test is the one the 2026-08-04 incident violated: writing
a measurement baseline must change the numbers asked for and *nothing else* --
above all, not the rationale comments that explain why the numbers are what
they are.

``TestAgainstTheRealBaseline`` runs against the committed
``temper_production_baseline.yaml`` itself (read-only -- it asserts on the
returned string and never writes the file), because a synthetic two-key
document would not exercise the thing that actually broke: a 350-line file
that is ~235 lines of comment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.repo import find_repo_root  # noqa: E402
from _lib.yaml_block_patch import (  # noqa: E402
    YamlBlockPatchError,
    patch_yaml_block,
)

DOC = """\
# Header comment explaining the whole file.
# Second header line.
alpha: 1
beta:
  nested: true

# A comment that belongs to gamma, sitting between blocks.
gamma:
  value: 10
  items:
  - a
  - b

# Trailing rationale, after the last block.
delta: 4
"""


def comment_count(text: str) -> int:
    return sum(1 for line in text.split("\n") if line.lstrip().startswith("#"))


class TestSplice:
    def test_replaces_only_the_target_block(self):
        patched = patch_yaml_block(DOC, "gamma", {"value": 99, "items": ["c"]})

        after = yaml.safe_load(patched)
        assert after["gamma"] == {"value": 99, "items": ["c"]}
        assert after["alpha"] == 1
        assert after["beta"] == {"nested": True}
        assert after["delta"] == 4

    def test_preserves_every_comment(self):
        patched = patch_yaml_block(DOC, "gamma", {"value": 99, "items": ["c"]})

        assert comment_count(patched) == comment_count(DOC)
        assert "# Header comment explaining the whole file." in patched
        assert "# A comment that belongs to gamma, sitting between blocks." in patched
        assert "# Trailing rationale, after the last block." in patched

    def test_identity_patch_is_byte_identical(self):
        """Re-writing a block with the data it already holds must be a no-op.

        A patcher that reformats on an identity write produces diff noise that
        hides the real change -- the reason a round-tripping loader was
        rejected for this job.
        """
        original_gamma = yaml.safe_load(DOC)["gamma"]

        assert patch_yaml_block(DOC, "gamma", original_gamma) == DOC

    def test_preserves_key_order_of_the_document(self):
        patched = patch_yaml_block(DOC, "beta", {"nested": False})

        assert list(yaml.safe_load(patched)) == list(yaml.safe_load(DOC))

    def test_patching_the_last_block_works(self):
        patched = patch_yaml_block(DOC, "delta", 5)

        assert yaml.safe_load(patched)["delta"] == 5
        assert comment_count(patched) == comment_count(DOC)


class TestFailsClosed:
    def test_missing_key_raises_and_writes_nothing(self):
        with pytest.raises(YamlBlockPatchError, match="not found"):
            patch_yaml_block(DOC, "epsilon", {"x": 1})

    def test_comment_inside_the_block_is_refused(self):
        """A splice would silently delete it -- the incident in miniature."""
        doc = "alpha: 1\ngamma:\n  # why value is 10\n  value: 10\nbeta: 2\n"

        with pytest.raises(YamlBlockPatchError, match="comment line"):
            patch_yaml_block(doc, "gamma", {"value": 11})

    def test_duplicate_top_level_key_is_refused(self):
        doc = "gamma:\n  value: 1\nbeta: 2\ngamma:\n  value: 3\n"

        with pytest.raises(YamlBlockPatchError, match="appears 2 times"):
            patch_yaml_block(doc, "gamma", {"value": 9})


class TestAgainstTheRealBaseline:
    """Read-only exercise against the file the incident destroyed."""

    @pytest.fixture
    def baseline_text(self) -> str:
        repo_root = find_repo_root(Path(__file__).resolve().parent)
        path = repo_root / "power_pcb_dataset" / "baselines" / "temper_production_baseline.yaml"
        if not path.exists():
            pytest.skip(f"baseline not present: {path}")
        return path.read_text()

    def test_baseline_is_comment_heavy(self, baseline_text):
        """Anti-vacuity: the cases below prove nothing on a comment-free file."""
        assert comment_count(baseline_text) > 100, (
            "the production baseline lost its rationale comments; this test "
            "exists because that is exactly what must not happen"
        )

    def test_rationale_header_survives_a_patch(self, baseline_text):
        block = dict(yaml.safe_load(baseline_text)["router_v6_routing"])
        block["routed_nets"] = 40

        patched = patch_yaml_block(baseline_text, "router_v6_routing", block)

        assert comment_count(patched) == comment_count(baseline_text)
        assert "# --- component_count / net_count removed (2026-07-29) ---" in patched
        assert yaml.safe_load(patched)["router_v6_routing"]["routed_nets"] == 40

    def test_patch_is_a_minimal_diff(self, baseline_text):
        """The safe_dump path produced -292/+91. This must produce ~2 lines."""
        import difflib

        block = dict(yaml.safe_load(baseline_text)["router_v6_routing"])
        block["routed_nets"] = 40

        patched = patch_yaml_block(baseline_text, "router_v6_routing", block)
        changed = [
            line
            for line in difflib.unified_diff(baseline_text.split("\n"), patched.split("\n"), n=0)
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]

        assert len(changed) == 2, "expected a 1-line change, got:\n" + "\n".join(changed)

    def test_unrelated_blocks_are_untouched(self, baseline_text):
        before = yaml.safe_load(baseline_text)
        block = dict(before["router_v6_routing"])
        block["routed_nets"] = 40

        after = yaml.safe_load(patch_yaml_block(baseline_text, "router_v6_routing", block))

        for key in before:
            if key != "router_v6_routing":
                assert after[key] == before[key], f"unrelated key {key!r} changed"
