"""正本仕様（``spec/protocol-v1.md``）と実装定数の整合性テスト。

仕様書の表記（UUID・opcode・flags・サイズ・§3.2 の例）が実装からずれたら
CI で検出するためのガード。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from p2pgps.protocol import (
    CCCD_UUID,
    CONTROL_CHARACTERISTIC_UUID,
    DEVICE_INFORMATION_SERVICE_UUID,
    EXTENDED_CHARACTERISTIC_UUID,
    FIRMWARE_REVISION_UUID,
    LOCATION_CHARACTERISTIC_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SERVICE_UUID,
    STATUS_CHARACTERISTIC_UUID,
    ControlCommand,
    ExtendedPacket,
    Flags,
    LastError,
    LocationPacket,
    Opcode,
    Provider,
    State,
    Status,
    StatusFlags,
    normalize_interval_ms,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "spec" / "protocol-v1.md"

UUID_PATTERN = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)


@pytest.fixture(scope="module")
def spec_text() -> str:
    assert SPEC_PATH.is_file(), f"canonical spec not found: {SPEC_PATH}"
    return SPEC_PATH.read_text(encoding="utf-8")


def test_spec_declares_itself_canonical(spec_text: str) -> None:
    assert "正本" in spec_text
    assert "protocol-v1" in spec_text or "プロトコル仕様 v1" in spec_text


def test_spec_contains_all_uuids(spec_text: str) -> None:
    uuids = {match.upper() for match in UUID_PATTERN.findall(spec_text)}
    expected = {
        SERVICE_UUID,
        LOCATION_CHARACTERISTIC_UUID,
        CONTROL_CHARACTERISTIC_UUID,
        STATUS_CHARACTERISTIC_UUID,
        EXTENDED_CHARACTERISTIC_UUID,
        DEVICE_INFORMATION_SERVICE_UUID,
        MANUFACTURER_NAME_UUID,
        MODEL_NUMBER_UUID,
        FIRMWARE_REVISION_UUID,
    }
    missing = expected - uuids
    assert missing == set(), f"UUIDs missing from spec: {sorted(missing)}"
    # CCCD は仕様 §1.1 ではショート UUID (0x2902) として言及される
    assert CCCD_UUID.endswith("2902-0000-1000-8000-00805F9B34FB")
    assert "0x2902" in spec_text


def test_spec_contains_all_sections(spec_text: str) -> None:
    for heading in (
        "## 1. 識別子",
        "## 2. バイトオーダー",
        "## 3. Location Packet",
        "## 4. Extended Location Packet",
        "## 5. Control characteristic",
        "## 6. Status characteristic",
        "## 7. シーケンス",
        "## 8. セキュリティ",
        "## 9. バージョニング",
        "## 10. テストベクタ",
    ):
        assert heading in spec_text, f"missing section: {heading}"


def test_spec_3_2_example_matches_implementation(spec_text: str) -> None:
    packet = LocationPacket(
        version=1,
        flags=int(Flags.VALID_FIX | Flags.ALTITUDE_VALID),
        sequence=42,
        latitude=356812360,
        longitude=1397671250,
        altitude_m=3,
        accuracy_m=5,
        speed_mps=0,
        timestamp=1763136000,
    )
    expected = packet.encode().hex()
    normalized_spec = spec_text.replace(" ", "").replace("\n", "").lower()
    assert expected in normalized_spec, (
        f"spec §3.2 example does not match implementation: {expected}"
    )


def test_spec_contains_flags_and_opcodes(spec_text: str) -> None:
    for flag in Flags:
        assert flag.name in spec_text, f"flag missing from spec: {flag.name}"
    for opcode in Opcode:
        if opcode is Opcode.AUTH:
            continue
        assert f"`0x{int(opcode):02X}`" in spec_text, (
            f"opcode missing from spec: {opcode.name}"
        )
    # AUTH は v2 予約として仕様に明記されている
    assert "0x10" in spec_text

    lowered = spec_text.lower()
    provider_phrases = {
        "UNKNOWN": "unknown",
        "GPS": "gps",
        "NETWORK": "network",
        "FUSED": "fused",
        "MANUAL_SIMULATED": "manual/simulated",
    }
    for provider in Provider:
        phrase = provider_phrases[provider.name]
        assert phrase in lowered, f"provider missing from spec: {provider.name}"
    for state in State:
        assert state.name.lower() in lowered, f"state missing from spec: {state.name}"
    error_phrases = {
        "NONE": "none",
        "UNKNOWN_OPCODE": "unknown opcode",
        "BAD_LENGTH": "bad length",
        "LOCATION_UNAVAILABLE": "location unavailable",
        "INTERNAL": "internal",
    }
    for error in LastError:
        phrase = error_phrases[error.name]
        assert phrase in lowered, f"last_error missing from spec: {error.name}"
    status_flag_phrases = {
        "EXTENDED_ENABLED": "extended enabled",
        "FIX_AVAILABLE": "fix available",
        "CHARGING": "charging",
        "LOW_BATTERY": "low battery",
    }
    for status_flag in StatusFlags:
        phrase = status_flag_phrases[status_flag.name]
        assert phrase in lowered, f"status flag missing from spec: {status_flag.name}"


def test_spec_contains_sizes(spec_text: str) -> None:
    assert "20 bytes" in spec_text
    assert "8 bytes" in spec_text
    assert "リトルエンディアン" in spec_text


def test_spec_validation_range_matches_constants(spec_text: str) -> None:
    # 仕様 §3.3-4 のレンジはスケール（度 × 10^7）と一致していること
    assert "-900_000_000 <= latitude <= 900_000_000" in spec_text
    assert "-1_800_000_000 <= longitude <= 1_800_000_000" in spec_text


def test_spec_contains_control_payload_sizes(spec_text: str) -> None:
    # Control は 1〜3 bytes、Status / Extended は 8 bytes 固定
    assert "1〜3 bytes" in spec_text
    assert "固定 8 bytes" in spec_text


def test_spec_interval_normalization_matches_implementation(spec_text: str) -> None:
    """仕様 §5.1（v1.0.1）の境界クランプ表と実装が一致する。"""
    assert "### 5.1" in spec_text
    assert "v1.0.1" in spec_text
    for row in (
        "| `0` | `1000`（既定値） |",
        "| `1`–`99` | `100`（下限にクランプ） |",
        "| `100`–`60000` | そのまま |",
        "| `60001`–`65535` | `60000`（上限にクランプ） |",
    ):
        assert row in spec_text, f"§5.1 row missing: {row}"

    assert normalize_interval_ms(0) == 1000
    assert normalize_interval_ms(1) == 100
    assert normalize_interval_ms(99) == 100
    assert normalize_interval_ms(100) == 100
    assert normalize_interval_ms(60000) == 60000
    assert normalize_interval_ms(60001) == 60000
    assert normalize_interval_ms(65535) == 60000
    # encode は生値を書く（正規化しない）
    assert ControlCommand.start(50).encode().hex() == "013200"
    assert ControlCommand.start(60001).encode().hex() == "0161ea"


def test_spec_contains_null_island_and_stale_rules(spec_text: str) -> None:
    assert "Null Island" in spec_text
    assert "±24 時間" in spec_text
    assert "sequence" in spec_text


def test_spec_contains_sequence_diagram(spec_text: str) -> None:
    assert "Sender (peripheral)" in spec_text
    assert "Receiver (central)" in spec_text
    assert "notify Location" in spec_text


def test_control_roundtrip_against_spec_opcodes() -> None:
    """仕様 §5 の opcode 表どおりにエンコードできること。"""
    assert ControlCommand.start(1000).encode() == bytes.fromhex("01e803")
    assert ControlCommand.stop().encode() == bytes.fromhex("02")
    assert ControlCommand.set_interval(500).encode() == bytes.fromhex("03f401")
    assert ControlCommand.request_fix().encode() == bytes.fromhex("04")
    assert ControlCommand.set_extended(True).encode() == bytes.fromhex("0501")
    assert ControlCommand.reset().encode() == bytes.fromhex("7f")


def test_extended_and_status_sizes() -> None:
    assert len(ExtendedPacket().encode()) == 8
    assert len(LocationPacket().encode()) == 20
    assert len(Status().encode()) == 8
