from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

HF_API_BASE_URL = "https://api-inference.huggingface.co/models"
DEFAULT_CLASSIFICATION_MODEL = "google/vit-base-patch16-224"
DEFAULT_CAPTION_MODEL = "nlpconnect/vit-gpt2-image-captioning"
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_TAGS = 8
MIN_CLASSIFICATION_SCORE = 0.05
IRRELEVANT_TAGS = {
    "image",
    "images",
    "photo",
    "photography",
    "picture",
    "illustration",
    "graphic",
    "art",
}
CAPTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "avec",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "for",
    "from",
    "in",
    "la",
    "le",
    "les",
    "of",
    "on",
    "sur",
    "the",
    "to",
    "une",
    "un",
}
PEOPLE_KEYWORDS = {
    "boy",
    "child",
    "children",
    "cook",
    "crowd",
    "face",
    "girl",
    "group",
    "human",
    "man",
    "men",
    "people",
    "person",
    "portrait",
    "woman",
    "women",
}


@dataclass(slots=True)
class AnalysisResult:
    description: str
    tags: list[str]
    has_people: bool
    source: str


class HuggingFaceService:
    def __init__(
        self,
        api_token: str,
        classification_model: str = DEFAULT_CLASSIFICATION_MODEL,
        caption_model: str = DEFAULT_CAPTION_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        max_tags: int = DEFAULT_MAX_TAGS,
        logger: logging.Logger | None = None,
    ) -> None:
        self.api_token = api_token.strip()
        self.classification_model = classification_model.strip() or DEFAULT_CLASSIFICATION_MODEL
        self.caption_model = caption_model.strip() or DEFAULT_CAPTION_MODEL
        self.timeout = max(5, int(timeout))
        self.max_tags = min(max(5, int(max_tags)), 10)
        self.logger = logger or logging.getLogger(__name__)
        self.enabled = bool(self.api_token)

        if not self.enabled:
            self.logger.warning("Hugging Face API token is missing. Upload analysis will use an empty fallback.")

    @property
    def provider_label(self) -> str:
        return "Hugging Face" if self.enabled else "Analyse indisponible"

    def analyze_image(self, image_path: str | Path) -> AnalysisResult:
        path = Path(image_path)
        if not path.exists():
            self.logger.warning("Image analysis skipped because the file does not exist: %s", path)
            return self._fallback_result()

        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            self.logger.warning("Image analysis skipped because the file could not be read: %s", exc)
            return self._fallback_result()

        if not image_bytes:
            self.logger.warning("Image analysis skipped because the file is empty: %s", path)
            return self._fallback_result()

        description = ""
        tags: list[str] = []

        if not self.enabled:
            return self._fallback_result()

        # Classification produces the main labels; captioning complements the record with a short description.
        try:
            classification_payload = self._query_model(self.classification_model, image_bytes)
            tags = self._parse_classification_tags(classification_payload)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Hugging Face classification failed for '%s': %s", path.name, exc)

        try:
            caption_payload = self._query_model(self.caption_model, image_bytes)
            description = self._parse_caption(caption_payload)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Hugging Face captioning failed for '%s': %s", path.name, exc)

        if description:
            tags = self._merge_tags(tags, self._caption_keywords(description))

        has_people = self._detect_people(tags, description)
        source = "huggingface" if tags or description else "fallback"
        return AnalysisResult(
            description=description,
            tags=tags[: self.max_tags],
            has_people=has_people,
            source=source,
        )

    def _query_model(self, model_id: str, image_bytes: bytes) -> Any:
        response = requests.post(
            f"{HF_API_BASE_URL}/{model_id}",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Accept": "application/json",
                "Content-Type": "application/octet-stream",
            },
            data=image_bytes,
            timeout=self.timeout,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Invalid JSON response from Hugging Face model '{model_id}'.") from exc

        if response.status_code >= 400:
            error_message = payload.get("error") if isinstance(payload, dict) else str(payload)
            raise RuntimeError(
                f"Hugging Face model '{model_id}' returned HTTP {response.status_code}: {error_message}"
            )

        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Hugging Face model '{model_id}' returned an error: {payload['error']}")

        return payload

    def _parse_classification_tags(self, payload: Any) -> list[str]:
        raw_items = payload
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            raw_items = payload[0]

        if not isinstance(raw_items, list):
            raise RuntimeError("Unexpected classification response shape.")

        tags: list[str] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            score = float(item.get("score") or 0)
            if score < MIN_CLASSIFICATION_SCORE:
                continue

            label = str(item.get("label") or "")
            if not label:
                continue

            for chunk in label.split(","):
                cleaned = self._clean_tag(chunk)
                if cleaned:
                    tags.append(cleaned)

        return self._limit_tags(tags)

    def _parse_caption(self, payload: Any) -> str:
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("generated_text"):
                    return self._clean_caption(str(item["generated_text"]))

        if isinstance(payload, dict) and payload.get("generated_text"):
            return self._clean_caption(str(payload["generated_text"]))

        raise RuntimeError("Unexpected caption response shape.")

    def _caption_keywords(self, description: str) -> list[str]:
        tokens = re.split(r"[^a-zA-Z0-9]+", description.lower())
        keywords: list[str] = []
        for token in tokens:
            if len(token) < 3 or token in CAPTION_STOPWORDS:
                continue
            cleaned = self._clean_tag(token)
            if cleaned:
                keywords.append(cleaned)
        return self._limit_tags(keywords)

    @staticmethod
    def _clean_caption(text: str) -> str:
        caption = re.sub(r"\s+", " ", text.strip())
        if not caption:
            return ""
        return caption[0].upper() + caption[1:]

    @staticmethod
    def _detect_people(tags: list[str], description: str) -> bool:
        words = set(re.split(r"[^a-zA-Z0-9]+", " ".join(tags + [description]).lower()))
        return bool(words & PEOPLE_KEYWORDS)

    def _clean_tag(self, value: str) -> str:
        cleaned = value.strip().lower()
        cleaned = cleaned.replace("_", " ").replace("-", " ")
        cleaned = re.sub(r"[^a-z0-9\s]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) < 2 or cleaned in IRRELEVANT_TAGS:
            return ""
        return cleaned

    def _limit_tags(self, tags: list[str]) -> list[str]:
        unique_tags: list[str] = []
        seen: set[str] = set()

        for tag in tags:
            if not tag or tag in seen:
                continue
            seen.add(tag)
            unique_tags.append(tag)
            if len(unique_tags) >= self.max_tags:
                break

        return unique_tags

    def _merge_tags(self, primary_tags: list[str], secondary_tags: list[str]) -> list[str]:
        return self._limit_tags(primary_tags + secondary_tags)

    @staticmethod
    def _fallback_result() -> AnalysisResult:
        return AnalysisResult(
            description="",
            tags=[],
            has_people=False,
            source="fallback",
        )


def build_huggingface_service(config: dict[str, object], logger: logging.Logger | None = None) -> HuggingFaceService:
    return HuggingFaceService(
        api_token=str(config.get("HUGGINGFACE_API_TOKEN", "")),
        classification_model=str(config.get("HUGGINGFACE_CLASSIFICATION_MODEL", DEFAULT_CLASSIFICATION_MODEL)),
        caption_model=str(config.get("HUGGINGFACE_CAPTION_MODEL", DEFAULT_CAPTION_MODEL)),
        timeout=int(config.get("HUGGINGFACE_TIMEOUT", DEFAULT_TIMEOUT)),
        max_tags=int(config.get("HUGGINGFACE_MAX_TAGS", DEFAULT_MAX_TAGS)),
        logger=logger,
    )
