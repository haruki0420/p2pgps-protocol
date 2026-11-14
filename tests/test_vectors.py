"""テストベクタ（``tests/vectors/*.json``）の検証。

仕様 §10 の全カテゴリがベクタとして存在すること、および期待 hex と実装が
一致することを確認する。iOS / Android 実装もこの JSON をそのまま使える。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from p2pgps.protocol import (
    ControlCommand,
    ControlLengthError,
    ExtendedPacket,
    LocationPacket,
    Status,
    UnknownOpcodeError,
    ValidationError,
    from_hex,
)
from p2pgps.vectors import (
    check_control_vector,
    check_extended_vector,
    check_location_vector,
    check_sequence_scenario,
    check_status_vector,
    load_vector_files,
    run_vectors,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "spec" / "protocol-v1.md"


def _ids(vectors: list[dict[str, Any]]) -> list[str]:
    return [str(vector["id"]) for vector in vectors]


# ---------------------------------------------------------------------------
# Location Packet ベクタ
# ---------------------------------------------------------------------------


def test_location_vectors_encode_decode(location_vectors: list[dict[str, Any]]) -> None:
    for vector in location_vectors:
        wire = vector["wire"]
        expected_hex = vector["hex"]
        packet = LocationPacket(**wire)
        assert packet.encode().hex() == expected_hex, vector["id"]
        decoded = LocationPacket.decode(from_hex(expected_hex))
        assert decoded.to_dict() == wire, vector["id"]


def test_location_vectors_validation(location_vectors: list[dict[str, Any]]) -> None:
    for vector in location_vectors:
        decoded = LocationPacket.decode(from_hex(vector["hex"]))
        expect = vector["expect"]
        if expect["valid"]:
            decoded.validate()
        else:
            with pytest.raises(ValidationError) as excinfo:
                decoded.validate()
            assert str(excinfo.value.reason) == expect["reason"], vector["id"]
        assert decoded.has_valid_fix == expect["valid_fix"], vector["id"]


def test_location_vectors_degrees(location_vectors: list[dict[str, Any]]) -> None:
    for vector in location_vectors:
        degrees = vector.get("degrees")
        if degrees is None:
            continue
        wire = vector["wire"]
        remaining = {
            key: value
            for key, value in wire.items()
            if key not in ("latitude", "longitude")
        }
        packet = LocationPacket.from_degrees(
            degrees["latitude"], degrees["longitude"], **remaining
        )
        assert packet.latitude == wire["latitude"], vector["id"]
        assert packet.longitude == wire["longitude"], vector["id"]
        assert packet.encode().hex() == vector["hex"], vector["id"]


def test_location_vectors_checker(location_vectors: list[dict[str, Any]]) -> None:
    for vector in location_vectors:
        assert check_location_vector(vector) == [], vector["id"]


def test_spec_3_2_example_vector(location_vectors: list[dict[str, Any]]) -> None:
    """仕様 §3.2 のエンコード例がベクタと一致する（正本との突き合わせ）。"""
    vector = next(
        item for item in location_vectors if item["id"] == "tokyo-station-spec-3-2"
    )
    assert vector["hex"] == "01032a004886441552c54e530300050000521769"
    # 仕様書に記載された hex を正規化して比較する
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    assert "01032a004886441552c54e530300050000521769" in spec_text.replace(
        " ", ""
    ).lower()


# ---------------------------------------------------------------------------
# Extended Location ベクタ
# ---------------------------------------------------------------------------


def test_extended_vectors_encode_decode(
    extended_vectors: list[dict[str, Any]],
) -> None:
    for vector in extended_vectors:
        packet = ExtendedPacket(**vector["wire"])
        assert packet.encode().hex() == vector["hex"], vector["id"]
        decoded = ExtendedPacket.decode(from_hex(vector["hex"]))
        assert decoded.to_dict() == vector["wire"], vector["id"]
        assert check_extended_vector(vector) == [], vector["id"]


def test_extended_vectors_validation(extended_vectors: list[dict[str, Any]]) -> None:
    for vector in extended_vectors:
        decoded = ExtendedPacket.decode(from_hex(vector["hex"]))
        expect = vector["expect"]
        if expect["valid"]:
            decoded.validate()
        else:
            with pytest.raises(ValidationError) as excinfo:
                decoded.validate()
            assert str(excinfo.value.reason) == expect["reason"], vector["id"]


# ---------------------------------------------------------------------------
# Control ベクタ
# ---------------------------------------------------------------------------


def test_control_vectors(control_vectors: list[dict[str, Any]]) -> None:
    for vector in control_vectors:
        expect = vector["expect"]
        if expect["valid"]:
            command = ControlCommand.from_dict(vector["command"])
            assert command.encode().hex() == vector["hex"], vector["id"]
            decoded = ControlCommand.decode(from_hex(vector["hex"]))
            assert decoded.to_dict() == {
                key: value
                for key, value in expect["decoded"].items()
                if key != "normalized_interval_ms"
            }, vector["id"]
            if "normalized_interval_ms" in expect["decoded"]:
                assert (
                    decoded.normalized_interval_ms
                    == expect["decoded"]["normalized_interval_ms"]
                ), vector["id"]
        else:
            expected_error = expect["error"]
            with pytest.raises((UnknownOpcodeError, ControlLengthError)) as excinfo:
                ControlCommand.decode(from_hex(vector["hex"]))
            error = excinfo.value
            assert error.last_error == expect["last_error"], vector["id"]
            if expected_error == "unknown_opcode":
                assert isinstance(error, UnknownOpcodeError), vector["id"]
            else:
                assert isinstance(error, ControlLengthError), vector["id"]
        assert check_control_vector(vector) == [], vector["id"]


def test_control_vectors_cover_all_opcodes(
    control_vectors: list[dict[str, Any]],
) -> None:
    opcodes = {
        vector["command"]["opcode"]
        for vector in control_vectors
        if vector.get("command")
    }
    assert opcodes == {
        "START",
        "STOP",
        "SET_INTERVAL",
        "REQUEST_FIX",
        "SET_EXTENDED",
        "RESET",
    }


def test_control_vectors_cover_interval_boundaries(
    control_vectors: list[dict[str, Any]],
) -> None:
    """仕様 §5.1 の境界値（0/1/99/100/60000/60001/65535）を網羅する。"""
    ids = {vector["id"] for vector in control_vectors}
    for expected_id in (
        "control-start-default",
        "control-start-1",
        "control-start-99",
        "control-start-100",
        "control-start-60000",
        "control-start-60001",
        "control-start-65535",
    ):
        assert expected_id in ids

    for vector in control_vectors:
        command = vector.get("command")
        if not command or "interval_ms" not in command:
            continue
        raw = command["interval_ms"]
        # hex は生値（opcode 1 byte + uint16 LE）
        assert bytes.fromhex(vector["hex"])[1:] == raw.to_bytes(2, "little"), vector["id"]
        assert vector["expect"]["decoded"]["interval_ms"] == raw, vector["id"]
        # normalized_interval_ms は仕様 §5.1 の適用値
        expected_normalized = {
            0: 1000,
            1: 100,
            50: 100,
            99: 100,
            100: 100,
            500: 500,
            1000: 1000,
            60000: 60000,
            60001: 60000,
            65535: 60000,
        }[raw]
        assert (
            vector["expect"]["decoded"]["normalized_interval_ms"]
            == expected_normalized
        ), vector["id"]


# ---------------------------------------------------------------------------
# Status ベクタ
# ---------------------------------------------------------------------------


def test_status_vectors(status_vectors: list[dict[str, Any]]) -> None:
    for vector in status_vectors:
        packet = Status(**vector["wire"])
        assert packet.encode().hex() == vector["hex"], vector["id"]
        decoded = Status.decode(from_hex(vector["hex"]))
        assert decoded.to_dict() == vector["wire"], vector["id"]
        expect = vector["expect"]
        if expect["valid"]:
            decoded.validate()
        else:
            with pytest.raises(ValidationError) as excinfo:
                decoded.validate()
            assert str(excinfo.value.reason) == expect["reason"], vector["id"]
        assert check_status_vector(vector) == [], vector["id"]


# ---------------------------------------------------------------------------
# sequence シナリオ
# ---------------------------------------------------------------------------


def test_sequence_scenarios(sequence_scenarios: list[dict[str, Any]]) -> None:
    from p2pgps.filter import SequenceTracker

    for scenario in sequence_scenarios:
        tracker = SequenceTracker()
        statuses = []
        accepted = []
        for packet_data in scenario["packets"]:
            decoded = LocationPacket.decode(from_hex(packet_data["hex"]))
            accepted.append(decoded.is_valid)
            statuses.append(tracker.observe(decoded.sequence).value)
        assert statuses == scenario["expect"]["sequence_status"], scenario["id"]
        assert accepted == scenario["expect"]["accepted"], scenario["id"]
        assert check_sequence_scenario(scenario) == [], scenario["id"]


# ---------------------------------------------------------------------------
# 仕様 §10 の網羅性
# ---------------------------------------------------------------------------


def test_vectors_cover_spec_section_10(
    location_vectors: list[dict[str, Any]],
    extended_vectors: list[dict[str, Any]],
    control_vectors: list[dict[str, Any]],
    status_vectors: list[dict[str, Any]],
    sequence_scenarios: list[dict[str, Any]],
) -> None:
    location_ids = set(_ids(location_vectors))
    extended_ids = set(_ids(extended_vectors))
    control_ids = set(_ids(control_vectors))
    status_ids = set(_ids(status_vectors))
    sequence_ids = set(_ids(sequence_scenarios))

    # 仕様 §10 の箇条書きに対応するベクタが存在する
    assert "tokyo-station" in location_ids  # 東京駅
    assert "antarctic" in location_ids  # 南極（負の緯度・経度、altitude 負）
    assert "null-island" in location_ids  # Null Island
    assert "out-of-range-latitude" in location_ids  # 範囲外緯度
    assert "unknown-version" in location_ids  # 未知バージョン
    assert "sequence-regression" in sequence_ids  # sequence 巻き戻り
    assert any("extended" in vector_id for vector_id in extended_ids)  # Extended
    assert any("control" in vector_id for vector_id in control_ids)  # Control

    # 主要な flags / 状態もベクタで網羅する
    assert "no-fix" in location_ids
    assert "reserved-flag-set" in location_ids
    assert "out-of-range-longitude" in location_ids
    assert "status-unknown-version" in status_ids


# ---------------------------------------------------------------------------
# ローダ / ランナー
# ---------------------------------------------------------------------------


def test_load_vector_files(vectors_dir: Path) -> None:
    files = load_vector_files(vectors_dir)
    names = {vector_file.path.name for vector_file in files}
    assert names == {
        "location.json",
        "extended.json",
        "control.json",
        "status.json",
        "sequences.json",
    }
    kinds = {vector_file.kind for vector_file in files}
    assert kinds == {"location", "extended", "control", "status", "sequence"}
    for vector_file in files:
        assert vector_file.schema.startswith("p2pgps-protocol/test-vectors/")


def test_run_vectors_all_pass(vectors_dir: Path) -> None:
    results = run_vectors(vectors_dir)
    assert results, "no vectors found"
    failures = [result for result in results if not result.ok]
    assert failures == []
    assert len(results) >= 40


def test_load_vector_files_rejects_bad_schema(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(
        json.dumps({"schema": "wrong", "kind": "location", "vectors": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_vector_files(tmp_path)


def test_load_vector_files_rejects_bad_kind(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(
        json.dumps(
            {"schema": "p2pgps-protocol/test-vectors/x@1", "kind": "bogus"}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_vector_files(tmp_path)
