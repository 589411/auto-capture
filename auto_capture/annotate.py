"""Click annotation — draw visual markers and create zoom-to-click GIFs."""

from __future__ import annotations

import math
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


def _draw_click_marker(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    scale: int = 2,
):
    """Draw a mouse-click style marker: concentric ripple rings + crosshair.

    This looks like a "click happened here" indicator — much more intuitive
    than a plain rectangle box.

    Args:
        draw: PIL ImageDraw instance.
        cx: X pixel coordinate of click center.
        cy: Y pixel coordinate of click center.
        color: RGB color tuple.
        scale: Retina scale factor (2 for standard Retina).
    """
    # Outer ripple ring (large, semi-transparent feel via thinner line)
    r_outer = 36 * scale
    draw.ellipse(
        [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
        outline=color,
        width=2 * scale,
    )

    # Inner ripple ring
    r_inner = 20 * scale
    draw.ellipse(
        [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
        outline=color,
        width=2 * scale,
    )

    # Center dot (filled)
    r_dot = 5 * scale
    draw.ellipse(
        [cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot],
        fill=color,
    )

    # Crosshair lines extending beyond the outer ring
    gap = r_outer + 4 * scale  # start of crosshair lines
    arm = 16 * scale            # length of each arm
    lw = 2 * scale              # line width

    # Top
    draw.line([(cx, cy - gap), (cx, cy - gap - arm)], fill=color, width=lw)
    # Bottom
    draw.line([(cx, cy + gap), (cx, cy + gap + arm)], fill=color, width=lw)
    # Left
    draw.line([(cx - gap, cy), (cx - gap - arm, cy)], fill=color, width=lw)
    # Right
    draw.line([(cx + gap, cy), (cx + gap + arm, cy)], fill=color, width=lw)


def annotate_click(
    image_path: Path,
    click_pos: tuple[float, float],
    window_origin: tuple[float, float] = (0, 0),
    config: AnnotationConfig | None = None,
    output_path: Path | None = None,
    retina_scale: int = 2,
) -> Path:
    """Draw a click annotation on a screenshot.

    Draws a concentric-ripple + crosshair marker at the click position,
    which is more intuitive than a plain rectangle.

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
    rel_x = (click_pos[0] - window_origin[0]) * retina_scale
    rel_y = (click_pos[1] - window_origin[1]) * retina_scale

    _draw_click_marker(draw, rel_x, rel_y, color, scale=retina_scale)

    save_path = output_path or image_path
    img.save(save_path)
    return save_path


def create_zoom_gif(
    image_path: Path,
    click_pos: tuple[float, float],
    window_origin: tuple[float, float] = (0, 0),
    output_path: Path | None = None,
    retina_scale: int = 2,
    num_frames: int = 12,
    zoom_factor: float = 4.0,
    frame_duration_ms: int = 80,
    hold_frames: int = 3,
    color: str = "#FF3B30",
) -> Path:
    """Create an animated GIF that zooms from full screenshot to click location.

    The animation helps readers understand WHERE on the screen the click is:
    - Frame 1: Full screenshot (overview — "it's in the top-left area")
    - Frames 2..N: Smoothly zoom into the click position
    - Final frames: Zoomed in with click marker (held for emphasis)

    Args:
        image_path: Path to the full screenshot PNG.
        click_pos: (x, y) screen coordinates of the click.
        window_origin: (x, y) of the captured area's top-left corner.
        output_path: Where to save the GIF. Defaults to same name with .gif.
        retina_scale: Retina scale factor.
        num_frames: Number of zoom transition frames.
        zoom_factor: How much to zoom in (4.0 = 400%).
        frame_duration_ms: Duration of each frame in ms.
        hold_frames: Extra frames to hold at the zoomed-in position.
        color: Click marker color.

    Returns:
        Path to the generated GIF.
    """
    if output_path is None:
        output_path = image_path.with_suffix(".gif")

    img = Image.open(image_path)
    img_w, img_h = img.size

    # Target pixel coordinates of click in the image
    target_x = (click_pos[0] - window_origin[0]) * retina_scale
    target_y = (click_pos[1] - window_origin[1]) * retina_scale

    # Clamp to image bounds
    target_x = max(0, min(target_x, img_w - 1))
    target_y = max(0, min(target_y, img_h - 1))

    # Output GIF size — use a reasonable size for web (max 800px wide)
    gif_w = min(img_w, 800)
    gif_h = int(gif_w * img_h / img_w)

    rgb_color = hex_to_rgb(color)

    frames: list[Image.Image] = []

    for i in range(num_frames + hold_frames):
        # Progress: 0.0 (full view) → 1.0 (zoomed in)
        if i < num_frames:
            t = i / max(num_frames - 1, 1)
        else:
            t = 1.0  # hold at zoomed position

        # Ease-in-out curve for smooth animation
        t_ease = (1 - math.cos(t * math.pi)) / 2

        # Calculate crop window: lerp from full image to zoomed region
        # At t=0: crop = full image
        # At t=1: crop = a small region around click point
        zoom_w = img_w / (1 + (zoom_factor - 1) * t_ease)
        zoom_h = img_h / (1 + (zoom_factor - 1) * t_ease)

        # Center the crop on the click point, clamped to image bounds
        crop_x = target_x - zoom_w / 2
        crop_y = target_y - zoom_h / 2

        # Clamp so crop doesn't go outside image
        crop_x = max(0, min(crop_x, img_w - zoom_w))
        crop_y = max(0, min(crop_y, img_h - zoom_h))

        crop_box = (
            int(crop_x),
            int(crop_y),
            int(crop_x + zoom_w),
            int(crop_y + zoom_h),
        )

        frame = img.crop(crop_box).resize((gif_w, gif_h), Image.LANCZOS)

        # Draw click marker on the last few frames (when zoomed in enough)
        if t_ease > 0.5:
            draw = ImageDraw.Draw(frame)
            # Recalculate click position relative to the crop
            marker_x = (target_x - crop_x) / zoom_w * gif_w
            marker_y = (target_y - crop_y) / zoom_h * gif_h
            # Scale marker for GIF size
            marker_scale = max(1, gif_w // 800)
            _draw_click_marker(draw, marker_x, marker_y, rgb_color, scale=marker_scale or 1)

        # Convert to RGB for GIF (no alpha)
        if frame.mode != "RGB":
            frame = frame.convert("RGB")

        frames.append(frame)

    # Save as animated GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,  # loop forever
        optimize=True,
    )

    return output_path


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
