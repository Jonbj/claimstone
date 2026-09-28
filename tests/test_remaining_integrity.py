"""Regressions for the remaining functional review findings, with offline transports."""
from types import SimpleNamespace

import pytest

from claimstone import (acquire, admissibility, chunk_sets, config, discover, discover_report,
                        extract, gate_audit, model_call, model_report, net, normalize, review)
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tests.fakes import FakeFetcher, ok
from tests.test_answer_authority import PROJECT, RECORD, corpus, respond

BODY = b'<html><body><p>First paragraph has evidence.</p><p>Second paragraph has evidence.</p></body></html>'
TH = {'confirm_chars': 1, 'min_section_chars': 0, 'merge_below': 0, 'max_chunk_chars': 30}


def parsed_store(tmp_path):
    store = Store('t', base=tmp_path)
    digest, path = store.store_bytes(BODY, '.html')
    store.append('acquisitions.jsonl', {'candidate_key': 's', 'source_id': 's', 'source_class': 'A',
        'acquired': True, 'sha256': digest, 'stored_path': str(path), 'content_type': 'text/html'})
    list(normalize.run(store, None, thresholds=TH))
    return store


def test_rechunking_publishes_exact_set_and_retains_immutable_history(tmp_path):
    store = parsed_store(tmp_path)
    old = chunk_sets.current(store)
    assert len(old) == 2
    list(normalize.run(store, None, thresholds=TH | {'max_chunk_chars': 9000}, force=True))
    new = chunk_sets.current(store)
    assert len(new) == 1 and old.keys().isdisjoint(new)
    assert len(list(store.read('chunks.jsonl'))) == 3
    assert store.latest_by('documents.jsonl', 'source_id')['s']['chunk_ids'] == list(new)
    rows = len(list(store.read('chunks.jsonl')))
    list(normalize.run(store, None, thresholds=TH | {'max_chunk_chars': 9000}, force=True))
    assert len(list(store.read('chunks.jsonl'))) == rows


def test_uncommitted_chunk_generation_is_not_visible(tmp_path):
    store = parsed_store(tmp_path)
    before = chunk_sets.current(store)
    store.append('chunks.jsonl', {'chunk_id': 's#uncommitted#c1', 'source_id': 's',
                                  'generation_sha256': 'uncommitted', 'text': 'never committed'})
    assert chunk_sets.current(store) == before


def test_legacy_chunk_ambiguity_refuses_to_guess_active_set(tmp_path):
    store = corpus(tmp_path)
    store.append('documents.jsonl', {'source_id': 'S1', 'fulltext_confirmed': True, 'chunks': 0})
    with pytest.raises(ValueError, match='normalize --force'):
        chunk_sets.current(store)


def test_changed_chunk_cannot_reuse_paid_answer_or_review(tmp_path):
    from claimstone import claim_records
    store = corpus(tmp_path)
    respond(store)
    extract.harvest(PROJECT, store, batch='e')
    assert len(claim_records.current(store)[0]) == 1
    # The quote is still present, but the whole passage changed. It is a different reading.
    store.append('chunks.jsonl', {'chunk_id': 'S1#1', 'source_id': 'S1',
                                  'text': RECORD['evidence_quote'] + ' Different context.'})
    assert claim_records.current(store)[0] == {}
    assert extract.harvest(PROJECT, store, batch='e')['accepted'] == 0


def test_identical_artifacts_for_two_sources_are_both_normalized(tmp_path):
    store = parsed_store(tmp_path)
    row = next(iter(store.read('acquisitions.jsonl')))
    store.append('acquisitions.jsonl', row | {'source_id': 's2', 'candidate_key': 's2'})
    rows = list(normalize.run(store, None, thresholds=TH))
    assert [r['source_id'] for r in rows] == ['s2']
    assert len(chunk_sets.current(store)) == 4


def test_full_review_contains_every_result_field_and_converted_values():
    claim = RECORD | {'estimate_as_written': '2%', 'estimate': .02, 'sample': 'participants',
                      'design': 'randomized', 'dependence': 'clustered', 'moderator': 'age',
                      'support_type': 'ENDORSEMENT', 'stance': 'CONTRADICTS'}
    prompt = review.review_unit(PROJECT.questions[0], claim, 'context')
    for key, value in claim.items():
        assert key in prompt and str(value) in prompt
    assert 'whole annotation' in review.SYSTEM


