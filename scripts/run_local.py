"""Explicit local entry point: load the repository .env before importing the app."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_local_env(path: Path) -> None:
    # Never search parent directories or override values supplied by a host.
    # Importing server.main/tests does not load private local credentials.
    load_dotenv(dotenv_path=path, override=False, interpolate=False, encoding="utf-8-sig")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args(argv)
    load_local_env(args.env_file)
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
