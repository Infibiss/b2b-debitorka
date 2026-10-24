# Offline payment-model foundation

**No production payment model has been trained or enabled.** Real authorized point-in-time client data is not available in this change. Tests use explicitly labelled engineering fixtures. The existing `/api/forecast` remains the empirical cash-scenario implementation; no candidate artifact is served by an API.

The new CPU-only pipeline trains regularized logistic regression using the Python standard library. It evaluates a tenant-specific binary target: **at least 90% of a snapshot's outstanding debt received within the following 30 days**. A classification probability is not expected receipts, a complete debtor risk assessment, a legal conclusion, or a financing decision. Multiplying it by debt would ignore partial recoveries and is not supported.

## Decision and evidence contract

Decision owner: a tenant's finance operator considering an offline candidate for future cash-planning research. Success means materially lower held-out Brier error than the constant probability learned from training labels, with adequate coverage and coarse calibration. Unacceptable mistakes are invented payment labels, future features, immature outcomes, overlapping invoices across splits, cross-tenant models, leaked customer identifiers and automatic production promotion.

There is no generic downloaded dataset, invented production training run, GPU requirement, pickle/joblib deserialization, external network request, extra dependency, notebook state, automatic ledger extraction, or deployment step. The existing ledger cannot reconstruct all immutable historical source/feature snapshots; the script therefore requires an explicit authorized export rather than fabricating historical training rows from current balances.

## Private JSONL dataset

Store the source file privately, for example in ignored `var/payment-model-input/`. Do not commit it. Maximum size is 50 MB and 50,000 snapshot rows. Use UTF-8 JSONL; duplicate JSON keys, NaN/Infinity, unexpected fields and mixed tenants are rejected.

The first line is a manifest with exactly these fields:

```json
{"record_type":"manifest","schema_version":1,"dataset_kind":"authorized_invoice_snapshots_v1","tenant_id":"ACTUAL_TENANT_ID","dataset_cutoff":"2026-10-24T12:00:00Z","provenance":"real_operational","authorization_ref":"PRIVATE_SOURCE_REVIEW_REFERENCE","feature_order":["age_days","log_amount","prior_late_fraction","prior_mean_delay_days","broken_promises"],"history_window_days":365,"label_horizon_days":30,"label_threshold":0.9}
```

This shows schema syntax, not supplied production data. `provenance` is `real_operational` for authorized operational evidence or `synthetic_fixture` for engineering tests. Unknown origins and other dataset kinds are rejected. An authorization reference is a reference to an independently retained review of permission, source provenance, feature definitions and financial reconciliation; a string in a JSON file does not itself prove authorization. The dataset digest links output evidence to the exact private input bytes.

Each following line is one invoice at one prediction-time snapshot:

```json
{"record_type":"snapshot","tenant_id":"ACTUAL_TENANT_ID","invoice_id":"PRIVATE_STABLE_INVOICE_ID","as_of":"2026-08-01T00:00:00Z","feature_observed_at":"2026-08-01T00:00:00Z","features":[12,11.512935,0.25,8.5,1],"net_fraction_paid_30d":0.95,"label_observed_at":"2026-09-02T00:00:00Z"}
```

The numbers are illustrative schema values and must never be relabelled as real client records. IDs remain in the private source/in-memory split checks, never in artifacts or evaluation reports. Exactly one snapshot per stable invoice is permitted across the entire dataset, so the same invoice cannot appear in training and evaluation. Use canonical stable invoice identities from the source; aliases, exports with changed invoice IDs, or provider duplicates must be reconciled before export.

All timestamps must have a timezone; ISO dates are also accepted and mean **midnight UTC**, not end of day. The cutoff cannot be in the future. `feature_observed_at` is the latest availability time of **any** input feature and must be no later than `as_of`. `label_observed_at` must be at least `as_of + 30 days` and no later than the dataset cutoff. A window ending later on the cutoff date is immature until its exact end timestamp passes.

The ordered feature vector is fixed and cannot be reordered or changed silently:

| Feature | Definition at `as_of` | Accepted range |
| --- | --- | --- |
| `age_days` | Whole calendar days relative to the invoice's contractual due date, using the tenant's documented business timezone | Integer −3,650 to 36,500 |
| `log_amount` | Natural `log1p` of the snapshot's outstanding **kopeks** | 0 to `log1p(10^15)` |
| `prior_late_fraction` | Fraction of other counterparty obligations due in the preceding 365 days whose lateness was already observable at `as_of`; include observed unpaid overdue obligations | 0 to 1 |
| `prior_mean_delay_days` | Mean nonnegative payment delay for other obligations reaching the target payment threshold in that 365-day history, using only verified bank receipts available by `as_of` | 0 to 36,500 |
| `broken_promises` | Count of other promises whose due dates fell in that history window and whose breach was already known at `as_of` | Integer 0 to 1,000,000 |

The 365-day history is `[as_of − 365 days, as_of)`. Exclude the current invoice and every event/label not yet observed. Late imports do not become knowledge available on their backdated economic date. Zero is valid only when source evidence supports it. If historical features are unavailable, omit the sample rather than inventing zero history. The exporter must document the business timezone and precisely reproduce these definitions from retained source evidence.

The target fraction is the confirmed dated bank receipts assigned to the snapshot debt during `(as_of, as_of + 30 days]`, less dated returns/corrections effective in that window, divided by the positive snapshot outstanding amount, capped to `[0,1]`. Opening balances, manual paid fields, unsupported payment claims and later net reversal totals are not bank receipts. Labels become available only after both the full window and source reconciliation/observation delay. `fraction >= 0.9` maps to label 1; lower fractions map to 0.

