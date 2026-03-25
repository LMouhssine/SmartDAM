from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()


class ImageAsset(db.Model):
    __tablename__ = "image_assets"

    ORIENTATION_LANDSCAPE = "landscape"
    ORIENTATION_PORTRAIT = "portrait"
    ORIENTATION_SQUARE = "square"
    ORIENTATION_UNKNOWN = "unknown"
    ORIENTATION_VALUES = {
        ORIENTATION_LANDSCAPE,
        ORIENTATION_PORTRAIT,
        ORIENTATION_SQUARE,
        ORIENTATION_UNKNOWN,
    }

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(1024), nullable=False)
    tags = db.Column(db.Text, nullable=False, default="")
    tags_json = db.Column(db.Text, nullable=False, default="[]")
    description = db.Column(db.Text, nullable=False, default="")
    has_people = db.Column(db.Boolean, nullable=False, default=False)
    image_width = db.Column(db.Integer, nullable=True)
    image_height = db.Column(db.Integer, nullable=True)
    orientation = db.Column(db.String(16), nullable=False, default=ORIENTATION_UNKNOWN)
    storage_backend = db.Column(db.String(32), nullable=False, default="local")
    storage_path = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False, default="application/octet-stream")
    analysis_source = db.Column(db.String(32), nullable=False, default="local")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @staticmethod
    def normalize_tags(values: Iterable[object]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            tag = str(value).strip()
            if not tag:
                continue

            lowered = tag.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            normalized_values.append(tag)

        return normalized_values

    @staticmethod
    def parse_tags_json(tags_json: str | None) -> list[str]:
        if not tags_json:
            return []

        try:
            raw_values = json.loads(tags_json)
        except json.JSONDecodeError:
            return []

        if not isinstance(raw_values, list):
            return []

        return ImageAsset.normalize_tags(raw_values)

    @staticmethod
    def parse_tags_text(tags: str | None) -> list[str]:
        if not tags:
            return []
        return ImageAsset.normalize_tags(tags.split(","))

    def set_tags(self, values: Iterable[object]) -> None:
        normalized_values = self.normalize_tags(values)
        self.tags_json = json.dumps(normalized_values, ensure_ascii=False)
        self.tags = ", ".join(normalized_values)

    @property
    def tag_list(self) -> list[str]:
        json_tags = self.parse_tags_json(self.tags_json)
        if json_tags:
            return json_tags
        return self.parse_tags_text(self.tags)


def ensure_image_asset_schema(logger) -> None:
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "image_assets" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("image_assets")}
    column_added = False

    with db.engine.begin() as connection:
        if "tags_json" not in columns:
            logger.info("Adding tags_json column to image_assets.")
            connection.execute(text("ALTER TABLE image_assets ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'"))
            column_added = True

        if "image_width" not in columns:
            logger.info("Adding image_width column to image_assets.")
            connection.execute(text("ALTER TABLE image_assets ADD COLUMN image_width INTEGER"))

        if "image_height" not in columns:
            logger.info("Adding image_height column to image_assets.")
            connection.execute(text("ALTER TABLE image_assets ADD COLUMN image_height INTEGER"))

        if "orientation" not in columns:
            logger.info("Adding orientation column to image_assets.")
            connection.execute(
                text(
                    "ALTER TABLE image_assets ADD COLUMN orientation VARCHAR(16) NOT NULL DEFAULT 'unknown'"
                )
            )

        rows = connection.execute(
            text("SELECT id, tags, tags_json, orientation FROM image_assets")
        ).mappings().all()

        for row in rows:
            current_tags_json = row.get("tags_json")
            normalized_values = ImageAsset.parse_tags_json(current_tags_json)
            if not normalized_values:
                normalized_values = ImageAsset.parse_tags_text(row.get("tags"))

            serialized_tags = json.dumps(normalized_values, ensure_ascii=False)
            mirrored_tags = ", ".join(normalized_values)
            normalized_orientation = row.get("orientation") or ImageAsset.ORIENTATION_UNKNOWN
            if normalized_orientation not in ImageAsset.ORIENTATION_VALUES:
                normalized_orientation = ImageAsset.ORIENTATION_UNKNOWN

            if (
                column_added
                or (current_tags_json or "") != serialized_tags
                or (row.get("tags") or "") != mirrored_tags
                or (row.get("orientation") or "") != normalized_orientation
            ):
                connection.execute(
                    text(
                        "UPDATE image_assets "
                        "SET tags_json = :tags_json, tags = :tags, orientation = :orientation "
                        "WHERE id = :image_id"
                    ),
                    {
                        "image_id": row["id"],
                        "tags_json": serialized_tags,
                        "tags": mirrored_tags,
                        "orientation": normalized_orientation,
                    },
                )
