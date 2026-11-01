"""Reproducible guardrail replay; optional paid Yandex eval only on synthetic data.

Run: python -m server.agent_evals --mode replay --out var/agent-eval.json
Real model evaluation: --mode yandex, with credentials already in process env.
No customer records or complete provider outputs are written to the report.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .agent_graph import extract_yandex
from .agent_models import validate_extraction

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "agent-candidates-v1.json"


def evaluate(*, mode="replay", extractor=None, fixtures=FIXTURES):
    dataset = json.loads(Path(fixtures).read_text(encoding='utf-8'))
    extractor = extractor or extract_yandex
    correct, true_ready, false_ready, missed_ready, failures, intent_correct = 0, 0, 0, 0, 0, 0
    outcomes = []
    for case in dataset["cases"]:
        if mode == "replay":
            payload, error = case["candidate"], None
        elif mode == "yandex":
            result = extractor(case["text"], case["received_at"], "eval-" + case["id"])
            payload, error = result["payload"], result["error"]
        else:
            raise ValueError("Unknown evaluation mode")
        extracted, reasons = validate_extraction(case["text"], payload, datetime.fromisoformat(case["received_at"]))
        if error:
            reasons.append(error)
            failures += 1
        ready = not reasons
        expected = case.get("live_expected_ready", case["expected_ready"]) if mode == "yandex" else case["expected_ready"]
        correct += ready == expected
        true_ready += ready and expected
        false_ready += ready and not expected
        missed_ready += expected and not ready
        expected_intent = case.get("live_expected_intent", case["expected_intent"]) if mode == "yandex" else case["expected_intent"]
        intent_correct += extracted.get("intent") == expected_intent
        outcomes.append({"id": case["id"], "expected_ready": expected, "ready": ready,
                         "intent": extracted.get("intent"), "expected_intent": expected_intent, "reasons": reasons})
    count = len(dataset["cases"])
    precision = true_ready / (true_ready + false_ready) if true_ready + false_ready else None
    recall = true_ready / (true_ready + missed_ready) if true_ready + missed_ready else None
    return {"dataset": dataset["version"], "mode": mode,
        "evaluation_scope": "synthetic_guardrail_replay" if mode == "replay" else "synthetic_live_yandex",
        "model_quality_measured": mode == "yandex", "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": count, "false_ready": false_ready, "true_ready": true_ready, "missed_ready": missed_ready,
        "provider_failures": failures, "ready_precision": precision, "ready_recall": recall,
        "decision_accuracy": correct / count, "intent_accuracy": intent_correct / count,
        "passed": failures == 0 and false_ready == 0 and precision == 1 and recall is not None and recall >= 0.8,
        "limitations": "Synthetic small dataset; replay does not measure LLM extraction quality or production/business outcomes.",
        "outcomes": outcomes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay", "yandex"), default="replay")
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()
    report = evaluate(mode=options.mode)
    if options.out:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "outcomes"}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)
