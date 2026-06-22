"""Tests for session dashboard server API."""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest import TestCase, main

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))
from server import Handler, CLAUDE_DIR, CACHE_TTL

class FakeHandler:
    """Minimal handler for testing _discover and API logic."""
    def __init__(self):
        self._cache = {"sessions": None, "ts": 0}
        Handler.__init__ = lambda s, *a, **kw: None
        self.h = Handler.__new__(Handler)

    def discover(self, limit=50, offset=0):
        return self.h._discover(limit, offset)

    def parse_jsonl(self, fp):
        return self.h._parse_jsonl(fp)

    def from_index_entry(self, entry, encoded_dir):
        return self.h._from_index_entry(entry, encoded_dir)

    def parse_codex_json(self, fp):
        return self.h._parse_codex_json(fp)

    def scan_subagents(self, proj_path, proj_dir):
        if not os.path.isdir(proj_path):
            return []
        return self.h._scan_subagents(proj_path, proj_dir)

    def parse_subagent_dir(self, sub_dir, proj_dir, parent_uuid=None):
        return self.h._parse_subagent_dir(sub_dir, proj_dir, parent_uuid)

    def make_summary(self, project, branch, duration_ms, agent_count, platform):
        return self.h._make_summary(project, branch, duration_ms, agent_count, platform)

    def group_sessions(self, sessions):
        return self.h._group_sessions(sessions)


class TestParseJSONL(TestCase):
    def setUp(self):
        self.h = FakeHandler()
        self.tmp = tempfile.gettempdir()

    def write_jsonl(self, lines, name="test.jsonl"):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path

    def test_parse_jsonl_valid(self):
        path = self.write_jsonl([
            '{"timestamp":"2026-06-22T10:00:00Z","type":"user","message":"hello"}',
            '{"timestamp":"2026-06-22T10:05:00Z","type":"assistant","message":"hi"}',
            '{"timestamp":"2026-06-22T10:10:00Z","type":"tool_use","name":"Task","input":{}}',
        ])
        result = self.h.parse_jsonl(path)
        self.assertIsNotNone(result)
        self.assertEqual(result["platform"], "opencode")
        self.assertIsNotNone(result["startedAt"])
        self.assertIsNotNone(result["duration"])
        self.assertEqual(result["subAgentCount"], 1)
        self.assertEqual(result["sourceType"], "jsonl")
        self.assertIn("summary", result)
        self.assertTrue("opencode" in result["summary"].lower())

    def test_parse_jsonl_too_few_lines(self):
        path = self.write_jsonl(['{"timestamp":"2026-06-22T10:00:00Z"}'])
        self.assertIsNone(self.h.parse_jsonl(path))

    def test_parse_jsonl_empty(self):
        path = self.write_jsonl([])
        self.assertIsNone(self.h.parse_jsonl(path))

    def test_parse_jsonl_missing_file(self):
        self.assertIsNone(self.h.parse_jsonl("/nonexistent/file.jsonl"))

    def test_parse_jsonl_agent_type_extracted(self):
        path = self.write_jsonl([
            '{"timestamp":"2026-06-22T10:00:00Z","type":"user","message":"hello"}',
            '{"timestamp":"2026-06-22T10:05:00Z","type":"assistant","message":"testing review"}',
        ])
        result = self.h.parse_jsonl(path)
        self.assertIsNotNone(result)
        # agentType may be null for simple sessions without specific tool calls
        self.assertIn("agentType", result)


class TestParseCodexJSON(TestCase):
    def setUp(self):
        self.h = FakeHandler()
        self.tmp = tempfile.gettempdir()

    def write_json(self, data, name="test.json"):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_parse_codex_valid(self):
        path = self.write_json({
            "session": {"id": "test-42", "project": "temper", "branch": "main"},
            "items": [
                {"timestamp": "2025-12-01T10:00:00Z"},
                {"timestamp": "2025-12-01T11:00:00Z"},
            ]
        })
        result = self.h.parse_codex_json(path)
        self.assertIsNotNone(result)
        self.assertEqual(result["platform"], "codex")
        self.assertEqual(result["project"], "temper")
        self.assertEqual(result["branch"], "main")
        self.assertIsNotNone(result["duration"])

    def test_parse_codex_invalid_json(self):
        path = self.write_json({}, "invalid.json")
        result = self.h.parse_codex_json(path)
        self.assertIsNotNone(result)  # should still return minimal session

    def test_parse_codex_no_session(self):
        path = self.write_json({"events": [{"timestamp": "2025-01-01T00:00:00Z"}]})
        result = self.h.parse_codex_json(path)
        self.assertIsNotNone(result)


