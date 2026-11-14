"""プロトコル実装の単体テスト（仕様 §1〜§6, §9）。"""

from __future__ import annotations

import struct
from decimal import Decimal

import pytest

from p2pgps.protocol import (
    CCCD_UUID,
    CONTROL_CHARACTERISTIC_UUID,
    DEFAULT_INTERVAL_MS,
    DEVICE_INFORMATION_SERVICE_UUID,
    EXTENDED_CHARACTERISTIC_UUID,
    EXTENDED_PACKET_SIZE,
    LATITUDE_MAX_E7,
    LOCATION_CHARACTERISTIC_UUID,
    LOCATION_FIELD_OFFSETS,
    LOCATION_PACKET_SIZE,
    LOCATION_SCALE,
    LONGITUDE_MAX_E7,
    MAX_INTERVAL_MS,
    MIN_INTERVAL_MS,
    PROTOCOL_VERSION,
    SERVICE_UUID,
    STATUS_CHARACTERISTIC_UUID,
    STATUS_FIELD_OFFSETS,
    STATUS_PACKET_SIZE,
    ControlCommand,
    ControlLengthError,
    ExtendedPacket,
    Flags,
    LastError,
    LocationPacket,
    Opcode,
    PacketLengthError,
    ProtocolError,
    Provider,
    RejectReason,
    State,
    Status,
    StatusFlags,
    UnknownOpcodeError,
    ValidationError,
    WireRangeError,
    decode_packet,
    degrees_to_e7,
    e7_to_degrees,
    from_hex,
    last_error_for_reason,
    normalize_interval_ms,
    packet_kind,
    to_hex,
    uuid_from_le_bytes,
    uuid_to_le_bytes,
)

# ---------------------------------------------------------------------------
# 定数 / UUID（仕様 §1）
# ---------------------------------------------------------------------------

ALL_UUIDS = [
    SERVICE_UUID,
    LOCATION_CHARACTERISTIC_UUID,
    CONTROL_CHARACTERISTIC_UUID,
    STATUS_CHARACTERISTIC_UUID,
    EXTENDED_CHARACTERISTIC_UUID,
    DEVICE_INFORMATION_SERVICE_UUID,
    CCCD_UUID,
]


def test_protocol_version_and_sizes() -> None:
    assert PROTOCOL_VERSION == 0x01
    assert LOCATION_PACKET_SIZE == 20
    assert EXTENDED_PACKET_SIZE == 8
    assert STATUS_PACKET_SIZE == 8
    assert LOCATION_SCALE == 10_000_000


def test_uuids_are_canonical_128bit() -> None:
    for value in ALL_UUIDS:
        assert len(value) == 36
        assert value == value.upper()
        assert uuid_from_le_bytes(uuid_to_le_bytes(value)) == value


def test_uuid_wire_order_is_little_endian() -> None:
    # BLE の 128-bit UUID はバイトオーダーがリトルエンディアン（仕様 §1）
    raw = uuid_to_le_bytes(SERVICE_UUID)
    assert len(raw) == 16
    assert raw[0] == 0x6F  # 文字列末尾の ...5E6F が先頭に来る
    assert raw[-1] == 0xB1  # 文字列先頭の B1 が末尾に来る


def test_uuid_from_le_bytes_rejects_bad_length() -> None:
    with pytest.raises(ValueError):
        uuid_from_le_bytes(b"\x00" * 15)


# ---------------------------------------------------------------------------
# Location Packet のレイアウト（仕様 §3）
# ---------------------------------------------------------------------------


def test_location_field_offsets_match_spec() -> None:
    assert LOCATION_FIELD_OFFSETS == {
        "version": (0, 1),
        "flags": (1, 1),
        "sequence": (2, 2),
        "latitude": (4, 4),
        "longitude": (8, 4),
        "altitude_m": (12, 2),
        "accuracy_m": (14, 1),
        "speed_mps": (15, 1),
        "timestamp": (16, 4),
    }


