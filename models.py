from __future__ import annotations

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class ImageAsset(db.Model):
    __tablename__ = "image_assets"

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    tags = db.Column(db.Text, nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    has_people = db.Column(db.Boolean, nullable=False, default=False)
    storage_backend = db.Column(db.String(32), nullable=False, default="local")
    storage_path = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False, default="application/octet-stream")
    analysis_source = db.Column(db.String(32), nullable=False, default="local")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]
