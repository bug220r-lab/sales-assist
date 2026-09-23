"""Explicit repository entry point. No Google access on import or default startup."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import doi_intake as intake
from .handoff import load_review_queue

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def outside_repository(path: Path) -> None:
    """Keep credentials, source history and generated orders outside this checkout."""
    resolved = path.resolve()
    if resolved == REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents:
        raise intake.IntakeError(
            "REPOSITORY_DATA_PATH_FORBIDDEN",
            "Use a local data path outside the Sales Assist checkout.",
        )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    enable_google = bool(argv and argv[0] == "--enable-google")
    if enable_google:
        argv.pop(0)
    if not argv:
        print("Sales Assist DOI Intake (separate companion process)")
        print("Commands: demo, verify, review; explicit --enable-google: auth, sheets.")
        print("Example: python -m companions.doi_intake demo")
        print("No source writes, Order Admin access, or synthetic database changes.")
        return 0
    try:
        if argv[0] == "review":
            p = argparse.ArgumentParser(description="Validate a queue without authorizing execution.")
            p.add_argument("folder", type=Path)
            p.add_argument("--run-id", required=True)
            p.add_argument("--source-date", required=True)
            p.add_argument("--max-age-hours", type=int, default=4)
            p.add_argument("--allow-synthetic", action="store_true")
            args = p.parse_args(argv[1:])
            outside_repository(args.folder)
            result = load_review_queue(
                args.folder, expected_run_id=args.run_id,
                expected_source_date=args.source_date,
                max_age_hours=args.max_age_hours, allow_synthetic=args.allow_synthetic,
            )
            print(json.dumps(result, indent=2))
            return 0
        if argv[0] in {"auth", "sheets"} and not enable_google:
            raise intake.IntakeError(
                "GOOGLE_NOT_ENABLED",
                "Live reads require --enable-google before auth or sheets. Nothing was accessed.",
            )
        args = intake.parser().parse_args(argv)
        for name in ("out", "token", "history", "client_secret", "folder"):
            value = getattr(args, name, None)
            if value is not None:
                outside_repository(value)
        return intake.main(argv)
    except intake.IntakeError as exc:
        print(json.dumps({"status": "BLOCKED", "error_code": exc.code,
                          "message": exc.message, "execution_authorized": False}),
              file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        print(json.dumps({"status": "BLOCKED", "error_code": "INTEGRATION_INPUT_INVALID",
                          "execution_authorized": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
