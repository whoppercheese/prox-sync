from __future__ import annotations

import sys

from sync.config import Settings
from sync.engine import sync
from sync.logger import setup_logging
from sync.parser import ConflictError


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    setup_logging(level=settings.LOG_LEVEL)

    try:
        sync(settings)
    except ConflictError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
