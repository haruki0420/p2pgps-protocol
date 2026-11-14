"""P2P GPS BLE protocol v1 — reference implementation.

このモジュールは ``spec/protocol-v1.md``（正本）の Python リファレンス実装である。
仕様の数値（オフセット・スケール・flags・opcode）と 1 バイトも違わないことを
``tests/`` で検証している。

設計方針:

* 標準ライブラリのみ（``struct`` / ``dataclasses`` / ``enum`` / ``decimal`` / ``uuid``）。
* すべてのマルチバイト整数は **リトルエンディアン**（仕様 §2）。
* 浮動小数点はワイヤ上に存在しない。緯度経度は int32 の「度 × 10^7」で保持する。
* ``decode()`` はバイト列を忠実にパースし、``validate()`` が仕様 §3.3 の破棄条件を
  判定する（パースと検証を分離することで、不正パケットの診断・テストを可能にする）。
* 例外は :class:`ProtocolError` 系に統一し、受信側の ``Status.last_error`` に
  対応付けられる :attr:`ValidationError.reason` を持つ。
"""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum, IntEnum, IntFlag
from typing import Any, ClassVar, Final, Mapping

__all__ = [
    # バージョン / サイズ
    "PROTOCOL_VERSION",
    "LOCATION_PACKET_SIZE",
    "EXTENDED_PACKET_SIZE",
    "STATUS_PACKET_SIZE",
    "LOCATION_SCALE",
    "LATITUDE_MAX_E7",
    "LONGITUDE_MAX_E7",
    "NULL_ISLAND_E7",
    "DEFAULT_INTERVAL_MS",
    "MIN_INTERVAL_MS",
    "MAX_INTERVAL_MS",
    # UUID
    "SERVICE_UUID",
    "LOCATION_CHARACTERISTIC_UUID",
    "CONTROL_CHARACTERISTIC_UUID",
    "STATUS_CHARACTERISTIC_UUID",
    "EXTENDED_CHARACTERISTIC_UUID",
    "DEVICE_INFORMATION_SERVICE_UUID",
    "MANUFACTURER_NAME_UUID",
    "MODEL_NUMBER_UUID",
    "FIRMWARE_REVISION_UUID",
    "CCCD_UUID",
    "ADVERTISED_NAME_PREFIX",
    "uuid_to_le_bytes",
    "uuid_from_le_bytes",
    # flags / enums
    "Flags",
    "Provider",
    "Opcode",
    "State",
    "StatusFlags",
    "LastError",
    "RejectReason",
    # 例外
    "ProtocolError",
    "PacketLengthError",
    "WireRangeError",
    "ValidationError",
    "UnknownOpcodeError",
    "ControlLengthError",
    # パケット
    "LocationPacket",
    "ExtendedPacket",
    "ControlCommand",
    "Status",
    # ヘルパ
    "to_hex",
    "from_hex",
    "decode_packet",
    "normalize_interval_ms",
    "last_error_for_reason",
    "LOCATION_FIELD_OFFSETS",
    "EXTENDED_FIELD_OFFSETS",
    "STATUS_FIELD_OFFSETS",
]

# ---------------------------------------------------------------------------
# 定数（仕様 §1, §3, §4, §5, §6）
# ---------------------------------------------------------------------------

PROTOCOL_VERSION: Final[int] = 0x01

LOCATION_PACKET_SIZE: Final[int] = 20
EXTENDED_PACKET_SIZE: Final[int] = 8
STATUS_PACKET_SIZE: Final[int] = 8

#: 緯度経度のスケール（度 × 10^7）。仕様 §3。
LOCATION_SCALE: Final[int] = 10_000_000

#: 緯度の有効範囲（±90° × 10^7）。仕様 §3.3-4。
LATITUDE_MAX_E7: Final[int] = 900_000_000
#: 経度の有効範囲（±180° × 10^7）。仕様 §3.3-4。
LONGITUDE_MAX_E7: Final[int] = 1_800_000_000

#: Null Island 判定半径（±0.0001° = 1000 units of 1e-7 deg）。仕様 §3.3-5。
NULL_ISLAND_E7: Final[int] = 1_000

#: Control の既定送信間隔。仕様 §5。
DEFAULT_INTERVAL_MS: Final[int] = 1_000
MIN_INTERVAL_MS: Final[int] = 100
MAX_INTERVAL_MS: Final[int] = 60_000

