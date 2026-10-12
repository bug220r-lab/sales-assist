"""Offline-only CLI. Live access is a separate explicit Python API opt-in."""

import argparse
import json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Help Scout evidence reader: live access disabled."
    )
    parser.add_argument(
        "--demo", action="store_true", help="run synthetic fake HTTP and print a safe summary"
    )
    args = parser.parse_args(argv)
    if not args.demo:
        parser.print_help()
        return 0
    from .demo import run_demo

    print(json.dumps(run_demo().summary(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
