"""Real Langfuse SDK instrumentation. Customer text/evidence never enter a span."""
import hashlib
import os
from contextlib import contextmanager


class Observation:
    def __init__(self, span=None, trace_id=None):
        self.span, self.trace_id = span, trace_id

    def finish(self, *, status, usage, latency_ms, estimated_cost_rub=None):
        if self.span is not None:
            metadata = {"status": status, "latency_ms": latency_ms,
                        "estimated_cost_rub": estimated_cost_rub,
                        "cost_currency": "RUB", "cost_basis": "operator_configured_rates" if estimated_cost_rub is not None else "unavailable"}
            try:
                self.span.update(metadata=metadata, usage_details=usage,
                                 level="DEFAULT" if status == "ok" else "WARNING")
            except Exception:
                # Observability is optional; an unavailable exporter must not
                # undo an approved, transactional business action.
                pass


class AgentObservability:
    def __init__(self, client=None):
        self.client = client
        if client is None and os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse import Langfuse
                self.client = Langfuse(public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                    base_url=os.getenv("LANGFUSE_BASE_URL", os.getenv("LANGFUSE_HOST", "http://127.0.0.1:3000")),
                    timeout=3, debug=False, environment=os.getenv("APP_ENV", "development"))
            except Exception:
                self.client = None

    @property
    def configured(self):
        return self.client is not None

    @contextmanager
    def observe(self, operation, proposal_id, *, model=None):
        if self.client is None:
            yield Observation()
            return
        trace_id = hashlib.sha256(proposal_id.encode()).hexdigest()[:32]
        # No automatic LangChain callbacks: they capture text/tool payloads.
        # Only these deliberately constructed spans reach Langfuse.
        try:
            context = self.client.start_as_current_observation(
                trace_context={"trace_id": trace_id}, name="mandato." + operation,
                as_type="generation" if operation == "extract" else "span",
                model=model, version="mandato-extract-v1", input=None, output=None,
                metadata={"workflow": "receivables_review", "prompt_version": "mandato-extract-v1"},
            )
            span = context.__enter__()
        except Exception:
            yield Observation()
            return
        try:
            yield Observation(span, trace_id)
        finally:
            try:
                # Never give exception text from the business layer to the SDK.
                # Body exceptions still propagate normally to the API caller.
                context.__exit__(None, None, None)
            except Exception:
                pass

    def flush(self):
        if self.client:
            try:
                self.client.flush()
            except Exception:
                pass
