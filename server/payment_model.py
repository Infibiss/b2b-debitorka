"""Offline, tenant-bound payment-classification candidates using only stdlib.

A probability of paying >=90% within 30 days is not expected cash. This module
never trains on the live ledger, promotes artifacts, or registers an API route.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re

FEATURE_ORDER = ('age_days', 'log_amount', 'prior_late_fraction', 'prior_mean_delay_days', 'broken_promises')
SCHEMA_VERSION = 1
DATASET_KIND = 'authorized_invoice_snapshots_v1'
METHOD = 'standardized_l2_logistic_v1'
MAX_DATASET_BYTES = 50_000_000
MAX_ROWS = 50_000
MAX_ARTIFACT_BYTES = 1_000_000
FEATURE_BOUNDS = ((-3650, 36500), (0, math.log1p(1_000_000_000_000_000)), (0, 1), (0, 36500), (0, 1_000_000))
MANIFEST_KEYS = {'record_type','schema_version','dataset_kind','tenant_id','dataset_cutoff','provenance','authorization_ref',
                 'feature_order','history_window_days','label_horizon_days','label_threshold'}
SNAPSHOT_KEYS = {'record_type','tenant_id','invoice_id','as_of','feature_observed_at','features','net_fraction_paid_30d','label_observed_at'}


class ContractError(ValueError):
    """Safe messages contain field names/counts, never customer source values."""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _reject_constant(_):
    raise ContractError('Non-finite JSON number')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError('Duplicate JSON key')
        result[key] = value
    return result


def _parse_json(value):
    try:
        return json.loads(value, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError) as error:
        raise ContractError('Invalid strict JSON') from None


def _keys(value, expected, context):
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError(context+' fields do not match the supported schema')


def _text(value, name, maximum=256):
    if (not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ContractError('Invalid '+name)
    return value


def _timestamp(value, name):
    try:
        if not isinstance(value, str):
            raise ValueError()
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            result = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        else:
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if result.tzinfo is None:
                raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ContractError('Invalid timezone-aware '+name) from None


def _number(value, name, lower=None, upper=None):
    if type(value) not in (int, float):
        raise ContractError('Invalid numeric '+name)
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ContractError('Invalid numeric '+name) from None
    if not math.isfinite(result) or (lower is not None and result < lower) or (upper is not None and result > upper):
        raise ContractError('Out-of-range numeric '+name)
    return result


def _features(values, feature_order):
    if (not isinstance(feature_order, (list, tuple)) or list(feature_order) != list(FEATURE_ORDER)
            or not isinstance(values, (list, tuple)) or len(values) != len(FEATURE_ORDER)):
        raise ContractError('Feature order or dimensions do not match')
    result = tuple(_number(value, name, *bounds) for value, name, bounds in zip(values, FEATURE_ORDER, FEATURE_BOUNDS))
    if not result[0].is_integer() or not result[4].is_integer():
        raise ContractError('Age and broken promises must be integers')
    return result


@dataclass(frozen=True)
class Snapshot:
    invoice_id: str
    as_of: datetime
    feature_observed_at: datetime
    label_observed_at: datetime
    features: tuple[float, ...]
    label: int


@dataclass(frozen=True)
class Dataset:
    tenant_binding_sha256: str
    cutoff: datetime
    provenance: str
    digest_sha256: str
    rows: tuple[Snapshot, ...]


def read_dataset(path, *, now=None):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_DATASET_BYTES+1)
        if len(raw) > MAX_DATASET_BYTES:
            raise ContractError('Dataset exceeds byte limit')
        lines = [line for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
    except (OSError, UnicodeError):
        raise ContractError('Dataset cannot be read as UTF-8 JSONL') from None
    if not lines or len(lines)-1 > MAX_ROWS:
        raise ContractError('Dataset record count outside bounds')
    manifest = _parse_json(lines[0])
    _keys(manifest, MANIFEST_KEYS, 'Manifest')
    if (manifest['record_type'] != 'manifest' or type(manifest['schema_version']) is not int
            or manifest['schema_version'] != SCHEMA_VERSION or manifest['dataset_kind'] != DATASET_KIND):
        raise ContractError('Unsupported authorized dataset kind or version')
    tenant_id = _text(manifest['tenant_id'], 'tenant binding')
    _text(manifest['authorization_ref'], 'authorization reference')
    if manifest['provenance'] not in ('real_operational', 'synthetic_fixture'):
        raise ContractError('Unsupported data provenance')
    if (manifest['feature_order'] != list(FEATURE_ORDER) or type(manifest['history_window_days']) is not int
            or manifest['history_window_days'] != 365 or type(manifest['label_horizon_days']) is not int
            or manifest['label_horizon_days'] != 30 or _number(manifest['label_threshold'], 'label threshold') != 0.9):
        raise ContractError('Unsupported feature/label definition')
    cutoff = _timestamp(manifest['dataset_cutoff'], 'dataset cutoff')
    if cutoff > (now or datetime.now(timezone.utc)):
        raise ContractError('Dataset cutoff is in the future')
    rows = []
    seen = set()
    for line in lines[1:]:
        row = _parse_json(line)
        _keys(row, SNAPSHOT_KEYS, 'Snapshot')
        if row['record_type'] != 'snapshot' or row['tenant_id'] != tenant_id:
            raise ContractError('Snapshot kind or tenant binding does not match')
        invoice_id = _text(row['invoice_id'], 'invoice identity')
        if invoice_id in seen:
            raise ContractError('Duplicate invoice snapshots are forbidden across all splits')
        seen.add(invoice_id)
        as_of = _timestamp(row['as_of'], 'as_of')
        observed = _timestamp(row['feature_observed_at'], 'feature observation')
        label_observed = _timestamp(row['label_observed_at'], 'label observation')
        if observed > as_of or not as_of+timedelta(days=30) <= label_observed <= cutoff:
            raise ContractError('Future feature or immature/unavailable 30-day label')
        features = _features(row['features'], manifest['feature_order'])
        fraction = _number(row['net_fraction_paid_30d'], 'net fraction paid in 30 days', 0, 1)
        rows.append(Snapshot(invoice_id, as_of, observed, label_observed, features, int(fraction >= 0.9)))
    return Dataset(hashlib.sha256(tenant_id.encode()).hexdigest(), cutoff, manifest['provenance'], hashlib.sha256(raw).hexdigest(), tuple(rows))


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 0
    epochs: int = 250
    learning_rate: float = 0.1
    l2: float = 0.01
    train_fraction: float = 0.6
    validation_fraction: float = 0.2
    min_train_samples: int = 30
    min_validation_samples: int = 20
    min_test_samples: int = 20
    min_class_samples: int = 5
    minimum_brier_gain: float = 0.005
    maximum_calibration_error: float = 0.15

    def __post_init__(self):
        for name, low, high in (('seed',0,2**32-1),('epochs',1,5000),('min_train_samples',30,MAX_ROWS),
                                ('min_validation_samples',20,MAX_ROWS),('min_test_samples',20,MAX_ROWS),('min_class_samples',5,MAX_ROWS)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ContractError('Invalid training configuration '+name)
        for name, low, high in (('learning_rate',1e-6,1),('l2',0,100),('train_fraction',0.1,0.8),
                                ('validation_fraction',0.1,0.5),('minimum_brier_gain',0.000001,0.25),('maximum_calibration_error',0.001,0.25)):
            _number(getattr(self,name),name,low,high)
        if self.train_fraction+self.validation_fraction >= 0.95:
            raise ContractError('Chronological test split must retain at least five percent')


def chronological_split(dataset, config):
    rows = sorted(dataset.rows, key=lambda row: (row.as_of, row.invoice_id))
    result = dict(train=[], validation=[], test=[], purged=[])
    if len(rows) < 3:
        result['purged'] = rows
        return result
    validation_start = rows[min(len(rows)-1, int(len(rows)*config.train_fraction))].as_of
    test_start = rows[min(len(rows)-1, int(len(rows)*(config.train_fraction+config.validation_fraction)))].as_of
    gap = timedelta(days=30)
    for row in rows:
        if row.as_of >= test_start:
            result['test'].append(row)
        elif row.as_of >= validation_start:
            target = 'validation' if row.as_of+gap < test_start and row.label_observed_at <= test_start else 'purged'
            result[target].append(row)
        else:
            target = 'train' if row.as_of+gap < validation_start and row.label_observed_at <= validation_start else 'purged'
            result[target].append(row)
    return result


def _sigmoid(value):
    if value >= 0:
        return 1/(1+math.exp(-value))
    exponent = math.exp(value)
    return exponent/(1+exponent)


def _coverage(rows):
    positives = sum(row.label for row in rows)
    return dict(samples=len(rows), positives=positives, negatives=len(rows)-positives)


def _coverage_reasons(metrics, config):
    reasons = []
    for split, minimum in (('train',config.min_train_samples),('validation',config.min_validation_samples),('test',config.min_test_samples)):
        stats = metrics.get(split, {})
        if (type(stats.get('samples')) is not int or stats['samples'] < minimum):
            reasons.append(split+'_insufficient_samples')
        if (type(stats.get('positives')) is not int or type(stats.get('negatives')) is not int
                or min(stats['positives'],stats['negatives']) < config.min_class_samples
                or stats['positives']+stats['negatives'] != stats.get('samples')):
            reasons.append(split+'_insufficient_class_coverage')
    return reasons


def promotion_gate(metrics, provenance, config):
    reasons = _coverage_reasons(metrics, config)
    if provenance != 'real_operational':
        reasons.append('non_operational_provenance')
    for split in ('validation', 'test'):
        stats = metrics.get(split, {})
        try:
            brier = _number(stats.get('brier'), 'brier', 0, 1)
            baseline = _number(stats.get('baseline_brier'), 'baseline brier', 0, 1)
            calibration = _number(stats.get('calibration_error'), 'calibration error', 0, 1)
            if baseline-brier < config.minimum_brier_gain:
                reasons.append(split+'_no_brier_improvement')
            if calibration > config.maximum_calibration_error:
                reasons.append(split+'_calibration_error')
        except ContractError:
            reasons.append(split+'_missing_or_invalid_metrics')
    return dict(eligible=not reasons, reasons=reasons, automatic_promotion=False,
                meaning='Offline evidence gate only; independent authorization and real-source audit still required')


def _evaluate(rows, probabilities, baseline):
    count = len(rows)
    bands = []
    for index in range(5):
        members = [(row.label, probability) for row, probability in zip(rows, probabilities) if min(4,int(probability*5)) == index]
        bands.append(dict(lower=index/5, upper=(index+1)/5, count=len(members),
            mean_probability=sum(p for _, p in members)/len(members) if members else None,
            observed_fraction=sum(y for y, _ in members)/len(members) if members else None))
    return _coverage(rows) | dict(brier=sum((p-row.label)**2 for row,p in zip(rows, probabilities))/count,
        baseline_brier=sum((baseline-row.label)**2 for row in rows)/count,
        calibration_error=sum(band['count']*abs(band['mean_probability']-band['observed_fraction']) for band in bands if band['count'])/count,
        calibration_bands=bands)


def _model_version(artifact):
    basis = {key: artifact[key] for key in ('method','coefficients','intercept','means','scales','config','training_data','tenant_binding_sha256')}
    return 'pay30-logit-v1-'+_digest(basis)[:16]


def train_candidate(dataset, config=None):
    config = config or TrainingConfig()
    splits = chronological_split(dataset, config)
    coverage = {name: _coverage(rows) for name, rows in splits.items() if name != 'purged'}
    report = dict(schema_version=1, method=METHOD, target='fraction_of_snapshot_debt_paid_within_30d_gte_0.9',
        dataset_digest_sha256=dataset.digest_sha256, provenance=dataset.provenance, config=asdict(config),
        splits={name: _coverage(rows) | dict(start=rows[0].as_of.isoformat() if rows else None, end=rows[-1].as_of.isoformat() if rows else None) for name, rows in splits.items()},
        metrics=coverage, baseline=dict(method='constant_training_label_prior', probability=None), promotion=None)
    manifest = dict(schema_version=1, dataset_digest_sha256=dataset.digest_sha256, dataset_cutoff=dataset.cutoff.isoformat(),
        tenant_binding_sha256=dataset.tenant_binding_sha256, provenance=dataset.provenance, sample_count=len(dataset.rows),
        feature_order=list(FEATURE_ORDER), history_window_days=365, label_horizon_days=30, label_threshold=0.9,
        model_version=None, artifact_sha256=None, production_ready=False)
    failures = _coverage_reasons(coverage, config)
    if len(splits['train'])*config.epochs > 20_000_000:
        failures.append('training_work_budget_exceeded')
    if failures:
        report['promotion'] = dict(eligible=False, reasons=failures, automatic_promotion=False)
        manifest['report_sha256'] = _digest(report)
        return dict(artifact=None, report=report, manifest=manifest)
    train = splits['train']
    means = [sum(row.features[j] for row in train)/len(train) for j in range(len(FEATURE_ORDER))]
    deviations = [math.sqrt(sum((row.features[j]-means[j])**2 for row in train)/len(train)) for j in range(len(FEATURE_ORDER))]
    scales = [value if value >= 1e-12 else 1.0 for value in deviations]
    def transform(row):
        return [(value-mean)/scale for value,mean,scale in zip(row.features,means,scales)]
    training_values = [transform(row) for row in train]
    randomizer = random.Random(config.seed)
    weights = [randomizer.uniform(-0.01,0.01) for _ in FEATURE_ORDER]
    intercept = 0.0
    for _ in range(config.epochs):
        gradients = [0.0]*len(FEATURE_ORDER)
        bias_gradient = 0.0
        for row,values in zip(train,training_values):
            error = _sigmoid(intercept+sum(weight*value for weight,value in zip(weights,values)))-row.label
            bias_gradient += error
            for j,value in enumerate(values):
                gradients[j] += error*value
        weights = [weight-config.learning_rate*(gradient/len(train)+config.l2*weight) for weight,gradient in zip(weights,gradients)]
        intercept -= config.learning_rate*bias_gradient/len(train)
    if any(not math.isfinite(value) for value in [*weights,intercept]):
        raise ContractError('Training diverged; candidate refused')
    baseline = sum(row.label for row in train)/len(train)
    metrics = {}
    for name in ('train','validation','test'):
        rows = splits[name]
        probabilities = [_sigmoid(intercept+sum(weight*value for weight,value in zip(weights,transform(row)))) for row in rows]
        metrics[name] = _evaluate(rows,probabilities,baseline)
    report.update(metrics=metrics, baseline=dict(method='constant_training_label_prior', probability=baseline),
                  promotion=promotion_gate(metrics,dataset.provenance,config))
    artifact = dict(schema_version=1,method=METHOD,stage='candidate',production_ready=False,
        tenant_binding_sha256=dataset.tenant_binding_sha256,feature_order=list(FEATURE_ORDER),history_window_days=365,
        label_horizon_days=30,label_threshold=0.9,coefficients=weights,intercept=intercept,means=means,scales=scales,
        config=asdict(config),training_data=dict(dataset_digest_sha256=dataset.digest_sha256,dataset_cutoff=dataset.cutoff.isoformat(),
            provenance=dataset.provenance,sample_count=len(dataset.rows)))
    artifact['model_version'] = _model_version(artifact)
    artifact['artifact_sha256'] = _digest(artifact)
    manifest.update(model_version=artifact['model_version'], artifact_sha256=artifact['artifact_sha256'], report_sha256=_digest(report))
    return dict(artifact=artifact, report=report, manifest=manifest)


@dataclass(frozen=True)
class ValidatedModel:
    model_version: str
    tenant_binding_sha256: str
    coefficients: tuple[float, ...]
    intercept: float
    means: tuple[float, ...]
    scales: tuple[float, ...]


def load_artifact(path, *, tenant_id, expected_model_version):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_ARTIFACT_BYTES+1)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ContractError('Artifact exceeds byte limit')
        artifact = _parse_json(raw.decode('utf-8'))
    except (OSError,UnicodeError):
        raise ContractError('Artifact cannot be read as UTF-8 JSON') from None
    expected = {'schema_version','method','stage','production_ready','tenant_binding_sha256','feature_order','history_window_days',
                'label_horizon_days','label_threshold','coefficients','intercept','means','scales','config','training_data','model_version','artifact_sha256'}
    _keys(artifact,expected,'Artifact')
    if (type(artifact['schema_version']) is not int or artifact['schema_version'] != 1 or artifact['method'] != METHOD
            or artifact['stage'] != 'candidate' or artifact['production_ready'] is not False
            or artifact['feature_order'] != list(FEATURE_ORDER) or type(artifact['history_window_days']) is not int
            or artifact['history_window_days'] != 365 or type(artifact['label_horizon_days']) is not int
            or artifact['label_horizon_days'] != 30 or _number(artifact['label_threshold'],'label threshold') != 0.9):
        raise ContractError('Unsupported artifact contract')
    tenant_hash = hashlib.sha256(_text(tenant_id,'tenant identity').encode()).hexdigest()
    if artifact['tenant_binding_sha256'] != tenant_hash:
        raise ContractError('Artifact tenant binding mismatch')
    if (artifact['model_version'] != expected_model_version or not isinstance(expected_model_version,str)
            or not re.fullmatch(r'pay30-logit-v1-[0-9a-f]{16}',expected_model_version)):
        raise ContractError('Artifact model version mismatch')
    _keys(artifact['config'],set(asdict(TrainingConfig())),'Training configuration')
    TrainingConfig(**artifact['config'])
    training = artifact['training_data']
    _keys(training,{'dataset_digest_sha256','dataset_cutoff','provenance','sample_count'},'Training data')
    if (not isinstance(training['dataset_digest_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',training['dataset_digest_sha256'])
            or training['provenance'] not in ('real_operational','synthetic_fixture') or type(training['sample_count']) is not int
            or not 1 <= training['sample_count'] <= MAX_ROWS or _timestamp(training['dataset_cutoff'],'dataset cutoff') > datetime.now(timezone.utc)):
        raise ContractError('Invalid training data metadata')
    vectors = {}
    for name in ('coefficients','means','scales'):
        if not isinstance(artifact[name],list) or len(artifact[name]) != len(FEATURE_ORDER):
            raise ContractError('Artifact vector dimensions mismatch')
        lower = 1e-12 if name == 'scales' else -1_000_000
        vectors[name] = tuple(_number(value,name,lower,1_000_000) for value in artifact[name])
        if name == 'means':
            for value,bounds in zip(vectors[name],FEATURE_BOUNDS):
                _number(value,'feature mean',*bounds)
    intercept = _number(artifact['intercept'],'intercept',-1_000_000,1_000_000)
    saved_digest = artifact['artifact_sha256']
    unhashed = dict(artifact)
    unhashed.pop('artifact_sha256')
    if not isinstance(saved_digest,str) or saved_digest != _digest(unhashed) or artifact['model_version'] != _model_version(artifact):
        raise ContractError('Artifact integrity mismatch')
    return ValidatedModel(artifact['model_version'],tenant_hash,vectors['coefficients'],intercept,vectors['means'],vectors['scales'])


def predict_probability(model, features, *, feature_order):
    if not isinstance(model,ValidatedModel):
        raise ContractError('A validated tenant-bound candidate model is required')
    values = _features(features,feature_order)
    standardized = [(value-mean)/scale for value,mean,scale in zip(values,model.means,model.scales)]
    return _sigmoid(model.intercept+sum(weight*value for weight,value in zip(model.coefficients,standardized)))
