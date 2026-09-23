"""Test doubles. No socket is opened and CLAIMSTONE_CONTACT_EMAIL is never needed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from claimstone import net


def ok(url: str, body: bytes, content_type: str = "application/pdf") -> net.Outcome:
    return net.Outcome(url, True, 200, None, "", content_type, body, 0.1)


def fail(url: str, status: int, failure_class: str, content_type: str = "text/html") -> net.Outcome:
    return net.Outcome(url, False, status, failure_class, "", content_type, None, 0.1)


@dataclass
class FakeFetcher:
    """Answers from dictionaries. `calls` records every URL, in order."""

    pages: dict[str, net.Outcome] = field(default_factory=dict)
    # Keyed by URL prefix, because Unpaywall URLs carry a contact email.
    json_pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def get(self, url: str, *, expect: tuple[str, ...] = (), as_json: bool = False) -> net.Outcome:
        self.calls.append(url)
        if url in self.pages:
            return self.pages[url]
        return net.Outcome(url, False, 404, net.NOT_FOUND, "fake: url not configured")

    def get_json(self, url: str) -> tuple[dict[str, Any] | None, net.Outcome]:
        self.calls.append(url)
        for prefix, payload in self.json_pages.items():
            if url.startswith(prefix):
                return payload, net.Outcome(url, True, 200)
        return None, net.Outcome(url, False, 404, net.NOT_FOUND, "fake: url not configured")
