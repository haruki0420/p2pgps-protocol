"""リポジトリのルートを ``sys.path`` に追加する。

``pip install -e .`` をしていない状態でも ``pytest`` が通るようにするための
保険（CI では editable install 済みなので実質不要）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
