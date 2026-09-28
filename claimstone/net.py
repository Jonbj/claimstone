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
from typing import Protocol

FETCH_VERSION = 2

REDIRECT = "REDIRECT_ERROR"

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

# Set by the content gate in fulltext.py rather than by HTTP: a 200 that carries a landing
# page, or the abstract page of a document, is a failure of acquisition even though the
# transfer succeeded.
LANDING = "LANDING_PAGE_ONLY"
ABSTRACT = "ABSTRACT_ONLY"
CHALLENGE = "BOT_CHALLENGE"
TOO_SHORT = "TOO_SHORT"
CORRUPT_PDF = "CORRUPT_PDF"
NOT_TEXT = "NOT_TEXT"
WAYBACK_MISS = "WAYBACK_MISS"
NO_LOCATIONS = "NO_LOCATIONS"

# Terminal: retrying changes nothing until the world changes, so a retry needs a named
# campaign. Transient: the next ordinary run should try again on its own.
TERMINAL = frozenset(
    {PAYWALL, ROBOTS, EXCLUDED, NOT_FOUND, BAD_TYPE, LANDING, ABSTRACT, TOO_SHORT,
     CORRUPT_PDF, NOT_TEXT, NO_LOCATIONS, REDIRECT,
     # Terminal on conduct grounds rather than because retrying could not work. The host asked us to
     # prove we are not a robot; knocking again without answering that is ignoring the request, so a
     # retry needs a named campaign like any other. The class exists to keep the *denominator* honest —
     # a challenge is a fact about our crawler and must not sit in the ledger as `ABSTRACT_ONLY`,
     # which is a fact about the source — and that job is done by the name, not by the retry policy.
     CHALLENGE}
)
TRANSIENT = frozenset(
    {TIMEOUT, CONNECTION, SERVER_ERROR, RATE_LIMITED, BUDGET, EMPTY, WAYBACK_MISS}
)


def is_terminal(failure_class: str | None) -> bool:
    """An unrecognised class counts as terminal: a typo must cost a retry, not a loop."""
    return failure_class not in TRANSIENT


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
    request_url: str = ""
    redirect_chain: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "request_url": self.request_url or self.url,
            "redirect_chain": list(self.redirect_chain),
            "fetch_version": FETCH_VERSION,
            "ok": self.ok,
            "http_status": self.status,
            "failure_class": self.failure_class,
            "detail": self.detail[:400],
            "content_type": self.content_type,
            "bytes": len(self.body) if self.body else 0,
            "elapsed_s": round(self.elapsed_s, 2),
        }


class FetcherLike(Protocol):
    """What the stages need from a fetcher. Tests supply their own implementation."""

    def get(self, url: str, *, expect: tuple[str, ...] = (), as_json: bool = False) -> Outcome: ...

    def get_json(self, url: str) -> tuple[dict[str, Any] | None, Outcome]: ...


