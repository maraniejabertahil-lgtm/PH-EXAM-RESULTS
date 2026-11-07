"""Record GitHub Actions jobs and individual steps in the private D1 timeline."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from d1_client import record_activity

def normalize_status(status, conclusion):
    if status == "in_progress":
        return "running"
    value = (conclusion or status or "").lower()
    if value == "success":
        return "success"
    if value in {"failure", "timed_out", "action_required"}:
        return "failed"
    if value in {"cancelled", "neutral"}:
        return "blocked"
    if value == "skipped":
        return "success"
    return "warning"

def github_jobs(repo, run_id, token):
    if not repo or not run_id or not token:
        return []
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PH-EXAM-RESULTS-Activity-Monitor/1.0",
    })
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("jobs", []) if isinstance(payload, dict) else []
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        return []

def duration_ms(started, completed):
    try:
        start = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        return max(0, int((end - start).total_seconds() * 1000))
    except (TypeError, ValueError):
        return None

def main():
    run_id = os.getenv("GITHUB_RUN_ID", "local")
    run_number = os.getenv("GITHUB_RUN_NUMBER", "")
    workflow = os.getenv("GITHUB_WORKFLOW", "GitHub Actions")
    branch = os.getenv("GITHUB_REF_NAME", "")
    sha = os.getenv("GITHUB_SHA", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    execution_id = f"gha:{run_id}"
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if repo else ""
    jobs = github_jobs(repo, run_id, os.getenv("GITHUB_TOKEN", ""))
    now = datetime.now(timezone.utc).isoformat()
    attempted = 0
    written = 0

    def persist(event):
        nonlocal attempted, written
        attempted += 1
        if record_activity(event):
            written += 1
    for job in jobs:
        job_name = str(job.get("name") or "workflow_job")
        steps = job.get("steps") if isinstance(job.get("steps"), list) else []
        if not steps:
            status = normalize_status(job.get("status"), job.get("conclusion"))
            persist({
                "event_id": f"gha:{run_id}:job:{job.get('id', job_name)}",
                "execution_id": execution_id,
                "occurred_at": job.get("completed_at") or job.get("started_at") or now,
                "component": "GitHub Actions", "operation": job_name,
                "status": status, "severity": "error" if status == "failed" else "info",
                "duration_ms": duration_ms(job.get("started_at"), job.get("completed_at")),
                "message": f"{workflow}: {job_name} {status}.", "source": "github_actions",
                "metadata": {"run_id": run_id, "run_number": run_number, "workflow": workflow,
                             "job": job_name, "branch": branch, "commit": sha, "run_url": run_url},
            })
        for step in steps:
            step_name = str(step.get("name") or "workflow_step")
            status = normalize_status(step.get("status"), step.get("conclusion"))
            persist({
                "event_id": f"gha:{run_id}:job:{job.get('id', job_name)}:step:{step.get('number', step_name)}",
                "execution_id": execution_id,
                "occurred_at": step.get("completed_at") or step.get("started_at") or now,
                "component": "GitHub Actions", "operation": job_name + " / " + step_name,
                "status": status, "severity": "error" if status == "failed" else ("warning" if status == "blocked" else "info"),
                "duration_ms": duration_ms(step.get("started_at"), step.get("completed_at")),
                "message": f"{workflow}: {step_name} {status}.",
                "error_code": str(step.get("conclusion") or "").upper() if status == "failed" else None,
                "error_message": (f"Step concluded with {step.get('conclusion')}. Open the linked workflow run for full logs." if status == "failed" else None),
                "source": "github_actions",
                "metadata": {"run_id": run_id, "run_number": run_number, "workflow": workflow,
                             "job": job_name, "branch": branch, "commit": sha, "run_url": run_url},
            })
    if not jobs:
        status = normalize_status("", os.getenv("JOB_STATUS", ""))
        persist({
            "event_id": f"gha:{run_id}:workflow-fallback",
            "execution_id": execution_id, "occurred_at": now,
            "component": "GitHub Actions", "operation": workflow,
            "status": status, "severity": "error" if status == "failed" else "info",
            "message": f"{workflow} completed with status {status}.", "source": "github_actions",
            "metadata": {"run_id": run_id, "run_number": run_number, "workflow": workflow,
                         "job": "workflow_run", "branch": branch, "commit": sha, "run_url": run_url},
        })

    if attempted == 0 or written != attempted:
        raise SystemExit(f"Private activity logging incomplete: {written}/{attempted} events persisted.")

if __name__ == "__main__":
    main()