def test_location_encode_places_each_field_at_spec_offset() -> None:
    packet = LocationPacket(
        version=1,
        flags=0x7F,
        sequence=0x1234,
        latitude=0x01020304,
        longitude=0x05060708,
        altitude_m=-2,
        accuracy_m=0xAA,
        speed_mps=0xBB,
        timestamp=0x0A0B0C0D,
    )
    raw = packet.encode()
    assert len(raw) == 20
    assert raw[0:1] == b"\x01"
    assert raw[1:2] == b"\x7f"
    assert raw[2:4] == b"\x34\x12"
    assert raw[4:8] == b"\x04\x03\x02\x01"
    assert raw[8:12] == b"\x08\x07\x06\x05"
    assert raw[12:14] == b"\xfe\xff"
    assert raw[14:15] == b"\xaa"
    assert raw[15:16] == b"\xbb"
    assert raw[16:20] == b"\x0d\x0c\x0b\x0a"


def test_location_decode_is_inverse_of_encode() -> None:
    packet = LocationPacket(
        flags=int(Flags.VALID_FIX | Flags.ALTITUDE_VALID),
        sequence=42,
        latitude=356812360,
        longitude=1397671250,
        altitude_m=3,
        accuracy_m=5,
        speed_mps=0,
        timestamp=1763136000,
    )
    assert LocationPacket.decode(packet.encode()) == packet
    assert LocationPacket.from_bytes(packet.to_bytes()) == packet


def test_location_defaults() -> None:
    packet = LocationPacket()
    assert packet.version == 1
    assert packet.flags == 0
    assert packet.sequence == 0
    assert packet.accuracy_m == 255
    assert packet.speed_mps == 255
    assert packet.has_valid_fix is False
    assert packet.is_valid is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", 256),
        ("flags", 256),
        ("sequence", 65536),
        ("latitude", 2**31),
        ("longitude", -(2**31) - 1),
        ("altitude_m", 32768),
        ("accuracy_m", 256),
        ("speed_mps", -1),
        ("timestamp", 2**32),
    ],
)
def test_location_encode_rejects_values_outside_wire_range(
    field: str, value: int
) -> None:
    kwargs = {field: value}
    with pytest.raises(WireRangeError):
        LocationPacket(**kwargs).encode()


def test_location_decode_rejects_wrong_length() -> None:
    with pytest.raises(PacketLengthError) as excinfo:
        LocationPacket.decode(b"\x00" * 19)
    assert excinfo.value.expected == 20
    assert excinfo.value.actual == 19
    with pytest.raises(PacketLengthError):
        LocationPacket.decode(b"\x00" * 21)


def test_location_boundary_values_roundtrip() -> None:
    packet = LocationPacket(
        flags=0x7F,
        sequence=65535,
        latitude=900000000,
        longitude=180000000,
        altitude_m=32767,
        accuracy_m=255,
        speed_mps=255,
        timestamp=4294967295,
    )
    assert LocationPacket.decode(packet.encode()) == packet
    packet = LocationPacket(
        flags=0,
        sequence=0,
        latitude=-900000000,
        longitude=-180000000,
        altitude_m=-32768,
        accuracy_m=0,
        speed_mps=0,
        timestamp=0,
    )
    assert LocationPacket.decode(packet.encode()) == packet


# ---------------------------------------------------------------------------
# Location Packet の検証（仕様 §3.3）
# ---------------------------------------------------------------------------


def _valid_packet(**overrides: object) -> LocationPacket:
    kwargs: dict[str, object] = {
        "flags": int(Flags.VALID_FIX),
        "sequence": 1,
        "latitude": 356812360,
        "longitude": 1397671250,
        "altitude_m": 0,
        "accuracy_m": 5,
        "speed_mps": 0,
        "timestamp": 1763136000,
    }
    kwargs.update(overrides)
    return LocationPacket(**kwargs)  # type: ignore[arg-type]


def test_valid_packet_passes_validation() -> None:
    _valid_packet().validate()
    assert _valid_packet().is_valid is True


def test_unknown_version_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valid_packet(version=2).validate()
    assert excinfo.value.reason == RejectReason.UNKNOWN_VERSION
    assert last_error_for_reason(excinfo.value.reason) == LastError.INTERNAL


def test_reserved_flag_bit_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valid_packet(flags=0x81).validate()
    assert excinfo.value.reason == RejectReason.RESERVED_FLAG_SET


