"""``python -m p2pgps`` — P2P GPS BLE protocol v1 リファレンス CLI。

サブコマンド:

* ``encode``  — パケットを hex へエンコード（``--kind`` で location/extended/control/status）
* ``decode``  — hex を JSON へデコード（``--hex`` で入力、``--kind auto`` で自動判定）
* ``vectors`` — ``tests/vectors/*.json`` の全テストベクタを検証
* ``serve``   — 送信側シミュレータ（bless があれば BLE ペリフェラル、無ければ stdout）
* ``scan``    — 受信側シミュレータ（bleak があれば BLE セントラルとして受信）

オプション依存: ``pip install "p2pgps-protocol[ble]"``（bleak + bless）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from typing import Any, Sequence

from . import __version__
from .filter import FixFilter
from .protocol import (
    CONTROL_CHARACTERISTIC_UUID,
    DEFAULT_INTERVAL_MS,
    LOCATION_CHARACTERISTIC_UUID,
    SERVICE_UUID,
    STATUS_CHARACTERISTIC_UUID,
    ControlCommand,
    ExtendedPacket,
    Flags,
    LastError,
    LocationPacket,
    Opcode,
    ProtocolError,
    Provider,
    State,
    Status,
    ValidationError,
    decode_packet,
    from_hex,
    normalize_interval_ms,
    packet_kind,
    to_hex,
)
from .vectors import find_vectors_dir, run_vectors

__all__ = ["main", "build_parser"]


# ---------------------------------------------------------------------------
# 共通ヘルパ
# ---------------------------------------------------------------------------


def _configure_stdio() -> None:
    """Windows の cp932 コンソールでも日本語・UTF-8 を出せるようにする。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - 環境依存
            pass


def _int_auto(text: str) -> int:
    """``0x`` 接頭辞付きも受け付ける int。"""
    return int(text, 0)


def _enum_value(enum_cls: Any, text: str) -> int:
    """列挙名（大文字小文字不問）または整数値を受け付ける。"""
    try:
        return int(text, 0)
    except ValueError:
        pass
    try:
        return int(enum_cls[text.strip().upper()])
    except KeyError:
        choices = ", ".join(member.name for member in enum_cls)
        raise argparse.ArgumentTypeError(
            f"invalid value {text!r} (expected one of: {choices}, or an integer)"
        ) from None


def _provider_value(text: str) -> int:
    normalized = text.strip().upper().replace("-", "_")
    try:
        return int(Provider[normalized])
    except KeyError:
        return _int_auto(text)


def _opcode_value(text: str) -> int:
    normalized = text.strip().upper()
    try:
        return int(Opcode[normalized])
    except KeyError:
        return _int_auto(text)


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _packet_validation(packet: Any) -> tuple[bool, str | None]:
    try:
        packet.validate()
        return True, None
    except ValidationError as exc:
        return False, str(exc.reason)


# ---------------------------------------------------------------------------
# encode
# ---------------------------------------------------------------------------


def _build_location(args: argparse.Namespace) -> LocationPacket:
    if args.lat is None or args.lon is None:
        raise ValueError("encode --kind location requires --lat and --lon")
    return LocationPacket.from_degrees(
        args.lat,
        args.lon,
        version=args.proto_version,
        flags=args.flags,
        sequence=args.seq,
        altitude_m=args.alt,
        accuracy_m=args.acc,
        speed_mps=args.speed,
        timestamp=args.ts,
    )


def _build_extended(args: argparse.Namespace) -> ExtendedPacket:
    return ExtendedPacket(
        version=args.proto_version,
        provider=args.provider,
        battery_pct=args.battery,
        satellites=args.satellites,
        course=args.course,
        vertical_accuracy_m=args.vacc,
        reserved=args.reserved,
    )


def _build_control(args: argparse.Namespace) -> ControlCommand:
    if args.opcode is None:
        raise ValueError("encode --kind control requires --opcode")
    payload: dict[str, Any] = {"opcode": args.opcode}
    if args.interval_ms is not None:
        payload["interval_ms"] = args.interval_ms
    if args.enabled is not None:
        payload["enabled"] = args.enabled
    return ControlCommand.from_dict(payload)