#: アドバタイズのローカルネーム接頭辞。仕様 §1.2。
ADVERTISED_NAME_PREFIX: Final[str] = "P2PGPS-"

# ---------------------------------------------------------------------------
# UUID（仕様 §1）
# ---------------------------------------------------------------------------

SERVICE_UUID: Final[str] = "B1E5A000-9C3D-4E7A-8F20-1A2B3C4D5E6F"
LOCATION_CHARACTERISTIC_UUID: Final[str] = "B1E5A001-9C3D-4E7A-8F20-1A2B3C4D5E6F"
CONTROL_CHARACTERISTIC_UUID: Final[str] = "B1E5A002-9C3D-4E7A-8F20-1A2B3C4D5E6F"
STATUS_CHARACTERISTIC_UUID: Final[str] = "B1E5A003-9C3D-4E7A-8F20-1A2B3C4D5E6F"
EXTENDED_CHARACTERISTIC_UUID: Final[str] = "B1E5A004-9C3D-4E7A-8F20-1A2B3C4D5E6F"

DEVICE_INFORMATION_SERVICE_UUID: Final[str] = "0000180A-0000-1000-8000-00805F9B34FB"
MANUFACTURER_NAME_UUID: Final[str] = "00002A29-0000-1000-8000-00805F9B34FB"
MODEL_NUMBER_UUID: Final[str] = "00002A24-0000-1000-8000-00805F9B34FB"
FIRMWARE_REVISION_UUID: Final[str] = "00002A26-0000-1000-8000-00805F9B34FB"

#: Client Characteristic Configuration Descriptor（notify 購読）。仕様 §1.1。
CCCD_UUID: Final[str] = "00002902-0000-1000-8000-00805F9B34FB"


def uuid_to_le_bytes(value: str) -> bytes:
    """128-bit UUID 文字列を BLE のワイヤ表現（リトルエンディアン 16 bytes）へ変換する。

    仕様 §1: 「バイトオーダーは BLE 標準（リトルエンディアン）で送信される」。
    BLE の 128-bit UUID は最下位オクテットから送信されるため、RFC 4122 の
    正規表現（ビッグエンディアン）を単純に逆順にした 16 bytes になる。
    """
    return uuid.UUID(value).bytes[::-1]


def uuid_from_le_bytes(data: bytes) -> str:
    """BLE のワイヤ表現（16 bytes LE）を UUID 文字列（大文字・ハイフン付き）へ戻す。"""
    if len(data) != 16:
        raise ValueError(f"UUID must be 16 bytes, got {len(data)}")
    return str(uuid.UUID(bytes=bytes(data)[::-1])).upper()


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------


class ProtocolError(Exception):
    """プロトコル実装の基底例外。"""


class PacketLengthError(ProtocolError):
    """固定長パケットの長さが仕様と一致しない。"""

    def __init__(self, expected: int, actual: int, kind: str = "packet") -> None:
        self.expected = expected
        self.actual = actual
        self.kind = kind
        super().__init__(f"{kind} must be {expected} bytes, got {actual}")


class WireRangeError(ProtocolError):
    """フィールド値がワイヤ表現（int32 等）に収まらない。"""

    def __init__(self, field: str, value: int, wire_type: str) -> None:
        self.field = field
        self.value = value
        self.wire_type = wire_type
        super().__init__(f"field {field}={value} does not fit in {wire_type}")


class ValidationError(ProtocolError):
    """受信側がパケットを破棄すべき条件に該当した（仕様 §3.3 / §4 / §6 / §9）。

    :attr:`reason` は :class:`RejectReason`（位置パケット）または短い文字列。
    """

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or f"invalid packet: {reason}")


class UnknownOpcodeError(ProtocolError):
    """Control characteristic の未知 opcode（仕様 §5: 無視し last_error=1）。"""

    last_error: ClassVar[int]

    def __init__(self, opcode: int) -> None:
        self.opcode = opcode
        super().__init__(f"unknown control opcode 0x{opcode:02X}")


class ControlLengthError(ProtocolError):
    """Control コマンドの長さ不正（仕様 §5: 無視し last_error=2）。"""

    last_error: ClassVar[int]

    def __init__(self, opcode: int, expected: int, actual: int) -> None:
        self.opcode = opcode
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"control opcode 0x{opcode:02X} must be {expected} bytes, got {actual}"
        )


# ---------------------------------------------------------------------------
# 列挙（仕様 §3.1, §4, §5, §6）
# ---------------------------------------------------------------------------


