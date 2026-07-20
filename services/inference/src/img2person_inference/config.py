"""Environment-driven service configuration."""

import os
from dataclasses import dataclass
from typing import Literal

Mode = Literal["mock", "lhm"]

MODE_ENV = "IMG2PERSON_INFERENCE_MODE"
PORT_ENV = "IMG2PERSON_INFERENCE_PORT"


@dataclass(frozen=True)
class Settings:
    mode: Mode
    port: int


def load_settings() -> Settings:
    mode_raw = os.environ.get(MODE_ENV, "mock").strip().lower()
    if mode_raw not in ("mock", "lhm"):
        raise ValueError(f"{MODE_ENV} must be 'mock' or 'lhm', got {mode_raw!r}")
    port_raw = os.environ.get(PORT_ENV, "8000").strip()
    try:
        port = int(port_raw)
    except ValueError:
        raise ValueError(f"{PORT_ENV} must be an integer, got {port_raw!r}") from None
    if not (1 <= port <= 65535):
        raise ValueError(f"{PORT_ENV} out of range: {port}")
    return Settings(mode=mode_raw, port=port)  # type: ignore[arg-type]
