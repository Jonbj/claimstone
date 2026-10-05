import json
from pathlib import Path
import pytest
from claimstone import model_call
from claimstone.runners.base import RawAnswer
from tools import run_source_screening as screen


@pytest.fixture
def plan_file(tmp_path):
    cases = [{'candidate_key':'case:a','title':'Trial report','source_text':'A trial tested outcomes after three months.', 'screening_level':'abstract'},
             {'candidate_key':'case:b','title':'Missing follow-up','source_text':'The follow-up duration is unspecified.', 'screening_level':'abstract'}]
    source = tmp_path/'input';source.mkdir()
    data = {'cases.json':cases,'reference.json':{'case:a':'INCLUDE','case:b':'UNCERTAIN'},
            'prior.json':{'budget_usd':10.,'priced_usd_at_plan_rates':.3,
                'unknown_attempt_reservation_usd':.4,'budget_accounted_usd':.7}}
    for n,d in data.items():(source/n).write_text(json.dumps(d))
    plan = {'screening_version':1,'registry_version':1,'question_text':'Outcome at three months',
        'criteria':{'H':{'dimension':'horizon','description':'three-month outcomes'}},
        'cases_path':str(source/'cases.json'),'reference_path':str(source/'reference.json'),
        'prior_budget_audit':str(source/'prior.json'),'budget_usd':10.,
        'experiment_base':str(tmp_path/'experiment'),'experiment_name':'pilot',
        'protected_roots':[str(source)],'batch':'screen-v1','max_output_tokens':900,
        'readers':[{'model':name,'price_in':1.,'price_out':2.,'context_tokens':32768,'think':False} for name in ['reader-a','reader-b']],
        'frozen_inputs':[{'path':str(source/n),'sha256':screen.digest(source/n)} for n in data]}
    f=tmp_path/'plan.json';f.write_text(json.dumps(plan));return f


def rewrite(path, fn):
    p=json.loads(path.read_text());fn(p);path.write_text(json.dumps(p))


def fake_runner(monkeypatch, *, bad_quote=False, unknown=False):
    class Runner:
        name='ollama-cloud';max_concurrency=1;min_interval_s=0.
        calls=0
        def __init__(self, **kw):self.model=kw['model']
        def harness_version(self):return 'test-screen-runner'
        def run(self, unit):
            Runner.calls+=1;body=json.loads(unit['user']);text=body['source_text'];uncertain=body['candidate_key']=='case:b'
            output={'decision':'UNCERTAIN' if uncertain else 'INCLUDE','criterion_ids':['H'],
                'reason':'Duration checked in supplied text','evidence_quote':'invented' if bad_quote else text,
                'missing_information':'Follow-up unspecified' if uncertain else ''}
            return RawAnswer(body=json.dumps(output).encode(),model=self.model,
                prompt_sent=model_call.rendered_prompt(unit['system'],unit['user']),
                usage={} if unknown else {'input_tokens':100,'output_tokens':80},
                cost_usd=None if unknown else .00026)
    monkeypatch.setattr(screen.bounded,'OllamaCloudRunner',Runner)
    monkeypatch.setenv('OLLAMA_API_KEY','test-credential');monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL','tests@example.org')
    return Runner


def test_offline_preview_no_writes_and_no_reference_leak(plan_file):
    before=set(plan_file.parent.rglob('*'));r=screen.run(plan_file)
    assert r['status']=='PREVIEW' and r['budget_accounted_usd']==.7
    assert set(plan_file.parent.rglob('*'))==before
    p,_,cases,_,_,units,_=screen.load(plan_file)
    for u,c in zip(units,cases):
        body=json.loads(u['user']);assert set(body)=={'candidate_key','title','source_text','screening_level','source_class','question','criteria'}
        assert body['source_text']==c['source_text']


def test_two_readers_resume_and_preserve_inputs(plan_file,monkeypatch):
    runner=fake_runner(monkeypatch);before={p:p.read_bytes() for p in (plan_file.parent/'input').iterdir()}
    r=screen.run(plan_file,execute=True)
    assert r['status']=='SCREENING_PILOT_COMPLETE' and runner.calls==4
    assert all(v['development_reference_agreement']==2 for v in r['readers'].values())
    assert r['budget_accounted_usd']>.7 and not r['automatic_adoption']
    r=screen.run(plan_file,execute=True);assert runner.calls==4
    assert all(p.read_bytes()==body for p,body in before.items())
    assert r['production_ledger_rows_written']==0