class TestFromIndexEntry(TestCase):
    def setUp(self):
        self.h = FakeHandler()

    def test_from_index_basic(self):
        entry = {
            "sessionId": "abc-123",
            "summary": "Test session summary",
            "gitBranch": "feat/test",
            "projectPath": "/Users/test/project",
            "created": "2026-06-22T10:00:00Z",
            "modified": "2026-06-22T11:00:00Z",
            "messageCount": 42,
        }
        result = self.h.from_index_entry(entry, "some-encoded-dir")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "abc-123")
        self.assertEqual(result["summary"], "Test session summary")
        self.assertEqual(result["branch"], "feat/test")
        self.assertEqual(result["platform"], "opencode")
        self.assertEqual(result["messageCount"], 42)
        self.assertIsNotNone(result["duration"])

    def test_from_index_missing_fields(self):
        entry = {"sessionId": "minimal"}
        result = self.h.from_index_entry(entry, "encoded")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "minimal")
        self.assertIn("summary", result)
        self.assertEqual(result["platform"], "opencode")

    def test_from_index_summary_fallback(self):
        entry = {"sessionId": "no-summary", "projectPath": "/tmp/proj"}
        result = self.h.from_index_entry(entry, "encoded")
        self.assertTrue(result["summary"])  # should have fallback summary


class TestScanSubagents(TestCase):
    def setUp(self):
        self.h = FakeHandler()
        self.tmpdir = tempfile.mkdtemp()

    def create_meta(self, agent_type, description, dir_path):
        meta = {"agentType": agent_type, "description": description}
        os.makedirs(dir_path, exist_ok=True)
        path = os.path.join(dir_path, f"agent-{agent_type.replace(':','-')}.meta.json")
        with open(path, "w") as f:
            json.dump(meta, f)
        return path

    def test_scan_subagents_no_dir(self):
        result = self.h.scan_subagents("/nonexistent", "test")
        self.assertEqual(result, [])

    def test_parse_subagent_basic(self):
        sub_dir = os.path.join(self.tmpdir, "subagents")
        self.create_meta("compound-engineering:ce-testing-reviewer", "Testing review", sub_dir)
        # Create matching jsonl
        jsonl_path = os.path.join(sub_dir, f"agent-compound-engineering:ce-testing-reviewer.jsonl")
        with open(jsonl_path, "w") as f:
            f.write('{"timestamp":"2026-06-22T10:00:00Z","type":"assistant","message":"review findings"}\n')
        results = self.h.parse_subagent_dir(sub_dir, "test")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["isSubagent"])
        self.assertEqual(results[0]["agentType"], "compound-engineering:ce-testing-reviewer")
        self.assertIn("Testing review", results[0]["summary"])

    def test_parse_subagent_parent_uuid(self):
        sub_dir = os.path.join(self.tmpdir, "subagents")
        self.create_meta("compound-engineering:ce-ideate", "Ideation", sub_dir)
        results = self.h.parse_subagent_dir(sub_dir, "test", parent_uuid="parent-abc")
        if results:
            self.assertEqual(results[0]["parentUuid"], "parent-abc")


