"""Offline engineering fixtures only; no synthetic data is a production model."""
import copy
import importlib
import importlib.util
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

FEATURES = ['age_days','log_amount','prior_late_fraction','prior_mean_delay_days','broken_promises']


def module():
    assert importlib.util.find_spec('server.payment_model') is not None, 'Offline payment model foundation is missing'
    return importlib.import_module('server.payment_model')


def fixture_lines(count=360):
    start = datetime(2024,1,1,tzinfo=timezone.utc)
    manifest = dict(record_type='manifest',schema_version=1,dataset_kind='authorized_invoice_snapshots_v1',
        tenant_id='fixture-tenant',dataset_cutoff='2025-02-01T00:00:00+00:00',provenance='synthetic_fixture',
        authorization_ref='engineering-test-only',feature_order=FEATURES,history_window_days=365,label_horizon_days=30,label_threshold=0.9)
    rows=[]
    for index in range(count):
        as_of=start+timedelta(days=index)
        age=(index%10-5)*4
        rows.append(dict(record_type='snapshot',tenant_id='fixture-tenant',invoice_id='private-invoice-'+str(index),
            as_of=as_of.isoformat(),feature_observed_at=as_of.isoformat(),
            features=[age,math.log1p(100000+index*100),float(index%3)/2,10.0,index%2],
            net_fraction_paid_30d=1.0 if age>=0 else 0.5,label_observed_at=(as_of+timedelta(days=30)).isoformat()))
    return [manifest,*rows]


def save(tmp_path,lines):
    path=tmp_path/'dataset.jsonl'
    path.write_text('\n'.join(json.dumps(line,ensure_ascii=False,allow_nan=True) for line in lines)+'\n',encoding='utf-8')
    return path


def test_dataset_rejects_future_features_labels_and_unmatured_targets(tmp_path):
    p=module()
    for change in [dict(feature_observed_at='2024-01-02T00:00:00Z'),
                   dict(label_observed_at='2024-01-30T00:00:00Z'),
                   dict(label_observed_at='2026-01-01T00:00:00Z')]:
        lines=fixture_lines();lines[1].update(change)
        with pytest.raises(p.ContractError):p.read_dataset(save(tmp_path,lines))


def test_dataset_rejects_wrong_kind_provenance_and_feature_order(tmp_path):
    p=module()
    for change in [dict(dataset_kind='generic_credit_csv'),dict(provenance='downloaded_unknown'),
                   dict(feature_order=list(reversed(FEATURES))),dict(label_horizon_days=60),dict(history_window_days=30)]:
        lines=fixture_lines();lines[0].update(change)
        with pytest.raises(p.ContractError):p.read_dataset(save(tmp_path,lines))


def test_dataset_rejects_nan_infinity_boolean_and_wrong_dimensions(tmp_path):
    p=module()
    for bad in [float('nan'),float('inf'),True,'1']:
        lines=fixture_lines();lines[1]['features'][0]=bad
        with pytest.raises(p.ContractError):p.read_dataset(save(tmp_path,lines))
    lines=fixture_lines();lines[1]['features'].append(1)
    with pytest.raises(p.ContractError):p.read_dataset(save(tmp_path,lines))


def test_dataset_rejects_cross_tenant_and_duplicate_invoice_snapshots(tmp_path):
    p=module()
    lines=fixture_lines();lines[1]['tenant_id']='another-tenant'
    with pytest.raises(p.ContractError):p.read_dataset(save(tmp_path,lines))
    lines=fixture_lines();lines[2]['invoice_id']=lines[1]['invoice_id']
    with pytest.raises(p.ContractError):p.read_dataset(save(tmp_path,lines))


def test_split_purges_label_window_and_availability_between_holdouts(tmp_path):
    p=module();dataset=p.read_dataset(save(tmp_path,fixture_lines()))
    splits=p.chronological_split(dataset,p.TrainingConfig())
    assert set(splits)=={'train','validation','test','purged'}
    for left,right in [('train','validation'),('validation','test')]:
        boundary=min(row.as_of for row in splits[right])
        assert all(row.as_of+timedelta(days=30)<boundary for row in splits[left])
        assert all(row.label_observed_at<=boundary for row in splits[left])
    assert splits['purged']
    ids=[row.invoice_id for split in ('train','validation','test') for row in splits[split]]
    assert len(ids)==len(set(ids))


