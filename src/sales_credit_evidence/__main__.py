"""Offline by default; explicit coordinated cached-token pilot only."""

import argparse
import json
from typing import Never


class _ArgumentError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse normally echoes rejected values, which could be sensitive.
        raise _ArgumentError from None


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Help Scout evidence reader: live access disabled by default.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--demo", action="store_true", help="run synthetic fake HTTP and print a safe summary"
    )
    mode.add_argument("--live", action="store_true", help="explicitly enable one cached-token read")
    parser.add_argument("--email", action="append", help="one source-proven customer email")
    parser.add_argument("--connection-path", action="append", help="approved local .dpapi path")
    parser.add_argument(
        "--ownership",
        action="append",
        choices=("cleanup-complete", "controlled-handoff-complete"),
        help="externally confirmed cleanup or handoff state",
    )
    parser.add_argument(
        "--confirm-sole-owner",
        action="store_true",
        help="attest the shared credential owner has coordinated all consumers",
    )
    try:
        args = parser.parse_args(argv)
        values = (args.email, args.connection_path, args.ownership)
        if any(value is not None and len(value) != 1 for value in values):
            raise _ArgumentError
        if args.demo and (any(values) or args.confirm_sole_owner):
            raise _ArgumentError
    except _ArgumentError:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "complete": False,
                    "credit_classification": "NOT_EVALUATED",
                    "issues": ["invalid_arguments"],
                }
            )
        )
        return 2
    if not args.demo and not args.live and not any(values) and not args.confirm_sole_owner:
        parser.print_help()
        return 0
    if args.demo:
        from .demo import run_demo

        print(json.dumps(run_demo().summary(), sort_keys=True))
        return 0
    from .pilot import PilotRequest, run_pilot

    result = run_pilot(
        PilotRequest(
            email=(args.email or [""])[0],
            connection_path=(args.connection_path or [""])[0],
            ownership=(args.ownership or [""])[0],
            sole_owner_confirmed=args.confirm_sole_owner,
            enable_live=args.live,
        )
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
