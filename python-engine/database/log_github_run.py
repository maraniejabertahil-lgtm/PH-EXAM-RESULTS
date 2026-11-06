"""Record a GitHub Actions job result in the private D1 activity timeline."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from d1_client import record_activity

def main():
    run_id = os.getenv("GITHUB_RUN_ID", "local")
    job = os.getenv("GITHUB_JOB", "unknown")
    status = os.getenv("JOB_STATUS", "warning").lower()
    if status not in {"success", "failed", "blocked", "warning"}:
        status = "warning"
    record_activity({
        "event_id": f"gha:{run_id}:{job}:finished",
        "execution_id": f"gha:{run_id}",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "component": "GitHub Actions",
        "operation": job,
        "status": status,
        "severity": "error" if status == "failed" else "info",
        "message": f"{os.getenv('GITHUB_WORKFLOW', 'GitHub Actions')}: {job} {status}.",
        "source": "github_actions",
        "metadata": {
            "run_id": run_id, "run_number": os.getenv("GITHUB_RUN_NUMBER", ""),
            "workflow": os.getenv("GITHUB_WORKFLOW", "GitHub Actions"),
            "job": job, "branch": os.getenv("GITHUB_REF_NAME", ""),
            "commit": os.getenv("GITHUB_SHA", ""),
        },
    })

if __name__ == "__main__":
    main()