@dataclass
class Fetcher:
    """One fetcher per run. Holds the per-domain budget so it survives a whole campaign."""

    excluded_hosts: frozenset[str] = frozenset()
    max_403_per_host: int = 5
    max_429_per_host: int = 3
    failure_ttl_s: int = 48 * 3600
    timeout_s: int = 30
    obey_robots: bool = True
    max_redirects: int = 10
    on_outcome: Any = None
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
        parsed = urllib.parse.urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(url, host)
        parser = self._robots[origin]
        if parser is None:
            return True
        try:
            return parser.can_fetch(USER_AGENT.split("/")[0], url)
        except Exception:
            return True

    def _load_robots(self, url: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        """Return a parser only if a real robots.txt was served; otherwise None (permissive)."""
        parsed = urllib.parse.urlsplit(url)
        outcome = self._get(f"{parsed.scheme}://{parsed.netloc}/robots.txt", check_robots=False)
        if not outcome.ok:
            self.robots_notes[host] = f"not served: {outcome.failure_class}"
            return None
        if outcome.status != 200:
            # 404 means no rules. 401/403 means we cannot read the rules, which is not the
            # same as being forbidden from the site — record it and proceed.
            self.robots_notes[host] = f"not served: HTTP {outcome.status}"
            return None

        ctype = outcome.content_type.split(";")[0].strip().lower()
        body = (outcome.body or b"" ).decode("utf-8", "replace")
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
        return self._get(url, expect=expect, as_json=as_json)

    def _get(self, url: str, *, expect=(), as_json=False, check_robots=True) -> Outcome:
        initial = url
        chain = []
        started = time.time()

        def finish(outcome):
            outcome.request_url = initial
            outcome.redirect_chain = list(chain)
            outcome.elapsed_s = time.time() - started
            if self.on_outcome:
                blocked = outcome.status is None and outcome.failure_class in (EXCLUDED, BUDGET, ROBOTS, REDIRECT)
                self.on_outcome(outcome, 'blocked' if blocked else ('transport' if check_robots else 'robots'))
            return outcome

        while True:
            host = host_of(url)
            if urllib.parse.urlparse(url).scheme not in ('http', 'https') or not host:
                return finish(Outcome(url, False, failure_class=REDIRECT, detail='non-HTTP destination'))
            if host in self.excluded_hosts or any(host.endswith('.' + h) for h in self.excluded_hosts):
                return finish(Outcome(url, False, failure_class=EXCLUDED, detail=f'{host} is excluded'))
            if self.budget_exhausted(host):
                return finish(Outcome(url, False, failure_class=BUDGET, detail=f'recent failures on {host}'))
            if check_robots and not self._robots_allows(url):
                return finish(Outcome(url, False, failure_class=ROBOTS, detail='robots.txt disallows'))
            # Fetching robots can itself spend the remaining host budget.
            if self.budget_exhausted(host):
                return finish(Outcome(url, False, failure_class=BUDGET, detail=f'recent failures on {host}'))
            if url in chain or len(chain) > self.max_redirects:
                return finish(Outcome(url, False, failure_class=REDIRECT, detail='redirect loop or limit'))
            chain.append(url)
            assert self._session is not None
            self._throttle()
            try:
                response = self._session.get(url, timeout=self.timeout_s, allow_redirects=False,
                    headers={'Accept': 'application/json'} if as_json else None)
            except requests.Timeout as exc:
                self._record_failure(host)
                return finish(Outcome(url, False, failure_class=TIMEOUT, detail=str(exc)))
            except requests.RequestException as exc:
                self._record_failure(host)
                return finish(Outcome(url, False, failure_class=CONNECTION, detail=str(exc)))
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location')
                if not location:
                    return finish(Outcome(url, False, response.status_code, REDIRECT, 'missing Location'))
                if self.on_outcome:
                    self.on_outcome(Outcome(url, True, response.status_code, request_url=initial,
                                            redirect_chain=list(chain)), 'redirect')
                url = urllib.parse.urljoin(url, location)
                continue
            break

        elapsed = time.time() - started
        ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        status = response.status_code

        # Charged to the host that actually refused us, which after a redirect is not the one we asked.
        # Measured, and it cost 17 candidates: every citation candidate's only address is a `doi.org`
        # URL, so a doi.org request landing on Wiley and taking a 403 charged the failure to doi.org —
        # one budget shared by every publisher the resolver points at, spending itself on 403s from
        # journals the next candidate had nothing to do with. The budget exists so a host that refused us
        # is not hammered, and a redirector is not that host.
        refused_by = host_of(getattr(response, "url", "") or url) or host

        if status == 403:
            self._record_failure(refused_by)
            return finish(Outcome(url, False, status, PAYWALL, "forbidden", ctype, elapsed_s=elapsed))
        if status == 429:
            self._record_failure(refused_by)
            return finish(Outcome(url, False, status, RATE_LIMITED, "rate limited", ctype,
                           elapsed_s=elapsed))
        if status == 404:
            return finish(Outcome(url, False, status, NOT_FOUND, "not found", ctype, elapsed_s=elapsed))
        if status >= 500:
            self._record_failure(refused_by)
            return finish(Outcome(url, False, status, SERVER_ERROR, f"status {status}", ctype,
                           elapsed_s=elapsed))
        if status >= 400:
            return finish(Outcome(url, False, status, f"HTTP_{status}", f"status {status}", ctype,
                           elapsed_s=elapsed))

        body = response.content or b""
        if not body:
            return finish(Outcome(url, False, status, EMPTY, "empty body", ctype, elapsed_s=elapsed))
        if expect and ctype and not any(e in ctype for e in expect):
            return finish(Outcome(url, False, status, BAD_TYPE, f"got {ctype}", ctype, body=body,
                           elapsed_s=elapsed))
        return finish(Outcome(url, True, status, None, "", ctype, body, elapsed))

    def get_json(self, url: str) -> tuple[dict[str, Any] | None, Outcome]:
        outcome = self.get(url, as_json=True)
        if not outcome.ok or not outcome.body:
            return None, outcome
        try:
            import json

            payload = json.loads(outcome.body.decode("utf-8", "replace"))
            if not isinstance(payload, dict):
                raise ValueError('expected a JSON object')
            return payload, outcome
        except ValueError as exc:
            outcome.ok = False
            outcome.failure_class = BAD_TYPE
            outcome.detail = f"invalid JSON: {exc}"
            return None, outcome
