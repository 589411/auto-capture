"""Click annotation — draw visual markers on screenshots at click positions."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .config import AnnotationConfig


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple.

    Args:
        hex_color: Color like '#FF3B30' or 'FF3B30'.

    Returns:
        (R, G, B) tuple.
    """
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def annotate_click(
    image_path: Path,
    click_pos: tuple[float, float],
    window_origin: tuple[float, float] = (0, 0),
    config: AnnotationConfig | None = None,
    output_path: Path | None = None,
    retina_scale: int = 2,
) -> Path:
    """Draw a click annotation on a screenshot.

    Args:
        image_path: Path to the screenshot PNG.
        click_pos: (x, y) screen coordinates of the click.
        window_origin: (x, y) screen coordinates of the captured window's top-left.
        config: Annotation style config. Uses defaults if None.
        output_path: Where to save. If None, overwrites the original.
        retina_scale: Retina display scale factor (2 for standard Retina).

    Returns:
        Path to the annotated image.
    """
    if config is None:
        config = AnnotationConfig()

    if not config.enabled:
        return image_path

    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    color = hex_to_rgb(config.color)

    # Convert screen coordinates to image pixel coordinates
    # On Retina displays, image pixels = screen points * retina_scale
    rel_x = (click_pos[0] - window_origin[0]) * retina_scale
    rel_y = (click_pos[1] - window_origin[1]) * retina_scale

    # Scale annotation dimensions for Retina
    size = config.size * retina_scale
    line_width = config.line_width * retina_scale
    padding = config.padding * retina_scale

    half_size = size // 2

    if config.shape == "circle":
        bbox = [
            rel_x - half_size - padding,
            rel_y - half_size - padding,
            rel_x + half_size + padding,
            rel_y + half_size + padding,
        ]
        draw.ellipse(bbox, outline=color, width=line_width)
    else:
        # Default: rectangle
        bbox = [
            rel_x - half_size - padding,
            rel_y - half_size - padding,
            rel_x + half_size + padding,
            rel_y + half_size + padding,
        ]
        draw.rectangle(bbox, outline=color, width=line_width)

    save_path = output_path or image_path
    img.save(save_path)
    return save_path


def get_window_origin(window_id: int) -> tuple[float, float]:
    """Get the screen origin (top-left point) of a window.

    Args:
        window_id: The CGWindowID.

    Returns:
        (x, y) of the window's top-left corner in screen coordinates.
    """
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionIncludingWindow,
        kCGWindowBounds,
    )

    info_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, window_id
    )

    if info_list and len(info_list) > 0:
        bounds = info_list[0].get(kCGWindowBounds, {})
        return (bounds.get("X", 0), bounds.get("Y", 0))

    return (0, 0)
