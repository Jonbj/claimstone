# JATS normalization before Europe PMC acquisition

Date: 2026-09-28 · Status: local parser and acquisition integration implemented; live measurement pending

D39/D41 measured PMC's acquisition value. HANDOFF identifies Europe PMC as the next route to
measure. Its [REST service](https://europepmc.org/RestfulWebService) exposes `/{id}/fullTextXML` for
the open-access subset, not every PMC article. Previously every non-PDF input went to HTML.
No acquisition gain is established by adding a parser.

## Implemented boundary

`jats.parse(bytes)` produces the existing `tei.Document` shape without I/O. It does not fetch
external DTDs and refuses internal entity declarations. The primary article requires front,
article-meta and body; nested sub-articles and responses are separate evidence.

Paragraphs retain inline whitespace and document order; nested headings keep their path.
Lists and appendices retain paragraphs. Abstracts, bibliography, table cells and notes remain
separate from body character counts. Figure captions and footnotes become notes; graphics and
formula images are not converted into text. Citation metadata comes from explicit tags; when no
article title is tagged, the citation stays verbatim. Empty reference placeholders do not count.

Textual JATS XHTML tables retain cell geometry: colspan/rowspan continuation positions stay empty,
with no copied values. Ragged rows are padded. Image-only tables, CALS, multiple textual alternatives,
invalid/overlapping spans and spans beyond the last row raise `UnsupportedJats`. Normalization
reports `JATS_UNSUPPORTED` without publishing a document/chunk row: our limitation leaves the
source awaiting. Malformed or non-article XML records `JATS_UNREADABLE`, following the existing
malformed-TEI convention.

Recorded XML media types (`application/xml`, `text/xml`, `application/jats+xml`) select JATS;
XHTML stays HTML. Rows record `format: jats` and the current parser version (`jats_parser_version: 2` after D78). This version enters the
JATS generation digest; existing PDF/HTML generation inputs remain identical. Confirmation uses
the same thresholds and its audit rereads the recorded format. No production ledger is rebuilt.

## Local measurement

`pytest -q tests/test_jats.py` passes 22 synthetic cases covering paragraph/inline boundaries,
namespaced input, table geometry, separate notes/references, malformed/abstract-only inputs,
unsupported tables, normalization without GROBID, confirmation audits, idempotence and versioned
generations. These are explicit fixture checks, not validation on publisher articles.

## Acquisition integration and pending measurement

Gate version 4 accepts only structurally valid JATS XML with sufficient body text; XML error
responses do not become articles. A declared PMC article URL adds Europe PMC's open-access
`fullTextXML` endpoint before the HTML copy, through the existing Fetcher (robots, contact,
timeout, outcome log and failure budget). A missing XML copy falls through to HTML. Licence is
read from the article's JATS declaration when present, never inferred from a successful
response. Unsupported table structures still leave stage 3 awaiting rather than discarding
acquired bytes. Europe PMC documents the endpoint as covering its open-access subset:
https://europepmc.org/RestfulWebService.

The first six manifest rows are frozen in `store/pmc-screen-time/audits/europe-pmc/jats-pilot-v1-plan.json`,
with manifest and source-policy hashes, a named campaign and a six-article ceiling. The pilot
tool previews offline, resumes by source id, records each request and XML/parse outcome in
separate audit ledgers, and stops on a host refusal. It writes no production stage ledger.
Ask the operator before executing this bounded sweep. Full-text XML availability and reuse
depend on each article's actual licence, which remains visible with the original response.

Compare confirmation, bibliography, tables, body text and column attribution against manual reading
for the same identities. Report unsupported structures and misses alongside successes. Do not
automatically replace current Q04 chunks: that changes the evidence hash and requires renewed review.
Live acquisition yield and scientific reader accuracy remain unmeasured. No registry, floor,
model request, adjudication or production profile changes in this step.
