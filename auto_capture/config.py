"""Configuration management for auto-capture."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".auto-capture.toml"


@dataclass
class AnnotationConfig:
    """Settings for click annotation overlay."""

    enabled: bool = True
    shape: str = "rectangle"  # "rectangle" or "circle"
    color: str = "#FF3B30"
    line_width: int = 3
    size: int = 40
    padding: int = 8


@dataclass
class CaptureConfig:
    """Settings for screen capture."""

    format: str = "png"
    delay_ms: int = 100  # ms to wait after click before capturing


@dataclass
class HotkeyConfig:
    """Settings for manual trigger hotkey."""

    trigger: str = "ctrl+shift+s"


@dataclass
class Config:
    """Top-level configuration."""

    annotation: AnnotationConfig = field(default_factory=AnnotationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load config from TOML file. Falls back to defaults if file doesn't exist."""
        config_path = path or DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return cls()

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        config = cls()

        if "annotation" in data:
            ann = data["annotation"]
            config.annotation = AnnotationConfig(
                enabled=ann.get("enabled", True),
                shape=ann.get("shape", "rectangle"),
                color=ann.get("color", "#FF3B30"),
                line_width=ann.get("line_width", 3),
                size=ann.get("size", 40),
                padding=ann.get("padding", 8),
            )

        if "capture" in data:
            cap = data["capture"]
            config.capture = CaptureConfig(
                format=cap.get("format", "png"),
                delay_ms=cap.get("delay_ms", 100),
            )

        if "hotkey" in data:
            hk = data["hotkey"]
            config.hotkey = HotkeyConfig(
                trigger=hk.get("trigger", "ctrl+shift+s"),
            )

        return config
