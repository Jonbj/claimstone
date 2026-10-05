import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from claimstone import net, resolve
from tests.fakes import FakeFetcher, fail, ok
from tests.test_jats import ARTICLE
from tools import pilot_europe_pmc_jats as pilot


def test_frozen_preview_and_host_refusal_stop_without_production_writes(tmp_path, monkeypatch):
    project_root = tmp_path / 'project'
    project_root.mkdir()
    rows = [f'PMC00{i}\tACA\thtml\thttps://pmc.ncbi.nlm.nih.gov/articles/PMC{i}/\tStudy {i}'
            for i in range(1, 4)]
    manifest = ('source_id\tclass\tformat\turl\ttitle\n' + '\n'.join(rows) + '\n').encode()
    (project_root / 'manifest.tsv').write_bytes(manifest)
    (project_root / 'sources.yaml').write_text('source_classes: []\n')
    plan = {'project': str(project_root), 'manifest_sha256': hashlib.sha256(manifest).hexdigest(),
            'sources_sha256': hashlib.sha256((project_root / 'sources.yaml').read_bytes()).hexdigest(),
            'max_articles': 3, 'source_ids': ['PMC001', 'PMC002', 'PMC003'],
            'campaign': 'bounded-jats-test'}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(pilot, 'load_project', lambda _: SimpleNamespace(
        root=project_root, name='fixture', excluded_hosts=(), gate_policy={},
        gate_thresholds={}, classes=()))
    store_base = tmp_path / 'store'
    preview = pilot.run(plan_path, store_base=store_base)
    assert preview['pending'] == 3
    assert not store_base.exists()

    first = resolve.europe_pmc_route('https://pmc.ncbi.nlm.nih.gov/articles/PMC1/')
    second = resolve.europe_pmc_route('https://pmc.ncbi.nlm.nih.gov/articles/PMC2/')
    article = ARTICLE.replace(b'Opening without a heading.', b'Opening evidence. ' * 300)
    fake = FakeFetcher(pages={first: ok(first, article, 'application/xml'),
                              second: fail(second, 403, net.PAYWALL)})
    result = pilot.run(plan_path, execute=True, fetcher=fake, store_base=store_base)
    assert result['attempted'] == 2 and result['pending'] == 1
    assert result['stopped_on_host_refusal'] == 'PMC002'
    outcomes = [json.loads(line) for line in
                (store_base / 'fixture/audits/europe-pmc/jats-pilot-v1/outcomes.jsonl').read_text().splitlines()]
    assert outcomes[0]['parse_status'] == 'PARSED'
    assert outcomes[1]['http_status'] == 403
    assert not (store_base / 'fixture/acquisitions.jsonl').exists()
    assert not (store_base / 'fixture/documents.jsonl').exists()
    with pytest.raises(ValueError, match='prior host refusal'):
        pilot.run(plan_path, execute=True, fetcher=fake, store_base=store_base)

    (project_root / 'sources.yaml').write_text('changed: true\n')
    with pytest.raises(ValueError, match='source policy changed'):
        pilot.run(plan_path, store_base=store_base)
