"""Tests for auto_capture.config."""

from pathlib import Path

from auto_capture.config import AnnotationConfig, CaptureConfig, Config, HotkeyConfig


def test_default_config():
    """Default config should have sensible values."""
    config = Config()
    assert config.annotation.enabled is True
    assert config.annotation.color == "#FF3B30"
    assert config.annotation.shape == "rectangle"
    assert config.annotation.size == 40
    assert config.capture.format == "png"
    assert config.capture.delay_ms == 100
    assert config.hotkey.trigger == "ctrl+shift+s"


def test_load_nonexistent_file():
    """Loading from a non-existent file should return defaults."""
    config = Config.load(Path("/nonexistent/.auto-capture.toml"))
    assert config.annotation.enabled is True
    assert config.capture.format == "png"


def test_load_from_toml(tmp_path):
    """Loading from a TOML file should override defaults."""
    toml_file = tmp_path / "test-config.toml"
    toml_file.write_text("""
[annotation]
enabled = false
color = "#00FF00"
size = 60

[capture]
delay_ms = 200
format = "jpg"

[hotkey]
trigger = "ctrl+shift+x"
""")

    config = Config.load(toml_file)
    assert config.annotation.enabled is False
    assert config.annotation.color == "#00FF00"
    assert config.annotation.size == 60
    assert config.capture.delay_ms == 200
    assert config.capture.format == "jpg"
    assert config.hotkey.trigger == "ctrl+shift+x"
    # Unset values keep defaults
    assert config.annotation.shape == "rectangle"
    assert config.annotation.line_width == 3
