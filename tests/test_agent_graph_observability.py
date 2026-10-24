import uuid

from test_agent_workflow import env, make_client, ingest


def test_fastapi_langgraph_workflow_emits_real_sdk_span(env, monkeypatch):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from server import agent
    from server.agent_observability import AgentObservability
    exporter = InMemorySpanExporter()
    client = Langfuse(public_key="pk-lf-" + str(uuid.uuid4()), secret_key="synthetic",
        base_url="http://127.0.0.1:3999", span_exporter=exporter)
    observer = AgentObservability(client=client)
    monkeypatch.setattr(agent, "AgentObservability", lambda: observer)
    http, text = make_client(env, monkeypatch)
    p = ingest(http, text)
    observer.flush()
    spans = exporter.get_finished_spans()
    assert any(span.name == "agentpay.workflow" for span in spans)
    assert all("langfuse.observation.input" not in dict(span.attributes) for span in spans)
    assert p["status"] == "review_required"
