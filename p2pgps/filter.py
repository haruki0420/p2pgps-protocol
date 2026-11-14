"""受信側の簡易フィルタ（範囲検証・stale 判定・外れ値除去）。

仕様 §3.3 の破棄条件は :class:`p2pgps.protocol.LocationPacket.validate` が担う。
このモジュールはその上に「受信側の表示・注入判断」に必要な状態を持つ:

* :class:`SequenceTracker` — sequence の巻き戻り / 重複 / 欠番の検出（仕様 §3.3-6:
  巻き戻ってもパケット自体は受理する。ログ用の判定のみ）。
* :func:`is_stale` — timestamp が現在時刻から ±24 時間を超えるか（仕様 §3.3-7:
  表示に警告。注入はユーザー設定に従う）。
* :class:`FixFilter` — 上記に加えて「直前の有効 fix からの移動速度」が閾値を
  超える点を外れ値として除去する（オプション。既定 100 m/s = 360 km/h）。

このモジュールも標準ライブラリのみ。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Final

from .protocol import (
    LocationPacket,
    ValidationError,
    e7_to_degrees,
)

__all__ = [
    "STALE_WINDOW_SECONDS",
    "DEFAULT_MAX_SPEED_MPS",
    "EARTH_RADIUS_M",
    "SequenceStatus",
    "SequenceTracker",
    "is_stale",
    "haversine_m",
    "FilterDecision",
    "FixFilter",
]

#: stale 判定の窓（±24 時間）。仕様 §3.3-7。
STALE_WINDOW_SECONDS: Final[int] = 24 * 60 * 60

#: 外れ値除去の既定閾値（100 m/s = 360 km/h）。GPS の瞬間移動を弾く用途。
DEFAULT_MAX_SPEED_MPS: Final[float] = 100.0

#: 地球半径（平均）。haversine 用。
EARTH_RADIUS_M: Final[float] = 6_371_008.8


class SequenceStatus(str, Enum):
    """連続受信における sequence の状態（仕様 §3.3-6）。"""

    FIRST = "first"
    OK = "ok"
    GAP = "gap"
    DUPLICATE = "duplicate"
    REGRESSION = "regression"


class SequenceTracker:
    """uint16 の sequence を監視する。

    65535 → 0 のラップを考慮する。巻き戻り（``REGRESSION``）でもパケットは
    受理する（仕様 §3.3-6）。判定はログ・診断用。
    """

    def __init__(self) -> None:
        self._last: int | None = None
        self.regressions: int = 0
        self.duplicates: int = 0
        self.gaps: int = 0
        self.received: int = 0

    @property
    def last(self) -> int | None:
        return self._last

    def reset(self) -> None:
        self._last = None
        self.regressions = 0
        self.duplicates = 0
        self.gaps = 0
        self.received = 0

    def observe(self, sequence: int) -> SequenceStatus:
        """次の sequence を観測して状態を返す。"""
        if not 0 <= int(sequence) <= 0xFFFF:
            raise ValueError(f"sequence must be uint16: {sequence}")
        seq = int(sequence)
        self.received += 1
        if self._last is None:
            status = SequenceStatus.FIRST
        else:
            delta = (seq - self._last) & 0xFFFF
            if delta == 0:
                status = SequenceStatus.DUPLICATE
                self.duplicates += 1
            elif delta == 1:
                status = SequenceStatus.OK
            elif delta < 0x8000:
                status = SequenceStatus.GAP
                self.gaps += 1
            else:
                status = SequenceStatus.REGRESSION
                self.regressions += 1
        self._last = seq
        return status


def is_stale(
    packet: LocationPacket,
    now: float | None = None,
    window_seconds: int = STALE_WINDOW_SECONDS,
) -> bool:
    """timestamp が現在時刻から ±``window_seconds`` を超えていれば True。

    ``timestamp == 0``（未設定）も stale 扱い。仕様 §3.3-7。
    """
    current = time.time() if now is None else float(now)
    return abs(current - packet.timestamp) > window_seconds


def haversine_m(
    latitude_a: int | float,
    longitude_a: int | float,
    latitude_b: int | float,
    longitude_b: int | float,
    *,
    e7: bool = True,
) -> float:
    """2 点間の大円距離（メートル）。

    ``e7=True``（既定）は引数を「度 × 10^7」の整数として解釈する。
    """
    if e7:
        lat_a = float(e7_to_degrees(latitude_a))
        lon_a = float(e7_to_degrees(longitude_a))
        lat_b = float(e7_to_degrees(latitude_b))
        lon_b = float(e7_to_degrees(longitude_b))
    else:
        lat_a, lon_a = float(latitude_a), float(longitude_a)
        lat_b, lon_b = float(latitude_b), float(longitude_b)

    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(lon_b - lon_a)
    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


@dataclass(slots=True, frozen=True)
class FilterDecision:
    """:meth:`FixFilter.feed` の判定結果。"""

    accepted: bool
    reason: str | None = None
    stale: bool = False
    sequence_status: SequenceStatus | None = None
    distance_m: float | None = None
    implied_speed_mps: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "stale": self.stale,
            "sequence_status": (
                None if self.sequence_status is None else self.sequence_status.value
            ),
            "distance_m": self.distance_m,
            "implied_speed_mps": self.implied_speed_mps,
        }


class FixFilter:
    """受信側の簡易フィルタ。

    使い方::

        filter_ = FixFilter()
        decision = filter_.feed(packet)
        if decision.accepted:
            use(packet)

    判定順:

    1. 仕様 §3.3 の検証（不正なら ``accepted=False``、``reason`` は
       :class:`p2pgps.protocol.RejectReason` の値）。
    2. sequence の観測（受理可否には影響しない）。
    3. 精度ゲート（``max_accuracy_m`` 指定時のみ。``255`` = 不明は通す）。
    4. 外れ値除去（直前の受理 fix からの移動速度が ``max_speed_mps`` 超で棄却）。
    5. stale 判定（受理するが ``stale=True``。注入可否は呼び出し側の設定）。
    """

    def __init__(
        self,
        *,
        max_speed_mps: float | None = DEFAULT_MAX_SPEED_MPS,
        max_accuracy_m: int | None = None,
        stale_window_seconds: int = STALE_WINDOW_SECONDS,
        sequence_tracker: SequenceTracker | None = None,
    ) -> None:
        self.max_speed_mps = max_speed_mps
        self.max_accuracy_m = max_accuracy_m
        self.stale_window_seconds = stale_window_seconds
        self.sequence_tracker = sequence_tracker or SequenceTracker()
        self._last_fix: LocationPacket | None = None

    @property
    def last_fix(self) -> LocationPacket | None:
        return self._last_fix

    def reset(self) -> None:
        self._last_fix = None
        self.sequence_tracker.reset()

    def feed(
        self,
        packet: LocationPacket,
        *,
        now: float | None = None,
    ) -> FilterDecision:
        """1 パケットを判定する。"""
        try:
            packet.validate()
        except ValidationError as exc:
            return FilterDecision(accepted=False, reason=str(exc.reason))

        sequence_status = self.sequence_tracker.observe(packet.sequence)
        stale = is_stale(packet, now=now, window_seconds=self.stale_window_seconds)

        if (
            self.max_accuracy_m is not None
            and packet.accuracy_m != 255
            and packet.accuracy_m > self.max_accuracy_m
        ):
            return FilterDecision(
                accepted=False,
                reason="low_accuracy",
                stale=stale,
                sequence_status=sequence_status,
            )

        distance_m: float | None = None
        implied_speed: float | None = None
        if self._last_fix is not None and self.max_speed_mps is not None:
            previous = self._last_fix
            dt = packet.timestamp - previous.timestamp
            if dt > 0:
                distance_m = haversine_m(
                    previous.latitude,
                    previous.longitude,
                    packet.latitude,
                    packet.longitude,
                )
                implied_speed = distance_m / dt
                if implied_speed > self.max_speed_mps:
                    return FilterDecision(
                        accepted=False,
                        reason="outlier",
                        stale=stale,
                        sequence_status=sequence_status,
                        distance_m=distance_m,
                        implied_speed_mps=implied_speed,
                    )

        self._last_fix = packet
        return FilterDecision(
            accepted=True,
            reason=None,
            stale=stale,
            sequence_status=sequence_status,
            distance_m=distance_m,
            implied_speed_mps=implied_speed,
        )
