"""D145: the open-web locator — policy, leads, host gating, identity on what was read."""
import pytest

from claimstone import net, normalize, web_locator
from claimstone.config import ConfigError
from claimstone.store import Store
from tests.test_normalize import FakeGrobid, PAPER, acquired
from tools import locate_web_copies as tool

POLICY = web_locator.validate_policy({
    "enabled": True, "allow_host_patterns": ["*.edu", "*.ac.uk"], "allow_hosts": ["repo.example.org"],
    "deny_hosts": ["scribd.com"], "max_results": 3})


def test_a_misspelt_or_malformed_policy_is_an_error_not_a_default():
    for bad in ({"enable": True}, {"allow_hosts": "x"}, {"max_results": 99}, {"provider": "bing"}, {"enabled": "yes"}, "x"):
        with pytest.raises(ConfigError):
            web_locator.validate_policy(bad)
    assert web_locator.validate_policy(None) == {}


def test_the_decision_order_is_excluded_then_denied_then_allowed_then_unclassified():
    d = lambda url: web_locator.decide(url, POLICY, ["shadow.example"])[0]
    assert d("https://shadow.example/x.pdf") == web_locator.DENIED_EXCLUDED
    assert d("https://www.scribd.com/doc/1") == web_locator.DENIED
    assert d("https://cs.mit.edu/papers/a.pdf") == web_locator.ALLOWED
    assert d("https://repo.example.org/a.pdf") == web_locator.ALLOWED
    assert d("https://someones-site.example/a.pdf") == web_locator.UNCLASSIFIED, "no author-site heuristic"
    assert d("ftp://cs.mit.edu/a.pdf") == web_locator.DENIED
    # an excluded host wins even when the allow list also names it
    both = web_locator.validate_policy({"allow_hosts": ["shadow.example"]})
    assert web_locator.decide("https://shadow.example/a", both, ["shadow.example"])[0] == web_locator.DENIED_EXCLUDED


def test_queries_need_a_real_title_and_the_second_is_the_bare_title():
    assert web_locator.queries_for({"title": "short"}) == []
    q = web_locator.queries_for({"title": "Exercise as a treatment for depression"})
    assert q == ['"Exercise as a treatment for depression" filetype:pdf', '"Exercise as a treatment for depression"']


def test_every_result_is_recorded_with_its_decision_and_only_the_window_is_offered(tmp_path):
    store = Store("p", base=tmp_path)
    payload = {"web": {"results": [{"url": f"https://u{i}.edu/a.pdf", "title": f"t{i}", "description": "d"} for i in range(5)]
                       + [{"url": "https://www.scribd.com/x", "title": "s"}]}}
    results = web_locator.parse_results(payload)
    row = web_locator.observation({"candidate_key": "doi:10.1/x", "title": "T"}, "q", results, POLICY, [],
                                  ok=True, failure_class=None, policy_source="project")
    store.append(web_locator.LEDGER, row)
    assert len(row["results"]) == 6 and row["allowed"] == 5 and row["policy_sha256"]
    leads = web_locator.leads(store, "doi:10.1/x")
    assert [l["rank"] for l in leads] == [1, 2, 3], "max_results=3 is the window; the rest stay in the ledger only"
    assert all(l["decision"] == web_locator.ALLOWED for l in leads)


def test_a_lead_is_fetched_only_from_a_host_the_plan_named(tmp_path):
    store = Store("p", base=tmp_path)
    results = web_locator.parse_results({"web": {"results": [
        {"url": "https://a.edu/x.pdf", "title": "t"}, {"url": "https://other.example/y.pdf", "title": "u"}]}})
    store.append(web_locator.LEDGER, web_locator.observation(
        {"candidate_key": "k"}, "q", results, POLICY, [], ok=True, failure_class=None, policy_source="project"))
    assert web_locator.fetch_locations(store, "k", None) == []
    assert web_locator.fetch_locations(store, "k", frozenset({"x.example"})) == []
    got = web_locator.fetch_locations(store, "k", frozenset({"a.edu", "other.example"}))
    assert [l.url for l in got] == ["https://a.edu/x.pdf"], "unclassified hosts are never fetched, even if a plan names them"
    assert got[0].provenance == "web_locator"