class Flags(IntFlag):
    """Location Packet の ``flags``（仕様 §3.1）。bit7 は予約（0 固定）。"""

    VALID_FIX = 0x01
    ALTITUDE_VALID = 0x02
    SPEED_VALID = 0x04
    SIMULATED = 0x08
    CHARGING = 0x10
    LOW_BATTERY = 0x20
    MOVING = 0x40


#: flags の予約ビット（受信側は 1 なら破棄）。仕様 §3.1 bit7。
RESERVED_FLAGS_MASK: Final[int] = 0x80


class Provider(IntEnum):
    """Extended Location Packet の ``provider``（仕様 §4）。"""

    UNKNOWN = 0
    GPS = 1
    NETWORK = 2
    FUSED = 3
    MANUAL_SIMULATED = 4


class Opcode(IntEnum):
    """Control characteristic の opcode（仕様 §5）。"""

    START = 0x01
    STOP = 0x02
    SET_INTERVAL = 0x03
    REQUEST_FIX = 0x04
    SET_EXTENDED = 0x05
    #: v2 で AUTH 用に予約（仕様 §8）。v1 では未知 opcode として扱う。
    AUTH = 0x10
    RESET = 0x7F


#: v1 で実装されている opcode（AUTH は予約のため含めない）。
V1_OPCODES: Final[frozenset[int]] = frozenset(
    {Opcode.START, Opcode.STOP, Opcode.SET_INTERVAL, Opcode.REQUEST_FIX,
     Opcode.SET_EXTENDED, Opcode.RESET}
)


class State(IntEnum):
    """Status characteristic の ``state``（仕様 §6）。"""

    IDLE = 0
    STREAMING = 1
    PAUSED = 2
    ERROR = 3


class StatusFlags(IntFlag):
    """Status characteristic の ``status_flags``（仕様 §6）。"""

    EXTENDED_ENABLED = 0x01
    FIX_AVAILABLE = 0x02
    CHARGING = 0x04
    LOW_BATTERY = 0x08


class LastError(IntEnum):
    """Status characteristic の ``last_error``（仕様 §6）。"""

    NONE = 0
    UNKNOWN_OPCODE = 1
    BAD_LENGTH = 2
    LOCATION_UNAVAILABLE = 3
    INTERNAL = 4


UnknownOpcodeError.last_error = int(LastError.UNKNOWN_OPCODE)
ControlLengthError.last_error = int(LastError.BAD_LENGTH)


class RejectReason(str, Enum):
    """Location Packet を破棄する理由（仕様 §3.3 / §9）。"""

    BAD_LENGTH = "bad_length"
    UNKNOWN_VERSION = "unknown_version"
    RESERVED_FLAG_SET = "reserved_flag_set"
    LATITUDE_OUT_OF_RANGE = "latitude_out_of_range"
    LONGITUDE_OUT_OF_RANGE = "longitude_out_of_range"
    NULL_ISLAND = "null_island"

    def __str__(self) -> str:
        # str(RejectReason.X) を "RejectReason.X" ではなく値にする
        return self.value