@pytest.mark.parametrize("latitude", [900000001, -900000001, 2**31 - 1])
def test_latitude_out_of_range_is_rejected(latitude: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valid_packet(latitude=latitude).validate()
    assert excinfo.value.reason == RejectReason.LATITUDE_OUT_OF_RANGE


@pytest.mark.parametrize("longitude", [1800000001, -1800000001])
def test_longitude_out_of_range_is_rejected(longitude: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valid_packet(longitude=longitude).validate()
    assert excinfo.value.reason == RejectReason.LONGITUDE_OUT_OF_RANGE


def test_validation_range_matches_e7_scale() -> None:
    # 仕様 §3.3-4 の数値はスケール（度 × 10^7）と整合させる必要がある。
    # 90° = 900_000_000、180° = 1_800_000_000。
    assert LATITUDE_MAX_E7 == 90 * LOCATION_SCALE
    assert LONGITUDE_MAX_E7 == 180 * LOCATION_SCALE
    _valid_packet(latitude=LATITUDE_MAX_E7, longitude=LONGITUDE_MAX_E7).validate()
    _valid_packet(latitude=-LATITUDE_MAX_E7, longitude=-LONGITUDE_MAX_E7).validate()


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(0, 0), (1000, 1000), (-1000, 1000), (1000, -1000), (-1000, -1000)],
)
def test_null_island_is_rejected_when_fix_is_valid(
    latitude: int, longitude: int
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valid_packet(latitude=latitude, longitude=longitude).validate()
    assert excinfo.value.reason == RejectReason.NULL_ISLAND


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(1001, 0), (0, 1001), (-1001, 0), (0, -1001), (2000, 2000)],
)
def test_points_outside_null_island_are_accepted(
    latitude: int, longitude: int
) -> None:
    _valid_packet(latitude=latitude, longitude=longitude).validate()


def test_null_island_is_allowed_when_fix_is_invalid() -> None:
    # VALID_FIX=0 のときは (0,0) でも「未測位」として受理する（仕様 §3.3-5）
    packet = _valid_packet(flags=0, latitude=0, longitude=0)
    packet.validate()
    assert packet.has_valid_fix is False
    assert packet.is_null_island is True


def test_validation_error_reason_is_str_enum() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _valid_packet(version=2).validate()
    assert excinfo.value.reason == "unknown_version"


# ---------------------------------------------------------------------------
# 度 <-> ワイヤ値（仕様 §3）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [
        ("35.6812360", 356812360),
        ("139.7671250", 1397671250),
        ("-89.9999999", -899999999),
        ("-180.0000000", -1800000000),
        ("0.0000000", 0),
        ("0.0000001", 1),
        ("-0.0000001", -1),
        (35.681236, 356812360),
        (Decimal("35.6812360"), 356812360),
    ],
)
def test_degrees_to_e7(degrees: object, expected: int) -> None:
    assert degrees_to_e7(degrees) == expected  # type: ignore[arg-type]


def test_degrees_to_e7_rounds_half_away_from_zero() -> None:
    assert degrees_to_e7("0.00000005") == 1
    assert degrees_to_e7("-0.00000005") == -1
    assert degrees_to_e7("35.68123605") == 356812361


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), Decimal("NaN"), Decimal("Infinity")],
)
def test_degrees_to_e7_rejects_non_finite(value: object) -> None:
    # L-21: NaN / inf は traceback ではなく ProtocolError にする
    with pytest.raises(ProtocolError):
        degrees_to_e7(value)  # type: ignore[arg-type]


def test_e7_to_degrees() -> None:
    assert e7_to_degrees(356812360) == Decimal("35.681236")
    assert e7_to_degrees(-899999999) == Decimal("-89.9999999")


def test_location_packet_from_degrees() -> None:
    packet = LocationPacket.from_degrees(
        "35.6812360",
        "139.7671250",
        flags=int(Flags.VALID_FIX | Flags.ALTITUDE_VALID),
        sequence=42,
        altitude_m=3,
        accuracy_m=5,
        speed_mps=0,
        timestamp=1763136000,
    )
    assert packet.latitude == 356812360
    assert packet.longitude == 1397671250
    assert packet.latitude_degrees == Decimal("35.681236")
    assert packet.to_degrees() == (Decimal("35.681236"), Decimal("139.767125"))


def test_location_to_dict_and_from_dict() -> None:
    packet = _valid_packet()
    data = packet.to_dict()
    assert set(data) == set(LOCATION_FIELD_OFFSETS)
    assert LocationPacket.from_dict(data) == packet


