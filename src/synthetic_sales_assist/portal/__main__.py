"""Run the owned synthetic localhost portal process."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast
from doi_csv_staging.review_policy import load_owner_confirmations, OwnerConfirmationError

from synthetic_sales_assist.persistence.paths import PathPolicyError, validate_local_path
from synthetic_sales_assist.portal.lifecycle import PortalLifecycleError
from synthetic_sales_assist.portal.lifecycle import new_local_token
from synthetic_sales_assist.portal.contracts import ScenarioApplicationProtocol
from synthetic_sales_assist.portal.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PortalServerError,
    open_runtime,
    PortalHTTPServer,
    PortalServerConfig,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--runtime-receipt", type=Path)
    parser.add_argument("--doi-csv-review-only", action="store_true")
    parser.add_argument("--doi-owner-confirmations", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runtime = None
    review_server = None
    try:
        confirmations = load_owner_confirmations(validate_local_path(args.doi_owner_confirmations) if args.doi_owner_confirmations is not None else None)
        if args.doi_csv_review_only:
            if args.data_dir is not None or args.runtime_receipt is not None:
                raise PortalServerError("REVIEW_ONLY_DATA_PATH_PROHIBITED")
            review_server = PortalHTTPServer(
                cast(ScenarioApplicationProtocol, None), PortalServerConfig(args.host, args.port, confirmations),
                csrf_token=new_local_token(), shutdown_token=new_local_token(), doi_csv_review_only=True,
            )
            print(f"DOI CSV review ready at {review_server.origin}/doi-csv-review", flush=True)
            try:
                review_server.serve_forever(poll_interval=0.1)
            finally:
                review_server.server_close()
            return 0
        if args.data_dir is None or args.runtime_receipt is None:
            raise PortalServerError("PORTAL_DATA_PATH_REQUIRED")
        receipt_path = validate_local_path(args.runtime_receipt)
        runtime = open_runtime(
            data_dir=args.data_dir,
            receipt_path=receipt_path,
            host=args.host,
            port=args.port,
            owner_confirmations=confirmations,
        )
        receipt = runtime.start()
        print(
            f"Synthetic Sales Assist ready at {receipt.origin} "
            f"(PID {receipt.pid}, schema {receipt.database_schema_version})",
            flush=True,
        )
        runtime.serve_forever()
    except KeyboardInterrupt:
        if review_server is not None:
            review_server.server_close()
        if runtime is not None:
            runtime.close()
        return 0
    except (PathPolicyError, PortalLifecycleError, PortalServerError, OwnerConfirmationError) as exc:
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
