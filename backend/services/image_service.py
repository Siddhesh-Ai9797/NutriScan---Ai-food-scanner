"""
Turns any uploaded photo into a clean JPEG before it reaches the model,
GPT-4o or S3. Handles iPhone HEIC photos, phone rotation, and very large
images, and rejects files that are not real images with a clear message.
"""
import io

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()  # lets Pillow open .heic / .heif (iPhone default)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SIDE_PX      = 2048
NOT_AN_IMAGE     = "We couldn't read that file as a photo. Please upload a JPEG, PNG, WEBP or iPhone photo."
TOO_LARGE        = "Image too large. Please upload an image under 10MB."


class ImageError(ValueError):
    """Raised with a message that is safe to show to the user."""


def normalize_image(raw: bytes) -> bytes:
    if not raw:
        raise ImageError(NOT_AN_IMAGE)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError(TOO_LARGE)
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)          # respect phone rotation
            if img.width < 32 or img.height < 32:
                raise ImageError("That photo is too small. Please take a closer photo of your food.")
            img = img.convert("RGB")
            img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=90)
            return out.getvalue()
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageError(NOT_AN_IMAGE)
