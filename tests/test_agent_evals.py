def test_replay_gate_measures_grounded_candidates_and_safe_abstentions():
    from server.agent_evals import evaluate
    report = evaluate()
    assert report["evaluation_scope"] == "synthetic_guardrail_replay"
    assert report["cases"] >= 15
    assert report["false_ready"] == 0
    assert report["ready_precision"] == 1.0
    assert report["decision_accuracy"] == 1.0
    assert report["model_quality_measured"] is False
    assert report["passed"] is True


def test_eval_rejects_adversarial_candidate_instead_of_promoting_bad_model():
    from server.agent_evals import evaluate
    def wrong(*args, **kwargs):
        return {"payload": {"intent": "promise", "amount_kopeks": 99999999, "due_date": "2026-10-28",
            "currency": "RUB", "ambiguous": False,
            "evidence": [{"field": "intent", "quote": "fake quote"}]}, "error": None}
    report = evaluate(mode="yandex", extractor=wrong)
    assert report["false_ready"] == 0
    assert report["passed"] is False
    assert report["model_quality_measured"] is True


def test_live_gold_does_not_treat_injected_bad_candidates_as_bad_input(tmp_path):
    import json
    from server.agent_evals import evaluate
    text = "Обещаем оплатить 300 рублей 27.10.2026."
    valid = {"intent": "promise", "amount_kopeks": 30000, "due_date": "2026-10-27", "currency": "RUB", "ambiguous": False,
        "evidence": [{"field": "intent", "quote": text}, {"field": "amount", "quote": "300 рублей"}, {"field": "due_date", "quote": "27.10.2026"}]}
    case = {"id": "bad-candidate-good-input", "text": text, "received_at": "2026-10-24T12:00:00+00:00",
        "expected_ready": False, "live_expected_ready": True, "expected_intent": "promise", "candidate": {**valid, "amount_kopeks": 999}}
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"version": "test", "cases": [case]},ensure_ascii=False),encoding='utf-8')
    assert evaluate(fixtures=path)["decision_accuracy"] == 1
    live = evaluate(mode="yandex", fixtures=path, extractor=lambda *a: {"payload": valid, "error": None})
    assert live["false_ready"] == 0 and live["decision_accuracy"] == 1 and live["passed"]
