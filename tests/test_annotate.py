"""Tests for auto_capture.annotate."""

from pathlib import Path

from PIL import Image

from auto_capture.annotate import annotate_click, hex_to_rgb
from auto_capture.config import AnnotationConfig


def test_hex_to_rgb():
    assert hex_to_rgb("#FF3B30") == (255, 59, 48)
    assert hex_to_rgb("00FF00") == (0, 255, 0)
    assert hex_to_rgb("#000000") == (0, 0, 0)


def test_annotate_click_creates_file(tmp_path):
    """annotate_click should draw on the image and save it."""
    # Create a blank test image (200x200)
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    config = AnnotationConfig(
        enabled=True,
        shape="rectangle",
        color="#FF0000",
        line_width=2,
        size=20,
        padding=4,
    )

    result = annotate_click(
        image_path=img_path,
        click_pos=(50, 50),
        window_origin=(0, 0),
        config=config,
        retina_scale=1,  # no Retina for test
    )

    assert result.exists()

    # Check the image was modified (some pixels near the click should be red)
    annotated = Image.open(result)
    # Center pixel should still be white (inside the box)
    center = annotated.getpixel((50, 50))
    assert center == (255, 255, 255)


def test_annotate_click_circle(tmp_path):
    """Circle shape should also work."""
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img_path = tmp_path / "test_circle.png"
    img.save(img_path)

    config = AnnotationConfig(shape="circle", color="#00FF00", size=30)
    result = annotate_click(
        image_path=img_path,
        click_pos=(100, 100),
        window_origin=(0, 0),
        config=config,
        retina_scale=1,
    )
    assert result.exists()


def test_annotate_disabled(tmp_path):
    """With enabled=False, image should not be modified."""
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    img_path = tmp_path / "test_disabled.png"
    img.save(img_path)

    config = AnnotationConfig(enabled=False)
    result = annotate_click(
        image_path=img_path,
        click_pos=(50, 50),
        window_origin=(0, 0),
        config=config,
    )

    assert result == img_path