#: 仕様 §3 のフィールド定義（オフセット, サイズ）。テスト・ドキュメント用。
LOCATION_FIELD_OFFSETS: Final[dict[str, tuple[int, int]]] = {
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

EXTENDED_FIELD_OFFSETS: Final[dict[str, tuple[int, int]]] = {
    "version": (0, 1),
    "provider": (1, 1),
    "battery_pct": (2, 1),
    "satellites": (3, 1),
    "course": (4, 2),
    "vertical_accuracy_m": (6, 1),
    "reserved": (7, 1),
}

STATUS_FIELD_OFFSETS: Final[dict[str, tuple[int, int]]] = {
    "version": (0, 1),
    "state": (1, 1),
    "interval_ms": (2, 2),
    "battery_pct": (4, 1),
    "status_flags": (5, 1),
    "last_error": (6, 1),
    "reserved": (7, 1),
}


# ---------------------------------------------------------------------------
# 共通ヘルパ
# ---------------------------------------------------------------------------


def to_hex(data: bytes | bytearray | memoryview, sep: str = " ") -> str:
    """バイト列を小文字 hex 文字列にする（``sep=""`` で連結）。"""
    raw = bytes(data)
    return sep.join(f"{b:02x}" for b in raw)


def from_hex(text: str) -> bytes:
    """hex 文字列をバイト列へ。空白・``:``・``-``・``,``・``0x`` を許容する。"""
    if not isinstance(text, str):
        raise TypeError("hex input must be a string")
    cleaned = (
        text.strip()
        .replace("0x", "")
        .replace("0X", "")
        .replace(":", "")
        .replace("-", "")
        .replace(",", "")
        .replace(" ", "")
        .replace("\t", "")
        .replace("\n", "")
        .replace("\r", "")
    )
    if len(cleaned) % 2 != 0:
        raise ValueError(f"hex string must have even length: {text!r}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:  # pragma: no cover - bytes.fromhex が詳細を出す
        raise ValueError(f"invalid hex string: {text!r}") from exc


def degrees_to_e7(value: str | float | Decimal) -> int:
    """度（10 進文字列 / float / Decimal）を int32 の「度 × 10^7」へ丸める。

    0.5 は 0 から遠ざかる方向に丸める（``ROUND_HALF_UP``）。仕様 §3 の例
    ``35.6812360 -> 356812360`` を厳密に再現するため、float は ``str()`` を
    経由して 10 進化する（2 進誤差を持ち込まない）。

    NaN / 無限大は :class:`ProtocolError`（CLI が traceback を出さないように）。
    """
    dec = Decimal(str(value))
    if not dec.is_finite():
        raise ProtocolError(f"coordinate must be a finite number: {value!r}")
    scaled = dec * LOCATION_SCALE
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def e7_to_degrees(value: int) -> Decimal:
    """「度 × 10^7」を Decimal の度へ変換する（表示用・丸めなし）。"""
    return Decimal(int(value)) / LOCATION_SCALE


def normalize_interval_ms(value: int) -> int:
    """Control の interval_ms を仕様 §5.1 に従って正規化する（境界クランプ）。

    * ``0`` → ``1000``（既定値）
    * ``1``–``99`` → ``100``（下限にクランプ）
    * ``100``–``60000`` → そのまま
    * ``60001``–``65535`` → ``60000``（上限にクランプ）

    受信側は **生値** を書き、送信側がこの関数の結果を適用する。
    """
    value = int(value)
    if value == 0:
        return DEFAULT_INTERVAL_MS
    if value < MIN_INTERVAL_MS:
        return MIN_INTERVAL_MS
    if value > MAX_INTERVAL_MS:
        return MAX_INTERVAL_MS
    return value


def last_error_for_reason(reason: str) -> int:
    """受信側の破棄理由を ``Status.last_error`` にマップする（参考実装）。

    仕様 §5 は Control の長さ不正 = 2、未知 opcode = 1。仕様 §9 は未知バージョンで
    ``last_error = 4`` を立てると規定するため、未知バージョンは 4 を返す。
    それ以外の位置パケット破棄は 3（location unavailable）とする。
    """
    if reason == RejectReason.BAD_LENGTH:
        return int(LastError.BAD_LENGTH)
    if reason == RejectReason.UNKNOWN_VERSION:
        return int(LastError.INTERNAL)  # 仕様 §9
    return int(LastError.LOCATION_UNAVAILABLE)


# ---------------------------------------------------------------------------
# Location Packet（20 bytes、仕様 §3）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LocationPacket:
    """Location Packet（20 bytes、仕様 §3）。

    緯度経度はワイヤ値（int32、度 × 10^7）で保持する。度で扱いたい場合は
    :meth:`from_degrees` / :attr:`latitude_degrees` を使う。
    """

    SIZE: ClassVar[int] = LOCATION_PACKET_SIZE
    #: version(B) flags(B) sequence(H) latitude(i) longitude(i)
    #: altitude_m(h: int16) accuracy_m(B) speed_mps(B) timestamp(I)
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<BBHiihBBI")

    version: int = PROTOCOL_VERSION
    flags: int = 0
    sequence: int = 0
    latitude: int = 0
    longitude: int = 0
    altitude_m: int = 0
    accuracy_m: int = 255
    speed_mps: int = 255
    timestamp: int = 0

    # -- 生成 ---------------------------------------------------------------
    @classmethod
    def from_degrees(
        cls,
        latitude_deg: str | float | Decimal,
        longitude_deg: str | float | Decimal,
        **kwargs: Any,
    ) -> "LocationPacket":
        """度で緯度経度を指定してパケットを作る（その他フィールドは kwargs）。"""
        return cls(
            latitude=degrees_to_e7(latitude_deg),
            longitude=degrees_to_e7(longitude_deg),
            **kwargs,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LocationPacket":
        """``wire`` 表現の dict（JSON ベクタ）から生成する。"""
        return cls(**dict(data))

    # -- エンコード / デコード ---------------------------------------------
    def encode(self) -> bytes:
        """20 bytes のリトルエンディアン表現を返す。"""
        try:
            return self.STRUCT.pack(
                self.version,
                self.flags,
                self.sequence,
                self.latitude,
                self.longitude,
                self.altitude_m,
                self.accuracy_m,
                self.speed_mps,
                self.timestamp,
            )
        except struct.error as exc:
            raise WireRangeError(
                "location packet", 0, "20-byte little-endian packet"
            ) from exc

    def to_bytes(self) -> bytes:
        """:meth:`encode` の別名。"""
        return self.encode()

    @classmethod
    def decode(cls, data: bytes | bytearray | memoryview) -> "LocationPacket":
        """20 bytes をパースする。長さ以外の検証は :meth:`validate` が行う。"""
        raw = bytes(data)
        if len(raw) != cls.SIZE:
            raise PacketLengthError(cls.SIZE, len(raw), "Location Packet")
        return cls(*cls.STRUCT.unpack(raw))

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> "LocationPacket":
        """:meth:`decode` の別名。"""
        return cls.decode(data)

    # -- 検証（仕様 §3.3） --------------------------------------------------
    def validate(self) -> None:
        """仕様 §3.3 の破棄条件を判定し、該当すれば :class:`ValidationError`。"""
        if self.version != PROTOCOL_VERSION:
            raise ValidationError(
                RejectReason.UNKNOWN_VERSION,
                f"unsupported version 0x{self.version:02X}",
            )
        if self.flags & RESERVED_FLAGS_MASK:
            raise ValidationError(
                RejectReason.RESERVED_FLAG_SET,
                f"reserved flag bit set: flags=0x{self.flags:02X}",
            )
        if not -LATITUDE_MAX_E7 <= self.latitude <= LATITUDE_MAX_E7:
            raise ValidationError(
                RejectReason.LATITUDE_OUT_OF_RANGE,
                f"latitude out of range: {self.latitude}",
            )
        if not -LONGITUDE_MAX_E7 <= self.longitude <= LONGITUDE_MAX_E7:
            raise ValidationError(
                RejectReason.LONGITUDE_OUT_OF_RANGE,
                f"longitude out of range: {self.longitude}",
            )
        if self.has_valid_fix and self.is_null_island:
            raise ValidationError(
                RejectReason.NULL_ISLAND,
                "valid fix at Null Island (0,0)",
            )

    @property
    def is_valid(self) -> bool:
        """:meth:`validate` が例外を出さないなら True。"""
        try:
            self.validate()
        except ValidationError:
            return False
        return True

    @property
    def has_valid_fix(self) -> bool:
        """``VALID_FIX`` ビット（仕様 §3.1 bit0）。"""
        return bool(self.flags & Flags.VALID_FIX)

    @property
    def is_null_island(self) -> bool:
        """(0,0) 近傍 ±0.0001° か（仕様 §3.3-5）。"""
        return (
            abs(self.latitude) <= NULL_ISLAND_E7
            and abs(self.longitude) <= NULL_ISLAND_E7
        )

    # -- 度への変換 ---------------------------------------------------------
    @property
    def latitude_degrees(self) -> Decimal:
        return e7_to_degrees(self.latitude)

    @property
    def longitude_degrees(self) -> Decimal:
        return e7_to_degrees(self.longitude)

    def to_degrees(self) -> tuple[Decimal, Decimal]:
        return self.latitude_degrees, self.longitude_degrees

    # -- 表示 ---------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """ワイヤ値の dict（テストベクタの ``wire`` と同じ形）。"""
        return {
            "version": self.version,
            "flags": self.flags,
            "sequence": self.sequence,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m,
            "accuracy_m": self.accuracy_m,
            "speed_mps": self.speed_mps,
            "timestamp": self.timestamp,
        }

    def to_readable_dict(self) -> dict[str, Any]:
        """デコード結果の人間向け表現（CLI の ``decode`` 出力）。"""
        data = self.to_dict()
        data["latitude_deg"] = str(self.latitude_degrees)
        data["longitude_deg"] = str(self.longitude_degrees)
        data["flags_decoded"] = [flag.name for flag in Flags if self.flags & flag]
        data["valid_fix"] = self.has_valid_fix
        return data


# ---------------------------------------------------------------------------
# Extended Location Packet（8 bytes、仕様 §4）
# ---------------------------------------------------------------------------

BATTERY_UNKNOWN: Final[int] = 255
SATELLITES_UNKNOWN: Final[int] = 255
COURSE_UNKNOWN: Final[int] = 65_535
VERTICAL_ACCURACY_UNKNOWN: Final[int] = 255
COURSE_MAX: Final[int] = 35_999


@dataclass(slots=True)
class ExtendedPacket:
    """Extended Location Packet（8 bytes、任意、仕様 §4）。"""

    SIZE: ClassVar[int] = EXTENDED_PACKET_SIZE
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<BBBBHBB")

    version: int = PROTOCOL_VERSION
    provider: int = int(Provider.UNKNOWN)
    battery_pct: int = BATTERY_UNKNOWN
    satellites: int = SATELLITES_UNKNOWN
    course: int = COURSE_UNKNOWN
    vertical_accuracy_m: int = VERTICAL_ACCURACY_UNKNOWN
    reserved: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExtendedPacket":
        return cls(**dict(data))

    def encode(self) -> bytes:
        try:
            return self.STRUCT.pack(
                self.version,
                self.provider,
                self.battery_pct,
                self.satellites,
                self.course,
                self.vertical_accuracy_m,
                self.reserved,
            )
        except struct.error as exc:
            raise WireRangeError(
                "extended packet", 0, "8-byte little-endian packet"
            ) from exc

    def to_bytes(self) -> bytes:
        return self.encode()

    @classmethod
    def decode(cls, data: bytes | bytearray | memoryview) -> "ExtendedPacket":
        raw = bytes(data)
        if len(raw) != cls.SIZE:
            raise PacketLengthError(cls.SIZE, len(raw), "Extended Location Packet")
        return cls(*cls.STRUCT.unpack(raw))

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> "ExtendedPacket":
        return cls.decode(data)

    def validate(self) -> None:
        """仕様 §4 の範囲を検証する（reserved は将来互換のため無視）。"""
        if self.version != PROTOCOL_VERSION:
            raise ValidationError(
                RejectReason.UNKNOWN_VERSION,
                f"unsupported extended version 0x{self.version:02X}",
            )
        if self.battery_pct != BATTERY_UNKNOWN and not 0 <= self.battery_pct <= 100:
            raise ValidationError(
                "bad_battery_pct", f"battery_pct out of range: {self.battery_pct}"
            )
        if self.course != COURSE_UNKNOWN and not 0 <= self.course <= COURSE_MAX:
            raise ValidationError("bad_course", f"course out of range: {self.course}")

    @property
    def is_valid(self) -> bool:
        try:
            self.validate()
        except ValidationError:
            return False
        return True

    @property
    def provider_name(self) -> str:
        try:
            return Provider(self.provider).name
        except ValueError:
            return f"UNKNOWN({self.provider})"

    @property
    def course_degrees(self) -> Decimal | None:
        if self.course == COURSE_UNKNOWN:
            return None
        return Decimal(int(self.course)) / 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "provider": self.provider,
            "battery_pct": self.battery_pct,
            "satellites": self.satellites,
            "course": self.course,
            "vertical_accuracy_m": self.vertical_accuracy_m,
            "reserved": self.reserved,
        }

    def to_readable_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        data["provider_name"] = self.provider_name
        data["course_degrees"] = (
            None if self.course_degrees is None else str(self.course_degrees)
        )
        return data


# ---------------------------------------------------------------------------
# Control characteristic（受信側 → 送信側、仕様 §5）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ControlCommand:
    """Control characteristic の 1 コマンド（1〜3 bytes、仕様 §5）。

    ``interval_ms`` はワイヤ上の生値（0 = 既定値の意味）を保持する。
    送信側が実際に使う値は :attr:`normalized_interval_ms`。
    """

    opcode: int
    interval_ms: int | None = None
    enabled: bool | None = None

    # -- コンストラクタ -----------------------------------------------------
    @classmethod
    def start(cls, interval_ms: int = 0) -> "ControlCommand":
        return cls(opcode=int(Opcode.START), interval_ms=int(interval_ms))

    @classmethod
    def stop(cls) -> "ControlCommand":
        return cls(opcode=int(Opcode.STOP))

    @classmethod
    def set_interval(cls, interval_ms: int) -> "ControlCommand":
        return cls(opcode=int(Opcode.SET_INTERVAL), interval_ms=int(interval_ms))

    @classmethod
    def request_fix(cls) -> "ControlCommand":
        return cls(opcode=int(Opcode.REQUEST_FIX))

    @classmethod
    def set_extended(cls, enabled: bool) -> "ControlCommand":
        return cls(opcode=int(Opcode.SET_EXTENDED), enabled=bool(enabled))

    @classmethod
    def reset(cls) -> "ControlCommand":
        return cls(opcode=int(Opcode.RESET))

    # -- プロパティ ---------------------------------------------------------
    @property
    def name(self) -> str:
        try:
            return Opcode(self.opcode).name
        except ValueError:
            return f"UNKNOWN(0x{self.opcode:02X})"

    @property
    def is_known(self) -> bool:
        return self.opcode in V1_OPCODES

    @property
    def normalized_interval_ms(self) -> int | None:
        """送信側が適用する interval_ms（仕様 §5.1 の正規化後）。"""
        if self.interval_ms is None:
            return None
        return normalize_interval_ms(self.interval_ms)

    # -- エンコード / デコード ---------------------------------------------
    def encode(self) -> bytes:
        """1〜3 bytes のリトルエンディアン表現を返す。

        ``START`` / ``SET_INTERVAL`` の ``interval_ms`` は **生値** をそのまま
        書く（正規化は送信側の責務。仕様 §5.1）。適用値は
        :attr:`normalized_interval_ms` で取得できる。
        """
        opcode = int(self.opcode)
        if opcode not in V1_OPCODES:
            raise UnknownOpcodeError(opcode)
        if opcode in (Opcode.START, Opcode.SET_INTERVAL):
            if self.interval_ms is None:
                raise ValueError(
                    f"{self.name} requires interval_ms (raw uint16 value)"
                )
            raw_interval = int(self.interval_ms)
            if not 0 <= raw_interval <= 0xFFFF:
                raise WireRangeError("interval_ms", raw_interval, "uint16")
            return struct.pack("<BH", opcode, raw_interval)
        if opcode == Opcode.SET_EXTENDED:
            enabled = 1 if self.enabled else 0
            return struct.pack("<BB", opcode, enabled)
        return struct.pack("<B", opcode)

    def to_bytes(self) -> bytes:
        return self.encode()

    @classmethod
    def decode(cls, data: bytes | bytearray | memoryview) -> "ControlCommand":
        """Control 書き込み値をパースする。

        未知 opcode は :class:`UnknownOpcodeError`（受信側は無視して
        ``last_error=1``）、長さ不正は :class:`ControlLengthError`
        （``last_error=2``）を送出する。
        """
        raw = bytes(data)
        if not raw:
            raise ControlLengthError(0, 1, 0)
        opcode = raw[0]
        if opcode not in V1_OPCODES:
            raise UnknownOpcodeError(opcode)
        if opcode in (Opcode.START, Opcode.SET_INTERVAL):
            if len(raw) != 3:
                raise ControlLengthError(opcode, 3, len(raw))
            (interval_ms,) = struct.unpack("<H", raw[1:])
            return cls(opcode=opcode, interval_ms=interval_ms)
        if opcode == Opcode.SET_EXTENDED:
            if len(raw) != 2:
                raise ControlLengthError(opcode, 2, len(raw))
            return cls(opcode=opcode, enabled=bool(raw[1]))
        if len(raw) != 1:
            raise ControlLengthError(opcode, 1, len(raw))
        return cls(opcode=opcode)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ControlCommand":
        """JSON ベクタの ``command`` 表現から生成する。

        ``opcode`` は ``"START"`` などの名前、または整数を受け付ける。
        """
        payload = dict(data)
        opcode = payload.pop("opcode")
        if isinstance(opcode, str):
            opcode = int(Opcode[opcode.upper()])
        return cls(opcode=int(opcode), **payload)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"opcode": self.name}
        if self.interval_ms is not None:
            data["interval_ms"] = self.interval_ms
        if self.enabled is not None:
            data["enabled"] = self.enabled
        return data

    def to_readable_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        data["opcode_value"] = int(self.opcode)
        if self.interval_ms is not None:
            data["normalized_interval_ms"] = self.normalized_interval_ms
        return data


# ---------------------------------------------------------------------------
# Status characteristic（8 bytes、仕様 §6）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Status:
    """Status characteristic（8 bytes、仕様 §6）。

    ``interval_ms`` は仕様 §5.1 の正規化後の値（送信側が適用中の送信間隔）。
    """

    SIZE: ClassVar[int] = STATUS_PACKET_SIZE
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<BBHBBBB")

    version: int = PROTOCOL_VERSION
    state: int = int(State.IDLE)
    interval_ms: int = DEFAULT_INTERVAL_MS
    battery_pct: int = 255
    status_flags: int = 0
    last_error: int = int(LastError.NONE)
    reserved: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Status":
        payload = dict(data)
        for key in ("state", "last_error"):
            value = payload.get(key)
            if isinstance(value, str):
                enum_cls = State if key == "state" else LastError
                payload[key] = int(enum_cls[value.upper()])
        return cls(**payload)

    def encode(self) -> bytes:
        try:
            return self.STRUCT.pack(
                self.version,
                self.state,
                self.interval_ms,
                self.battery_pct,
                self.status_flags,
                self.last_error,
                self.reserved,
            )
        except struct.error as exc:
            raise WireRangeError("status", 0, "8-byte little-endian packet") from exc

    def to_bytes(self) -> bytes:
        return self.encode()

    @classmethod
    def decode(cls, data: bytes | bytearray | memoryview) -> "Status":
        raw = bytes(data)
        if len(raw) != cls.SIZE:
            raise PacketLengthError(cls.SIZE, len(raw), "Status")
        return cls(*cls.STRUCT.unpack(raw))

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> "Status":
        return cls.decode(data)

    def validate(self) -> None:
        """バージョンのみ検証する（未知フィールドは将来互換のため無視）。"""
        if self.version != PROTOCOL_VERSION:
            raise ValidationError(
                RejectReason.UNKNOWN_VERSION,
                f"unsupported status version 0x{self.version:02X}",
            )

    @property
    def is_valid(self) -> bool:
        try:
            self.validate()
        except ValidationError:
            return False
        return True

    @property
    def state_name(self) -> str:
        try:
            return State(self.state).name
        except ValueError:
            return f"UNKNOWN({self.state})"

    @property
    def last_error_name(self) -> str:
        try:
            return LastError(self.last_error).name
        except ValueError:
            return f"UNKNOWN({self.last_error})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "state": self.state,
            "interval_ms": self.interval_ms,
            "battery_pct": self.battery_pct,
            "status_flags": self.status_flags,
            "last_error": self.last_error,
            "reserved": self.reserved,
        }

    def to_readable_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        data["state_name"] = self.state_name
        data["last_error_name"] = self.last_error_name
        data["status_flags_decoded"] = [
            flag.name for flag in StatusFlags if self.status_flags & flag
        ]
        return data


