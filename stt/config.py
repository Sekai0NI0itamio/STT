from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import tomllib


@dataclass(frozen=True, slots=True)
class STTConfig:
    root_dir: Path
    incoming_dir: Path
    outputs_dir: Path
    max_input_mb: int = 25
    sample_rate_hz: int = 16000
    audio_channels: int = 1
    chunk_seconds: int = 300
    max_parallel_files: int = 2
    backend: str = "faster-whisper"
    model: str = "small"
    emit_chunk_debug: bool = False
    fail_on_any_error: bool = True

    @property
    def max_input_bytes(self) -> int:
        return self.max_input_mb * 1024 * 1024

    @property
    def incoming_dir_abs(self) -> Path:
        return resolve_repo_path(self.root_dir, self.incoming_dir)

    @property
    def outputs_dir_abs(self) -> Path:
        return resolve_repo_path(self.root_dir, self.outputs_dir)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["root_dir"] = self.root_dir.as_posix()
        data["incoming_dir"] = self.incoming_dir.as_posix()
        data["outputs_dir"] = self.outputs_dir.as_posix()
        return data


def resolve_repo_path(root_dir: Path, configured_path: Path) -> Path:
    if configured_path.is_absolute():
        return configured_path
    return (root_dir / configured_path).resolve()


def load_config(
    config_path: str | Path = "stt.toml",
    overrides: dict[str, Any] | None = None,
) -> STTConfig:
    config_path = Path(config_path).resolve()
    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    root_dir = config_path.parent

    values: dict[str, Any] = {
        "root_dir": root_dir,
        "incoming_dir": Path(raw.get("incoming_dir", "incoming")),
        "outputs_dir": Path(raw.get("outputs_dir", "outputs")),
        "max_input_mb": int(raw.get("max_input_mb", 25)),
        "sample_rate_hz": int(raw.get("sample_rate_hz", 16000)),
        "audio_channels": int(raw.get("audio_channels", 1)),
        "chunk_seconds": int(raw.get("chunk_seconds", 300)),
        "max_parallel_files": int(raw.get("max_parallel_files", 2)),
        "backend": str(raw.get("backend", "faster-whisper")),
        "model": str(raw.get("model", "small")),
        "emit_chunk_debug": _as_bool(raw.get("emit_chunk_debug", False)),
        "fail_on_any_error": _as_bool(raw.get("fail_on_any_error", True)),
    }

    if overrides:
        for key, value in overrides.items():
            if value is None:
                continue
            if key in {"incoming_dir", "outputs_dir"}:
                values[key] = Path(str(value))
            elif key in {
                "max_input_mb",
                "sample_rate_hz",
                "audio_channels",
                "chunk_seconds",
                "max_parallel_files",
            }:
                values[key] = int(value)
            elif key in {"emit_chunk_debug", "fail_on_any_error"}:
                values[key] = _as_bool(value)
            else:
                values[key] = str(value)

    config = STTConfig(**values)
    _validate_config(config)
    return config


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    if isinstance(value, int):
        return bool(value)
    raise ValueError(f"Unsupported boolean value: {value!r}")


def _validate_config(config: STTConfig) -> None:
    if config.chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be greater than zero")
    if config.max_input_mb <= 0:
        raise ValueError("max_input_mb must be greater than zero")
    if config.sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be greater than zero")
    if config.audio_channels <= 0:
        raise ValueError("audio_channels must be greater than zero")
    if config.max_parallel_files <= 0:
        raise ValueError("max_parallel_files must be greater than zero")
    if not config.backend:
        raise ValueError("backend must be set")
    if not config.model:
        raise ValueError("model must be set")