The reader validates declared structure, numerical domains, identities and availability timestamps. **It cannot independently establish the authenticity of upstream bank evidence or prove that aggregate feature calculations omitted future events.** Audit the authorized exporter and source trace before any operational use. Setting `provenance=real_operational` is not that audit.

## Chronological training and evaluation

The deterministic split boundaries are the 60th and 80th percentile positions after sorting snapshots by `as_of`. Equal snapshot timestamps stay together. The model never selects rows by the outcome:

- Training rows precede the validation boundary by **more than 30 days**, and their labels must have been observed by that boundary.
- Validation rows start at the validation boundary, end more than 30 days before the test boundary, and have labels observed by the test boundary.
- Test rows start at the test boundary; the input contract already requires all test labels mature and observed by the dataset cutoff.
- Boundary, immature-for-the-next-split and late-observation rows are purged. Split counts, date bounds and purged coverage are reported explicitly.

Normalization means/scales are calculated from training only. Constant columns use scale 1. A seeded initializer and full-batch gradient descent run a fixed number of epochs with L2 regularization on coefficients, excluding the intercept. Defaults: seed 0, 250 epochs, learning rate 0.1, L2 0.01. Each run is bounded to at most 20 million training-row/epoch updates; the configuration also limits epochs to 5,000. Same input bytes, configuration and Python numerical environment reproduce the same artifact/report; no runtime timestamps or random artifact IDs are introduced.

Hyperparameters must be chosen using training/validation evidence before inspecting the test result. Repeatedly selecting a candidate based on the same test set contaminates that holdout; obtain a later untouched time window before claiming a selected model generalizes.

The baseline probability is the positive-label fraction in **training**, applied unchanged to validation/test. Reports contain Brier error for the candidate and baseline, sample and class counts, five fixed probability calibration bands, and weighted absolute calibration error (ECE). Empty bands have null rates. Calibration bands from a small finite sample are descriptive, not proof of statistical calibration.

The offline eligibility gate fails closed unless:

- Provenance is `real_operational`.
- Training has at least 30 samples; validation and test each have at least 20.
- Every split has at least five positive and five negative outcomes.
- Validation and test Brier errors each improve over the training-prior baseline by at least 0.005.
- Validation and test ECE are at most 0.15; every required metric is finite and present.

These defaults are explicit initial engineering gates, not evidence that twenty test invoices establish production reliability. Sparse/time-concentrated data, adverse economic changes, export selection bias and counterparty concentration can remain important. Review larger rolling windows, counterparty/source/age slices and interval uncertainty before changing customer decisions. One invoice per dataset prevents direct invoice overlap; it does not claim independent counterparties or remove correlation between invoices from the same debtor.

Insufficient class/sample coverage yields an abstention with no weights. A fitted candidate with poor evidence still receives a report and remains ineligible. **Even a passing offline gate never changes `stage=candidate` or `production_ready=false`.** There is no automatic serving or promotion.

## Run and inspect

From the repository root, with an authorized operational dataset:

```sh
.venv/bin/python scripts/train_payment_model.py \
  --dataset var/payment-model-input/authorized-snapshots.jsonl \
  --output-dir var/payment-model
```

An optional explicit engineering fixture run requires `--allow-fixture`; it always fails production eligibility. No fixture-generation command is provided as a production data substitute.

Each versioned bundle under the repository's ignored `var/` contains:

- `candidate.json` when fitting was possible: feature order, train-only preprocessing, coefficients/intercept, config, target definition, data digest, provenance, tenant binding hash, deterministic model version, and integrity digest.
- `report.json`: chronological split coverage, baseline, candidate metrics/calibration bands and gate reasons.
- `manifest.json`: source digest/cutoff, method contract, report/artifact hashes and explicit candidate status.

Insufficient data produces only report and manifest under an `abstained-…` directory. JSON files are written atomically with private temporary-file permissions. The CLI refuses output outside the repository's ignored `var/`, prints a fixed safe JSON summary without source paths or customer/invoice IDs, and never prints dataset content. Exit 0 means the **offline evidence gate** passed, 2 means completed evaluation/abstention with a failed gate, and 1 means invalid input or unavailable output. None means deployed or production-ready.

## Optional offline inference helper

`load_artifact(path, tenant_id=…, expected_model_version=…)` returns a validated candidate model. It bounds file size, strictly parses JSON, rejects duplicate keys, checks the exact supported schema/feature order/configuration, validates finite bounded parameters and positive scales, checks tenant binding/model version and verifies the integrity digest. `predict_probability(model, features, feature_order=…)` uses the same ordered feature contract and training normalization.

Only JSON numbers and metadata are loaded; pickle, arbitrary Python imports and executable object reconstruction are absent. A hash detects accidental changes; **it is not a signature or proof of artifact authenticity**. Keep the expected version and full manifest digest in a trusted private review record. A tenant SHA-256 binding prevents accidental model mixing; it is not anonymization or authorization by itself. There is deliberately no HTTP route, live score, production switch or model registry promotion mechanism.

## Verification and next evidence

```sh
.venv/bin/python -m pytest tests/test_payment_model.py -q
```

Tests cover future features, immature/late labels, chronological purge gaps, globally repeated invoices, wrong tenant/kind/provenance/feature order, strict money-derived numeric domains, non-finite values, reproducible fitting, train-only preprocessing, constant-baseline comparison, class/sample failures, synthetic nonpromotion, malformed/oversized/rehashed malicious artifacts, tenant/version isolation and the real CLI output boundary.

The next experiment requires a reviewed operational export with valid source provenance and a later untouched time period. Run the fixed baseline, inspect slices and errors, preserve the private evidence bundle, then decide whether any new model is justified. No new operational quality claim can be made from these fixture tests. Rollback/fallback is to leave this pipeline offline and retain the existing empirical forecast or abstention; the module changes no ledger data or production traffic.
