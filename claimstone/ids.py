"""Identifier normalisation. Boring, and load-bearing for deduplication."""

from __future__ import annotations

import re
import unicodedata
import urllib.parse

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9<>\[\]]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arXiv:)\s*([0-9]{4}\.[0-9]{4,5})", re.I)
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_SPACE_RE = re.compile(r"\s+")

# How a candidate's identity is derived is an instrument, like the content gate's version and the
# chunker's: change it and every row written under the old rule lands under a different key, so the
# same work becomes two candidates and a denominator silently grows. Measured, on a store of 39
# references: 13 ghost rows, each correctly noting the other as a possible duplicate, and a found
# count of 50. `tools/check_instrument_versions.py` refuses a bump the design record does not name.
CANDIDATE_KEY_VERSION = 2


def normalize_doi(value: str | None) -> str | None:
    """Return a bare lowercase DOI, or None. Accepts URLs, `doi:` prefixes and raw DOIs."""
    if not value:
        return None
    text = urllib.parse.unquote(str(value).strip())
    match = _DOI_RE.search(text)
    if not match:
        return None
    doi = match.group(0).lower().rstrip(").,;")
    # Publisher URLs often append a file suffix that is not part of the DOI.
    for suffix in (".pdf", ".xml", ".full", ".abstract"):
        if doi.endswith(suffix):
            doi = doi[: -len(suffix)]
    return doi or None


def arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    match = _ARXIV_RE.search(str(value))
    return match.group(1) if match else None


def normalize_title(value: str | None) -> str:
    """Fold a title to a comparison key: accents, punctuation and spacing removed."""
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", str(value).lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _PUNCT_RE.sub(" ", folded)
    return _SPACE_RE.sub(" ", folded).strip()


def normalize_url(value: str | None) -> str:
    """Drop tracking parameters and fragments so the same page is one candidate."""
    if not value:
        return ""
    parts = urllib.parse.urlsplit(str(value).strip())
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(("utm_", "gclid", "fbclid", "mc_"))
    ]
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        ((parts.scheme or "https").lower(), host, path, urllib.parse.urlencode(query), "")
    )


def candidate_key(*, doi: str | None, title: str | None, url: str | None) -> str:
    """Identity for deduplication, in order of trustworthiness: DOI, then title, then URL.

    Title is used before URL deliberately: the same work appears at many URLs (preprint,
    repository, publisher), and collapsing those is the point of version lineage.

    Version 2: unchanged here, but the citation channel now overrides it, keying on the reference
    stage 3 gave it. Preferring a DOI is right for a search result and wrong for a reference, because
    resolution *adds* a DOI and a derived key would move. See `CANDIDATE_KEY_VERSION`.
    """
    if doi:
        return f"doi:{doi}"
    folded = normalize_title(title)
    if folded:
        return f"title:{folded}"
    return f"url:{normalize_url(url)}"
