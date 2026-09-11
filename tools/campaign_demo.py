"""Launch the integrated synthetic campaign demo in a fresh explicit local data root."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_sales_assist.campaign_replies.application import WorkspaceApplication  # noqa: E402
from synthetic_sales_assist.persistence.paths import resolve_data_paths  # noqa: E402
from synthetic_sales_assist.portal.server import open_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    paths = resolve_data_paths(args.data_dir)
    paths.ensure_directories()
    workspace = WorkspaceApplication(paths.data / "campaign_replies.sqlite3")
    workspace.post({"action": "demo"})
    if args.prepare_only:
        print("SYNTHETIC_CAMPAIGN_DEMO_PREPARED")
        return 0
    runtime = open_runtime(
        data_dir=args.data_dir,
        receipt_path=paths.runtime / "service.json",
        port=args.port,
    )
    try:
        receipt = runtime.start()
        print(f"SYNTHETIC_DEMO_READY {receipt.origin}/campaigns", flush=True)
        print("Local drafts only. Press Ctrl+C to stop this demo process.", flush=True)
        runtime.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