def test_missing_text_blocks_spending(plan_file,monkeypatch):
    p=json.loads(plan_file.read_text());f=Path(p['cases_path']);cases=json.loads(f.read_text());cases[0]['source_text']='';f.write_text(json.dumps(cases))
    rewrite(plan_file,lambda p:p['frozen_inputs'][0].update(sha256=screen.digest(f)))
    runner=fake_runner(monkeypatch);r=screen.run(plan_file,execute=True)
    assert r['status']=='BLOCKED_MISSING_TEXT' and runner.calls==0


def test_quote_failure_is_pending_not_eligibility(plan_file,monkeypatch):
    runner=fake_runner(monkeypatch,bad_quote=True);r=screen.run(plan_file,execute=True)
    assert r['status']=='AWAITING_VALID_SCREENING' and runner.calls==4
    assert all(v['invalid_evidence']==2 and v['answered']==0 for v in r['readers'].values())
    screen.run(plan_file,execute=True);assert runner.calls==4


def test_unknown_attempt_cost_retains_full_reservation(plan_file,monkeypatch):
    runner=fake_runner(monkeypatch,unknown=True);r=screen.run(plan_file,execute=True)
    assert r['status']=='STOPPED' and runner.calls==1
    assert r['unknown_attempt_reservation_usd']>.4
    assert r['new_run_accounting']['priced_usd_at_plan_rates']==0


def test_insufficient_remaining_budget_stops_before_contact(plan_file,monkeypatch):
    p=json.loads(plan_file.read_text());f=Path(p['prior_budget_audit']);a=json.loads(f.read_text());a.update(priced_usd_at_plan_rates=9.59,budget_accounted_usd=9.99);f.write_text(json.dumps(a))
    rewrite(plan_file,lambda p:p['frozen_inputs'][2].update(sha256=screen.digest(f)))
    runner=fake_runner(monkeypatch);r=screen.run(plan_file,execute=True)
    assert r['status']=='STOPPED' and runner.calls==0


def test_changed_inputs_rejected(plan_file):
    p=json.loads(plan_file.read_text());Path(p['cases_path']).write_text('[]')
    with pytest.raises(ValueError,match='frozen input changed'):screen.run(plan_file)


def test_nonisolated_store_rejected(plan_file):
    rewrite(plan_file,lambda p:p.update(experiment_base=str(plan_file.parent/'input')))
    with pytest.raises(ValueError,match='must not overlap'):screen.run(plan_file)


def test_changed_request_body_rejected(plan_file):
    screen.run(plan_file,prepare=True);_,_,_,_,q,_,_=screen.load(plan_file)
    row=q.requests()[0];row['user']='tampered';q.store.append(q.requests_name,row)
    with pytest.raises(ValueError,match='request content changed'):screen.run(plan_file)


def test_overlarge_input_rejected_before_contact(plan_file):
    rewrite(plan_file,lambda p:p['readers'][0].update(context_tokens=100))
    with pytest.raises(ValueError,match='context bound'):screen.run(plan_file)


def test_undeclared_criteria_and_empty_uncertainty_rejected():
    c={'source_text':'known text'};o={'decision':'UNCERTAIN','criterion_ids':['X'],'reason':'why','evidence_quote':'','missing_information':''}
    assert screen.inspect_answer(o,c,{'H':{}})=='MISSING_REASON_OR_CRITERION'
    o['criterion_ids']=['H'];assert screen.inspect_answer(o,c,{'H':{}})=='MISSING_UNCERTAINTY_REASON'


def test_historical_budget_cannot_reset(plan_file):
    rewrite(plan_file,lambda p:p.update(budget_usd=20.))
    with pytest.raises(ValueError,match='retain original'):screen.run(plan_file)


