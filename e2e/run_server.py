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
    os.environ["APP_URL"] = "http://127.0.0.1:8001"
    os.environ["SECURE_COOKIES"] = "false"
    # Browser tests must never contact external email or model providers.
    for key in list(os.environ):
        if key.startswith(("SMTP_", "YANDEX_", "LLM_")):
            os.environ.pop(key, None)
    uvicorn.run("server.main:app", host="127.0.0.1", port=8001, log_level="warning")
