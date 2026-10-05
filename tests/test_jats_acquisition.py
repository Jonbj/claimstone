"""The XML route must not turn an API response into an acquired article."""

from claimstone import acquire, fulltext, net, resolve
from claimstone.store import Store
from tests.fakes import FakeFetcher, fail, ok
from tests.test_fulltext import cited
from tests.test_jats import ARTICLE


PMC = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7196181/'
XML = 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7196181/fullTextXML'


def candidate():
    return {'candidate_key': 'doi:10.1234/example', 'source_class': 'ACA',
            'doi': None, 'title': 'A synthetic study', 'url': PMC}


def test_xml_route_is_before_html_and_retains_article_licence(tmp_path):
    assert resolve.europe_pmc_route('https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7196181') == XML
    assert resolve.europe_pmc_route('https://elsewhere.example/PMC7196181') is None
    locations, _ = resolve.plan(FakeFetcher(), candidate(), use_apis=False)
    assert [loc.url for loc in locations] == [XML, PMC]
    article = ARTICLE.replace(b'<abstract>',
        b'<permissions><license xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'xlink:href="https://creativecommons.org/licenses/by/4.0/"/></permissions><abstract>')
    fetcher = FakeFetcher(pages={XML: ok(XML, article, 'application/xml')})
    row = acquire.acquire_one(fetcher, Store('t', base=tmp_path), candidate(), use_apis=False,
                              thresholds={'min_text_chars': 100, 'fulltext_chars': 100})
    assert row['acquired'] and row['gate']['kind'] == fulltext.JATS_FULLTEXT
    assert row['provenance'] == 'europe-pmc'
    assert row['licence'] == 'https://creativecommons.org/licenses/by/4.0/'
    assert row['stored_path'].endswith('.xml')


def test_missing_or_invalid_xml_falls_through_to_confirmable_html(tmp_path):
    html = cited(100)
    fetcher = FakeFetcher(pages={XML: fail(XML, 404, net.NOT_FOUND),
                                 PMC: ok(PMC, html, 'text/html')})
    row = acquire.acquire_one(fetcher, Store('t', base=tmp_path), candidate(), use_apis=False)
    assert row['acquired'] and row['gate']['kind'] == fulltext.HTML_FULLTEXT
    assert [a['http_status'] for a in row['attempts']] == [404, 200]

    bad = b'<response>' + b'not an article ' * 400 + b'</response>'
    verdict = fulltext.classify(bad, 'application/xml', XML)
    assert verdict.kind == fulltext.NOT_TEXT and not verdict.accepted
    unsupported = ARTICLE.replace(b'<table>', b'<table><tgroup/>')
    assert fulltext.classify(unsupported, 'application/xml', XML,
        {'min_text_chars': 100, 'fulltext_chars': 100}).accepted

    nested_only = (b'<article><front><article-meta/></front><body><p>short</p>'
                   b'<sub-article><body><p>' + b'other work ' * 400 +
                   b'</p></body></sub-article></body></article>')
    assert fulltext.classify(nested_only, 'application/xml', XML).kind == fulltext.TOO_SHORT


def test_body_bibliography_counts_for_gate_and_nested_licence_url(tmp_path):
    payload = (b'<article xmlns:xlink="http://www.w3.org/1999/xlink">'
               b'<front><article-meta><permissions><license><license-p>'
               b'<ext-link xlink:href="https://creativecommons.org/licenses/by/4.0/"/>'
               b'</license-p></license></permissions></article-meta></front>'
               b'<body><p>' + b'evidence ' * 500 + b'</p><ref-list>'
               b'<ref><mixed-citation>Reference</mixed-citation></ref></ref-list>'
               b'<sub-article><ref-list><ref><mixed-citation>Other</mixed-citation>'
               b'</ref></ref-list></sub-article></body></article>')
    verdict = fulltext.classify(payload, 'application/xml', XML)
    assert verdict.kind == fulltext.JATS_FULLTEXT
    assert acquire._jats_licence(payload) == 'https://creativecommons.org/licenses/by/4.0/'
    nested_only = payload.replace(b'<ref-list><ref><mixed-citation>Reference</mixed-citation></ref></ref-list>', b'')
    assert fulltext.classify(nested_only, 'application/xml', XML).kind == fulltext.ABSTRACT_ONLY
    subarticle_licence = (b'<article><front><article-meta/></front><body><p>Text</p></body>'
                          b'<sub-article><front><article-meta><license license-type="cc-by"/>'
                          b'</article-meta></front></sub-article></article>')
    assert acquire._jats_licence(subarticle_licence) is None
