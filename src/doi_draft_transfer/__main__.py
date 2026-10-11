"""Run only the separately configured draft-review service."""

from .launch import main

if __name__ == "__main__":
    raise SystemExit(main())
