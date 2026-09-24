"""The gate. A landing page answering 200 is the failure mode this exists to catch."""

import pytest

from claimstone import fulltext


def pdf(size: int = 12000, *, eof: bool = True) -> bytes:
    body = b"%PDF-1.4\n" + b"x" * size
    return body + b"\n%%EOF" if eof else body


def page(paragraphs: int, extra: str = "") -> bytes:
    """Synthetic markup. Real publisher pages are not copied into this repository."""
    body = "".join(
        f"<p>Sentence {i} of a document about abnormal returns around news events.</p>"
        for i in range(paragraphs)
    )
    return f"<html><head><style>p{{color:red}}</style></head><body>{extra}{body}</body></html>".encode()


def cited(paragraphs: int) -> bytes:
    """A document that argues from evidence: it has a reference list."""
    body = "".join(
        f"<p>Paragraph {i} (Fama and French, 1993) shows an effect.</p>"
        for i in range(paragraphs)
    )
    return f"<html><body>{body}<h2>References</h2><p>Fama, E. 1993.</p></body></html>".encode()


def test_a_well_formed_pdf_is_full_text():
    verdict = fulltext.classify(pdf(), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.PDF_FULLTEXT
    assert verdict.accepted is True


def test_a_truncated_pdf_is_corrupt_not_full_text():
    verdict = fulltext.classify(pdf(eof=False), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.CORRUPT_PDF
    assert verdict.accepted is False


def test_an_error_page_served_as_pdf_is_not_text():
    verdict = fulltext.classify(page(4), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.NOT_TEXT


def test_a_tiny_pdf_is_too_short():
    verdict = fulltext.classify(pdf(500), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.TOO_SHORT


def test_a_landing_page_is_rejected():
    body = page(40, extra="<p>Purchase PDF to read the full article.</p>")
    verdict = fulltext.classify(body, "text/html", "https://publisher.example/article")
    assert verdict.kind == fulltext.LANDING_PAGE_ONLY
    assert "purchase pdf" in verdict.reason


def test_a_long_article_is_accepted_despite_a_sign_in_link():
    body = cited(400)
    verdict = fulltext.classify(body, "text/html", "https://repo.example/article")
    assert verdict.kind == fulltext.HTML_FULLTEXT


def test_a_summary_page_without_a_reference_list_is_abstract_only():
    # Measured case: 4190-9243 chars of vendor research summary, no citations. A
    # length-only rule accepted these, which is what ABSTRACT_ONLY exists to stop.
    verdict = fulltext.classify(page(60), "text/html", "https://vendor.example/research/x")
    assert verdict.kind == fulltext.ABSTRACT_ONLY
    assert "no reference list" in verdict.reason


def test_a_short_summary_is_abstract_only_not_too_short():
    verdict = fulltext.classify(page(12), "text/html", "https://vendor.example/research/x")
    assert verdict.kind == fulltext.ABSTRACT_ONLY


def test_a_cited_document_below_the_fulltext_bar_is_accepted():
    verdict = fulltext.classify(cited(60), "text/html", "https://repo.example/a")
    assert verdict.kind == fulltext.HTML_FULLTEXT


def test_too_short_now_means_a_truncated_document_that_cites():
    verdict = fulltext.classify(cited(3), "text/html", "https://repo.example/a")
    assert verdict.kind == fulltext.TOO_SHORT
    assert "truncation" in verdict.reason


def test_script_and_style_do_not_count_as_text():
    noisy = b"<html><body><script>" + b"var x = 1;" * 2000 + b"</script><p>hi</p></body></html>"
    verdict = fulltext.classify(noisy, "text/html", "https://x.org/a")
    assert verdict.chars is not None and verdict.chars < 100
    assert verdict.accepted is False


def test_thresholds_are_reported_with_the_verdict():
    verdict = fulltext.classify(pdf(), "application/pdf", "https://x.org/a.pdf")
    row = verdict.as_row({"min_pdf_bytes": 10000})
    assert row["gate_version"] == fulltext.GATE_VERSION
    assert row["thresholds"]["min_pdf_bytes"] == 10000


# --- the gate's language and genre assumptions are declarable ------------------

def cited_in(language_heading: str, paragraphs: int = 120) -> bytes:
    body = "".join(f"<p>Paragrafo {i} mostra un effetto.</p>" for i in range(paragraphs))
    return f"<html><body>{body}<h2>{language_heading}</h2><p>Fama 1993.</p></body></html>".encode()


def test_the_default_reference_headings_are_english():
    verdict = fulltext.classify(cited_in("References"), "text/html", "https://x.org/a")
    assert verdict.kind == fulltext.HTML_FULLTEXT


def test_a_project_can_declare_its_own_reference_headings():
    # An Italian or German corpus must be expressible without editing this package: invariant 4
    # says the engine holds no domain knowledge, and "a bibliography is headed References" is
    # knowledge about a language and a genre.
    policy = {"reference_headings": ("bibliografia", "riferimenti")}
    assert fulltext.classify(cited_in("Bibliografia"), "text/html", "https://x.org/a",
                             policy=policy).kind == fulltext.HTML_FULLTEXT
    # And the English default no longer applies once the project has spoken.
    assert fulltext.classify(cited_in("References"), "text/html", "https://x.org/a",
                             policy=policy).kind == fulltext.ABSTRACT_ONLY


def test_a_project_can_declare_its_own_paywall_phrases():
    body = page(40, extra="<p>Acquista il PDF per leggere l'articolo completo.</p>")
    policy = {"paywall_phrases": ("acquista il pdf",)}
    verdict = fulltext.classify(body, "text/html", "https://p.example/a", policy=policy)
    assert verdict.kind == fulltext.LANDING_PAGE_ONLY
    assert "acquista il pdf" in verdict.reason


def test_a_genre_without_bibliographies_can_switch_the_signal_off():
    # A corpus of regulatory filings or API documentation has no reference lists. Requiring one
    # would reject every source in it.
    policy = {"structural_signal": "none"}
    short = fulltext.classify(page(60), "text/html", "https://reg.example/a", policy=policy)
    assert short.kind == fulltext.HTML_FULLTEXT
    assert "no structural signal is required" in short.reason


def test_switching_the_signal_off_still_rejects_what_is_merely_short():
    policy = {"structural_signal": "none"}
    verdict = fulltext.classify(page(2), "text/html", "https://reg.example/a", policy=policy)
    assert verdict.kind == fulltext.TOO_SHORT


def test_an_unknown_structural_signal_is_refused():
    with pytest.raises(ValueError, match="vibes"):
        fulltext.classify(page(60), "text/html", "https://x.org/a",
                          policy={"structural_signal": "vibes"})


def test_the_policy_in_force_is_recorded_with_the_verdict():
    # A rate computed under a different policy is not comparable to one computed under this, and
    # without recording it the difference is invisible — the rule the thresholds already follow.
    policy = {"structural_signal": "none"}
    row = fulltext.classify(page(60), "text/html", "https://x.org/a",
                            policy=policy).as_row({}, policy=policy)
    assert row["policy"]["structural_signal"] == "none"