def test_late_observed_labels_are_purged_from_earlier_split(tmp_path):
    p=module();lines=fixture_lines()
    lines[1]['label_observed_at']='2025-01-01T00:00:00Z'
    dataset=p.read_dataset(save(tmp_path,lines));splits=p.chronological_split(dataset,p.TrainingConfig())
    assert lines[1]['invoice_id'] not in {row.invoice_id for row in splits['train']}


def test_training_is_reproducible_and_synthetic_is_never_promotable(tmp_path):
    p=module();dataset=p.read_dataset(save(tmp_path,fixture_lines()))
    config=p.TrainingConfig(epochs=150)
    first=p.train_candidate(dataset,config);second=p.train_candidate(dataset,config)
    assert first==second
    assert first['artifact']['stage']=='candidate' and first['artifact']['production_ready'] is False
    assert first['report']['promotion']['eligible'] is False
    assert 'non_operational_provenance' in first['report']['promotion']['reasons']
    test=first['report']['metrics']['test']
    assert test['brier']<test['baseline_brier']
    assert sum(band['count'] for band in test['calibration_bands'])==test['samples']
    serialized=json.dumps(first)
    assert 'private-invoice-' not in serialized and 'fixture-tenant' not in serialized


def test_insufficient_or_single_class_history_fails_closed(tmp_path):
    p=module()
    small=p.train_candidate(p.read_dataset(save(tmp_path,fixture_lines(20))),p.TrainingConfig(epochs=5))
    assert small['artifact'] is None and small['report']['promotion']['eligible'] is False
    lines=fixture_lines()
    for row in lines[1:]:row['net_fraction_paid_30d']=1.0
    single=p.train_candidate(p.read_dataset(save(tmp_path,lines)),p.TrainingConfig(epochs=5))
    assert single['artifact'] is None
    assert any('class' in reason for reason in single['report']['promotion']['reasons'])


def test_promotion_requires_real_origin_sample_coverage_and_brier_gain():
    p=module()
    def stats(brier=0.1,baseline=0.25):
        return dict(samples=100,positives=50,negatives=50,brier=brier,baseline_brier=baseline,calibration_error=0.02)
    metrics={key:stats() for key in ('train','validation','test')}
    assert p.promotion_gate(metrics,'real_operational',p.TrainingConfig())['eligible'] is True
    metrics['test']=stats(0.26,0.25)
    assert p.promotion_gate(metrics,'real_operational',p.TrainingConfig())['eligible'] is False
    metrics['test']=stats();metrics['test']['positives']=0
    assert p.promotion_gate(metrics,'real_operational',p.TrainingConfig())['eligible'] is False


def test_artifact_validation_checks_tenant_version_order_and_safe_numbers(tmp_path):
    p=module();result=p.train_candidate(p.read_dataset(save(tmp_path,fixture_lines())),p.TrainingConfig(epochs=50))
    path=tmp_path/'candidate.json';artifact=result['artifact'];path.write_text(json.dumps(artifact))
    model=p.load_artifact(path,tenant_id='fixture-tenant',expected_model_version=artifact['model_version'])
    prediction=p.predict_probability(model,[0,10.0,0.5,10.0,0],feature_order=FEATURES)
    assert 0<=prediction<=1
    with pytest.raises(p.ContractError):p.load_artifact(path,tenant_id='other-tenant',expected_model_version=artifact['model_version'])
    with pytest.raises(p.ContractError):p.load_artifact(path,tenant_id='fixture-tenant',expected_model_version='different-version')
    with pytest.raises(p.ContractError):p.predict_probability(model,[0,10,0.5,10,0],feature_order=list(reversed(FEATURES)))
    for mutation in [dict(coefficients=[float('nan')]*5),dict(feature_order=list(reversed(FEATURES))),dict(__reduce__='run arbitrary code')]:
        damaged=copy.deepcopy(artifact);damaged.update(mutation);path.write_text(json.dumps(damaged))
        with pytest.raises(p.ContractError):p.load_artifact(path,tenant_id='fixture-tenant',expected_model_version=artifact['model_version'])


