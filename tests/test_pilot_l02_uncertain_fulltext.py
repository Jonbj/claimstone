"""The five-case audit is bounded, resumable, and isolated from production ledgers."""
from types import SimpleNamespace

from claimstone import net
from tests.fakes import FakeFetcher, ok
from tools import pilot_l02_uncertain_fulltext as pilot


def test_oa_location_skips_resolver_and_forbidden_hosts():
    payload = {'oa_locations': [
        {'url': 'https://doi.org/10.1234/x'},
        {'url_for_pdf': 'https://sci-hub.se/x.pdf'},
        {'url_for_pdf': 'https://university.example/work.pdf', 'license': 'cc-by'},
    ]}
    url, entry = pilot._oa_location(payload, frozenset({'sci-hub.se'}))
    assert url == 'https://university.example/work.pdf' and entry['license'] == 'cc-by'


def test_bounded_audit_resumes_without_production_writes(tmp_path, monkeypatch):
    targets = [{'candidate_key': f'doi:10.1234/{n}',
                'route': 'cached_openalex_pdf' if n < 2 else 'unpaywall',
                'url': f'https://archive.example/{n}.pdf'} for n in range(5)]
    plan = {'campaign': 'five-work-test', 'max_metadata_requests': 3, 'max_copy_requests': 5}
    project = SimpleNamespace(name='fixture', excluded_hosts=())
    monkeypatch.setattr(pilot, 'prepare', lambda _: (plan, project, targets))
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'researcher@example.org')
    pdf = b'%PDF-1.4\n' + b'0' * 11000 + b'\n%%EOF'
    fake = FakeFetcher(pages={f'https://archive.example/{n}.pdf':
                              ok(f'https://archive.example/{n}.pdf', pdf)
                              for n in range(5)})
    for n in range(2, 5):
        fake.json_pages[f'https://api.unpaywall.org/v2/10.1234/{n}'] = {
            'oa_status': 'green', 'oa_locations': [
                {'url_for_pdf': f'https://archive.example/{n}.pdf', 'license': 'cc-by'}]}
    preview = pilot.run(tmp_path / 'plan.json', store_base=tmp_path)
    assert preview['pending'] == 5 and not (tmp_path / 'fixture').exists()
    result = pilot.run(tmp_path / 'plan.json', execute=True, fetcher=fake, store_base=tmp_path)
    assert result['attempted'] == 5 and result['pending'] == 0
    assert len(fake.calls) == 8  # three metadata responses, one copy per work
    assert pilot.run(tmp_path / 'plan.json', execute=True, fetcher=fake,
                     store_base=tmp_path)['pending'] == 0
    assert len(fake.calls) == 8
    store = tmp_path / 'fixture'
    assert len((store / pilot.LEDGER).read_text().splitlines()) == 5
    assert not (store / 'acquisitions.jsonl').exists()
    assert not (store / 'documents.jsonl').exists()
    assert not (store / 'candidates.jsonl').exists()