def _build_status(args: argparse.Namespace) -> Status:
    return Status(
        version=args.proto_version,
        state=args.state,
        interval_ms=args.interval_ms if args.interval_ms is not None else DEFAULT_INTERVAL_MS,
        battery_pct=args.battery,
        status_flags=args.status_flags,
        last_error=args.last_error,
        reserved=args.reserved,
    )


def _cmd_encode(args: argparse.Namespace) -> int:
    builders = {
        "location": _build_location,
        "extended": _build_extended,
        "control": _build_control,
        "status": _build_status,
    }
    packet = builders[args.kind](args)
    data = packet.encode()
    if args.json:
        payload: dict[str, Any] = {
            "kind": args.kind,
            "hex": to_hex(data, sep=""),
            "bytes": len(data),
            "fields": packet.to_dict(),
        }
        if hasattr(packet, "to_readable_dict"):
            payload["decoded"] = packet.to_readable_dict()
        if args.kind == "location":
            valid, reason = _packet_validation(packet)
            payload["valid"] = valid
            payload["reason"] = reason
        _emit(payload)
    else:
        print(to_hex(data, sep=""))
    return 0


# ---------------------------------------------------------------------------
# decode
# ---------------------------------------------------------------------------


def _cmd_decode(args: argparse.Namespace) -> int:
    hex_input = args.hex_input if args.hex_input is not None else args.packet
    if not hex_input:
        raise ValueError("decode requires --hex <hex string> (or a positional hex)")
    try:
        raw = from_hex(hex_input)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        packet = decode_packet(raw, kind=args.kind)
    except (ProtocolError, ValueError) as exc:
        payload = {
            "kind": args.kind,
            "hex": to_hex(raw, sep=""),
            "length": len(raw),
            "valid": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }
        last_error = getattr(exc, "last_error", None)
        if last_error is not None:
            payload["last_error"] = last_error
        _emit(payload)
        return 2

    kind = packet_kind(packet)
    if kind in ("location", "extended", "status"):
        valid, reason = _packet_validation(packet)
    else:
        valid, reason = packet.is_known, None
    payload = {
        "kind": kind,
        "hex": to_hex(raw, sep=""),
        "length": len(raw),
        "valid": valid,
        "reason": reason,
        "fields": packet.to_dict(),
    }
    if hasattr(packet, "to_readable_dict"):
        payload["decoded"] = packet.to_readable_dict()
    _emit(payload)
    return 0 if valid else 1


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------


