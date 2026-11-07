import os
import unittest
from pathlib import Path
from unittest.mock import patch

from database import log_github_run


class WorkflowActivityLoggerTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_NUMBER": "7",
            "GITHUB_WORKFLOW": "Deploy Private Owner Dashboard",
            "GITHUB_REF_NAME": "main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_REPOSITORY": "owner/repo",
            "JOB_STATUS": "success",
        }

    def test_workflow_fallback_event_is_persisted_when_jobs_are_unavailable(self):
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(log_github_run, "github_jobs", return_value=[]), \
             patch.object(log_github_run, "record_activity", return_value=True) as write:
            log_github_run.main()
        self.assertEqual(write.call_count, 1)
        event = write.call_args.args[0]
        self.assertEqual(event["event_id"], "gha:12345:workflow-fallback")
        self.assertEqual(event["metadata"]["run_url"], "https://github.com/owner/repo/actions/runs/12345")

    def test_each_job_step_is_persisted(self):
        jobs = [{
            "id": 99,
            "name": "Validate dashboard",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-11-07T10:00:00Z",
            "completed_at": "2026-11-07T10:00:01Z",
            "steps": [{
                "number": 1,
                "name": "Run tests",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-11-07T10:00:00Z",
                "completed_at": "2026-11-07T10:00:01Z",
            }],
        }]
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(log_github_run, "github_jobs", return_value=jobs), \
             patch.object(log_github_run, "record_activity", return_value=True) as write:
            log_github_run.main()
        self.assertEqual(write.call_count, 1)
        self.assertEqual(write.call_args.args[0]["operation"], "Validate dashboard / Run tests")

    def test_logger_fails_if_d1_does_not_persist_events(self):
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(log_github_run, "github_jobs", return_value=[]), \
             patch.object(log_github_run, "record_activity", return_value=False):
            with self.assertRaisesRegex(SystemExit, "0/1 events persisted"):
                log_github_run.main()

    def test_workflows_use_live_github_expression_syntax(self):
        root = Path(__file__).resolve().parents[2]
        for relative in (
            ".github/workflows/record-workflow-activity.yml",
            ".github/workflows/migrate-d1-monitoring.yml",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("\\${{", source, relative)


if __name__ == "__main__":
    unittest.main()