def test_identity_passes_a_matching_title_and_separates_wrong_from_unverified():
    ok = web_locator.identity_check("Exercise as a treatment for depression: a meta-analysis",
                                    "Exercise as a treatment for depression: A Meta-Analysis")
    assert ok["passed"] and ok["similarity"] >= web_locator.TITLE_SIMILARITY
    sub = web_locator.identity_check("Exercise as a treatment for depression", "Exercise as a treatment for depression: an update")
    assert sub["passed"], "a subtitle on one side only"
    wrong = web_locator.identity_check("Sleep hygiene in adolescents", "Exercise as a treatment for depression")
    assert not wrong["passed"] and wrong["failure_class"] == web_locator.WRONG_DOCUMENT
    blank = web_locator.identity_check("", "Exercise as a treatment for depression")
    assert not blank["passed"] and blank["failure_class"] == web_locator.IDENTITY_UNVERIFIED
    assert web_locator.identity_check("x", None)["failure_class"] == web_locator.IDENTITY_UNVERIFIED


def test_normalize_does_not_confirm_a_web_copy_of_another_work(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k:a", "title": "A completely different study about sleep"})
    row = acquired("a", store)
    row["provenance"] = "web_locator"
    store.append("acquisitions.jsonl", row)
    out = list(normalize.run(store, FakeGrobid()))
    assert out[0]["fulltext_confirmed"] is False
    assert out[0]["failure_class"] in (web_locator.WRONG_DOCUMENT, web_locator.IDENTITY_UNVERIFIED)
    assert out[0]["identity_check"]["passed"] is False and out[0]["chunks"] == 0


def test_a_catalogue_copy_is_not_subjected_to_the_web_identity_check(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k:a", "title": "Whatever"})
    store.append("acquisitions.jsonl", acquired("a", store))
    out = list(normalize.run(store, FakeGrobid()))
    assert out[0]["fulltext_confirmed"] is True and out[0]["identity_check"] is None


class Fetcher:
    def __init__(self, first_empty=False):
        self.urls, self.first_empty = [], first_empty

    def get_json(self, url):
        self.urls.append(url)
        empty = self.first_empty and "filetype" in url
        results = [] if empty else [{"url": "https://a.edu/p.pdf", "title": "T"}]
        return {"web": {"results": results}}, net.Outcome(url, True, 200)


class P:
    web_locator, web_locator_declared, excluded_hosts, name = POLICY, True, (), "p"


def test_the_tool_previews_runs_within_ceilings_and_asks_a_second_time_only_after_an_empty_first(tmp_path):
    store = Store("p", base=tmp_path)
    for i in range(2):
        store.append("candidates.jsonl", {"candidate_key": f"doi:10.1000/x{i}", "title": f"A long enough title number {i}"})
    store.append("candidates.jsonl", {"candidate_key": "doi:10.1000/held", "title": "Already obtained work here"})
    store.append("acquisitions.jsonl", {"candidate_key": "doi:10.1000/held", "acquired": True})
    preview = tool.run("p", store_base=tmp_path, project=P())
    assert preview["candidates_pending"] == 2 and preview["requests_min"] == 2 and preview["requests_max"] == 4
    fetcher = Fetcher(first_empty=True)
    done = tool.run("p", execute=True, store_base=tmp_path, project=P(), fetcher=fetcher)
    assert done["requests_made"] == 4 and all(u.startswith("https://api.search.brave.com/") for u in fetcher.urls)
    again = Fetcher()
    tool.run("p", execute=True, store_base=tmp_path, project=P(), fetcher=again)
    assert again.urls == [], "a candidate already located is not asked again"
    with pytest.raises(ValueError, match="exceed the approved"):
        store.append("candidates.jsonl", {"candidate_key": "doi:10.1000/new", "title": "Another long enough title"})
        tool.run("p", execute=True, store_base=tmp_path, project=P(), fetcher=Fetcher(), max_candidates=0)
    # nothing but the locator ledger and the request log was written
    assert len(list(store.read("candidates.jsonl"))) == 4
