"""Run the dependency-free foundation and Shared Domain Engine test suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))


def main(test_names: list[str] | None = None) -> int:
    names = test_names if test_names is not None else sys.argv[1:]
    if names:
        suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    else:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
