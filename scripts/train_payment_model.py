#!/usr/bin/env python3
"""Evaluate a local authorized JSONL dataset; candidate artifacts stay under var/."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.payment_model import ContractError, TrainingConfig, read_dataset, train_candidate


def _write_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as target:
            temporary = Path(target.name)
            json.dump(value,target,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
            target.write('\n')
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',required=True,help='Private authorized JSONL file; never echoed')
    parser.add_argument('--output-dir',default=str(ROOT/'var'/'payment-model'),help='Candidate bundle base directory under repository var/')
    parser.add_argument('--epochs',type=int,default=250)
    parser.add_argument('--learning-rate',type=float,default=0.1)
    parser.add_argument('--l2',type=float,default=0.01)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--allow-fixture',action='store_true',help='Explicit engineering-only evaluation; production gate still fails')
    args = parser.parse_args(argv)
    try:
        output = Path(args.output_dir).expanduser().resolve()
        var = (ROOT/'var').resolve()
        if output != var and var not in output.parents:
            raise ContractError('Output must stay under repository var/')
        config = TrainingConfig(seed=args.seed,epochs=args.epochs,learning_rate=args.learning_rate,l2=args.l2)
        dataset = read_dataset(args.dataset)
        if dataset.provenance != 'real_operational' and not args.allow_fixture:
            raise ContractError('Synthetic fixtures require explicit --allow-fixture and cannot pass the production gate')
        result = train_candidate(dataset,config)
        artifact, report, manifest = result['artifact'],result['report'],result['manifest']
        bundle = output/(artifact['model_version'] if artifact else 'abstained-'+dataset.digest_sha256[:16])
        bundle.mkdir(parents=True,exist_ok=True,mode=0o700)
        _write_json(bundle/'report.json',report)
        _write_json(bundle/'manifest.json',manifest)
        if artifact:
            _write_json(bundle/'candidate.json',artifact)
        print(json.dumps(dict(status='candidate_evaluated' if artifact else 'abstained',
            model_version=manifest['model_version'],gate_eligible=report['promotion']['eligible'],production_ready=False,
            reasons=report['promotion']['reasons']),sort_keys=True))
        return 0 if report['promotion']['eligible'] else 2
    except ContractError as error:
        print(json.dumps(dict(status='invalid_input',error=str(error),production_ready=False),sort_keys=True))
        return 1
    except OSError:
        print(json.dumps(dict(status='output_unavailable',error='Cannot write private candidate bundle',production_ready=False),sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
