"""Auto-redact sensitive information in screenshots using macOS Vision OCR.

Workflow:
1. Run OCR on the screenshot via macOS Vision framework
2. Pattern-match recognized text against known sensitive formats
3. Apply mosaic (pixelation) to matched regions

Supported patterns:
- Credit card numbers (with Luhn validation)
- API keys (OpenAI, Anthropic, Google, AWS, GitHub)
- Email addresses
- Generic secret/token strings
- Custom user-defined patterns via config
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from PIL import Image

from .config import RedactConfig


class SensitiveRegion(NamedTuple):
    """A region in the image containing sensitive information."""

    x: int  # pixel x (top-left)
    y: int  # pixel y (top-left)
    w: int  # width in pixels
    h: int  # height in pixels
    pattern_name: str
    matched_text: str  # masked for safe logging


def _mask_text(text: str) -> str:
    """Partially mask text for safe logging.

    Examples:
        "4532123456789012" → "45**********9012"
        "sk-abc123xyz" → "sk**********yz"
        "short" → "sh*rt"
    """
    if len(text) <= 4:
        return "****"
    visible = max(2, len(text) // 8)
    return text[:visible] + "*" * (len(text) - visible * 2) + text[-visible:]


def luhn_check(num_str: str) -> bool:
    """Validate a number string using the Luhn algorithm.

    Used to reduce false positives for credit card detection —
    random 16-digit numbers rarely pass this check.

    Args:
        num_str: String that may contain digits and separators.

    Returns:
        True if the digits pass the Luhn check.
    """
    digits = [int(d) for d in num_str if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _ocr_image(image_path: Path) -> tuple[list[dict], tuple[int, int]]:
    """Run macOS Vision OCR on an image.

    Uses VNRecognizeTextRequest with accurate recognition level.

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (ocr_results, (img_width, img_height)).
        Each result dict has keys: text, candidate, bbox.
    """
    import Vision
    from Foundation import NSURL
    from Quartz import (
        CGImageGetHeight,
        CGImageGetWidth,
        CGImageSourceCreateImageAtIndex,
        CGImageSourceCreateWithURL,
    )

    url = NSURL.fileURLWithPath_(str(image_path))
    source = CGImageSourceCreateWithURL(url, None)
    if source is None:
        return [], (0, 0)

    cg_image = CGImageSourceCreateImageAtIndex(source, 0, None)
    if cg_image is None:
        return [], (0, 0)

    img_w = CGImageGetWidth(cg_image)
    img_h = CGImageGetHeight(cg_image)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, None
    )
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(False)  # Raw text, no auto-correct
    request.setRecognitionLanguages_(["en", "zh-Hant", "zh-Hans"])

    success, error = handler.performRequests_error_([request], None)
    if not success:
        return [], (img_w, img_h)

    results = []
    for observation in request.results():
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        text = str(candidate.string())
        bbox = observation.boundingBox()

        results.append({
            "text": text,
            "candidate": candidate,
            "bbox": bbox,
        })

    return results, (img_w, img_h)


def _bbox_to_pixels(
    bbox,
    img_w: int,
    img_h: int,
    padding: int = 0,
) -> tuple[int, int, int, int]:
    """Convert Vision normalized bounding box to pixel coordinates.

    Vision framework uses normalized coordinates (0.0–1.0) with
    origin at the **bottom-left**. PIL uses pixel coordinates with
    origin at the **top-left**.

    Args:
        bbox: CGRect from Vision (normalized, bottom-left origin).
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        padding: Extra pixels to add around the region.

    Returns:
        (x, y, w, h) in pixel coordinates, top-left origin.
    """
    x = int(bbox.origin.x * img_w) - padding
    y = int((1.0 - bbox.origin.y - bbox.size.height) * img_h) - padding
    w = int(bbox.size.width * img_w) + padding * 2
    h = int(bbox.size.height * img_h) + padding * 2

    # Clamp to image bounds
    x = max(0, x)
    y = max(0, y)
    w = min(w, img_w - x)
    h = min(h, img_h - y)

    return x, y, w, h


def _find_sensitive_regions(
    ocr_results: list[dict],
    img_w: int,
    img_h: int,
    config: RedactConfig,
) -> list[SensitiveRegion]:
    """Match OCR text against sensitive patterns and return pixel regions.

    For each text observation, checks all active patterns. When a match is
    found, attempts to get a precise sub-range bounding box via Vision's
    boundingBoxForRange API. Falls back to the full observation box.

    Args:
        ocr_results: Output from _ocr_image().
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        config: Redaction configuration.

    Returns:
        List of SensitiveRegion with pixel coordinates.
    """
    regions: list[SensitiveRegion] = []

    # Compile active patterns
    active_patterns: dict[str, re.Pattern] = {}
    for name, pattern in config.patterns.items():
        if name not in config.disabled_patterns:
            try:
                active_patterns[name] = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue

    for result in ocr_results:
        text = result["text"]
        candidate = result["candidate"]
        obs_bbox = result["bbox"]

        for name, compiled in active_patterns.items():
            for match in compiled.finditer(text):
                matched_text = match.group()

                # Extra validation: credit card must pass Luhn check
                if name == "credit_card" and not luhn_check(matched_text):
                    continue

                # Try to get precise bounding box for the matched substring
                bbox = obs_bbox  # fallback to full observation
                try:
                    ns_range = (match.start(), match.end() - match.start())
                    rect_obs, err = candidate.boundingBoxForRange_error_(
                        ns_range, None
                    )
                    if rect_obs is not None and err is None:
                        bbox = rect_obs.boundingBox()
                except Exception:
                    pass  # use observation-level bbox

                x, y, w, h = _bbox_to_pixels(bbox, img_w, img_h, config.padding)

                if w > 0 and h > 0:
                    regions.append(SensitiveRegion(
                        x=x, y=y, w=w, h=h,
                        pattern_name=name,
                        matched_text=_mask_text(matched_text),
                    ))

    return regions


def _apply_mosaic(
    img: Image.Image,
    region: SensitiveRegion,
    block_size: int = 10,
) -> None:
    """Apply mosaic (pixelation) effect to a region in-place.

    Shrinks the region to tiny dimensions then scales back up with
    nearest-neighbor interpolation, creating a blocky mosaic effect.

    Args:
        img: PIL Image to modify (in-place).
        region: Region to pixelate.
        block_size: Mosaic block size in pixels. Larger = more blurred.
    """
    x, y, w, h = region.x, region.y, region.w, region.h
    box = (x, y, x + w, y + h)

    cropped = img.crop(box)
    small_w = max(1, w // block_size)
    small_h = max(1, h // block_size)

    small = cropped.resize((small_w, small_h), Image.NEAREST)
    mosaic = small.resize((w, h), Image.NEAREST)
    img.paste(mosaic, (x, y))


def redact_image(
    image_path: Path,
    config: RedactConfig | None = None,
    output_path: Path | None = None,
) -> tuple[Path, list[SensitiveRegion]]:
    """Detect and mosaic sensitive information in a screenshot.

    Uses macOS Vision framework for OCR, then matches recognized text
    against patterns for credit cards, API keys, emails, etc.
    Matched regions are covered with a mosaic (pixelation) effect.

    This should be called BEFORE annotation (click markers) so that
    the redaction operates on the clean screenshot.

    Args:
        image_path: Path to the screenshot.
        config: Redaction settings. Uses defaults (disabled) if None.
        output_path: Where to save. If None, overwrites the original.

    Returns:
        Tuple of (output_path, list of redacted regions).
    """
    if config is None:
        config = RedactConfig()

    if not config.enabled:
        return (output_path or image_path), []

    # Run OCR
    ocr_results, (img_w, img_h) = _ocr_image(image_path)
    if not ocr_results:
        return (output_path or image_path), []

    # Find sensitive regions
    regions = _find_sensitive_regions(ocr_results, img_w, img_h, config)
    if not regions:
        return (output_path or image_path), []

    # Apply mosaic to each region
    img = Image.open(image_path)
    for region in regions:
        _apply_mosaic(img, region, config.block_size)

    save_path = output_path or image_path
    img.save(save_path)
    img.close()

    return save_path, regions
