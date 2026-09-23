"""Shared test setup.

The contact address is required to build an Unpaywall or OpenAlex URL at all — identifying the
crawler is a condition of using those APIs politely, and `net.contact_email()` refuses to
guess. Setting it here is configuration, not a network capability: no test opens a socket, and
no test constructs a real `net.Fetcher`.
"""

import pytest


@pytest.fixture(autouse=True)
def _contact_address(monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "tests@example.org")