def _cmd_vectors(args: argparse.Namespace) -> int:
    try:
        directory = find_vectors_dir(args.dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    results = run_vectors(directory)
    if args.json:
        print(
            json.dumps(
                {
                    "directory": str(directory),
                    "total": len(results),
                    "passed": sum(1 for result in results if result.ok),
                    "results": [result.to_dict() for result in results],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"vectors: {directory}")
        grouped: dict[str, list[Any]] = {}
        for result in results:
            grouped.setdefault(result.file, []).append(result)
        for filename, file_results in grouped.items():
            passed = sum(1 for result in file_results if result.ok)
            print(f"  {filename}: {passed}/{len(file_results)} passed")
            for result in file_results:
                if not result.ok:
                    for error in result.errors:
                        print(f"    FAIL {error}")
        passed_total = sum(1 for result in results if result.ok)
        print(f"total: {passed_total}/{len(results)} passed")
    return 0 if all(result.ok for result in results) else 1


# ---------------------------------------------------------------------------
# serve（送信側シミュレータ）
# ---------------------------------------------------------------------------


def _make_packet(args: argparse.Namespace, sequence: int) -> LocationPacket:
    flags = args.flags if args.flags is not None else int(Flags.VALID_FIX | Flags.SIMULATED)
    return LocationPacket.from_degrees(
        args.lat,
        args.lon,
        flags=flags,
        sequence=sequence & 0xFFFF,
        altitude_m=args.alt,
        accuracy_m=args.acc,
        speed_mps=args.speed,
        timestamp=int(time.time()),
    )


def _serve_stdout(args: argparse.Namespace) -> int:
    sequence = args.seq_start
    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            packet = _make_packet(args, sequence)
            print(to_hex(packet.encode(), sep=""), flush=True)
            sequence = (sequence + 1) & 0xFFFF
            sent += 1
            if args.count and sent >= args.count:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:  # pragma: no cover - 対話用
        pass
    return 0


async def _serve_bless(args: argparse.Namespace) -> int:
    from bless import (  # type: ignore[import-not-found]
        BlessServer,
        GATTAttributePermissions,
        GATTCharacteristicProperties,
    )

    service_uuid = SERVICE_UUID.lower()
    location_uuid = LOCATION_CHARACTERISTIC_UUID.lower()
    status_uuid = STATUS_CHARACTERISTIC_UUID.lower()
    properties = (
        GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
    )
    permissions = GATTAttributePermissions.readable

    server = BlessServer(name=args.device_name)
    server.add_new_service(service_uuid)
    server.add_new_characteristic(
        service_uuid, location_uuid, properties, bytearray(LocationPacket.SIZE), permissions
    )
    server.add_new_characteristic(
        service_uuid, status_uuid, properties, bytearray(Status.SIZE), permissions
    )
    await server.start()
    print(f"advertising as {args.device_name} (service {SERVICE_UUID})", flush=True)

    status = Status(
        state=State.STREAMING,
        interval_ms=normalize_interval_ms(max(0, int(args.interval * 1000))),
    )
    server.get_characteristic(status_uuid).value = bytearray(status.encode())
    server.update_value(service_uuid, status_uuid)

    sequence = args.seq_start
    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            packet = _make_packet(args, sequence)
            server.get_characteristic(location_uuid).value = bytearray(packet.encode())
            server.update_value(service_uuid, location_uuid)
            sequence = (sequence + 1) & 0xFFFF
            sent += 1
            await asyncio.sleep(args.interval)
    finally:
        await server.stop()
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    if not math.isfinite(args.interval) or args.interval <= 0:
        print("error: --interval must be a finite number > 0", file=sys.stderr)
        return 2
    if not (math.isfinite(args.lat) and math.isfinite(args.lon)):
        print("error: --lat/--lon must be finite numbers", file=sys.stderr)
        return 2
    backend = "stdout" if args.stdout else args.backend
    if backend == "auto":
        try:
            import bless  # noqa: F401  # type: ignore[import-not-found]

            backend = "bless"
        except ImportError:
            backend = "stdout"
    if backend == "bless":
        try:
            return asyncio.run(_serve_bless(args))
        except ImportError:
            print(
                "warning: bless is not installed; falling back to stdout "
                '(install with: pip install "p2pgps-protocol[ble]")',
                file=sys.stderr,
            )
    if backend == "stdout":
        return _serve_stdout(args)
    print(f"error: unknown backend {backend!r}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# scan（受信側シミュレータ、bleak 使用）
# ---------------------------------------------------------------------------


async def _scan_devices(args: argparse.Namespace) -> int:
    from bleak import BleakScanner  # type: ignore[import-not-found]

    devices = await BleakScanner.discover(timeout=args.timeout)
    matched = [
        device
        for device in devices
        if (device.name or "").startswith(args.name_prefix)
    ]
    if not matched:
        print(f"no devices with prefix {args.name_prefix!r} found", file=sys.stderr)
        return 1
    for device in matched:
        print(
            json.dumps(
                {
                    "name": device.name,
                    "address": device.address,
                    "rssi": getattr(device, "rssi", None),
                },
                ensure_ascii=False,
            )
        )
    return 0


async def _scan_receive(args: argparse.Namespace) -> int:
    from bleak import BleakClient, BleakScanner  # type: ignore[import-not-found]

    device = await BleakScanner.find_device_by_address(args.connect, timeout=args.timeout)
    if device is None:
        print(f"error: device {args.connect!r} not found", file=sys.stderr)
        return 1
    filter_ = FixFilter()
    async with BleakClient(device) as client:
        status_raw = await client.read_gatt_char(STATUS_CHARACTERISTIC_UUID)
        status = Status.decode(status_raw)
        print(json.dumps({"status": status.to_readable_dict()}, ensure_ascii=False))
        await client.write_gatt_char(
            CONTROL_CHARACTERISTIC_UUID,
            ControlCommand.start(args.interval_ms).encode(),
            response=False,
        )

        def on_location(_: Any, data: bytearray) -> None:
            try:
                packet = LocationPacket.decode(data)
            except ProtocolError as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))
                return
            decision = filter_.feed(packet)
            payload = {
                "packet": packet.to_readable_dict(),
                "decision": decision.to_dict(),
            }
            print(json.dumps(payload, ensure_ascii=False), flush=True)

        await client.start_notify(LOCATION_CHARACTERISTIC_UUID, on_location)
        try:
            await asyncio.sleep(args.duration)
        finally:
            try:
                await client.stop_notify(LOCATION_CHARACTERISTIC_UUID)
            except Exception:  # noqa: BLE001 - 切断済みなら無視
                pass
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    try:
        import bleak  # noqa: F401  # type: ignore[import-not-found]
    except ImportError:
        print(
            "error: bleak is not installed. Install optional dependency: "
            'pip install "p2pgps-protocol[ble]"',
            file=sys.stderr,
        )
        return 2
    if args.connect:
        return asyncio.run(_scan_receive(args))
    return asyncio.run(_scan_devices(args))


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def _add_common_output_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--hex", action="store_true", help="hex 文字列で出力（既定）")
    group.add_argument("--json", action="store_true", help="JSON で出力")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p2pgps",
        description=(
            "P2P GPS BLE protocol v1 reference CLI "
            "(spec: spec/protocol-v1.md)"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- encode -------------------------------------------------------------
    encode = subparsers.add_parser(
        "encode", help="パケットを hex へエンコードする"
    )
    encode.add_argument(
        "--kind",
        choices=("location", "extended", "control", "status"),
        default="location",
        help="パケット種別（既定: location）",
    )
    _add_common_output_flags(encode)
    encode.add_argument("--lat", type=float, help="緯度（度、location 必須）")
    encode.add_argument("--lon", type=float, help="経度（度、location 必須）")
    encode.add_argument("--alt", type=int, default=0, help="標高 m（既定: 0）")
    encode.add_argument("--acc", type=int, default=255, help="水平精度 m（既定: 255=不明）")
    encode.add_argument("--speed", type=int, default=255, help="速度 m/s（既定: 255=不明）")
    encode.add_argument("--flags", type=_int_auto, default=0, help="flags（既定: 0）")
    encode.add_argument("--seq", type=_int_auto, default=0, help="sequence（既定: 0）")
    encode.add_argument("--ts", type=_int_auto, default=0, help="Unix 秒（既定: 0）")
    encode.add_argument(
        "--proto-version", type=_int_auto, default=1, help="プロトコル version（既定: 1）"
    )
    encode.add_argument(
        "--provider", type=_provider_value, default=int(Provider.UNKNOWN),
        help="provider 名または整数（extended）",
    )
    encode.add_argument("--battery", type=_int_auto, default=255, help="バッテリー %（既定: 255=不明）")
    encode.add_argument("--satellites", type=_int_auto, default=255, help="衛星数（既定: 255=不明）")
    encode.add_argument("--course", type=_int_auto, default=65535, help="進行方向 ×100（既定: 65535=不明）")
    encode.add_argument("--vacc", type=_int_auto, default=255, help="垂直精度 m（既定: 255=不明）")
    encode.add_argument("--reserved", type=_int_auto, default=0, help="reserved（既定: 0）")
    encode.add_argument("--opcode", type=_opcode_value, default=None, help="Control opcode 名または整数")
    encode.add_argument(
        "--interval-ms",
        type=_int_auto,
        default=None,
        help="送信間隔の生値 ms（START / SET_INTERVAL では必須。正規化は仕様 §5.1）",
    )
    encode.add_argument("--enabled", type=_int_auto, choices=(0, 1), default=None, help="SET_EXTENDED の 0/1")
    encode.add_argument("--state", type=lambda text: _enum_value(State, text), default=int(State.IDLE), help="Status state 名または整数")
    encode.add_argument("--status-flags", type=_int_auto, default=0, help="Status status_flags（既定: 0）")
    encode.add_argument("--last-error", type=lambda text: _enum_value(LastError, text), default=int(LastError.NONE), help="Status last_error 名または整数")

    # -- decode -------------------------------------------------------------
    decode = subparsers.add_parser("decode", help="hex を JSON へデコードする")
    decode.add_argument("--hex", dest="hex_input", default=None, help="入力 hex（空白区切り可）")
    decode.add_argument("packet", nargs="?", default=None, help="入力 hex（位置引数でも可）")
    decode.add_argument(
        "--kind",
        choices=("auto", "location", "extended", "control", "status"),
        default="auto",
        help="パケット種別（既定: auto。8 bytes は status と判定）",
    )
    decode.add_argument("--json", action="store_true", help="JSON で出力（既定）")

    # -- vectors ------------------------------------------------------------
    vectors = subparsers.add_parser("vectors", help="テストベクタを検証する")
    vectors.add_argument("--dir", default=None, help="ベクタディレクトリ（既定: tests/vectors）")
    vectors.add_argument("--json", action="store_true", help="JSON で出力")

    # -- serve --------------------------------------------------------------
    serve = subparsers.add_parser(
        "serve",
        help="送信側シミュレータ（BLE ペリフェラル / stdout）",
        description=(
            "送信側シミュレータ。Location / Status を notify する。"
            "Control characteristic の write 受信は未実装（受信側シミュレータ "
            "`scan --connect` は実機向け）。"
        ),
    )
    serve.add_argument("--lat", type=float, default=35.6812360, help="緯度（既定: 東京駅）")
    serve.add_argument("--lon", type=float, default=139.7671250, help="経度（既定: 東京駅）")
    serve.add_argument("--alt", type=int, default=0, help="標高 m")
    serve.add_argument("--acc", type=int, default=5, help="水平精度 m（既定: 5）")
    serve.add_argument("--speed", type=int, default=0, help="速度 m/s（既定: 0）")
    serve.add_argument("--flags", type=_int_auto, default=None, help="flags（既定: VALID_FIX|SIMULATED）")
    serve.add_argument("--interval", type=float, default=1.0, help="送信間隔 秒（既定: 1.0）")
    serve.add_argument("--count", type=int, default=0, help="送信回数（0=無限、既定: 0）")
    serve.add_argument("--seq-start", type=_int_auto, default=0, help="開始 sequence（既定: 0）")
    serve.add_argument("--device-name", default=None, help="アドバタイズ名（既定: P2PGPS-PYTHON-XXXX）")
    serve.add_argument("--backend", choices=("auto", "bless", "stdout"), default="auto", help="送信バックエンド（既定: auto）")
    serve.add_argument("--stdout", action="store_true", help="stdout バックエンドを強制する")

    # -- scan ---------------------------------------------------------------
    scan = subparsers.add_parser("scan", help="受信側シミュレータ（bleak が必要）")
    scan.add_argument("--timeout", type=float, default=5.0, help="スキャン秒（既定: 5.0）")
    scan.add_argument("--name-prefix", default="P2PGPS-", help="名前フィルタ（既定: P2PGPS-）")
    scan.add_argument("--connect", default=None, help="この address に接続して notify を表示する")
    scan.add_argument("--duration", type=float, default=10.0, help="受信秒（既定: 10.0）")
    scan.add_argument("--interval-ms", type=_int_auto, default=1000, help="START で要求する間隔 ms")

    return parser


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve" and args.device_name is None:
        args.device_name = f"P2PGPS-PYTHON-{random.randint(0, 0xFFFF):04X}"
    try:
        if args.command == "encode":
            return _cmd_encode(args)
        if args.command == "decode":
            return _cmd_decode(args)
        if args.command == "vectors":
            return _cmd_vectors(args)
        if args.command == "serve":
            return _cmd_serve(args)
        if args.command == "scan":
            return _cmd_scan(args)
    except (ProtocolError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover - 対話用
        return 130
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
