from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from azure.ai.vision.imageanalysis import ImageAnalysisClient
    from azure.ai.vision.imageanalysis.models import VisualFeatures
    from azure.core.credentials import AzureKeyCredential

    AZURE_VISION_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - local mode still works without the SDK.
    ImageAnalysisClient = None
    VisualFeatures = None
    AzureKeyCredential = None
    AZURE_VISION_SDK_AVAILABLE = False


class VisionError(RuntimeError):
    """Raised when image analysis cannot be completed."""


@dataclass(slots=True)
class AnalysisResult:
    description: str
    tags: list[str]
    has_people: bool
    source: str


def _unique_tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []

    for value in values:
        tag = value.strip()
        if not tag:
            continue

        lowered = tag.lower()
        if lowered in seen:
            continue

        seen.add(lowered)
        unique_values.append(tag)

    return unique_values


class AzureVisionService:
    def __init__(
        self,
        endpoint: str,
        key: str,
        language: str = "fr",
        logger: logging.Logger | None = None,
    ) -> None:
        self.endpoint = endpoint.strip()
        self.key = key.strip()
        self.language = language.strip() or "fr"
        self.logger = logger or logging.getLogger(__name__)
        self.enabled = bool(self.endpoint and self.key and AZURE_VISION_SDK_AVAILABLE)
        self._client = None

        if self.endpoint and self.key and not AZURE_VISION_SDK_AVAILABLE:
            self.logger.warning("Azure Vision SDK is not installed. Local fallback will be used instead.")

    @property
    def provider_label(self) -> str:
        return "Azure Vision" if self.enabled else "Analyse locale"

    def _get_client(self):
        if not self.enabled:
            return None

        if self._client is None:
            self._client = ImageAnalysisClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.key),
            )
        return self._client

    def analyze_image_url(self, image_url: str, original_filename: str) -> AnalysisResult:
        if not self.enabled:
            raise VisionError("Azure Vision n'est pas configuré.")

        if not image_url:
            raise VisionError("Azure Vision requiert une URL d'image publique.")

        try:
            result = self._get_client().analyze_from_url(
                image_url=image_url,
                visual_features=[
                    VisualFeatures.CAPTION,
                    VisualFeatures.TAGS,
                    VisualFeatures.PEOPLE,
                ],
                language=self.language,
                gender_neutral_caption=True,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Azure Vision analysis failed for '%s'.", original_filename)
            raise VisionError("Azure Vision n'a pas pu analyser l'image.") from exc

        return self._build_analysis_result(result, original_filename, source="azure")

    def analyze_image(self, image_data: bytes, original_filename: str) -> AnalysisResult:
        if not image_data:
            return self._local_fallback(original_filename)

        if not self.enabled:
            return self._local_fallback(original_filename)

        try:
            result = self._get_client().analyze(
                image_data=image_data,
                visual_features=[
                    VisualFeatures.CAPTION,
                    VisualFeatures.TAGS,
                    VisualFeatures.PEOPLE,
                ],
                language=self.language,
                gender_neutral_caption=True,
            )
            return self._build_analysis_result(result, original_filename, source="azure")
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "Azure Vision local analysis failed for '%s'. Falling back to local tags: %s",
                original_filename,
                exc,
            )
            return self._local_fallback(original_filename)

    def _build_analysis_result(self, result, original_filename: str, source: str) -> AnalysisResult:
        tags = [
            tag.name
            for tag in getattr(getattr(result, "tags", None), "list", [])
            if getattr(tag, "name", None)
        ]
        has_people = bool(getattr(getattr(result, "people", None), "list", []))

        if has_people:
            tags.extend(["people", "person"])

        normalized_tags = _unique_tags(tags)
        if not normalized_tags:
            normalized_tags = self._fallback_tags(original_filename)

        description = getattr(getattr(result, "caption", None), "text", None) or self._default_description(
            original_filename
        )

        return AnalysisResult(
            description=description,
            tags=normalized_tags,
            has_people=has_people,
            source=source,
        )

    def _local_fallback(self, original_filename: str) -> AnalysisResult:
        normalized_tags = self._fallback_tags(original_filename)
        has_people = any(
            tag.lower() in {"person", "people", "portrait", "face", "man", "woman", "child"}
            for tag in normalized_tags
        )
        if has_people:
            normalized_tags = _unique_tags(normalized_tags + ["people"])

        return AnalysisResult(
            description=self._default_description(original_filename),
            tags=normalized_tags,
            has_people=has_people,
            source="local",
        )

    def _fallback_tags(self, original_filename: str) -> list[str]:
        filename_stem = Path(original_filename).stem.lower()
        tokens = re.split(r"[^a-zA-Z0-9]+", filename_stem)
        fallback_tags = [token for token in tokens if len(token) > 1]
        fallback_tags.extend(["image", "envoi"])
        return _unique_tags(fallback_tags) or ["image", "envoi"]

    @staticmethod
    def _default_description(original_filename: str) -> str:
        filename_stem = Path(original_filename).stem.replace("-", " ").replace("_", " ").strip()
        if filename_stem:
            return f"Image envoyée : {filename_stem}"
        return "Image envoyée"


def build_vision_service(config: dict[str, object], logger: logging.Logger | None = None) -> AzureVisionService:
    return AzureVisionService(
        endpoint=str(config.get("VISION_ENDPOINT", "")),
        key=str(config.get("VISION_KEY", "")),
        language=str(config.get("VISION_LANGUAGE", "fr")),
        logger=logger,
    )
