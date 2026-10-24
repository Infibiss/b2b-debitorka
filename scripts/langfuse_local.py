"""Local Langfuse bootstrap/check. Never reads the application .env or prints keys."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ENV_FILE = ROOT / "var" / "langfuse-local.env"


def initialize():
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if ENV_FILE.exists():
        print("Local Langfuse configuration already exists; credentials preserved.")
        return
    fields = {name: secrets.token_hex(32) for name in (
        "LF_POSTGRES_PASSWORD", "LF_CLICKHOUSE_PASSWORD", "LF_REDIS_PASSWORD", "LF_S3_PASSWORD",
        "LF_SALT", "LF_ENCRYPTION_KEY", "LF_NEXTAUTH_SECRET", "LF_USER_PASSWORD")}
    fields.update(LANGFUSE_PUBLIC_KEY="pk-lf-" + str(uuid.uuid4()),
                  LANGFUSE_SECRET_KEY="sk-lf-" + str(uuid.uuid4()), LANGFUSE_BASE_URL="http://127.0.0.1:3033")
    descriptor = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in fields.items()))
    print("Created var/langfuse-local.env with mode 0600; no secrets printed.")


def values():
    # Read only the file generated above, not the user's application .env.
    return dict(line.split("=", 1) for line in ENV_FILE.read_text().splitlines() if line and not line.startswith("#"))


def observations_for_trace(settings, trace_id, start, end):
    import httpx
    response = httpx.get(settings["LANGFUSE_BASE_URL"] + "/api/public/v2/observations",
        params={"traceId": trace_id, "fromStartTime": start, "toStartTime": end,
                "fields": "core,basic,io,model,usage,metadata", "limit": 10},
        auth=(settings["LANGFUSE_PUBLIC_KEY"], settings["LANGFUSE_SECRET_KEY"]), timeout=5, trust_env=False)
    if response.status_code != 200:
        raise RuntimeError(f"Langfuse observations read unavailable: HTTP {response.status_code}")
    return response.json().get("data", [])


def verify():
    import httpx
    from langfuse import Langfuse
    from server.agent_observability import AgentObservability
    settings = values()
    client = Langfuse(public_key=settings["LANGFUSE_PUBLIC_KEY"], secret_key=settings["LANGFUSE_SECRET_KEY"],
        base_url=settings["LANGFUSE_BASE_URL"], timeout=5, environment="local-synthetic-canary")
    if not client.auth_check():
        raise SystemExit("Langfuse authentication failed; check local service readiness.")
    observer = AgentObservability(client=client)
    start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with observer.observe("extract", "synthetic-canary-" + str(uuid.uuid4()), model="synthetic-fixture") as observation:
        observation.finish(status="ok", usage={"input": 20, "output": 10}, latency_ms=1, estimated_cost_rub=0)
    client.flush()
    for _ in range(20):
        rows = observations_for_trace(settings, observation.trace_id, start,
            (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat())
        matching = [row for row in rows if row.get("model") == "synthetic-fixture" and row.get("traceId") == observation.trace_id]
        if matching:
            if any(row.get("input") not in (None, "", "null") or row.get("output") not in (None, "", "null") for row in matching):
                raise SystemExit("Privacy check failed: canary unexpectedly contains input/output.")
            output = {"status": "delivered", "trace_id": observation.trace_id,
                      "host": settings["LANGFUSE_BASE_URL"], "contains_customer_data": False,
                      "observation_count": len(matching), "input_tokens": matching[0].get("inputUsage"),
                      "output_tokens": matching[0].get("outputUsage"), "read_api": "/api/public/v2/observations"}
            report = ROOT / "var" / "langfuse-canary.json"
            report.write_text(json.dumps(output, indent=2) + "\n")
            print(json.dumps(output))
            return
        time.sleep(2)
    raise SystemExit("Synthetic trace not visible after bounded wait; delivery is unverified.")


def run_application():
    settings = values()
    os.environ.update({key: settings[key] for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")})
    # Keys are inherited in the environment, never put into argv/logs.
    os.execv(sys.executable, [sys.executable, "-m", "scripts.run_local"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "verify", "run-app"))
    args = parser.parse_args()
    {"init": initialize, "verify": verify, "run-app": run_application}[args.action]()
