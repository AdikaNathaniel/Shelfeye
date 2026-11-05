"""Cheap local image checks, so we only pay for an OpenAI call when the shelf changes."""
import io

from PIL import Image, ImageChops

FINGERPRINT_SIZE = (160, 90)
PIXEL_DIFF_LEVEL = 30  # 0-255; smaller differences are treated as sensor noise


def fingerprint(path):
    """A small greyscale copy of the image used for change detection."""
    with Image.open(path) as img:
        return img.convert("L").resize(FINGERPRINT_SIZE)


def changed_fraction(a, b):
    """Fraction of pixels (0.0-1.0) that differ noticeably between two fingerprints."""
    diff = ImageChops.difference(a, b).point(lambda p: 255 if p > PIXEL_DIFF_LEVEL else 0)
    return diff.histogram()[255] / (a.width * a.height)


def jpeg_for_api(path, max_side=1536):
    """Downscale and re-encode the photo to keep upload size and API cost down."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue()