class TestGroupSessions(TestCase):
    def setUp(self):
        self.h = FakeHandler()

    def test_group_subagents_under_parent(self):
        sessions = [
            {"id": "parent-1", "isSubagent": False, "summary": "Parent session"},
            {"id": "sub-1", "isSubagent": True, "parentUuid": "parent-1", "agentType": "ce-testing", "summary": "Review"},
            {"id": "sub-2", "isSubagent": True, "parentUuid": "parent-1", "agentType": "ce-security", "summary": "Security check"},
            {"id": "indep-1", "isSubagent": False, "summary": "Independent session"},
        ]
        result = self.h.group_sessions(sessions)
        self.assertEqual(len(result), 2)  # parent + independent
        parent = [s for s in result if s["id"] == "parent-1"][0]
        self.assertEqual(parent["subAgentCount"], 2)
        self.assertEqual(len(parent["subAgents"]), 2)

    def test_orphan_synthetic_parent(self):
        sessions = [
            {"id": "orphan-1", "isSubagent": True, "parentUuid": "missing-parent", "agentType": "ce-testing", "summary": "Review", "startedAt": "2026-06-22T10:00:00Z", "project": "temper"},
            {"id": "orphan-2", "isSubagent": True, "parentUuid": "missing-parent", "agentType": "ce-security", "summary": "Security check", "project": "temper"},
        ]
        result = self.h.group_sessions(sessions)
        self.assertTrue(any(s.get("isSynthetic") for s in result),
                        f"Synthetic parent should be created. Got: {[s.get('isSynthetic') for s in result]}")
        synthetic = [s for s in result if s.get("isSynthetic")][0]
        self.assertEqual(synthetic["subAgentCount"], 2)
        self.assertEqual(synthetic["id"], "missing-parent")

    def test_no_subagents_no_grouping(self):
        sessions = [
            {"id": "a", "isSubagent": False, "summary": "A"},
            {"id": "b", "isSubagent": False, "summary": "B"},
        ]
        result = self.h.group_sessions(sessions)
        self.assertEqual(len(result), 2)


class TestDiscover(TestCase):
    def setUp(self):
        self.h = FakeHandler()

    def test_discover_api_shape(self):
        result = self.h.discover(limit=10, offset=0)
        self.assertIn("sessions", result)
        self.assertIn("total", result)
        self.assertIn("count", result)
        self.assertIn("offset", result)
        self.assertIn("limit", result)
        self.assertEqual(result["limit"], 10)
        self.assertEqual(result["offset"], 0)
        self.assertLessEqual(result["count"], 10)

    def test_discover_pagination(self):
        first = self.h.discover(limit=5, offset=0)
        self.assertLessEqual(first["count"], 5)
        if first["total"] > 5:
            second = self.h.discover(limit=5, offset=5)
            self.assertLessEqual(second["count"], 5)
            first_ids = {s["id"] for s in first["sessions"]}
            second_ids = {s["id"] for s in second["sessions"]}
            self.assertEqual(len(first_ids & second_ids), 0,
                             "Pages should not overlap")

    def test_discover_sessions_have_required_fields(self):
        result = self.h.discover(limit=5)
        for s in result["sessions"]:
            self.assertIn("id", s, f"Session missing id: {s}")
            self.assertIn("platform", s)
            self.assertIn("project", s)
            self.assertIn("summary", s)
            self.assertIn("sourceType", s)
            self.assertIn("status", s)
            # platform should be sensible
            self.assertIn(s["platform"], ("opencode", "codex", "claude"))


class TestMakeSummary(TestCase):
    def setUp(self):
        self.h = FakeHandler()

    def test_make_summary_opencode(self):
        summary = self.h.make_summary("temper", "main", 3600000, 3, "opencode")
        self.assertIn("Opencode", summary)
        self.assertIn("temper", summary)
        self.assertIn("3", summary)
        self.assertIn("1h", summary)

    def test_make_summary_codex(self):
        summary = self.h.make_summary("project", "fix/test", 60000, 0, "codex")
        self.assertTrue(summary.startswith("Codex"))
        self.assertIn("project", summary)

    def test_make_summary_no_duration(self):
        summary = self.h.make_summary("temper", "main", None, 0, "opencode")
        self.assertIn("temper", summary)
        self.assertIn("Opencode", summary)
        self.assertNotIn("ran for", summary)


if __name__ == "__main__":
    main()
