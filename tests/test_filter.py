"""受信側フィルタ（範囲検証・stale・sequence・外れ値除去）のテスト。"""

from __future__ import annotations

import pytest

from p2pgps.filter import (
    DEFAULT_MAX_SPEED_MPS,
    STALE_WINDOW_SECONDS,
    FilterDecision,
    FixFilter,
    SequenceStatus,
    SequenceTracker,
    haversine_m,
    is_stale,
)
from p2pgps.protocol import Flags, LocationPacket

TOKYO = (356812360, 1397671250)  # 東京駅
OSAKA = (346937000, 1355023000)  # 大阪駅


def make_packet(
    *,
    latitude: int = TOKYO[0],
    longitude: int = TOKYO[1],
    sequence: int = 1,
    timestamp: int = 1763136000,
    flags: int = int(Flags.VALID_FIX),
    accuracy_m: int = 5,
) -> LocationPacket:
    return LocationPacket(
        flags=flags,
        sequence=sequence,
        latitude=latitude,
        longitude=longitude,
        altitude_m=0,
        accuracy_m=accuracy_m,
        speed_mps=0,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# SequenceTracker（仕様 §3.3-6）
# ---------------------------------------------------------------------------


def test_sequence_tracker_statuses() -> None:
    tracker = SequenceTracker()
    assert tracker.observe(10) is SequenceStatus.FIRST
    assert tracker.observe(11) is SequenceStatus.OK
    assert tracker.observe(11) is SequenceStatus.DUPLICATE
    assert tracker.observe(15) is SequenceStatus.GAP
    assert tracker.observe(14) is SequenceStatus.REGRESSION
    assert tracker.last == 14
    assert tracker.received == 5
    assert tracker.duplicates == 1
    assert tracker.gaps == 1
    assert tracker.regressions == 1


def test_sequence_tracker_handles_uint16_wrap() -> None:
    tracker = SequenceTracker()
    assert tracker.observe(65534) is SequenceStatus.FIRST
    assert tracker.observe(65535) is SequenceStatus.OK
    assert tracker.observe(0) is SequenceStatus.OK
    assert tracker.observe(1) is SequenceStatus.OK
    assert tracker.regressions == 0


def test_sequence_tracker_reset() -> None:
    tracker = SequenceTracker()
    tracker.observe(1)
    tracker.observe(0)  # regression
    tracker.reset()
    assert tracker.last is None
    assert tracker.received == 0
    assert tracker.regressions == 0
    assert tracker.observe(7) is SequenceStatus.FIRST


@pytest.mark.parametrize("sequence", [-1, 65536])
def test_sequence_tracker_rejects_out_of_range(sequence: int) -> None:
    with pytest.raises(ValueError):
        SequenceTracker().observe(sequence)


# ---------------------------------------------------------------------------
# stale 判定（仕様 §3.3-7）
# ---------------------------------------------------------------------------


def test_is_stale_window() -> None:
    packet = make_packet(timestamp=1_000_000)
    assert STALE_WINDOW_SECONDS == 24 * 60 * 60
    assert is_stale(packet, now=1_000_000) is False
    assert is_stale(packet, now=1_000_000 + STALE_WINDOW_SECONDS) is False
    assert is_stale(packet, now=1_000_000 + STALE_WINDOW_SECONDS + 1) is True
    assert is_stale(packet, now=1_000_000 - STALE_WINDOW_SECONDS - 1) is True


def test_timestamp_zero_is_stale() -> None:
    packet = make_packet(timestamp=0)
    assert is_stale(packet, now=1_763_136_000) is True


# ---------------------------------------------------------------------------
# 距離計算
# ---------------------------------------------------------------------------


def test_haversine_zero_distance() -> None:
    assert haversine_m(TOKYO[0], TOKYO[1], TOKYO[0], TOKYO[1]) == pytest.approx(0.0)


def test_haversine_tokyo_osaka() -> None:
    distance = haversine_m(TOKYO[0], TOKYO[1], OSAKA[0], OSAKA[1])
    assert 390_000 < distance < 410_000


def test_haversine_accepts_degrees() -> None:
    distance = haversine_m(
        35.681236, 139.767125, 34.6937, 135.5023, e7=False
    )
    assert 390_000 < distance < 410_000


# ---------------------------------------------------------------------------
# FixFilter
# ---------------------------------------------------------------------------


def test_fix_filter_accepts_valid_packet() -> None:
    filter_ = FixFilter()
    decision = filter_.feed(make_packet(), now=1_763_136_000)
    assert decision.accepted is True
    assert decision.reason is None
    assert decision.stale is False
    assert decision.sequence_status is SequenceStatus.FIRST
    assert filter_.last_fix is not None


def test_fix_filter_rejects_invalid_packet() -> None:
    filter_ = FixFilter()
    decision = filter_.feed(make_packet(latitude=0, longitude=0))
    assert decision.accepted is False
    assert decision.reason == "null_island"
    assert filter_.last_fix is None


def test_fix_filter_marks_stale_but_accepts() -> None:
    filter_ = FixFilter()
    packet = make_packet(timestamp=1_000_000)
    decision = filter_.feed(packet, now=1_000_000 + STALE_WINDOW_SECONDS + 1)
    assert decision.accepted is True
    assert decision.stale is True


def test_fix_filter_rejects_outlier() -> None:
    filter_ = FixFilter(max_speed_mps=100.0)
    first = make_packet(sequence=1, timestamp=1000)
    assert filter_.feed(first).accepted is True
    # 1 秒で東京 → 大阪（約 400 km）は 100 m/s を超える
    second = make_packet(
        latitude=OSAKA[0], longitude=OSAKA[1], sequence=2, timestamp=1001
    )
    decision = filter_.feed(second)
    assert decision.accepted is False
    assert decision.reason == "outlier"
    assert decision.distance_m is not None
    assert decision.implied_speed_mps is not None
    assert decision.implied_speed_mps > 100.0
    # 棄却された点は last_fix を更新しない
    assert filter_.last_fix is first


def test_fix_filter_accepts_normal_movement() -> None:
    filter_ = FixFilter(max_speed_mps=100.0)
    first = make_packet(sequence=1, timestamp=1000)
    filter_.feed(first)
    # 北へ約 10 m、1 秒後（約 10 m/s）
    second = make_packet(sequence=2, timestamp=1001, latitude=TOKYO[0] + 900)
    decision = filter_.feed(second)
    assert decision.accepted is True
    assert decision.implied_speed_mps is not None
    assert 5.0 < decision.implied_speed_mps < 15.0


def test_fix_filter_skips_outlier_check_without_positive_dt() -> None:
    filter_ = FixFilter(max_speed_mps=1.0)
    filter_.feed(make_packet(sequence=1, timestamp=1000))
    # 同じ timestamp なら速度を計算できないので外れ値判定しない
    decision = filter_.feed(
        make_packet(
            latitude=OSAKA[0], longitude=OSAKA[1], sequence=2, timestamp=1000
        )
    )
    assert decision.accepted is True
    assert decision.implied_speed_mps is None


def test_fix_filter_accuracy_gate() -> None:
    filter_ = FixFilter(max_accuracy_m=10)
    assert filter_.feed(make_packet(accuracy_m=11)).accepted is False
    assert filter_.feed(make_packet(accuracy_m=11)).reason == "low_accuracy"
    # 255 = 不明は通す
    assert filter_.feed(make_packet(accuracy_m=255)).accepted is True


def test_fix_filter_accepts_no_fix_packet() -> None:
    filter_ = FixFilter()
    packet = make_packet(flags=0, latitude=0, longitude=0)
    decision = filter_.feed(packet)
    assert decision.accepted is True
    assert decision.reason is None


def test_fix_filter_sequence_duplicate() -> None:
    filter_ = FixFilter()
    packet = make_packet(sequence=5)
    assert filter_.feed(packet).sequence_status is SequenceStatus.FIRST
    assert filter_.feed(packet).sequence_status is SequenceStatus.DUPLICATE


def test_fix_filter_reset() -> None:
    filter_ = FixFilter()
    filter_.feed(make_packet())
    filter_.reset()
    assert filter_.last_fix is None
    assert filter_.sequence_tracker.last is None


def test_default_max_speed() -> None:
    assert DEFAULT_MAX_SPEED_MPS == 100.0


def test_filter_decision_to_dict() -> None:
    decision = FilterDecision(
        accepted=True,
        stale=True,
        sequence_status=SequenceStatus.OK,
        distance_m=10.0,
        implied_speed_mps=10.0,
    )
    data = decision.to_dict()
    assert data["accepted"] is True
    assert data["stale"] is True
    assert data["sequence_status"] == "ok"
    assert data["distance_m"] == 10.0
