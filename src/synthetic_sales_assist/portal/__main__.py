"""Run the owned synthetic localhost portal process."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from synthetic_sales_assist.persistence.paths import PathPolicyError, validate_local_path
from synthetic_sales_assist.portal.lifecycle import PortalLifecycleError
from synthetic_sales_assist.portal.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PortalServerError,
    open_runtime,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--runtime-receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runtime = None
    try:
        receipt_path = validate_local_path(args.runtime_receipt)
        runtime = open_runtime(
            data_dir=args.data_dir,
            receipt_path=receipt_path,
            host=args.host,
            port=args.port,
        )
        receipt = runtime.start()
        print(
            f"Synthetic Sales Assist ready at {receipt.origin} "
            f"(PID {receipt.pid}, schema {receipt.database_schema_version})",
            flush=True,
        )
        runtime.serve_forever()
    except KeyboardInterrupt:
        if runtime is not None:
            runtime.close()
        return 0
    except (PathPolicyError, PortalLifecycleError, PortalServerError) as exc:
        print(f"PORTAL_START_FAILED:{getattr(exc, 'code', type(exc).__name__)}", file=sys.stderr)
        if runtime is not None:
            runtime.close()
        return 1
    except Exception:
        print("PORTAL_START_FAILED:INTERNAL_ERROR", file=sys.stderr)
        if runtime is not None:
            runtime.close()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
