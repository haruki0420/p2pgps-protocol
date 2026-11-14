"""CLI（``python -m p2pgps``）の統合テスト。

subprocess で実際に ``python -m p2pgps`` を起動し、CI（Ubuntu / Windows）で
同じ挙動になることを確認する。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent

TOKYO_SPEC_HEX = "01032a004886441552c54e530300050000521769"


def run_cli(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "p2pgps", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def parse_json_output(result: subprocess.CompletedProcess[str]) -> Any:
    assert result.stdout.strip(), f"no stdout (stderr={result.stderr!r})"
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# 基本
# ---------------------------------------------------------------------------


def test_module_help() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    for command in ("encode", "decode", "vectors", "serve", "scan"):
        assert command in result.stdout


def test_version() -> None:
    result = run_cli("--version")
    assert result.returncode == 0
    assert "1.0.0" in result.stdout


# ---------------------------------------------------------------------------
# encode
# ---------------------------------------------------------------------------


def test_encode_location_matches_spec_example() -> None:
    result = run_cli(
        "encode",
        "--lat", "35.6812360",
        "--lon", "139.7671250",
        "--flags", "3",
        "--seq", "42",
        "--alt", "3",
        "--acc", "5",
        "--speed", "0",
        "--ts", "1763136000",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == TOKYO_SPEC_HEX


def test_encode_location_json() -> None:
    result = run_cli(
        "encode",
        "--lat", "35.6812360",
        "--lon", "139.7671250",
        "--flags", "7",
        "--seq", "42",
        "--alt", "3",
        "--acc", "5",
        "--speed", "12",
        "--ts", "1763136000",
        "--json",
    )
    payload = parse_json_output(result)
    assert result.returncode == 0
    assert payload["kind"] == "location"
    assert payload["hex"] == "01072a004886441552c54e530300050c00521769"
    assert payload["fields"]["latitude"] == 356812360
    assert payload["decoded"]["latitude_deg"].startswith("35.681236")
    assert payload["valid"] is True


def test_encode_control() -> None:
    result = run_cli("encode", "--kind", "control", "--opcode", "START", "--interval-ms", "1000")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "01e803"
    result = run_cli("encode", "--kind", "control", "--opcode", "reset")
    assert result.stdout.strip() == "7f"


def test_encode_extended() -> None:
    result = run_cli(
        "encode",
        "--kind", "extended",
        "--provider", "gps",
        "--battery", "87",
        "--satellites", "12",
        "--course", "12345",
        "--vacc", "5",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0101570c39300500"


def test_encode_status() -> None:
    result = run_cli(
        "encode",
        "--kind", "status",
        "--state", "streaming",
        "--interval-ms", "1000",
        "--battery", "80",
        "--status-flags", "3",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0101e80350030000"


def test_encode_location_requires_lat_lon() -> None:
    result = run_cli("encode", "--lat", "35.0")
    assert result.returncode == 2
    assert "requires --lat and --lon" in result.stderr


def test_encode_unknown_opcode_fails() -> None:
    result = run_cli("encode", "--kind", "control", "--opcode", "0x10")
    assert result.returncode == 2
    assert "unknown control opcode" in result.stderr


# ---------------------------------------------------------------------------
# decode
# ---------------------------------------------------------------------------


def test_decode_location() -> None:
    result = run_cli("decode", "--hex", TOKYO_SPEC_HEX)
    payload = parse_json_output(result)
    assert result.returncode == 0
    assert payload["kind"] == "location"
    assert payload["valid"] is True
    assert payload["fields"]["latitude"] == 356812360
    assert payload["fields"]["longitude"] == 1397671250
    assert payload["fields"]["altitude_m"] == 3
    assert payload["decoded"]["flags_decoded"] == ["VALID_FIX", "ALTITUDE_VALID"]


def test_decode_accepts_spaced_hex() -> None:
    spaced = " ".join(TOKYO_SPEC_HEX[i : i + 2] for i in range(0, 40, 2))
    result = run_cli("decode", "--hex", spaced)
    assert result.returncode == 0
    assert parse_json_output(result)["valid"] is True


def test_decode_null_island_is_invalid(location_vectors: list[dict[str, Any]]) -> None:
    vector = next(item for item in location_vectors if item["id"] == "null-island")
    result = run_cli("decode", "--hex", vector["hex"])
    payload = parse_json_output(result)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["reason"] == "null_island"


def test_decode_unknown_opcode() -> None:
    result = run_cli("decode", "--hex", "10", "--kind", "control")
    payload = parse_json_output(result)
    assert result.returncode == 2
    assert payload["error"] == "UnknownOpcodeError"
    assert payload["last_error"] == 1


def test_decode_bad_length() -> None:
    result = run_cli("decode", "--hex", "01e8", "--kind", "control")
    payload = parse_json_output(result)
    assert result.returncode == 2
    assert payload["error"] == "ControlLengthError"
    assert payload["last_error"] == 2


def test_decode_extended_requires_kind() -> None:
    result = run_cli("decode", "--hex", "0101570c39300500", "--kind", "extended")
    payload = parse_json_output(result)
    assert result.returncode == 0
    assert payload["kind"] == "extended"
    assert payload["fields"]["provider"] == 1
    assert payload["decoded"]["provider_name"] == "GPS"


def test_decode_auto_8bytes_is_status() -> None:
    result = run_cli("decode", "--hex", "0101e80350030000")
    payload = parse_json_output(result)
    assert result.returncode == 0
    assert payload["kind"] == "status"


def test_decode_invalid_hex() -> None:
    result = run_cli("decode", "--hex", "zz")
    assert result.returncode == 2
    assert "invalid hex" in result.stderr


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------


def test_vectors_command() -> None:
    result = run_cli("vectors")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "location.json" in result.stdout
    assert "total:" in result.stdout
    assert "passed" in result.stdout


def test_vectors_command_json() -> None:
    result = run_cli("vectors", "--json")
    payload = parse_json_output(result)
    assert result.returncode == 0
    assert payload["total"] >= 40
    assert payload["passed"] == payload["total"]
    assert all(item["ok"] for item in payload["results"])


# ---------------------------------------------------------------------------
# serve（stdout バックエンド）
# ---------------------------------------------------------------------------


def test_serve_stdout() -> None:
    result = run_cli(
        "serve", "--stdout", "--count", "2", "--interval", "0.01", "--seq-start", "10"
    )
    assert result.returncode == 0, result.stderr
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    for line in lines:
        assert len(line) == 40
        assert all(char in "0123456789abcdef" for char in line)
    first = bytes.fromhex(lines[0])
    second = bytes.fromhex(lines[1])
    assert first[0] == 1
    assert first[2] | (first[3] << 8) == 10
    assert second[2] | (second[3] << 8) == 11
    # 既定 flags = VALID_FIX | SIMULATED
    assert first[1] == 0x09
    # 緯度経度は既定で東京駅
    assert int.from_bytes(first[4:8], "little", signed=True) == 356812360


def test_serve_rejects_bad_interval() -> None:
    result = run_cli("serve", "--stdout", "--interval", "0", "--count", "1")
    assert result.returncode == 2
    assert "--interval must be > 0" in result.stderr


# ---------------------------------------------------------------------------
# scan（bleak 未インストール時の挙動）
# ---------------------------------------------------------------------------


def test_scan_without_bleak_reports_helpful_error() -> None:
    try:
        import bleak  # noqa: F401
    except ImportError:
        pass
    else:  # pragma: no cover - CI では bleak を入れない
        pytest.skip("bleak is installed; error path is not exercised")
    result = run_cli("scan")
    assert result.returncode == 2
    assert "bleak is not installed" in result.stderr
    assert "p2pgps-protocol[ble]" in result.stderr
