"""Redacted Yandex check; an actual generic paid request requires --live."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_local import ROOT, load_local_env


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--live", action="store_true", help="Make one generic request to Yandex; no client records")
    args = parser.parse_args(argv)
    load_local_env(args.env_file)
    from server import llm
    result = llm.probe() if args.live else llm.configuration_status()
    if not args.live:
        result["status"] = "configured_not_tested" if result["configured"] else "configuration_error"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in ("ok", "configured_not_tested") else 1


if __name__ == "__main__":
    raise SystemExit(main())