def test_old_reviews_cannot_attest_the_new_full_result_task(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    extract.harvest(PROJECT, store, batch='e')
    identifier = next(iter(store.latest_by('claims.jsonl', 'claim_id')))
    store.append('reviews.jsonl', {'claim_id': identifier, 'verdict': 'SUPPORTED'})
    assert not review.current(store)
    assert review.build(PROJECT, store, batch='full')['units'] == 1


def test_changed_annotation_digest_invalidates_a_full_review(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    extract.harvest(PROJECT, store, batch='e')
    review.build(PROJECT, store, batch='r')
    respond(store, lane='review', batch='r', model='reviewer',
            output={'verdict': 'SUPPORTED', 'reason': 'all fields supported'})
    review.harvest(PROJECT, store, batch='r')
    assert review.current(store)
    row = next(iter(store.latest_by('claims.jsonl', 'claim_id').values()))
    store.append('claims.jsonl', row | {'estimate': 999})
    assert not review.current(store)


def response(url, status=200, **headers):
    return SimpleNamespace(url=url, status_code=status, headers=headers,
                           content=b'body', text='body')


def fetcher(routes):
    held = net.Fetcher(pause_s=0, obey_robots=False)
    visited = []
    def get(url, **kwargs):
        assert kwargs['allow_redirects'] is False
        visited.append(url)
        return routes[url]
    held._session = SimpleNamespace(get=get)
    return held, visited


@pytest.mark.parametrize('guard', ['excluded', 'robots', 'budget'])
def test_every_redirect_destination_is_checked_before_transport(guard):
    start, target = 'https://a.example/start', 'https://b.example/end'
    f, visited = fetcher({start: response(start, 302, Location=target)})
    if guard == 'excluded':
        f.excluded_hosts = frozenset({'b.example'})
    elif guard == 'robots':
        f._robots_allows = lambda url: url != target
    else:
        f.budget_exhausted = lambda host: host == 'b.example'
    outcome = f.get(start)
    assert not outcome.ok and visited == [start]
    assert outcome.url == target and outcome.request_url == start


def test_relative_redirect_records_final_location_and_chain():
    start, target = 'https://a.example/start', 'https://a.example/end'
    f, visited = fetcher({start: response(start, 302, Location='/end'), target: response(target)})
    outcome = f.get(start)
    assert outcome.ok and outcome.url == target
    assert visited == outcome.redirect_chain == [start, target]


@pytest.mark.parametrize('location', ['/start', 'file:///etc/passwd', None])
def test_redirect_loop_non_http_or_missing_destination_is_refused(location):
    start = 'https://a.example/start'
    headers = {'Location': location} if location else {}
    f, visited = fetcher({start: response(start, 302, **headers)})
    assert f.get(start).failure_class == net.REDIRECT
    assert visited == [start]


def test_robots_redirect_cannot_request_an_excluded_host():
    start, target = 'https://a.example/robots.txt', 'https://excluded.example/rules'
    f, visited = fetcher({start: response(start, 302, Location=target)})
    f.excluded_hosts = frozenset({'excluded.example'})
    assert f._load_robots('https://a.example/document', 'a.example') is None
    assert visited == [start]
    assert net.EXCLUDED in f.robots_notes['a.example']


def test_redirect_and_robots_requests_are_recorded_separately(tmp_path):
    start, target = 'https://a.example/start', 'https://b.example/end'
    f, visited = fetcher({start: response(start, 302, Location=target), target: response(target)})
    store = Store('t', base=tmp_path)
    RecordingFetcher(f, store, purpose='probe').get(start)
    rows = list(store.read('requests.jsonl'))
    assert [r['event'] for r in rows] == ['redirect', 'transport', 'response']
    assert rows[-1]['request_url'] == start and rows[-1]['url'] == target
    assert rows[-1]['raw_sha256']


@pytest.mark.parametrize('payload,success,failure', [({'results': []}, True, None),
    ({}, False, 'INVALID_SEARCH_RESPONSE'), ({'results': 'wrong'}, False, 'INVALID_SEARCH_RESPONSE'),
    (None, False, net.NOT_FOUND)])
def test_empty_failed_and_malformed_searches_have_distinct_records(tmp_path, payload, success, failure):
    project = SimpleNamespace(topics=(config.Topic('T', 'topic', ('term',)),), classes=())
    pages = {'https://api.openalex.org/works?': payload} if payload is not None else {}
    store = Store('t', base=tmp_path)
    result = discover.run(project, store, FakeFetcher(json_pages=pages), apis=('openalex',), round_name='r')
    query = next(iter(store.read('queries.jsonl')))
    assert query['ok'] == success and query['failure_class'] == failure
    assert result['final'] == success
    assert list(store.read('requests.jsonl'))
    assert discover_report.summarise(store)['search']['failed'] == int(not success)


def test_failed_search_blocks_round_completion_but_not_a_curated_manifest(tmp_path):
    store = corpus(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 's', 'source_id': 'S1', 'source_class': 'A', 'round': 'r'})
    store.append('acquisitions.jsonl', {'candidate_key': 's', 'source_id': 'S1', 'acquired': True})
    store.append('queries.jsonl', {'query_id': 'q', 'round': 'r', 'ok': False})
    assert 'awaiting_discovery' in admissibility.rate(store, round_name='r')['blocking']
    assert 'awaiting_discovery' not in admissibility.rate(store, manifest_only=True)['blocking']


def test_acquisition_resolver_requests_are_recorded_even_without_a_location(tmp_path):
    store = Store('t', base=tmp_path)
    acquire.acquire_one(FakeFetcher(), store, {'candidate_key': 'doi:x', 'doi': '10.1234/x',
        'source_class': 'A', 'url': '', 'title': 'A sufficiently long scholarly title'})
    rows = list(store.read('requests.jsonl'))
    assert rows and all(row['purpose'] == 'acquisition' for row in rows)
    assert any('api.unpaywall.org' in row['url'] for row in rows)


def test_sweep_uses_found_population_project_thresholds_and_class_policy(tmp_path):
    from tests.test_fulltext import page
    store = Store('t', base=tmp_path)
    _, path = store.store_bytes(page(60), '.html')
    for key in ('s', 'unattempted'):
        store.append('candidates.jsonl', {'candidate_key': key, 'source_id': key, 'source_class': 'A', 'round': 'r'})
    store.append('candidates.jsonl', {'candidate_key': 'outside', 'source_class': 'A', 'round': 'other'})
    store.append('acquisitions.jsonl', {'candidate_key': 's', 'source_class': 'A', 'stored_path': str(path),
        'content_type': 'text/html', 'url': 'https://example.org', 'acquired': True})
    classes = (config.SourceClass('A', 'guidance', 'declared', gate_policy={'structural_signal': 'none'}),)
    point = gate_audit.sweep(store, 'min_text_chars', [100], thresholds={'fulltext_chars': 999999},
                             classes=classes, round_name='r')[0]
    assert point['found'] == 2 and point['attempted'] == 1
    assert point['accepted'] == 1 and point['rate'] == .5
    assert point['thresholds']['fulltext_chars'] == 999999 and point['basis'] == 'obtained'
    assert list(gate_audit.regate(store, campaign='offline', classes=classes))[0]['acquired']


def test_confirmations_set_the_same_basis_for_every_class(tmp_path):
    store = corpus(tmp_path)
    for source, confirmed in [('a', True), ('b', False)]:
        store.append('candidates.jsonl', {'candidate_key': source, 'source_class': 'A'})
        store.append('acquisitions.jsonl', {'candidate_key': source, 'source_id': source, 'acquired': True})
        store.append('documents.jsonl', {'source_id': source, 'fulltext_confirmed': confirmed})
    bucket = admissibility.rate(store)['by_class']['A']
    assert bucket['obtained_rate'] == 1 and bucket['confirmed_rate'] == .5
    assert bucket['basis'] == 'confirmed' and bucket['rate'] == .5


def test_model_report_totals_include_every_reader_and_exclude_rejudge_cost(tmp_path):
    store = corpus(tmp_path)
    for model in ('m1', 'm2'):
        row = respond(store, model=model, cost_usd=.1)
        queue = model_call.Queue(store, lane='extract', batch='e')
        store.append(queue.results_name, row | {'ok': False, 'output': None, 'rejudged_from': '', 'cost_usd': None})
    report = model_report.summarise(store, lane='extract', batch='e')
    assert report['calls'] == sum(r['calls'] for r in report['by_reader'].values()) == 2
    assert report['calls'] == sum(r['calls'] for r in report['by_backend'].values())
    assert report['attempts'] == 2 and report['by_backend']['fake']['cost_usd'] == .2


def test_chunk_manifest_refuses_tampered_text(tmp_path):
    store = parsed_store(tmp_path)
    row = next(iter(chunk_sets.current(store).values()))
    store.append('chunks.jsonl', row | {'text': 'changed after normalization'})
    with pytest.raises(ValueError, match='text hash mismatch'):
        chunk_sets.current(store)


def test_rejudge_does_not_increment_the_next_physical_attempt(tmp_path):
    from tests.fakes import FakeRunner
    from claimstone.runners.base import RawAnswer
    from tests.test_model_call import unit
    store = Store('t', base=tmp_path)
    queue = model_call.Queue(store, lane='extract', batch='e')
    queue.write([unit()])
    runner = FakeRunner(default=RawAnswer(body=b'[]', model='reported-model'))
    first = list(model_call.drain(queue, runner))[0]
    strict = {'type': 'array', 'minItems': 1}
    assert list(model_call.rejudge(queue, response_schema=strict))
    retried = list(model_call.drain(queue, runner, retry_classes=('SCHEMA_INVALID',)))[0]
    assert first['attempt_no'] == 1 and retried['attempt_no'] == 2


def test_robots_refusal_can_spend_the_last_budget_before_the_document():
    robots = 'https://a.example/robots.txt'
    f, visited = fetcher({robots: response(robots, 403)})
    f.obey_robots = True
    f.max_403_per_host = 1
    assert f.get('https://a.example/document').failure_class == net.BUDGET
    assert visited == [robots]


def test_robots_cache_and_request_follow_the_exact_origin():
    first, second = 'https://a.example/document', 'https://a.example:8443/document'
    routes = {first: response(first), second: response(second)}
    for origin in ('https://a.example', 'https://a.example:8443'):
        rules = response(origin + '/robots.txt', **{'Content-Type': 'text/plain'})
        rules.content = b'User-agent: *\nDisallow: /document' if ':8443' in origin else b'User-agent: *\nDisallow:'
        routes[rules.url] = rules
    f, visited = fetcher(routes)
    f.obey_robots = True
    assert f.get(first).ok
    assert f.get(second).failure_class == net.ROBOTS
    assert second not in visited and 'https://a.example:8443/robots.txt' in visited


def test_malformed_nested_crossref_response_records_a_failed_query(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    project = SimpleNamespace(topics=(config.Topic('T', 'topic', ('term',)),), classes=())
    store = Store('t', base=tmp_path)
    f = FakeFetcher(json_pages={'https://api.crossref.org/works?': {
        'message': {'items': [{'title': ['title'], 'issued': {'date-parts': {'malformed': []}}}]}}})
    result = discover.run(project, store, f, apis=('crossref',))
    assert not result['final']
    assert next(iter(store.read('queries.jsonl')))['failure_class'] == 'INVALID_SEARCH_RESPONSE'
    assert not list(store.read('candidates.jsonl'))


def test_discovery_cli_reports_failed_queries_and_returns_failure(tmp_path, monkeypatch, capsys):
    from claimstone import cli
    project = SimpleNamespace(topics=(config.Topic('T', 'topic', ('term',)),), classes=(), excluded_hosts=())
    store = Store('t', base=tmp_path)
    monkeypatch.setattr(cli, 'load_project', lambda path: project)
    monkeypatch.setattr(cli, '_checked_store', lambda args, project: store)
    monkeypatch.setattr(net, 'contact_email', lambda: 'test@example.org')
    monkeypatch.setattr(net, 'Fetcher', lambda **kwargs: FakeFetcher())
    args = cli.build_parser().parse_args(['discover', 'project', '--api', 'openalex', '--round', 'r'])
    assert args.func(args) == 3
    assert 'incomplete search' in capsys.readouterr().out