def test_v2_requires_separate_exact_exposure_and_horizon_evidence(plan_file):
    rewrite(plan_file, lambda p: p.update(screening_version=2, criteria={
        'E': {'dimension': 'exposure', 'description': 'text-derived signal'},
        'H': {'dimension': 'horizon', 'description': 'future outcome at three months'},
    }))
    plan, _, cases, _, _, units, _ = screen.load(plan_file)
    assert plan['screening_version'] == 2
    assert units[0]['screening_version'] == 2
    assert {'exposure_quote', 'horizon_quote'} <= set(units[0]['response_schema']['required'])
    case = {'source_text': 'Text sentiment predicts returns after three months.'}
    answer = {'decision': 'INCLUDE', 'criterion_ids': ['E', 'H'], 'reason': 'test',
              'evidence_quote': case['source_text'], 'exposure_quote': 'Text sentiment',
              'horizon_quote': 'after three months', 'missing_information': ''}
    assert screen.inspect_answer(answer, case, plan['criteria'], 2) is None
    answer['exposure_quote'] = 'News appeared'
    assert screen.inspect_answer(answer, case, plan['criteria'], 2) == 'UNVERIFIED_EXPOSURE_QUOTE'
    answer['exposure_quote'] = ''
    assert screen.inspect_answer(answer, case, plan['criteria'], 2) == 'MISSING_EXPOSURE_EVIDENCE'
    answer['exposure_quote'] = 'Text sentiment'
    answer['horizon_quote'] = ''
    assert screen.inspect_answer(answer, case, plan['criteria'], 2) == 'MISSING_HORIZON_EVIDENCE'


def test_v1_requests_keep_original_instrument(plan_file):
    plan, _, cases, _, _, units, _ = screen.load(plan_file)
    assert plan['screening_version'] == 1
    assert units[0]['screening_version'] == 1
    assert 'exposure_quote' not in units[0]['response_schema']['properties']


def test_v3_format_instruction_and_v2_replay_remain_distinct(plan_file):
    rewrite(plan_file, lambda p: p.update(screening_version=3))
    _, _, _, _, _, v3, _ = screen.load(plan_file)
    assert 'omit empty-string fields' in v3[0]['system']
    assert v3[0]['screening_version'] == 3
    assert 'exposure_quote' in v3[0]['response_schema']['required']
    rewrite(plan_file, lambda p: p.update(screening_version=2))
    _, _, _, _, _, v2, _ = screen.load(plan_file)
    assert v2[0]['screening_version'] == 2
    assert v3[0]['call_id'] != v2[0]['call_id']


def test_v2_malformed_uncertain_does_not_stop_other_reader_or_retry(plan_file, monkeypatch):
    rewrite(plan_file, lambda p: p.update(screening_version=2, criteria={
        'E': {'dimension': 'exposure', 'description': 'text-derived signal'},
        'H': {'dimension': 'horizon', 'description': 'future outcome at three months'},
    }))
    class Runner:
        name = 'ollama-cloud'; max_concurrency = 1; min_interval_s = 0.
        calls = []
        def __init__(self, **kw): self.model = kw['model']
        def harness_version(self): return 'test-screen-runner'
        def run(self, unit):
            body = json.loads(unit['user']); Runner.calls.append((self.model, body['candidate_key']))
            result = {'decision': 'INCLUDE', 'criterion_ids': ['E', 'H'],
                      'reason': 'Test', 'evidence_quote': body['source_text'],
                      'exposure_quote': body['source_text'],
                      'horizon_quote': body['source_text'], 'missing_information': ''}
            if body['candidate_key'] == 'case:b':
                result = {'decision': 'UNCERTAIN', 'criterion_ids': ['H'], 'reason': 'Missing follow-up',
                          'evidence_quote': body['source_text'], 'missing_information': 'Duration unspecified'}
            return RawAnswer(body=json.dumps(result).encode(), model=self.model,
                prompt_sent=model_call.rendered_prompt(unit['system'], unit['user']),
                usage={'input_tokens': 100, 'output_tokens': 80}, cost_usd=.00026)
    monkeypatch.setattr(screen.bounded, 'OllamaCloudRunner', Runner)
    monkeypatch.setenv('OLLAMA_API_KEY', 'test-credential')
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'tests@example.org')
    result = screen.run(plan_file, execute=True)
    assert result['status'] == 'AWAITING_VALID_SCREENING'
    assert Runner.calls == [('reader-a', 'case:a'), ('reader-a', 'case:b'),
                            ('reader-b', 'case:a'), ('reader-b', 'case:b')]
    assert all(r['answered'] == 1 and r['unanswered'] == 1
               for r in result['readers'].values())
    screen.run(plan_file, execute=True)
    assert len(Runner.calls) == 4
