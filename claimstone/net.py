"""HTTP with a conscience: timeouts, identification, robots, and a domain failure budget.

Two rules here exist because breaking them corrupts the science rather than merely being
impolite. First, every outcome is recorded: a swallowed failure inflates the acquisition
rate, which is the figure that decides whether a round may produce verdicts at all.
Second, a host that refuses us is not hammered — the per-domain budget and its TTL are
what keep a blocked publisher from turning into thousands of requests.
"""

from __future__ import annotations

import os
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any

import requests

USER_AGENT = (
    "Claimstone/0.1 (evidence-synthesis research tool; "
    "+https://github.com/Jonbj/claimstone; contact: {contact})"
)

# Distinct failure classes, because "it failed" is not an actionable denominator.
PAYWALL = "PAYWALL_403"
RATE_LIMITED = "RATE_LIMITED_429"
NOT_FOUND = "NOT_FOUND_404"
SERVER_ERROR = "SERVER_ERROR_5XX"
TIMEOUT = "TIMEOUT"
CONNECTION = "CONNECTION_ERROR"
EXCLUDED = "EXCLUDED_HOST"
ROBOTS = "ROBOTS_DISALLOWED"
BUDGET = "DOMAIN_BUDGET_EXHAUSTED"
BAD_TYPE = "UNEXPECTED_CONTENT_TYPE"
EMPTY = "EMPTY_RESPONSE"


class ContactNotConfigured(RuntimeError):
    """Refusing to make anonymous automated requests against scholarly infrastructure."""


def contact_email() -> str:
    email = (os.environ.get("CLAIMSTONE_CONTACT_EMAIL") or "").strip()
    if not email or "@" not in email:
        raise ContactNotConfigured(
            "set CLAIMSTONE_CONTACT_EMAIL to a real address: Crossref and Unpaywall require "
            "it, and identifying the crawler is a condition of using these APIs politely"
        )
    return email


