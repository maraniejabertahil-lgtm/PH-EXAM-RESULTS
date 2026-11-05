"""Release-gated Facebook/Telegram broadcaster with fail-closed idempotency."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
CONTEXT = "ph-exam-results/broadcast"


class BroadcastError(RuntimeError):
    pass


def request_json(url, method="GET", token=None, payload=None, form=None):
    headers = {"User-Agent": "PH-EXAM-RESULTS-broadcaster/1.0"}
    data = None
    if token:
        headers.update({"Authorization": "Bearer " + token,
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"})
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=25) as response:
            raw = response.read()
            return json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as exc:
        raise BroadcastError("External API returned HTTP " + str(exc.code)) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BroadcastError("External API request failed; sensitive details withheld.") from exc


def validate_deployment(run):
    if (run.get("name") != "Deploy Cloudflare Pages" or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("head_branch") != "main"):
        raise BroadcastError("Broadcast blocked: no successful Cloudflare Pages deployment on main.")


def announcement(authority, examination, year, pages_url):
    from urllib.parse import urlsplit
    parsed = urlsplit(pages_url or "")
    if (authority not in {"PRC", "CSC"} or not re.fullmatch(r"[A-Za-z0-9 .&()_-]{1,80}", examination or "")
            or not re.fullmatch(r"20[0-9]{2}", str(year))
            or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password):
        raise BroadcastError("Invalid announcement identity or HTTPS website URL.")
    return f"{authority} {examination} ({year}) results are available. Search passer names and official sequence numbers: {pages_url.rstrip('/')}"


def verify_live_site(url):
    request = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "PH-EXAM-RESULTS-broadcaster/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if not 200 <= response.status < 400:
                raise BroadcastError("Published website health check did not succeed.")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise BroadcastError("Published website health check failed.") from exc


def publish(repo, run_id, pages_url, authority, examination, year, github_token,
            facebook_page_id="", facebook_token="", telegram_token="", telegram_chat_id="",
            dry_run=True):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or "") or not github_token:
        raise BroadcastError("Repository identity and GITHUB_TOKEN are required.")
    run = request_json(f"{API}/repos/{repo}/actions/runs/{int(run_id)}", token=github_token)
    validate_deployment(run)
    sha = run.get("head_sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise BroadcastError("Deployment commit SHA is invalid.")
    prs = request_json(f"{API}/repos/{repo}/commits/{sha}/pulls", token=github_token)
    matches = [p for p in prs if p.get("base", {}).get("ref") == "main"
               and p.get("merged_at") and p.get("merge_commit_sha") == sha]
    if len(matches) != 1:
        raise BroadcastError("Deployment commit does not identify exactly one merged dataset PR.")
    message = announcement(authority, examination, year, pages_url)
    verify_live_site(pages_url)
    if dry_run:
        return {"status": "dry_run", "pr": matches[0]["number"], "message": message}

    if not all((facebook_page_id, facebook_token, telegram_token, telegram_chat_id)):
        raise BroadcastError("Facebook and Telegram credentials and destination IDs are required.")
    statuses = request_json(f"{API}/repos/{repo}/commits/{sha}/statuses", token=github_token)
    old = next((s.get("state") for s in statuses if s.get("context") == CONTEXT), None)
    if old == "success":
        return {"status": "already_broadcast", "pr": matches[0]["number"]}
    if old in {"pending", "error"}:
        raise BroadcastError("Prior broadcast is pending or failed; manual review prevents duplicate posts.")

    def mark(state, description):
        request_json(f"{API}/repos/{repo}/statuses/{sha}", method="POST", token=github_token,
                     payload={"state": state, "context": CONTEXT, "description": description})

    mark("pending", "Social announcements in progress")
    try:
        fb_result = request_json("https://graph.facebook.com/v21.0/" + urllib.parse.quote(facebook_page_id, safe="") + "/feed",
                                 method="POST", form={"message": message, "access_token": facebook_token})
        if not fb_result.get("id"):
            raise BroadcastError("Facebook did not confirm publication.")
        tg_result = request_json("https://api.telegram.org/bot" + telegram_token + "/sendMessage",
                                 method="POST", payload={"chat_id": telegram_chat_id, "text": message})
        if tg_result.get("ok") is not True:
            raise BroadcastError("Telegram did not confirm delivery.")
    except BroadcastError:
        mark("error", "Broadcast failed or partially completed; manual review required")
        raise
    mark("success", "Facebook and Telegram announcements sent")
    return {"status": "published", "pr": matches[0]["number"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-run-id", type=int, required=True)
    parser.add_argument("--authority", choices=("PRC", "CSC"), required=True)
    parser.add_argument("--examination", required=True)
    parser.add_argument("--year", required=True)
    parser.add_argument("--publish", action="store_true", help="Send posts; default is dry-run.")
    args = parser.parse_args()
    try:
        result = publish(os.getenv("GITHUB_REPOSITORY", ""), args.deployment_run_id,
                         os.getenv("PAGES_URL", ""), args.authority, args.examination, args.year,
                         os.getenv("GITHUB_TOKEN", ""), os.getenv("FACEBOOK_PAGE_ID", ""),
                         os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", ""), os.getenv("TELEGRAM_BOT_TOKEN", ""),
                         os.getenv("TELEGRAM_CHAT_ID", ""), dry_run=not args.publish)
        print(json.dumps(result))
        return 0
    except BroadcastError as exc:
        print("Broadcast blocked: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
