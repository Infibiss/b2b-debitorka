"""Run the built production app against an isolated, disposable test database."""
import os
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

with tempfile.TemporaryDirectory(prefix="agentpay-playwright-") as directory:
    os.environ["DATABASE_PATH"] = str(Path(directory) / "agentpay.sqlite3")
    os.environ["APP_ENV"] = "test"
    os.environ["APP_TIMEZONE"] = "Europe/Moscow"
    os.environ["APP_URL"] = "http://127.0.0.1:8001"
    os.environ["SECURE_COOKIES"] = "false"
    # Browser tests never inherit real email/model/source credentials.
    for key in list(os.environ):
        if key in ("DATABASE_URL", "MANDATO_INTEGRATIONS_JSON") or key.startswith(("SMTP_", "YANDEX_", "LLM_", "LANGFUSE_", "LANGSMITH_", "DADATA_")):
            os.environ.pop(key, None)
    # Stable provider contract for browser tests only. The real CBR adapter and
    # refusal of unverified coverage are exercised by server/test_legal*.py tests.
    # This executable is never used by the production container.
    from server import legal
    from server.business_time import business_today

    def browser_rate_contract(through):
        if through > business_today():
            raise ValueError("Future rates cannot be verified")
        return {
            "version": f"browser-test-rate-contract-{through}",
            "verified_through": str(through),
            "available_from": "2016-08-01",
            "last_observation_on": str(through),
            "source": "https://example.invalid/browser-test-rate-contract",
            "raw_sha256": "0" * 64,
            "daily_rows": 100,
            "periods": [{"from_on": "2016-08-01", "annual_percent": "10"}],
        }

    legal._fetch_official_rates = browser_rate_contract
    uvicorn.run("server.main:app", host="127.0.0.1", port=8001, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")