def host_of(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


@dataclass
class Outcome:
    """What happened, whether or not it worked. Always recorded."""

    url: str
    ok: bool
    status: int | None = None
    failure_class: str | None = None
    detail: str = ""
    content_type: str = ""
    body: bytes | None = None
    elapsed_s: float = 0.0

    def as_row(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "ok": self.ok,
            "http_status": self.status,
            "failure_class": self.failure_class,
            "detail": self.detail[:400],
            "content_type": self.content_type,
            "bytes": len(self.body) if self.body else 0,
            "elapsed_s": round(self.elapsed_s, 2),
        }


@dataclass
class Fetcher:
    """One fetcher per run. Holds the per-domain budget so it survives a whole campaign."""

    excluded_hosts: frozenset[str] = frozenset()
    max_403_per_host: int = 5
    max_429_per_host: int = 3
    failure_ttl_s: int = 48 * 3600
    timeout_s: int = 30
    obey_robots: bool = True
    pause_s: float = 0.34

    _host_failures: dict[str, list[float]] = field(default_factory=dict)
    _robots: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)
    robots_notes: dict[str, str] = field(default_factory=dict)
    _session: requests.Session | None = None
    _last_request: float = 0.0

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT.format(contact=contact_email())

    # -- budget ---------------------------------------------------------------

    def _record_failure(self, host: str) -> None:
        self._host_failures.setdefault(host, []).append(time.time())

    def _recent_failures(self, host: str) -> int:
        cutoff = time.time() - self.failure_ttl_s
        kept = [t for t in self._host_failures.get(host, []) if t >= cutoff]
        self._host_failures[host] = kept
        return len(kept)

    def budget_exhausted(self, host: str) -> bool:
        return self._recent_failures(host) >= self.max_403_per_host

    # -- robots ---------------------------------------------------------------

    def _robots_allows(self, url: str) -> bool:
        """Honour robots.txt only when a robots.txt was actually served.

        urllib's RobotFileParser.read() treats a 403 on /robots.txt as "disallow
        everything", and happily parses an HTML error page as if it were rules. Several
        hosts in real manifests do exactly that: federalreserve.gov and sec.gov return HTML
        for /robots.txt, users.nber.org returns 403. Trusting the parser there invents
        prohibitions that were never stated and **deflates the acquisition rate**, which is
        the number that decides whether a round may produce verdicts. So the file is
        fetched here, and only a genuine 200 text/plain robots file is binding.
        """
        if not self.obey_robots:
            return True
        host = host_of(url)
        if host not in self._robots:
            self._robots[host] = self._load_robots(url, host)
        parser = self._robots[host]
        if parser is None:
            return True
        try:
            return parser.can_fetch(USER_AGENT.split("/")[0], url)
        except Exception:
            return True

    def _load_robots(self, url: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        """Return a parser only if a real robots.txt was served; otherwise None (permissive)."""
        scheme = urllib.parse.urlparse(url).scheme or "https"
        assert self._session is not None
        try:
            self._throttle()
            response = self._session.get(f"{scheme}://{host}/robots.txt", timeout=self.timeout_s)
        except requests.RequestException as exc:
            self.robots_notes[host] = f"unreachable: {type(exc).__name__}"
            return None

        if response.status_code != 200:
            # 404 means no rules. 401/403 means we cannot read the rules, which is not the
            # same as being forbidden from the site — record it and proceed.
            self.robots_notes[host] = f"not served: HTTP {response.status_code}"
            return None

        ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        body = response.text or ""
        looks_like_html = body.lstrip()[:1] == "<" or "html" in ctype
        mentions_rules = "user-agent" in body.lower()
        if looks_like_html or not mentions_rules:
            self.robots_notes[host] = f"not a robots file (content-type {ctype or 'unknown'})"
            return None

        parser = urllib.robotparser.RobotFileParser()
        parser.parse(body.splitlines())
        self.robots_notes[host] = "honoured"
        return parser

    # -- fetching -------------------------------------------------------------

    def _throttle(self) -> None:
        wait = self.pause_s - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    def get(self, url: str, *, expect: tuple[str, ...] = (), as_json: bool = False) -> Outcome:
        host = host_of(url)
        if host in self.excluded_hosts:
            return Outcome(url, False, failure_class=EXCLUDED, detail=f"{host} is excluded")
        if self.budget_exhausted(host):
            return Outcome(
                url, False, failure_class=BUDGET,
                detail=f"{self._recent_failures(host)} recent failures on {host}",
            )
        if not self._robots_allows(url):
            return Outcome(url, False, failure_class=ROBOTS, detail="robots.txt disallows")

        assert self._session is not None
        self._throttle()
        started = time.time()
        try:
            response = self._session.get(
                url, timeout=self.timeout_s, allow_redirects=True,
                headers={"Accept": "application/json"} if as_json else None,
            )
        except requests.Timeout as exc:
            self._record_failure(host)
            return Outcome(url, False, failure_class=TIMEOUT, detail=str(exc),
                           elapsed_s=time.time() - started)
        except requests.RequestException as exc:
            self._record_failure(host)
            return Outcome(url, False, failure_class=CONNECTION, detail=str(exc),
                           elapsed_s=time.time() - started)

        elapsed = time.time() - started
        ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        status = response.status_code

        if status == 403:
            self._record_failure(host)
            return Outcome(url, False, status, PAYWALL, "forbidden", ctype, elapsed_s=elapsed)
        if status == 429:
            self._record_failure(host)
            return Outcome(url, False, status, RATE_LIMITED, "rate limited", ctype,
                           elapsed_s=elapsed)
        if status == 404:
            return Outcome(url, False, status, NOT_FOUND, "not found", ctype, elapsed_s=elapsed)
        if status >= 500:
            self._record_failure(host)
            return Outcome(url, False, status, SERVER_ERROR, f"status {status}", ctype,
                           elapsed_s=elapsed)
        if status >= 400:
            return Outcome(url, False, status, f"HTTP_{status}", f"status {status}", ctype,
                           elapsed_s=elapsed)

        body = response.content or b""
        if not body:
            return Outcome(url, False, status, EMPTY, "empty body", ctype, elapsed_s=elapsed)
        if expect and ctype and not any(e in ctype for e in expect):
            return Outcome(url, False, status, BAD_TYPE, f"got {ctype}", ctype, body=body,
                           elapsed_s=elapsed)
        return Outcome(url, True, status, None, "", ctype, body, elapsed)

    def get_json(self, url: str) -> tuple[dict[str, Any] | None, Outcome]:
        outcome = self.get(url, as_json=True)
        if not outcome.ok or not outcome.body:
            return None, outcome
        try:
            import json

            return json.loads(outcome.body.decode("utf-8", "replace")), outcome
        except ValueError as exc:
            outcome.ok = False
            outcome.failure_class = BAD_TYPE
            outcome.detail = f"invalid JSON: {exc}"
            return None, outcome
