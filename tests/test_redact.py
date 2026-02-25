"""Tests for auto_capture.redact."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw, ImageFont

from auto_capture.config import DEFAULT_REDACT_PATTERNS, RedactConfig
from auto_capture.redact import (
    SensitiveRegion,
    _apply_mosaic,
    _mask_text,
    luhn_check,
    redact_image,
)


# ── Luhn check ──────────────────────────────────────────────

def test_luhn_valid_visa():
    """Known valid Visa test number."""
    assert luhn_check("4111111111111111") is True


def test_luhn_valid_mastercard():
    """Known valid Mastercard test number."""
    assert luhn_check("5500000000000004") is True


def test_luhn_valid_with_separators():
    """Luhn should ignore dashes and spaces."""
    assert luhn_check("4111-1111-1111-1111") is True
    assert luhn_check("4111 1111 1111 1111") is True


def test_luhn_invalid():
    """Random digits should fail Luhn."""
    assert luhn_check("1234567890123456") is False


def test_luhn_too_short():
    """Too few digits should fail."""
    assert luhn_check("12345") is False


def test_luhn_too_long():
    """More than 19 digits should fail."""
    assert luhn_check("1" * 20) is False


# ── Mask text ────────────────────────────────────────────────

def test_mask_text_long():
    result = _mask_text("4111111111111111")
    assert result.startswith("41")
    assert result.endswith("11")
    assert "*" in result
    assert len(result) == 16


def test_mask_text_short():
    assert _mask_text("abc") == "****"


def test_mask_text_medium():
    result = _mask_text("sk-abc123")
    assert result.startswith("sk")
    assert result.endswith("23")
    assert "*" in result


# ── Mosaic ───────────────────────────────────────────────────

def test_apply_mosaic_changes_pixels(tmp_path):
    """Mosaic should visibly alter the targeted region."""
    img = Image.new("RGB", (200, 200), color=(255, 0, 0))

    # Draw some detailed content in the target region
    draw = ImageDraw.Draw(img)
    for i in range(50, 150):
        c = (i, 255 - i, i // 2)
        draw.line([(50, i), (150, i)], fill=c)

    # Sample a pixel before mosaic
    before = img.getpixel((100, 100))

    region = SensitiveRegion(x=50, y=50, w=100, h=100, pattern_name="test", matched_text="***")
    _apply_mosaic(img, region, block_size=10)

    after = img.getpixel((100, 100))
    # The pixel value should have changed (mosaic effect)
    assert before != after


def test_apply_mosaic_does_not_affect_outside(tmp_path):
    """Pixels outside the mosaic region should be unchanged."""
    img = Image.new("RGB", (200, 200), color=(0, 128, 255))

    region = SensitiveRegion(x=50, y=50, w=50, h=50, pattern_name="test", matched_text="***")
    _apply_mosaic(img, region, block_size=5)

    # Corner pixel should be unaffected
    assert img.getpixel((0, 0)) == (0, 128, 255)
    assert img.getpixel((199, 199)) == (0, 128, 255)


# ── RedactConfig ──────────────────────────────────────────────

def test_redact_config_defaults():
    """Default RedactConfig should be disabled with all patterns."""
    config = RedactConfig()
    assert config.enabled is False
    assert "credit_card" in config.patterns
    assert "openai_key" in config.patterns
    assert "email" in config.patterns
    assert config.block_size == 10
    assert config.padding == 6


def test_redact_config_disabled_patterns():
    """Disabled patterns should be listed."""
    config = RedactConfig(enabled=True, disabled_patterns=["email"])
    assert "email" in config.disabled_patterns


# ── Pattern matching ──────────────────────────────────────────

def test_default_patterns_compile():
    """All default patterns should be valid regex."""
    import re
    for name, pattern in DEFAULT_REDACT_PATTERNS.items():
        compiled = re.compile(pattern, re.IGNORECASE)
        assert compiled is not None, f"Pattern {name} failed to compile"


def test_credit_card_pattern_matches():
    """Credit card pattern should match various formats."""
    import re
    pattern = re.compile(DEFAULT_REDACT_PATTERNS["credit_card"])

    # Standard formats
    assert pattern.search("4111111111111111")
    assert pattern.search("4111-1111-1111-1111")
    assert pattern.search("4111 1111 1111 1111")


def test_openai_key_pattern():
    """OpenAI key pattern should match sk-... strings."""
    import re
    pattern = re.compile(DEFAULT_REDACT_PATTERNS["openai_key"])
    assert pattern.search("sk-abcdefghijklmnopqrstuvwx")
    assert not pattern.search("sk-short")


def test_email_pattern():
    """Email pattern should match standard addresses."""
    import re
    pattern = re.compile(DEFAULT_REDACT_PATTERNS["email"])
    assert pattern.search("user@example.com")
    assert pattern.search("test.name+tag@domain.co.jp")
    assert not pattern.search("not-an-email")


def test_github_token_pattern():
    """GitHub token pattern should match ghp_, gho_, etc."""
    import re
    pattern = re.compile(DEFAULT_REDACT_PATTERNS["github_token"])
    token = "ghp_" + "a" * 40
    assert pattern.search(token)
    assert not pattern.search("ghp_tooshort")


# ── redact_image disabled ─────────────────────────────────────

def test_redact_image_disabled(tmp_path):
    """When disabled, redact_image should return immediately without changes."""
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    config = RedactConfig(enabled=False)
    result_path, regions = redact_image(img_path, config)

    assert result_path == img_path
    assert regions == []


# ── Integration with OCR (mocked) ─────────────────────────────

def test_redact_image_with_mocked_ocr(tmp_path):
    """redact_image should mosaic detected sensitive regions."""
    # Create a test image
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Draw some "text" area (won't actually be text, but we mock OCR)
    draw.rectangle([100, 100, 400, 130], fill=(0, 0, 0))
    img_path = tmp_path / "screenshot.png"
    img.save(img_path)

    config = RedactConfig(enabled=True)

    # Mock the OCR to return a "credit card number"
    mock_bbox = MagicMock()
    mock_bbox.origin.x = 0.125    # 100/800
    mock_bbox.origin.y = 1.0 - 130/600 - 30/600  # Vision uses bottom-left origin
    mock_bbox.size.width = 300/800  # 0.375
    mock_bbox.size.height = 30/600  # 0.05

    # The Luhn-valid test card number
    mock_candidate = MagicMock()
    mock_candidate.string.return_value = "4111 1111 1111 1111"
    # boundingBoxForRange_error_ returns the same bbox
    mock_rect_obs = MagicMock()
    mock_rect_obs.boundingBox.return_value = mock_bbox
    mock_candidate.boundingBoxForRange_error_.return_value = (mock_rect_obs, None)

    mock_ocr_results = [{
        "text": "4111 1111 1111 1111",
        "candidate": mock_candidate,
        "bbox": mock_bbox,
    }]

    with patch("auto_capture.redact._ocr_image", return_value=(mock_ocr_results, (800, 600))):
        result_path, regions = redact_image(img_path, config)

    assert result_path == img_path
    assert len(regions) == 1
    assert regions[0].pattern_name == "credit_card"
    assert "****" not in regions[0].matched_text or "*" in regions[0].matched_text

    # Verify the image was modified
    modified = Image.open(result_path)
    assert modified.size == (800, 600)
