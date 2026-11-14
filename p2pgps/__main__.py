"""``python -m p2pgps`` のエントリポイント。"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