def test_location_readable_dict() -> None:
    readable = _valid_packet(flags=0x07).to_readable_dict()
    assert Decimal(readable["latitude_deg"]) == Decimal("35.681236")
    assert readable["valid_fix"] is True
    assert "VALID_FIX" in readable["flags_decoded"]
    assert "ALTITUDE_VALID" in readable["flags_decoded"]
    assert "SPEED_VALID" in readable["flags_decoded"]


# ---------------------------------------------------------------------------
# Extended Location Packet（仕様 §4）
# ---------------------------------------------------------------------------


def test_extended_field_offsets_match_spec() -> None:
    assert EXTENDED_PACKET_SIZE == 8
    raw = ExtendedPacket(
        version=1,
        provider=int(Provider.GPS),
        battery_pct=87,
        satellites=12,
        course=12345,
        vertical_accuracy_m=5,
        reserved=0,
    ).encode()
    assert raw == bytes.fromhex("0101570c39300500")


def test_extended_roundtrip() -> None:
    packet = ExtendedPacket(
        provider=int(Provider.FUSED),
        battery_pct=42,
        satellites=9,
        course=35999,
        vertical_accuracy_m=12,
    )
    assert ExtendedPacket.decode(packet.encode()) == packet
    assert packet.provider_name == "FUSED"
    assert packet.course_degrees == Decimal("359.99")


def test_extended_unknown_values() -> None:
    packet = ExtendedPacket()
    assert packet.battery_pct == 255
    assert packet.satellites == 255
    assert packet.course == 65535
    assert packet.course_degrees is None
    assert packet.provider_name == "UNKNOWN"
    assert packet.is_valid is True


def test_extended_validation() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ExtendedPacket(version=2).validate()
    assert excinfo.value.reason == RejectReason.UNKNOWN_VERSION
    with pytest.raises(ValidationError):
        ExtendedPacket(battery_pct=101).validate()
    with pytest.raises(ValidationError):
        ExtendedPacket(course=36000).validate()
    # reserved は将来互換のため無視する
    ExtendedPacket(reserved=0xFF).validate()


def test_extended_decode_rejects_wrong_length() -> None:
    with pytest.raises(PacketLengthError):
        ExtendedPacket.decode(b"\x00" * 7)


# ---------------------------------------------------------------------------
# Control characteristic（仕様 §5）
# ---------------------------------------------------------------------------


def test_control_opcode_values_match_spec() -> None:
    assert int(Opcode.START) == 0x01
    assert int(Opcode.STOP) == 0x02
    assert int(Opcode.SET_INTERVAL) == 0x03
    assert int(Opcode.REQUEST_FIX) == 0x04
    assert int(Opcode.SET_EXTENDED) == 0x05
    assert int(Opcode.AUTH) == 0x10
    assert int(Opcode.RESET) == 0x7F


@pytest.mark.parametrize(
    ("command", "expected_hex"),
    [
        # 仕様 §5.1: encode は生値をそのまま書く（正規化しない）
        (ControlCommand.start(0), "010000"),
        (ControlCommand.start(1), "010100"),
        (ControlCommand.start(50), "013200"),
        (ControlCommand.start(99), "016300"),
        (ControlCommand.start(100), "016400"),
        (ControlCommand.start(1000), "01e803"),
        (ControlCommand.start(60000), "0160ea"),
        (ControlCommand.start(60001), "0161ea"),
        (ControlCommand.start(65535), "01ffff"),
        (ControlCommand.stop(), "02"),
        (ControlCommand.set_interval(0), "030000"),
        (ControlCommand.set_interval(500), "03f401"),
        (ControlCommand.set_interval(60001), "0361ea"),
        (ControlCommand.request_fix(), "04"),
        (ControlCommand.set_extended(True), "0501"),
        (ControlCommand.set_extended(False), "0500"),
        (ControlCommand.reset(), "7f"),
    ],
)
def test_control_encode(command: ControlCommand, expected_hex: str) -> None:
    assert command.encode().hex() == expected_hex


def test_control_encode_requires_interval() -> None:
    # L-20: START / SET_INTERVAL の interval_ms は必須 payload
    for command in (
        ControlCommand(opcode=int(Opcode.START)),
        ControlCommand(opcode=int(Opcode.SET_INTERVAL)),
    ):
        with pytest.raises(ValueError):
            command.encode()


