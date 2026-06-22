"""Tests for the heuristic artifact matcher."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matcher


class TestMatcher(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = self.tmpdir.name
        # Create docs directories
        for sub in ("plans", "brainstorms", "solutions"):
            os.makedirs(os.path.join(self.root, "docs", sub), exist_ok=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _touch(self, rel_path, content="", mtime_delta=0):
        fp = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(content)
        if mtime_delta:
            os.utime(fp, (os.path.getatime(fp), datetime.now().timestamp() + mtime_delta))
        return fp

    def _iso_ts(self, seconds_ago=0):
        t = datetime.now(timezone.utc).timestamp() - seconds_ago
        return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()

    def test_happy_path(self):
        fp = self._touch("docs/plans/2026-06-22-purge-and-protect.md",
                         "---\ntitle: Purge and Protect\n---\nPlan content")
        now = datetime.now().timestamp()
        os.utime(fp, (now, now))
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(60),
            "duration": 30000,
            "summary": "purge-and-protect plan for temper project",
            "agentType": "ce-plan",
        }
        results = matcher.match_session(session, self.root)
        self.assertTrue(len(results) >= 1)
        best = results[0]
        self.assertEqual(best["confidence"], "high")
        self.assertIn("timestamp", best["match_method"])
        self.assertIn("keywords", best["match_method"])
        self.assertIn("agentType", best["match_method"])

    def test_no_description_no_agentType(self):
        fp = self._touch("docs/plans/some-plan.md", "content")
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(60),
            "duration": 30000,
        }
        results = matcher.match_session(session, self.root)
        # File was just created (mtime=now), session was 60s ago with 30s duration
        # Window: [now - 360, now + 240]. File mtime = now → full timestamp match.
        # Timestamp contribution = 0.5, no keywords (no summary), no agentType.
        # Combined = 0.5 → "high" from timestamp alone
        if results:
            self.assertEqual(results[0]["match_method"], "timestamp")

    def test_no_possible_matches(self):
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(5),
            "duration": 1000,
            "summary": "brand new session",
        }
        results = matcher.match_session(session, self.root)
        self.assertEqual(results, [])

    def test_deleted_file(self):
        self._touch("docs/plans/deleted-plan.md", "content")
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(60),
            "duration": 30000,
            "summary": "deleted plan",
            "agentType": "ce-plan",
        }
        results = matcher.match_session(session, self.root)
        # Delete the file
        os.remove(os.path.join(self.root, "docs/plans/deleted-plan.md"))
        # Re-run; the matcher sees only what's on disk, so no match
        results2 = matcher.match_session(session, self.root)
        self.assertEqual(results2, [])

    def test_stopword_filtering(self):
        fp = self._touch("docs/plans/plan.md", "content")
        now = datetime.now().timestamp()
        os.utime(fp, (now, now))
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(60),
            "duration": 30000,
            "summary": "the plan for the project",
            "agentType": "ce-plan",
        }
        results = matcher.match_session(session, self.root)
        self.assertTrue(len(results) >= 1)
        r = results[0]
        self.assertIn("agentType", r["match_method"])
        self.assertIn("timestamp", r["match_method"])
        # Keywords should be empty, so no "keywords" in match_method

    def test_missing_docs_dir(self):
        empty_dir = tempfile.TemporaryDirectory()
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(60),
            "duration": 30000,
            "summary": "test",
        }
        results = matcher.match_session(session, empty_dir.name)
        self.assertEqual(results, [])
        empty_dir.cleanup()

    def test_agentType_directory_mapping(self):
        fp = self._touch("docs/brainstorms/idea.md", "content")
        now = datetime.now().timestamp()
        os.utime(fp, (now, now))
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(60),
            "duration": 30000,
            "summary": "brainstorm idea",
            "agentType": "ce-brainstorm",
        }
        results = matcher.match_session(session, self.root)
        self.assertTrue(len(results) >= 1)

    def test_score_thresholds(self):
        fp = self._touch("docs/plans/edge-plan.md", "content")
        # File mtime far outside window (6 hours ago)
        os.utime(fp, (datetime.now().timestamp() - 21600, datetime.now().timestamp() - 21600))
        session = {
            "id": "test-session",
            "startedAt": self._iso_ts(300),
            "duration": 60000,
        }
        results = matcher.match_session(session, self.root)
        # No agentType, no summary, file far from window → no match
        self.assertEqual(results, [])

    def test_scan_empty_project(self):
        empty = tempfile.TemporaryDirectory()
        arts = matcher.scan_project_docs(empty.name)
        self.assertEqual(arts, [])
        empty.cleanup()


if __name__ == "__main__":
    unittest.main()
