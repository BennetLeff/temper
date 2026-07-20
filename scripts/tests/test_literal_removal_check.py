"""Tests for literal_removal_check.py."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literal_removal_check import (
    extract_literals,
    find_external_references,
    hunks_from_diff,
    is_noise,
    main,
    removed_literals_per_file,
)


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    return tmp_path


class TestExtractLiterals:
    def test_extracts_numeric_literal(self):
        tokens = extract_literals("CONNECTION_THRESHOLD_MM = 0.5")
        assert "0.5" in tokens

    def test_extracts_quoted_string_literal(self):
        tokens = extract_literals('layer = "F.Cu"')
        assert '"F.Cu"' in tokens

    def test_extracts_all_caps_constant_name(self):
        tokens = extract_literals("CONNECTION_THRESHOLD_MM = 0.5")
        assert "CONNECTION_THRESHOLD_MM" in tokens

    def test_ignores_lowercase_identifiers(self):
        tokens = extract_literals("threshold_mm = get_value()")
        assert not any(t.islower() for t in tokens)

    def test_empty_line_yields_no_tokens(self):
        assert extract_literals("") == set()


class TestHunksFromDiff:
    def test_parses_single_file_single_hunk(self):
        diff_text = (
            "diff --git a/adapter.py b/adapter.py\n"
            "--- a/adapter.py\n"
            "+++ b/adapter.py\n"
            "@@ -10 +10 @@\n"
            '-    layer = "F.Cu"\n'
            '+    layer = path_layer\n'
        )
        files = hunks_from_diff(diff_text)
        assert list(files.keys()) == ["adapter.py"]
        assert len(files["adapter.py"]) == 1
        hunk = files["adapter.py"][0]
        assert hunk["removed"] == ['    layer = "F.Cu"']
        assert hunk["added"] == ["    layer = path_layer"]

    def test_parses_multiple_files(self):
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-old_a\n"
            "+new_a\n"
            "diff --git a/b.py b/b.py\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -1 +1 @@\n"
            "-old_b\n"
            "+new_b\n"
        )
        files = hunks_from_diff(diff_text)
        assert set(files.keys()) == {"a.py", "b.py"}

    def test_multiple_hunks_in_one_file(self):
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-first\n"
            "+first_new\n"
            "@@ -20 +20 @@\n"
            "-second\n"
            "+second_new\n"
        )
        files = hunks_from_diff(diff_text)
        assert len(files["a.py"]) == 2

    def test_empty_diff_yields_no_files(self):
        assert hunks_from_diff("") == {}


class TestRemovedLiteralsPerFile:
    def test_flags_true_removal(self):
        diff_text = (
            "diff --git a/adapter.py b/adapter.py\n"
            "--- a/adapter.py\n"
            "+++ b/adapter.py\n"
            "@@ -10 +10 @@\n"
            '-    layer = "F.Cu"\n'
            "+    layer = path_layer\n"
        )
        flagged = removed_literals_per_file(diff_text)
        assert flagged == {"adapter.py": {'"F.Cu"'}}

    def test_does_not_flag_edited_token_present_in_added_line(self):
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            '-x = "KEEP_ME"\n'
            '+x = "KEEP_ME"  # reformatted\n'
        )
        flagged = removed_literals_per_file(diff_text)
        assert flagged == {}

    def test_filters_noise_tokens(self):
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-x = 0\n"
            "+x = get_default()\n"
        )
        flagged = removed_literals_per_file(diff_text)
        assert flagged == {}

    def test_file_with_no_flagged_literals_absent_from_result(self):
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-x = old_fn()\n"
            "+x = new_fn()\n"
        )
        assert removed_literals_per_file(diff_text) == {}


class TestFindExternalReferences:
    def test_finds_reference_in_another_file(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "adapter.py").write_text('layer = path_layer\n')
        (repo / "other.py").write_text('DEFAULT_LAYER = "F.Cu"\n')
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)

        refs = find_external_references('"F.Cu"', "adapter.py", repo_root=repo)

        assert len(refs) == 1
        assert "other.py" in refs[0]

    def test_excludes_the_source_file_itself(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "adapter.py").write_text('# was "F.Cu" here once\n')
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)

        refs = find_external_references('"F.Cu"', "adapter.py", repo_root=repo)

        assert refs == []

    def test_no_references_returns_empty_list(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "adapter.py").write_text("layer = path_layer\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)

        refs = find_external_references('"NOWHERE_TOKEN"', "adapter.py", repo_root=repo)

        assert refs == []


class TestMain:
    def test_reports_finding_and_exits_zero(self, tmp_path, capsys):
        repo = _init_repo(tmp_path)
        (repo / "adapter.py").write_text('layer = "F.Cu"\n')
        (repo / "other.py").write_text('DEFAULT_LAYER = "F.Cu"\n')
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)

        (repo / "adapter.py").write_text("layer = path_layer\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "remove hardcode"], cwd=repo, check=True)

        exit_code = main(["--base", "HEAD~1"], repo_root=repo)

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "adapter.py" in captured.out
        assert "F.Cu" in captured.out
        assert "other.py" in captured.out

    def test_clean_message_when_nothing_flagged(self, tmp_path, capsys):
        repo = _init_repo(tmp_path)
        (repo / "a.py").write_text("x = old_fn()\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)

        (repo / "a.py").write_text("x = new_fn()\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "refactor"], cwd=repo, check=True)

        exit_code = main(["--base", "HEAD~1"], repo_root=repo)

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "no removed literals" in captured.out


class TestIsNoise:
    def test_common_short_numbers_are_noise(self):
        assert is_noise("0")
        assert is_noise("1")
        assert is_noise("-1")

    def test_empty_string_literal_is_noise(self):
        assert is_noise('""')

    def test_meaningful_constant_is_not_noise(self):
        assert not is_noise("CONNECTION_THRESHOLD_MM")

    def test_meaningful_decimal_is_not_noise(self):
        assert not is_noise("0.5")
