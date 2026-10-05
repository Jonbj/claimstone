from dataclasses import replace

from claimstone.config import Topic
from tests.test_synthesize import _project
from tools import resume_research_search as run


def test_completed_capped_queries_are_not_repeated(monkeypatch):
    monkeypatch.setattr(run.audit, 'build', lambda *args: {'queries': [
        {'status': 'COMPLETED', 'result_cap_reached': True},
        {'status': 'FAILED'}, {'status': 'NOT_RUN'}, {'status': 'SHALLOWER_THAN_PLANNED'}]})
    assert [q['status'] for q in run.pending(None, None, None)] == [
        'FAILED', 'NOT_RUN', 'SHALLOWER_THAN_PLANNED']


def test_resume_preserves_scope_and_stops_on_first_provider_failure(tmp_path, monkeypatch):
    project = replace(_project(tmp_path), topics=(Topic(id='T1', label='Topic', terms=('a', 'b')),))
    queries = [{'topic_id': 'T1', 'query': q, 'source_api': 'openalex', 'per_query': 25}
               for q in ['a', 'b']]
    seen = []
    def discover(scoped, store, fetcher, **kwargs):
        seen.append((scoped.topics, kwargs, fetcher))
        assert scoped.population == project.population
        assert scoped.questions == project.questions
        return {'final': False}
    (tmp_path/'sources.yaml').write_text('{}')
    monkeypatch.setattr(run.discover, 'run', discover)
    fetcher = object()
    assert run.resume(project, None, {'search_round': 'dated'}, queries, fetcher) == [{'final': False}]
    assert len(seen) == 1
    assert seen[0][0][0].terms == ('a',)
    assert seen[0][1] == {'apis': ('openalex',), 'per_query': 25, 'round_name': 'dated'}
    assert seen[0][2] is fetcher