# ---------------------------------------------------------------------------
# 汎用デコード（CLI / 受信側シミュレータ用）
# ---------------------------------------------------------------------------

Packet = LocationPacket | ExtendedPacket | ControlCommand | Status


def decode_packet(data: bytes | bytearray | memoryview, kind: str = "auto") -> Packet:
    """長さと ``kind`` からパケットをデコードする。

    ``kind="auto"`` は 20 bytes → Location、8 bytes → Status、1〜3 bytes →
    Control と判定する。Extended（8 bytes）は Status と長さが同じなので
    ``kind="extended"`` を明示する必要がある。
    """
    raw = bytes(data)
    normalized = kind.lower()
    if normalized == "location":
        return LocationPacket.decode(raw)
    if normalized == "extended":
        return ExtendedPacket.decode(raw)
    if normalized == "control":
        return ControlCommand.decode(raw)
    if normalized == "status":
        return Status.decode(raw)
    if normalized != "auto":
        raise ValueError(f"unknown packet kind: {kind!r}")
    if len(raw) == LOCATION_PACKET_SIZE:
        return LocationPacket.decode(raw)
    if len(raw) == STATUS_PACKET_SIZE:
        return Status.decode(raw)
    if 1 <= len(raw) <= 3:
        return ControlCommand.decode(raw)
    raise PacketLengthError(LOCATION_PACKET_SIZE, len(raw), "packet")


def packet_kind(packet: Packet) -> str:
    """パケットオブジェクトの種別名を返す。"""
    if isinstance(packet, LocationPacket):
        return "location"
    if isinstance(packet, ExtendedPacket):
        return "extended"
    if isinstance(packet, ControlCommand):
        return "control"
    if isinstance(packet, Status):
        return "status"
    raise TypeError(f"unknown packet type: {type(packet)!r}")
