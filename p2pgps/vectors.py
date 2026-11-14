"""テストベクタ（``tests/vectors/*.json``）の読み込みと検証。

テストベクタは iOS / Android / Python の 3 実装が共有する機械可読な契約データである。
形式は ``tests/vectors/README.md`` を参照。

* :func:`find_vectors_dir` — ベクタディレクトリの探索（CLI 用）。
* :func:`load_vector_files` — JSON の読み込み。
* :func:`run_vectors` — 全ベクタを実装に対して検証する（``p2pgps vectors``）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from .protocol import (
    ControlCommand,
    ControlLengthError,
    ExtendedPacket,
    LocationPacket,
    Status,
    UnknownOpcodeError,
    ValidationError,
    from_hex,
)

__all__ = [
    "VECTOR_SCHEMA_PREFIX",
    "SUPPORTED_KINDS",
    "VectorFile",
    "VectorResult",
    "find_vectors_dir",
    "load_vector_files",
    "run_vectors",
    "check_location_vector",
    "check_extended_vector",
    "check_control_vector",
    "check_status_vector",
    "check_sequence_scenario",
]

VECTOR_SCHEMA_PREFIX: Final[str] = "p2pgps-protocol/test-vectors/"
SUPPORTED_KINDS: Final[tuple[str, ...]] = (
    "location",
    "extended",
    "control",
    "status",
    "sequence",
)


@dataclass(slots=True)
class VectorFile:
    """1 つのベクタ JSON ファイル。"""

    path: Path
    schema: str
    kind: str
    data: dict[str, Any]

    @property
    def vectors(self) -> list[dict[str, Any]]:
        return list(self.data.get("vectors", []))

    @property
    def scenarios(self) -> list[dict[str, Any]]:
        return list(self.data.get("scenarios", []))


@dataclass(slots=True)
class VectorResult:
    """1 ベクタの検証結果。"""

    file: str
    vector_id: str
    ok: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "id": self.vector_id,
            "ok": self.ok,
            "errors": self.errors,
        }


def find_vectors_dir(explicit: str | Path | None = None) -> Path:
    """ベクタディレクトリを探す。

    優先順位: 明示指定 → リポジトリ直下 ``tests/vectors`` →
    カレントディレクトリ配下 ``tests/vectors``。
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / "tests" / "vectors")
    candidates.append(Path.cwd() / "tests" / "vectors")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        "tests/vectors not found (searched: "
        + ", ".join(str(path) for path in candidates)
        + ")"
    )