def test_json_rejects_duplicate_keys_and_oversize_artifacts(tmp_path):
    p=module();path=tmp_path/'malicious.json'
    for value in ['{"schema_version":1,"schema_version":2}','NaN','["not", "an", "artifact"]','x'*1_000_001]:
        path.write_text(value)
        with pytest.raises(p.ContractError):p.load_artifact(path,tenant_id='fixture-tenant',expected_model_version='pay30-logit-v1-0000000000000000')


def test_config_rejects_nonfinite_and_unbounded_work():
    p=module()
    for change in [dict(epochs=0),dict(epochs=100001),dict(learning_rate=float('nan')),dict(l2=-1),dict(seed=True)]:
        with pytest.raises(p.ContractError):p.TrainingConfig(**change)


def test_holdout_features_do_not_change_training_preprocessing_or_weights(tmp_path):
    p=module();lines=fixture_lines();config=p.TrainingConfig(epochs=30)
    first=p.train_candidate(p.read_dataset(save(tmp_path,lines)),config)
    for row in lines[289:]:
        row['features'][1]=30.0
        row['features'][3]=1000.0
    second=p.train_candidate(p.read_dataset(save(tmp_path,lines)),config)
    for key in ('coefficients','intercept','means','scales'):
        assert first['artifact'][key]==second['artifact'][key]


def test_rehashed_malicious_artifact_still_fails_semantic_validation(tmp_path):
    p=module();result=p.train_candidate(p.read_dataset(save(tmp_path,fixture_lines())),p.TrainingConfig(epochs=5))
    for name,bad in [('scales',[0]*5),('coefficients',[1e300]*5),('means',[0,10,-1,10,0])]:
        artifact=copy.deepcopy(result['artifact']);artifact[name]=bad
        artifact['model_version']=p._model_version(artifact)
        artifact.pop('artifact_sha256');artifact['artifact_sha256']=p._digest(artifact)
        path=tmp_path/'candidate.json';path.write_text(json.dumps(artifact))
        with pytest.raises(p.ContractError):p.load_artifact(path,tenant_id='fixture-tenant',expected_model_version=artifact['model_version'])


def test_cli_writes_candidate_bundle_with_honest_nonpromotion_and_no_pii(tmp_path):
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    p=module();dataset=save(tmp_path,fixture_lines())
    root=Path(__file__).resolve().parents[1]
    (root/'var').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='model-test-',dir=root/'var') as output:
        command=[sys.executable,str(root/'scripts'/'train_payment_model.py'),'--dataset',str(dataset),'--output-dir',output,'--epochs','20']
        refused=subprocess.run(command,capture_output=True,text=True,check=False)
        assert refused.returncode==1 and '--allow-fixture' in refused.stdout
        run=subprocess.run([*command,'--allow-fixture'],capture_output=True,text=True,check=False)
        assert run.returncode==2,run.stdout+run.stderr
        summary=json.loads(run.stdout)
        assert summary['production_ready'] is False and summary['gate_eligible'] is False
        assert 'private-invoice-' not in run.stdout and 'fixture-tenant' not in run.stdout
        bundle=Path(output)/summary['model_version']
        assert {path.name for path in bundle.iterdir()}=={'candidate.json','manifest.json','report.json'}
        artifact=json.loads((bundle/'candidate.json').read_text())
        p.load_artifact(bundle/'candidate.json',tenant_id='fixture-tenant',expected_model_version=artifact['model_version'])
        # tmp_path may itself be under var/ when pytest uses --basetemp there.
        # This owned directory is always outside var/, regardless of the runner.
        with tempfile.TemporaryDirectory(prefix='.model-outside-var-',dir=root) as forbidden:
            outside=subprocess.run([*command[:4],'--output-dir',forbidden],capture_output=True,text=True,check=False)
            assert outside.returncode==1 and 'under repository var/' in outside.stdout
