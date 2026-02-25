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

# Built-in patterns for sensitive data detection
DEFAULT_REDACT_PATTERNS: dict[str, str] = {
    # Credit card numbers (13–19 digits, various separators) — validated with Luhn
    "credit_card": r"(?:\d[ -]?){13,19}",
    # OpenAI API keys
    "openai_key": r"\bsk-[A-Za-z0-9]{20,}\b",
    # Anthropic API keys
    "anthropic_key": r"\bsk-ant-[A-Za-z0-9_-]{20,}\b",
    # Google API keys
    "google_key": r"\bAIza[A-Za-z0-9_-]{35}\b",
    # AWS access keys
    "aws_key": r"\bAKIA[A-Z0-9]{16}\b",
    # GitHub tokens
    "github_token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b",
    # Generic secret/token strings with common prefixes
    "generic_secret": (
        r"\b(?:sk|pk|api|key|token|secret|password|bearer)"
        r"[-_][A-Za-z0-9_-]{16,}\b"
    ),
    # Email addresses
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
}


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
class RedactConfig:
    """Settings for automatic sensitive information redaction.

    When enabled, screenshots are scanned with macOS Vision OCR and
    matched text regions are covered with a mosaic (pixelation) effect.
    """

    enabled: bool = False  # opt-in — must explicitly enable
    patterns: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_REDACT_PATTERNS)
    )
    block_size: int = 10  # mosaic block size (pixels); larger = more blurred
    padding: int = 6  # extra pixels around detected text
    disabled_patterns: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Top-level configuration."""

    annotation: AnnotationConfig = field(default_factory=AnnotationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    redact: RedactConfig = field(default_factory=RedactConfig)

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

        if "redact" in data:
            r = data["redact"]
            # Start with built-in patterns, merge user extras
            patterns = dict(DEFAULT_REDACT_PATTERNS)
            if "extra_patterns" in r:
                patterns.update(r["extra_patterns"])
            config.redact = RedactConfig(
                enabled=r.get("enabled", False),
                patterns=patterns,
                block_size=r.get("block_size", 10),
                padding=r.get("padding", 6),
                disabled_patterns=r.get("disabled_patterns", []),
            )

        return config