@pytest.mark.parametrize("raw", [-1, 65536])
def test_control_encode_rejects_out_of_uint16(raw: int) -> None:
    with pytest.raises(WireRangeError):
        ControlCommand.start(raw).encode()


@pytest.mark.parametrize(
    ("hex_value", "opcode", "interval_ms", "enabled"),
    [
        ("01e803", Opcode.START, 1000, None),
        ("016400", Opcode.START, 100, None),
        ("02", Opcode.STOP, None, None),
        ("03f401", Opcode.SET_INTERVAL, 500, None),
        ("04", Opcode.REQUEST_FIX, None, None),
        ("0501", Opcode.SET_EXTENDED, None, True),
        ("0500", Opcode.SET_EXTENDED, None, False),
        ("7f", Opcode.RESET, None, None),
    ],
)
def test_control_decode(
    hex_value: str,
    opcode: Opcode,
    interval_ms: int | None,
    enabled: bool | None,
) -> None:
    command = ControlCommand.decode(from_hex(hex_value))
    assert command.opcode == int(opcode)
    assert command.name == opcode.name
    assert command.interval_ms == interval_ms
    assert command.enabled is enabled


def test_control_decode_keeps_raw_interval_and_normalizes() -> None:
    # 生値はそのまま保持し、送信側が適用する値を normalized_interval_ms で示す
    command = ControlCommand.decode(from_hex("013200"))  # 生値 50 ms
    assert command.interval_ms == 50
    assert command.normalized_interval_ms == 100  # 仕様 §5.1: 下限 100
    # encode は生値をそのまま書く（正規化しない）
    assert command.encode().hex() == "013200"


@pytest.mark.parametrize("hex_value", ["10", "ff", "00"])
def test_control_unknown_opcode(hex_value: str) -> None:
    with pytest.raises(UnknownOpcodeError) as excinfo:
        ControlCommand.decode(from_hex(hex_value))
    assert excinfo.value.last_error == LastError.UNKNOWN_OPCODE
    assert excinfo.value.opcode == int(hex_value, 16)


@pytest.mark.parametrize("hex_value", ["", "01", "01e8", "02ff", "050100"])
def test_control_bad_length(hex_value: str) -> None:
    with pytest.raises(ControlLengthError) as excinfo:
        ControlCommand.decode(from_hex(hex_value))
    assert excinfo.value.last_error == LastError.BAD_LENGTH


def test_control_encode_unknown_opcode() -> None:
    with pytest.raises(UnknownOpcodeError):
        ControlCommand(opcode=0x10).encode()  # AUTH は v2 予約
    with pytest.raises(UnknownOpcodeError):
        ControlCommand(opcode=0xFF).encode()


def test_control_from_dict_and_to_dict() -> None:
    command = ControlCommand.from_dict({"opcode": "start", "interval_ms": 1000})
    assert command == ControlCommand.start(1000)
    assert command.to_dict() == {"opcode": "START", "interval_ms": 1000}
    assert command.to_readable_dict()["normalized_interval_ms"] == 1000
    extended = ControlCommand.from_dict({"opcode": "SET_EXTENDED", "enabled": True})
    assert extended.to_dict() == {"opcode": "SET_EXTENDED", "enabled": True}
    assert extended.is_known is True


def test_normalize_interval_ms() -> None:
    # 仕様 §5.1 の境界クランプ表
    assert normalize_interval_ms(0) == 1000  # 既定値
    assert normalize_interval_ms(1) == 100
    assert normalize_interval_ms(50) == 100
    assert normalize_interval_ms(99) == 100
    assert normalize_interval_ms(100) == 100
    assert normalize_interval_ms(101) == 101
    assert normalize_interval_ms(59999) == 59999
    assert normalize_interval_ms(60000) == 60000
    assert normalize_interval_ms(60001) == 60000
    assert normalize_interval_ms(65535) == 60000
    assert MIN_INTERVAL_MS == 100
    assert MAX_INTERVAL_MS == 60000
    assert DEFAULT_INTERVAL_MS == 1000


# ---------------------------------------------------------------------------
# Status characteristic（仕様 §6）
# ---------------------------------------------------------------------------


