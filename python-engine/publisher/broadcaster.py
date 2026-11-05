"""Post-deployment result announcements for Facebook Pages and Telegram."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class BroadcastError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


@dataclass(frozen=True)
class Settings:
    facebook_page_id: str | None
    facebook_token: str | None
    facebook_version: str | None
    telegram_token: str | None
    telegram_chat_id: str | None
    site_url: str | None
    event_id: str | None
    repository: str | None
    github_token: str | None
    ledger_branch: str = "automation/broadcast-ledger"

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("FACEBOOK_PAGE_ID"), os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN"),
            os.getenv("FACEBOOK_GRAPH_API_VERSION"), os.getenv("TELEGRAM_BOT_TOKEN"),
            os.getenv("TELEGRAM_CHAT_ID"), os.getenv("PUBLIC_SITE_URL"),
            os.getenv("BROADCAST_EVENT_ID"), os.getenv("GITHUB_REPOSITORY"),
            os.getenv("GITHUB_TOKEN"), os.getenv("BROADCAST_LEDGER_BRANCH", "automation/broadcast-ledger"),
        )


def result_routes(paths: Iterable[str]) -> list[dict[str, str]]:
    pattern = re.compile(
        r"^public/data/(?P<authority>PRC|CSC)/(?P<exam>[A-Za-z0-9_-]{1,80})/(?P<year>20\d{2})/manifest\.json$"
    )
    found = {}
    for path in paths:
        match = pattern.fullmatch(path.strip() if isinstance(path, str) else "")
        if match:
            route = match.groupdict()
            found[(route["authority"], route["exam"], route["year"])] = route
    return [found[key] for key in sorted(found)]


def _site_url(value: str | None) -> str:
    parsed = urllib.parse.urlsplit(value or "")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise BroadcastError("PUBLIC_SITE_URL must be a credential-free HTTPS URL.")
    return value.rstrip("/")


def _message(route: dict[str, str], site_url: str) -> str:
    query = urllib.parse.urlencode(route)
    return (
        f"Verified {route['authority']} {route['exam'].replace('-', ' ')} {route['year']} "
        f"examination results are now live.\nSearch the result dataset: {site_url}/?{query}"
    )


class GitHubLedger:
    """Persistent send-state on a separate branch; uncertain sends are never retried blindly."""

    def __init__(self, settings: Settings, opener=urllib.request.urlopen):
        if not settings.repository or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", settings.repository):
            raise BroadcastError("GITHUB_REPOSITORY must use owner/name format.")
        if not settings.github_token:
            raise BroadcastError("GITHUB_TOKEN is required for broadcast idempotency.")
        self.root = f"https://api.github.com/repos/{settings.repository}"
        self.token, self.branch, self.opener = settings.github_token, settings.ledger_branch, opener

    def api(self, method: str, path: str, payload=None, missing_ok=False):
        request = urllib.request.Request(
            self.root + path,
            data=None if payload is None else json.dumps(payload).encode(),
            method=method,
            headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                     "User-Agent": "PH-EXAM-RESULTS-Broadcast-Ledger/1.0"},
        )
        try:
            with self.opener(request, timeout=15) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise BroadcastError(f"GitHub ledger API returned HTTP {exc.code}.", uncertain=exc.code >= 500) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BroadcastError(f"GitHub ledger request failed: {type(exc).__name__}.", uncertain=True) from exc

    def read(self):
        ref_path = "/git/ref/heads/" + urllib.parse.quote(self.branch, safe="/")
        if self.api("GET", ref_path, missing_ok=True) is None:
            main = self.api("GET", "/git/ref/heads/main")
            sha = main.get("object", {}).get("sha")
            if not sha:
                raise BroadcastError("Cannot initialize broadcast ledger from main.")
            self.api("POST", "/git/refs", {"ref": f"refs/heads/{self.branch}", "sha": sha})
        query = urllib.parse.urlencode({"ref": self.branch})
        item = self.api("GET", "/contents/.github/broadcast-ledger.json?" + query, missing_ok=True)
        if item is None:
            return {"schema_version": 1, "deliveries": {}}, None
        try:
            value = json.loads(base64.b64decode(item["content"]).decode())
            if value.get("schema_version") != 1 or not isinstance(value.get("deliveries"), dict):
                raise ValueError("invalid schema")
            return value, item["sha"]
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise BroadcastError("Broadcast ledger is malformed; refusing to send.") from exc

    def status(self, key):
        data, _ = self.read()
        entry = data["deliveries"].get(key, {})
        return entry.get("status") if isinstance(entry, dict) else None

    def set_status(self, key, status):
        data, sha = self.read()
        data["deliveries"][key] = {"status": status}
        body = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        payload = {"message": "chore(broadcast): update delivery ledger",
                   "content": base64.b64encode(body).decode(), "branch": self.branch}
        if sha:
            payload["sha"] = sha
        self.api("PUT", "/contents/.github/broadcast-ledger.json", payload)


def _post(url: str, data: bytes, content_type: str, opener, *, label: str) -> dict:
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": content_type, "Accept": "application/json",
                 "User-Agent": "PH-EXAM-RESULTS-Broadcaster/1.0"},
    )
    try:
        with opener(request, timeout=15) as response:
            raw = response.read()
            result = json.loads(raw.decode()) if raw else {}
            if not 200 <= response.status < 300:
                raise BroadcastError(f"{label} returned HTTP {response.status}.")
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise BroadcastError(f"{label} returned HTTP {exc.code}: {detail}", uncertain=exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BroadcastError(f"{label} request failed: {type(exc).__name__}.", uncertain=True) from exc


def send_facebook(message: str, settings: Settings, opener=urllib.request.urlopen) -> dict:
    if not all((settings.facebook_page_id, settings.facebook_token, settings.facebook_version)):
        raise BroadcastError("Facebook requires page ID, Page access token, and Graph API version.")
    if not re.fullmatch(r"v\d+\.\d+", settings.facebook_version):
        raise BroadcastError("FACEBOOK_GRAPH_API_VERSION must use the vNN.N format.")
    url = f"https://graph.facebook.com/{settings.facebook_version}/{urllib.parse.quote(settings.facebook_page_id, safe='')}/feed"
    body = urllib.parse.urlencode({"message": message, "access_token": settings.facebook_token}).encode()
    result = _post(url, body, "application/x-www-form-urlencoded", opener, label="Facebook Graph API")
    if not result.get("id"):
        raise BroadcastError("Facebook did not confirm the Page post.", uncertain=True)
    return {"post_id": str(result["id"])}


def send_telegram(message: str, settings: Settings, opener=urllib.request.urlopen) -> dict:
    if not settings.telegram_token or not settings.telegram_chat_id:
        raise BroadcastError("Telegram requires bot token and chat ID.")
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    body = json.dumps({"chat_id": settings.telegram_chat_id, "text": message}).encode()
    result = _post(url, body, "application/json", opener, label="Telegram Bot API")
    if result.get("ok") is not True or not isinstance(result.get("result"), dict) or not result["result"].get("message_id"):
        raise BroadcastError("Telegram did not confirm message delivery.")
    return {"message_id": result["result"]["message_id"]}


def broadcast(paths, settings: Settings, *, deployment_succeeded: bool, dry_run=False,
              opener=urllib.request.urlopen, ledger=None):
    if deployment_succeeded is not True:
        raise BroadcastError("Broadcast blocked: Pages deployment has not succeeded.")
    routes = result_routes(paths)
    if not routes:
        return {"status": "skipped", "reason": "No result manifest changed.", "announcements": 0}
    channels = []
    if any((settings.facebook_page_id, settings.facebook_token, settings.facebook_version)):
        channels.append("facebook")
    if settings.telegram_token or settings.telegram_chat_id:
        channels.append("telegram")
    if not channels:
        return {"status": "skipped", "reason": "No channels configured.", "announcements": 0}
    site = _site_url(settings.site_url)
    if not dry_run:
        if not settings.event_id or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", settings.event_id):
            raise BroadcastError("BROADCAST_EVENT_ID is required.")
        ledger = ledger or GitHubLedger(settings, opener)
    outcomes = []
    for route in routes:
        message = _message(route, site)
        if dry_run:
            outcomes.append({"route": route, "status": "dry_run", "message": message})
            continue
        route_key = "/".join((route["authority"], route["exam"], route["year"]))
        for channel in channels:
            key = f"{settings.event_id}:{route_key}:{channel}"
            previous = ledger.status(key)
            if previous == "sent":
                outcomes.append({"route": route, "channel": channel, "status": "already_sent"})
                continue
            if previous == "pending":
                raise BroadcastError(f"{key} is pending; owner reconciliation required.", uncertain=True)
            ledger.set_status(key, "pending")
            try:
                result = send_facebook(message, settings, opener) if channel == "facebook" else send_telegram(message, settings, opener)
            except BroadcastError as exc:
                if not exc.uncertain:
                    ledger.set_status(key, "failed")
                raise
            try:
                ledger.set_status(key, "sent")
            except BroadcastError as exc:
                raise BroadcastError("Provider accepted the message but ledger update failed; reconcile manually.",
                                     uncertain=True) from exc
            outcomes.append({"route": route, "channel": channel, "status": "sent", "provider_result": result})
    return {"status": "dry_run" if dry_run else "sent", "announcements": len(outcomes), "outcomes": outcomes}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Announce newly deployed examination result datasets.")
    parser.add_argument("--changed-files", required=True)
    parser.add_argument("--deployment-succeeded", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = Path(args.changed_files).read_text(encoding="utf-8").splitlines()
        result = broadcast(paths, Settings.from_env(), deployment_succeeded=args.deployment_succeeded,
                           dry_run=args.dry_run)
    except (OSError, BroadcastError) as exc:
        print(f"BROADCAST STOPPED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
