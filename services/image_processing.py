from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from models import ImageAsset

THUMBNAIL_CONTENT_TYPE = "image/jpeg"
THUMBNAIL_EXTENSION = ".jpg"


class InvalidImageError(RuntimeError):
    """Raised when the uploaded payload is not a valid image."""


@dataclass(slots=True)
class ProcessedImage:
    width: int
    height: int
    orientation: str
    content_type: str
    thumbnail_bytes: bytes
    thumbnail_content_type: str = THUMBNAIL_CONTENT_TYPE
    thumbnail_extension: str = THUMBNAIL_EXTENSION


def process_image_upload(file_bytes: bytes, thumbnail_max_size: int = 640) -> ProcessedImage:
    try:
        with Image.open(BytesIO(file_bytes)) as source_image:
            source_image.load()
            width, height = source_image.size
            content_type = Image.MIME.get(source_image.format) or "application/octet-stream"
            normalized_image = ImageOps.exif_transpose(source_image)
            thumbnail_bytes = _build_thumbnail(normalized_image, thumbnail_max_size)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Le fichier envoyé n'est pas une image valide.") from exc

    return ProcessedImage(
        width=width,
        height=height,
        orientation=detect_orientation(width, height),
        content_type=content_type,
        thumbnail_bytes=thumbnail_bytes,
    )


def detect_orientation(width: int | None, height: int | None) -> str:
    if not width or not height:
        return ImageAsset.ORIENTATION_UNKNOWN
    if width > height:
        return ImageAsset.ORIENTATION_LANDSCAPE
    if height > width:
        return ImageAsset.ORIENTATION_PORTRAIT
    return ImageAsset.ORIENTATION_SQUARE


def _build_thumbnail(image: Image.Image, thumbnail_max_size: int) -> bytes:
    preview = image.copy()

    if preview.mode in {"RGBA", "LA"} or (preview.mode == "P" and "transparency" in preview.info):
        rgba_image = preview.convert("RGBA")
        flattened = Image.new("RGB", preview.size, (255, 255, 255))
        flattened.paste(rgba_image, mask=rgba_image.getchannel("A"))
        preview = flattened
    elif preview.mode != "RGB":
        preview = preview.convert("RGB")

    preview.thumbnail((thumbnail_max_size, thumbnail_max_size))

    buffer = BytesIO()
    preview.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()