def test_status_field_offsets_and_encode() -> None:
    assert STATUS_FIELD_OFFSETS == {
        "version": (0, 1),
        "state": (1, 1),
        "interval_ms": (2, 2),
        "battery_pct": (4, 1),
        "status_flags": (5, 1),
        "last_error": (6, 1),
        "reserved": (7, 1),
    }
    status = Status(
        state=int(State.STREAMING),
        interval_ms=1000,
        battery_pct=80,
        status_flags=int(StatusFlags.EXTENDED_ENABLED | StatusFlags.FIX_AVAILABLE),
        last_error=int(LastError.NONE),
    )
    assert status.encode() == bytes.fromhex("0101e80350030000")


def test_status_roundtrip() -> None:
    status = Status(
        state=int(State.ERROR),
        interval_ms=500,
        battery_pct=20,
        status_flags=int(StatusFlags.LOW_BATTERY),
        last_error=int(LastError.LOCATION_UNAVAILABLE),
    )
    decoded = Status.decode(status.encode())
    assert decoded == status
    assert decoded.state_name == "ERROR"
    assert decoded.last_error_name == "LOCATION_UNAVAILABLE"
    assert "LOW_BATTERY" in decoded.to_readable_dict()["status_flags_decoded"]


def test_status_validation() -> None:
    Status().validate()
    with pytest.raises(ValidationError) as excinfo:
        Status(version=2).validate()
    assert excinfo.value.reason == RejectReason.UNKNOWN_VERSION
    assert Status(version=2).is_valid is False


def test_status_from_dict_with_names() -> None:
    status = Status.from_dict(
        {
            "state": "streaming",
            "last_error": "none",
            "interval_ms": 1000,
            "battery_pct": 80,
            "status_flags": 3,
        }
    )
    assert status.state == int(State.STREAMING)
    assert status.last_error == int(LastError.NONE)


def test_status_decode_rejects_wrong_length() -> None:
    with pytest.raises(PacketLengthError):
        Status.decode(b"\x00" * 9)


# ---------------------------------------------------------------------------
# hex ヘルパ / 汎用デコード
# ---------------------------------------------------------------------------


def test_to_hex_and_from_hex() -> None:
    raw = bytes.fromhex("01032a004886441552c54e530300050000521769")
    assert to_hex(raw, sep="") == raw.hex()
    assert to_hex(raw) == " ".join(f"{b:02x}" for b in raw)
    for text in (
        raw.hex(),
        to_hex(raw),
        to_hex(raw).upper(),
        ":".join(f"{b:02x}" for b in raw),
        "0x" + raw.hex(),
    ):
        assert from_hex(text) == raw


@pytest.mark.parametrize("text", ["0", "abc", "zz", "01 0g"])
def test_from_hex_rejects_invalid_input(text: str) -> None:
    with pytest.raises(ValueError):
        from_hex(text)


def test_from_hex_rejects_non_string() -> None:
    with pytest.raises(TypeError):
        from_hex(123)  # type: ignore[arg-type]


def test_decode_packet_auto_detection() -> None:
    location = LocationPacket(flags=1, latitude=356812360, longitude=1397671250)
    assert packet_kind(decode_packet(location.encode())) == "location"
    status = Status()
    assert packet_kind(decode_packet(status.encode())) == "status"
    control = ControlCommand.stop()
    assert packet_kind(decode_packet(control.encode())) == "control"
    extended = ExtendedPacket()
    assert packet_kind(decode_packet(extended.encode(), kind="extended")) == "extended"


def test_decode_packet_rejects_bad_length() -> None:
    with pytest.raises(PacketLengthError):
        decode_packet(b"\x00" * 5)
    with pytest.raises(ValueError):
        decode_packet(b"\x00" * 20, kind="bogus")


def test_last_error_for_reason() -> None:
    assert last_error_for_reason(RejectReason.BAD_LENGTH) == LastError.BAD_LENGTH
    assert last_error_for_reason(RejectReason.UNKNOWN_VERSION) == LastError.INTERNAL
    assert (
        last_error_for_reason(RejectReason.NULL_ISLAND)
        == LastError.LOCATION_UNAVAILABLE
    )


def test_location_struct_is_20_bytes() -> None:
    assert struct.calcsize("<BBHiihBBI") == 20
