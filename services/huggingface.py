from __future__ import annotations

import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

HF_API_BASE_URL = "https://router.huggingface.co/hf-inference/models"
DEFAULT_CLASSIFICATION_MODEL = "microsoft/resnet-50"
DEFAULT_DETECTION_MODEL = "facebook/detr-resnet-50"
DEFAULT_CAPTION_MODEL = "Salesforce/blip-image-captioning-large"
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_TAGS = 8
MIN_CLASSIFICATION_SCORE = 0.10
MIN_DETECTION_SCORE = 0.3
IRRELEVANT_TAGS = {
    # Generic / meta
    "image", "images", "photo", "photography", "picture", "illustration",
    "graphic", "art", "object", "objects", "item", "thing", "stuff",
    # Marine / coral — commonly confused with food textures by ResNet
    "coral", "brain coral", "coral reef", "coral fungus", "reef", "brain",
    "sea anemone", "anemone", "jellyfish", "nudibranch", "starfish",
    "sea urchin", "sponge", "seaweed", "kelp", "algae",
    # Geological / mineral
    "rock", "stone", "mineral", "fossil", "crystal", "gem", "gemstone",
    # Abstract / texture ResNet artefacts
    "pattern", "texture", "surface", "background", "abstract",
    "web site", "website", "web page", "screen",
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
TAG_FR_TRANSLATIONS: dict[str, str] = {
    # ── COCO / DETR detection classes ─────────────────────────────────────
    "person": "personne",
    "bicycle": "vélo",
    "car": "voiture",
    "motorcycle": "moto",
    "bus": "bus",
    "truck": "camion",
    "bottle": "bouteille",
    "wine glass": "verre à vin",
    "cup": "tasse",
    "fork": "fourchette",
    "knife": "couteau",
    "spoon": "cuillère",
    "bowl": "bol",
    "banana": "banane",
    "apple": "pomme",
    "sandwich": "sandwich",
    "orange": "orange",
    "broccoli": "brocoli",
    "carrot": "carotte",
    "hot dog": "hot-dog",
    "pizza": "pizza",
    "donut": "beignet",
    "cake": "gâteau",
    "chair": "chaise",
    "dining table": "table",
    "oven": "four",
    "toaster": "grille-pain",
    "sink": "évier",
    "refrigerator": "réfrigérateur",
    "microwave": "micro-ondes",
    "scissors": "ciseaux",
    "vase": "vase",
    "potted plant": "plante en pot",
    "couch": "canapé",
    "bed": "lit",
    "toilet": "toilettes",
    "wine bottle": "bouteille de vin",
    # ── ResNet-50 / ImageNet food & kitchen ───────────────────────────────
    "bakery": "boulangerie",
    "bread": "pain",
    "baguette": "baguette",
    "croissant": "croissant",
    "cheese": "fromage",
    "butter": "beurre",
    "egg": "œuf",
    "eggs": "œufs",
    "meat": "viande",
    "chicken": "poulet",
    "beef": "bœuf",
    "steak": "steak",
    "pork": "porc",
    "lamb": "agneau",
    "fish": "poisson",
    "seafood": "fruits de mer",
    "shrimp": "crevette",
    "salad": "salade",
    "soup": "soupe",
    "pasta": "pâtes",
    "rice": "riz",
    "burger": "burger",
    "fries": "frites",
    "dessert": "dessert",
    "chocolate": "chocolat",
    "ice cream": "glace",
    "cookie": "biscuit",
    "pastry": "pâtisserie",
    "tart": "tarte",
    "fruit": "fruit",
    "vegetable": "légume",
    "tomato": "tomate",
    "onion": "oignon",
    "garlic": "ail",
    "mushroom": "champignon",
    "avocado": "avocat",
    "strawberry": "fraise",
    "lemon": "citron",
    "grape": "raisin",
    "coffee": "café",
    "tea": "thé",
    "juice": "jus",
    "cocktail": "cocktail",
    "beer": "bière",
    "wine": "vin",
    "drink": "boisson",
    "beverage": "boisson",
    # ── Kitchen & environment ─────────────────────────────────────────────
    "kitchen": "cuisine",
    "plate": "assiette",
    "dish": "plat",
    "meal": "repas",
    "food": "aliment",
    "cooking": "cuisine",
    "restaurant": "restaurant",
    "table": "table",
    "counter": "comptoir",
    "cutting board": "planche à découper",
    "pan": "poêle",
    "pot": "casserole",
    "wooden spoon": "cuillère en bois",
    "spatula": "spatule",
    "bowl of food": "bol de nourriture",
    # ── People & portrait ─────────────────────────────────────────────────
    "man": "homme",
    "woman": "femme",
    "boy": "garçon",
    "girl": "fille",
    "child": "enfant",
    "children": "enfants",
    "people": "personnes",
    "crowd": "foule",
    "face": "visage",
    "portrait": "portrait",
    "group": "groupe",
    "chef": "chef cuisinier",
    "cook": "cuisinier",
    "waiter": "serveur",
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
        detection_model: str = DEFAULT_DETECTION_MODEL,
        caption_model: str = DEFAULT_CAPTION_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        max_tags: int = DEFAULT_MAX_TAGS,
        logger: logging.Logger | None = None,
    ) -> None:
        self.api_token = api_token.strip()
        self.classification_model = classification_model.strip() or DEFAULT_CLASSIFICATION_MODEL
        self.detection_model = detection_model.strip() or DEFAULT_DETECTION_MODEL
        self.caption_model = caption_model.strip()
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

        content_type = self._guess_content_type(path)
        description = ""
        tags: list[str] = []
        detected_objects: list[str] = []

        if not self.enabled:
            return self._fallback_result()

        # Classification and object detection are both available on the current Hugging Face router.
        try:
            classification_payload = self._query_model(self.classification_model, image_bytes, content_type)
            tags = self._parse_classification_tags(classification_payload)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Hugging Face classification failed for '%s': %s", path.name, exc)

        try:
            detection_payload = self._query_model(self.detection_model, image_bytes, content_type)
            detected_objects = self._parse_detection_tags(detection_payload)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Hugging Face object detection failed for '%s': %s", path.name, exc)

        tags = self._merge_tags(detected_objects, tags)

        try:
            if self.caption_model:
                caption_payload = self._query_model(self.caption_model, image_bytes, content_type)
                description = self._parse_caption(caption_payload)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Hugging Face captioning failed for '%s': %s", path.name, exc)

        if description:
            tags = self._merge_tags(tags, self._caption_keywords(description))

        # People detection must run on English tags (before translation)
        has_people = self._detect_people(tags, description)
        # Translate tags to French
        tags = [self._translate_tag(t) for t in tags]
        # Build French description if no caption was generated
        if not description and tags:
            description = self._build_description(tags)

        source = "huggingface" if tags or description else "fallback"
        return AnalysisResult(
            description=description,
            tags=tags[: self.max_tags],
            has_people=has_people,
            source=source,
        )

    def _query_model(self, model_id: str, image_bytes: bytes, content_type: str) -> Any:
        if not model_id:
            raise RuntimeError("No Hugging Face model configured for this task.")

        response = requests.post(
            f"{HF_API_BASE_URL}/{model_id}",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            data=image_bytes,
            timeout=self.timeout,
        )

        response_type = (response.headers.get("content-type") or "").lower()
        response_preview = response.text.replace("\n", " ").strip()[:240]

        if response.status_code >= 400:
            raise RuntimeError(
                f"Hugging Face model '{model_id}' returned HTTP {response.status_code}: "
                f"{response_preview or 'empty response'}"
            )

        if "application/json" not in response_type:
            raise RuntimeError(
                f"Hugging Face model '{model_id}' returned unexpected content type '{response_type or 'unknown'}': "
                f"{response_preview or 'empty response'}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid JSON response from Hugging Face model '{model_id}': {response_preview or 'empty response'}"
            ) from exc

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

    def _parse_detection_tags(self, payload: Any) -> list[str]:
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected object detection response shape.")

        tags: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            score = float(item.get("score") or 0)
            if score < MIN_DETECTION_SCORE:
                continue

            label = self._clean_tag(str(item.get("label") or ""))
            if label:
                tags.append(label)

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

    def _build_description(self, tags: list[str]) -> str:
        priority_tags = tags[:3]
        if not priority_tags:
            return ""

        if len(priority_tags) == 1:
            return f"Élément détecté : {priority_tags[0]}."

        return f"Éléments détectés : {', '.join(priority_tags[:-1])} et {priority_tags[-1]}."

    @staticmethod
    def _translate_tag(tag: str) -> str:
        return TAG_FR_TRANSLATIONS.get(tag, tag)

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
    def _guess_content_type(path: Path) -> str:
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or "image/jpeg"

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
        detection_model=str(config.get("HUGGINGFACE_DETECTION_MODEL", DEFAULT_DETECTION_MODEL)),
        caption_model=str(config.get("HUGGINGFACE_CAPTION_MODEL", DEFAULT_CAPTION_MODEL)),
        timeout=int(config.get("HUGGINGFACE_TIMEOUT", DEFAULT_TIMEOUT)),
        max_tags=int(config.get("HUGGINGFACE_MAX_TAGS", DEFAULT_MAX_TAGS)),
        logger=logger,
    )
