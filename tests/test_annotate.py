"""Tests for auto_capture.annotate."""

from pathlib import Path

from PIL import Image

from auto_capture.annotate import annotate_click, create_zoom_gif, hex_to_rgb
from auto_capture.config import AnnotationConfig


def test_hex_to_rgb():
    assert hex_to_rgb("#FF3B30") == (255, 59, 48)
    assert hex_to_rgb("00FF00") == (0, 255, 0)
    assert hex_to_rgb("#000000") == (0, 0, 0)


def test_annotate_click_creates_file(tmp_path):
    """annotate_click should draw the click marker on the image."""
    # Create a blank test image (400x400)
    img = Image.new("RGB", (400, 400), color=(255, 255, 255))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    config = AnnotationConfig(enabled=True, color="#FF0000")

    result = annotate_click(
        image_path=img_path,
        click_pos=(100, 100),
        window_origin=(0, 0),
        config=config,
        retina_scale=1,
    )

    assert result.exists()

    annotated = Image.open(result)
    # New marker has a filled center dot — it should be red
    center = annotated.getpixel((100, 100))
    assert center == (255, 0, 0), f"Center dot should be red, got {center}"

    # A pixel far from the click should still be white
    far = annotated.getpixel((10, 10))
    assert far == (255, 255, 255)


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


def test_create_zoom_gif(tmp_path):
    """create_zoom_gif should produce a valid animated GIF."""
    img = Image.new("RGB", (800, 600), color=(200, 200, 200))
    img_path = tmp_path / "screenshot.png"
    img.save(img_path)

    gif_path = create_zoom_gif(
        image_path=img_path,
        click_pos=(200, 150),
        window_origin=(0, 0),
        retina_scale=1,
        num_frames=5,
        hold_frames=2,
    )

    assert gif_path.exists()
    assert gif_path.suffix == ".gif"
    assert gif_path.stat().st_size > 0

    # Verify it's an animated GIF
    gif = Image.open(gif_path)
    assert gif.is_animated
    assert gif.n_frames >= 2  # at least some frames survived optimization
