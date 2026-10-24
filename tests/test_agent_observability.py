def test_actual_sdk_exports_minimized_generation_and_usage():
    import json
    import uuid
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from server.agent_observability import AgentObservability
    exporter = InMemorySpanExporter()
    client = Langfuse(public_key="pk-lf-" + str(uuid.uuid4()), secret_key="synthetic",
                      base_url="http://127.0.0.1:3999", span_exporter=exporter)
    observer = AgentObservability(client=client)
    with observer.observe("extract", "opaque-proposal", model="yandexgpt/5.1") as observation:
        observation.finish(status="ok", usage={"input": 20, "output": 40}, latency_ms=21,
                           estimated_cost_rub=0.01)
    client.flush()
    spans = exporter.get_finished_spans()
    assert spans, "Langfuse SDK must emit actual OpenTelemetry spans"
    data = json.dumps([dict(span.attributes) for span in spans], ensure_ascii=False)
    assert "20" in data and "40" in data
    assert "estimated_cost_rub" in data and "21" in data
    assert "input.value" not in data and "output.value" not in data
    assert "opaque-proposal" not in data  # only non-reversible trace seed crosses boundary


def test_unconfigured_observation_is_safe_and_explicit(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from server.agent_observability import AgentObservability
    observer = AgentObservability()
    assert observer.configured is False
    with observer.observe("extract", "opaque-proposal") as observation:
        observation.finish(status="unconfigured", usage={}, latency_ms=1)
    assert observation.trace_id is None


def test_sdk_initialization_failure_disables_telemetry(monkeypatch):
    import langfuse
    from server.agent_observability import AgentObservability
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-synthetic")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "synthetic")
    def unavailable(**kwargs):
        raise ConnectionError("synthetic telemetry endpoint unavailable")
    monkeypatch.setattr(langfuse, "Langfuse", unavailable)
    observer = AgentObservability()
    assert observer.configured is False
    with observer.observe("workflow", "opaque") as observation:
        observation.finish(status="ok", usage={}, latency_ms=1)


def test_sdk_failures_do_not_break_business_or_hide_domain_exception():
    import pytest
    from server.agent_observability import AgentObservability
    class Span:
        def update(self, **kwargs):
            raise ConnectionError("synthetic update failure")
    class Context:
        def __init__(self, fail):
            self.fail = fail
        def __enter__(self):
            if self.fail == "enter":
                raise ConnectionError("synthetic enter failure")
            return Span()
        def __exit__(self, *exc):
            assert exc == (None, None, None), "domain exception details must not reach telemetry"
            raise ConnectionError("synthetic exit failure")
    class Client:
        def __init__(self, fail):
            self.fail = fail
        def start_as_current_observation(self, **kwargs):
            if self.fail == "start":
                raise ConnectionError("synthetic start failure")
            return Context(self.fail)
        def flush(self):
            raise ConnectionError("synthetic flush failure")
    for fail in ("start", "enter", "update", "exit"):
        observer = AgentObservability(client=Client(fail))
        reached = []
        with observer.observe("workflow", "opaque") as observation:
            reached.append("business executed")
            observation.finish(status="ok", usage={}, latency_ms=1)
        assert reached == ["business executed"]
        observer.flush()
        with pytest.raises(ValueError, match="business validation failed"):
            with observer.observe("workflow", "opaque"):
                raise ValueError("business validation failed")
