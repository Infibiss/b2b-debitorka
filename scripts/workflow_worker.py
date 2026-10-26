#!/usr/bin/env python3
"""Run the durable Mandato scheduler: python -m scripts.workflow_worker [--once]."""
import argparse
import asyncio
import json

from server.database import Config, initialize
from server.workflow import run_once, scheduler_loop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = Config.from_environment()
    initialize(config)
    if args.once:
        print(json.dumps(run_once(config)))
    else:
        asyncio.run(scheduler_loop(config))


if __name__ == '__main__':
    main()
