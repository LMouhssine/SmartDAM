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
        tag = value.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        unique_values.append(tag)

    return unique_values


class AzureVisionService:
    def __init__(self, endpoint: str, key: str, logger: logging.Logger | None = None) -> None:
        self.endpoint = endpoint.strip()
        self.key = key.strip()
        self.logger = logger or logging.getLogger(__name__)
        self.enabled = bool(self.endpoint and self.key and AZURE_VISION_SDK_AVAILABLE)
        self._client = None

        if self.endpoint and self.key and not AZURE_VISION_SDK_AVAILABLE:
            self.logger.warning("Azure Vision SDK is not installed. Falling back to local analysis.")

    @property
    def provider_label(self) -> str:
        return "Azure Vision" if self.enabled else "Local fallback"

    def _get_client(self):
        if not self.enabled:
            return None

        if self._client is None:
            self._client = ImageAnalysisClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.key),
            )
        return self._client

    def analyze_image(self, image_data: bytes, original_filename: str) -> AnalysisResult:
        if not image_data or not self.enabled:
            return self._local_fallback(original_filename)

        try:
            result = self._get_client().analyze(
                image_data=image_data,
                visual_features=[
                    VisualFeatures.CAPTION,
                    VisualFeatures.TAGS,
                    VisualFeatures.PEOPLE,
                ],
                gender_neutral_caption=True,
            )

            tags = [
                tag.name
                for tag in getattr(getattr(result, "tags", None), "list", [])
                if getattr(tag, "name", None)
            ]
            has_people = bool(getattr(getattr(result, "people", None), "list", []))

            if has_people:
                tags.extend(["people", "person"])

            normalized_tags = _unique_tags(tags)
            description = getattr(getattr(result, "caption", None), "text", None) or self._default_description(
                original_filename
            )

            if not normalized_tags:
                fallback = self._local_fallback(original_filename)
                return AnalysisResult(
                    description=description,
                    tags=fallback.tags,
                    has_people=has_people or fallback.has_people,
                    source="local",
                )

            return AnalysisResult(
                description=description,
                tags=normalized_tags,
                has_people=has_people,
                source="azure",
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Azure Vision analysis failed, using local fallback instead: %s", exc)
            return self._local_fallback(original_filename)

    def _local_fallback(self, original_filename: str) -> AnalysisResult:
        filename_stem = Path(original_filename).stem.lower()
        tokens = re.split(r"[^a-zA-Z0-9]+", filename_stem)
        tags = [token for token in tokens if len(token) > 1]
        tags.extend(["image", "upload"])
        normalized_tags = _unique_tags(tags)

        has_people = any(
            tag in {"person", "people", "portrait", "face", "man", "woman", "child"}
            for tag in normalized_tags
        )
        if has_people:
            normalized_tags = _unique_tags(normalized_tags + ["people"])

        return AnalysisResult(
            description=self._default_description(original_filename),
            tags=normalized_tags or ["image", "upload"],
            has_people=has_people,
            source="local",
        )

    @staticmethod
    def _default_description(original_filename: str) -> str:
        filename_stem = Path(original_filename).stem.replace("-", " ").replace("_", " ").strip()
        if filename_stem:
            return f"Uploaded image: {filename_stem}"
        return "Uploaded image"


def build_vision_service(config: dict[str, object], logger: logging.Logger | None = None) -> AzureVisionService:
    return AzureVisionService(
        endpoint=str(config.get("VISION_ENDPOINT", "")),
        key=str(config.get("VISION_KEY", "")),
        logger=logger,
    )