def load_vector_files(directory: str | Path) -> list[VectorFile]:
    """ディレクトリ内の ``*.json`` を読み込む（ファイル名順）。"""
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"vector directory not found: {root}")
    files: list[VectorFile] = []
    for path in sorted(root.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        schema = data.get("schema", "")
        if not isinstance(schema, str) or not schema.startswith(VECTOR_SCHEMA_PREFIX):
            raise ValueError(
                f"{path.name}: schema must start with {VECTOR_SCHEMA_PREFIX!r}, "
                f"got {schema!r}"
            )
        kind = data.get("kind")
        if kind not in SUPPORTED_KINDS:
            raise ValueError(f"{path.name}: unsupported kind {kind!r}")
        files.append(VectorFile(path=path, schema=schema, kind=kind, data=data))
    return files


def _expect_reason(packet: LocationPacket) -> str | None:
    try:
        packet.validate()
    except ValidationError as exc:
        return str(exc.reason)
    return None


def check_location_vector(vector: dict[str, Any]) -> list[str]:
    """Location ベクタ 1 件を検証し、エラー文字列のリストを返す。"""
    errors: list[str] = []
    vector_id = vector.get("id", "<unknown>")
    wire = dict(vector["wire"])
    expected_hex = str(vector["hex"]).lower()
    expect = vector.get("expect", {})

    packet = LocationPacket(**wire)
    try:
        encoded = packet.encode()
    except Exception as exc:  # noqa: BLE001 - ベクタ検証で原因を集約する
        return [f"{vector_id}: encode failed: {exc}"]
    if encoded.hex() != expected_hex:
        errors.append(
            f"{vector_id}: encode mismatch: {encoded.hex()} != {expected_hex}"
        )

    try:
        decoded = LocationPacket.decode(from_hex(expected_hex))
    except Exception as exc:  # noqa: BLE001
        return errors + [f"{vector_id}: decode failed: {exc}"]
    if decoded.to_dict() != wire:
        errors.append(f"{vector_id}: decode mismatch: {decoded.to_dict()} != {wire}")

    valid = decoded.is_valid
    if valid != bool(expect.get("valid")):
        errors.append(
            f"{vector_id}: valid={valid} but expect.valid={expect.get('valid')}"
        )
    expected_reason = expect.get("reason")
    actual_reason = _expect_reason(decoded)
    if actual_reason != expected_reason:
        errors.append(
            f"{vector_id}: reason={actual_reason!r} but expect.reason={expected_reason!r}"
        )
    if "valid_fix" in expect and decoded.has_valid_fix != bool(expect["valid_fix"]):
        errors.append(
            f"{vector_id}: valid_fix={decoded.has_valid_fix} "
            f"but expect.valid_fix={expect['valid_fix']}"
        )

    degrees = vector.get("degrees")
    if degrees:
        remaining = {
            key: value
            for key, value in wire.items()
            if key not in ("latitude", "longitude")
        }
        from_degrees = LocationPacket.from_degrees(
            degrees["latitude"], degrees["longitude"], **remaining
        )
        if (from_degrees.latitude, from_degrees.longitude) != (
            wire["latitude"],
            wire["longitude"],
        ):
            errors.append(
                f"{vector_id}: degrees conversion mismatch: "
                f"({from_degrees.latitude}, {from_degrees.longitude}) != "
                f"({wire['latitude']}, {wire['longitude']})"
            )
    return errors


def check_extended_vector(vector: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    vector_id = vector.get("id", "<unknown>")
    wire = dict(vector["wire"])
    expected_hex = str(vector["hex"]).lower()
    expect = vector.get("expect", {})

    packet = ExtendedPacket(**wire)
    if packet.encode().hex() != expected_hex:
        errors.append(
            f"{vector_id}: encode mismatch: {packet.encode().hex()} != {expected_hex}"
        )
    decoded = ExtendedPacket.decode(from_hex(expected_hex))
    if decoded.to_dict() != wire:
        errors.append(f"{vector_id}: decode mismatch: {decoded.to_dict()} != {wire}")
    valid = decoded.is_valid
    if valid != bool(expect.get("valid")):
        errors.append(
            f"{vector_id}: valid={valid} but expect.valid={expect.get('valid')}"
        )
    try:
        decoded.validate()
        actual_reason = None
    except ValidationError as exc:
        actual_reason = str(exc.reason)
    if actual_reason != expect.get("reason"):
        errors.append(
            f"{vector_id}: reason={actual_reason!r} "
            f"but expect.reason={expect.get('reason')!r}"
        )
    return errors


def check_control_vector(vector: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    vector_id = vector.get("id", "<unknown>")
    expected_hex = str(vector["hex"]).lower()
    expect = vector.get("expect", {})
    command_data = vector.get("command")

    if expect.get("valid", True) and command_data is not None:
        command = ControlCommand.from_dict(command_data)
        encoded = command.encode()
        if encoded.hex() != expected_hex:
            errors.append(
                f"{vector_id}: encode mismatch: {encoded.hex()} != {expected_hex}"
            )
        decoded = ControlCommand.decode(from_hex(expected_hex))
        expected_decoded = expect.get("decoded", {})
        if decoded.to_dict() != {
            key: value
            for key, value in expected_decoded.items()
            if key != "normalized_interval_ms"
        }:
            errors.append(
                f"{vector_id}: decode mismatch: {decoded.to_dict()} != "
                f"{expected_decoded}"
            )
        if "normalized_interval_ms" in expected_decoded:
            if decoded.normalized_interval_ms != expected_decoded[
                "normalized_interval_ms"
            ]:
                errors.append(
                    f"{vector_id}: normalized_interval_ms="
                    f"{decoded.normalized_interval_ms} != "
                    f"{expected_decoded['normalized_interval_ms']}"
                )
        return errors

    # 異常系: デコードが仕様どおりの例外になるか
    expected_error = expect.get("error")
    try:
        ControlCommand.decode(from_hex(expected_hex))
    except UnknownOpcodeError as exc:
        if expected_error != "unknown_opcode":
            errors.append(f"{vector_id}: unexpected UnknownOpcodeError: {exc}")
        elif exc.last_error != expect.get("last_error"):
            errors.append(
                f"{vector_id}: last_error={exc.last_error} != {expect.get('last_error')}"
            )
    except ControlLengthError as exc:
        if expected_error != "bad_length":
            errors.append(f"{vector_id}: unexpected ControlLengthError: {exc}")
        elif exc.last_error != expect.get("last_error"):
            errors.append(
                f"{vector_id}: last_error={exc.last_error} != {expect.get('last_error')}"
            )
    else:
        errors.append(f"{vector_id}: expected {expected_error} but decode succeeded")
    return errors


def check_status_vector(vector: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    vector_id = vector.get("id", "<unknown>")
    wire = dict(vector["wire"])
    expected_hex = str(vector["hex"]).lower()
    expect = vector.get("expect", {})

    packet = Status(**wire)
    if packet.encode().hex() != expected_hex:
        errors.append(
            f"{vector_id}: encode mismatch: {packet.encode().hex()} != {expected_hex}"
        )
    decoded = Status.decode(from_hex(expected_hex))
    if decoded.to_dict() != wire:
        errors.append(f"{vector_id}: decode mismatch: {decoded.to_dict()} != {wire}")
    valid = decoded.is_valid
    if valid != bool(expect.get("valid")):
        errors.append(
            f"{vector_id}: valid={valid} but expect.valid={expect.get('valid')}"
        )
    try:
        decoded.validate()
        actual_reason = None
    except ValidationError as exc:
        actual_reason = str(exc.reason)
    if actual_reason != expect.get("reason"):
        errors.append(
            f"{vector_id}: reason={actual_reason!r} "
            f"but expect.reason={expect.get('reason')!r}"
        )
    return errors


def check_sequence_scenario(scenario: dict[str, Any]) -> list[str]:
    """sequence シナリオ（複数パケット）を検証する。"""
    from .filter import SequenceTracker

    errors: list[str] = []
    scenario_id = scenario.get("id", "<unknown>")
    expect = scenario.get("expect", {})
    expected_status = list(expect.get("sequence_status", []))
    expected_accepted = list(expect.get("accepted", []))
    tracker = SequenceTracker()
    actual_status: list[str] = []
    actual_accepted: list[bool] = []
    for packet_data in scenario.get("packets", []):
        wire = dict(packet_data["wire"])
        expected_hex = str(packet_data["hex"]).lower()
        packet = LocationPacket(**wire)
        if packet.encode().hex() != expected_hex:
            errors.append(
                f"{scenario_id}: packet encode mismatch: "
                f"{packet.encode().hex()} != {expected_hex}"
            )
        decoded = LocationPacket.decode(from_hex(expected_hex))
        actual_accepted.append(decoded.is_valid)
        actual_status.append(tracker.observe(decoded.sequence).value)
    if actual_status != expected_status:
        errors.append(
            f"{scenario_id}: sequence_status={actual_status} != {expected_status}"
        )
    if actual_accepted != expected_accepted:
        errors.append(
            f"{scenario_id}: accepted={actual_accepted} != {expected_accepted}"
        )
    return errors


_CHECKERS = {
    "location": check_location_vector,
    "extended": check_extended_vector,
    "control": check_control_vector,
    "status": check_status_vector,
}


def run_vectors(directory: str | Path | None = None) -> list[VectorResult]:
    """全ベクタを検証し、結果のリストを返す。"""
    root = find_vectors_dir(directory)
    results: list[VectorResult] = []
    for vector_file in load_vector_files(root):
        if vector_file.kind == "sequence":
            for scenario in vector_file.scenarios:
                errors = check_sequence_scenario(scenario)
                results.append(
                    VectorResult(
                        file=vector_file.path.name,
                        vector_id=str(scenario.get("id", "<unknown>")),
                        ok=not errors,
                        errors=errors,
                    )
                )
            continue
        checker = _CHECKERS[vector_file.kind]
        for vector in vector_file.vectors:
            errors = checker(vector)
            results.append(
                VectorResult(
                    file=vector_file.path.name,
                    vector_id=str(vector.get("id", "<unknown>")),
                    ok=not errors,
                    errors=errors,
                )
            )
    return results
