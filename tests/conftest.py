"""pytest 共通フィクスチャ（テストベクタの読み込み）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

VECTORS_DIR = Path(__file__).resolve().parent / "vectors"


def load_vector_file(name: str) -> dict[str, Any]:
    with (VECTORS_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def vectors_dir() -> Path:
    return VECTORS_DIR


@pytest.fixture(scope="session")
def location_vectors() -> list[dict[str, Any]]:
    return load_vector_file("location.json")["vectors"]


@pytest.fixture(scope="session")
def extended_vectors() -> list[dict[str, Any]]:
    return load_vector_file("extended.json")["vectors"]


@pytest.fixture(scope="session")
def control_vectors() -> list[dict[str, Any]]:
    return load_vector_file("control.json")["vectors"]


@pytest.fixture(scope="session")
def status_vectors() -> list[dict[str, Any]]:
    return load_vector_file("status.json")["vectors"]


@pytest.fixture(scope="session")
def sequence_scenarios() -> list[dict[str, Any]]:
    return load_vector_file("sequences.json")["scenarios"]
