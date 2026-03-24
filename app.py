from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from models import ImageAsset, db, ensure_image_asset_schema
from services.azure_vision import VisionError, build_vision_service
from services.storage import StorageError, build_storage_manager

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "ico"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> Flask:
    app = Flask(__name__)
    upload_folder = Path(os.getenv("UPLOAD_FOLDER", BASE_DIR / "uploads")).resolve()
    upload_folder.mkdir(parents=True, exist_ok=True)

    app.config.update(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "smartdam-dev-secret"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'smartdam.db'}"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
        UPLOAD_FOLDER=str(upload_folder),
        ALLOWED_EXTENSIONS=ALLOWED_EXTENSIONS,
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO").upper(),
        USE_AZURE_STORAGE=env_flag("USE_AZURE_STORAGE", default=False),
        AZURE_STORAGE_CONNECTION_STRING=os.getenv("AZURE_STORAGE_CONNECTION_STRING", ""),
        AZURE_STORAGE_CONTAINER=os.getenv("AZURE_STORAGE_CONTAINER", "smartdam-images"),
        VISION_ENDPOINT=os.getenv("VISION_ENDPOINT", ""),
        VISION_KEY=os.getenv("VISION_KEY", ""),
        VISION_LANGUAGE=os.getenv("VISION_LANGUAGE", "fr"),
    )

    app.logger.setLevel(getattr(logging, app.config["LOG_LEVEL"], logging.INFO))

    db.init_app(app)
    app.extensions["smartdam.storage"] = build_storage_manager(app.config, logger=app.logger)
    app.extensions["smartdam.vision"] = build_vision_service(app.config, logger=app.logger)

    with app.app_context():
        db.create_all()
        ensure_image_asset_schema(app.logger)

    register_routes(app)
    return app


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS


def register_routes(app: Flask) -> None:
    @app.context_processor
    def inject_template_context() -> dict[str, object]:
        storage = app.extensions["smartdam.storage"]
        vision = app.extensions["smartdam.vision"]
        return {
            "storage_label": storage.default_backend_label,
            "vision_label": vision.provider_label,
            "azure_storage_enabled": storage.azure_enabled,
            "azure_storage_active": storage.azure_primary_enabled,
            "azure_vision_enabled": vision.enabled,
        }

    @app.get("/")
    def index():
        search_query = request.args.get("q", "").strip()
        people_only = request.args.get("people_only") == "1"

        image_query = ImageAsset.query.order_by(ImageAsset.created_at.desc())

        if search_query:
            like_query = f"%{search_query}%"
            image_query = image_query.filter(
                or_(
                    ImageAsset.tags.ilike(like_query),
                    ImageAsset.description.ilike(like_query),
                    ImageAsset.original_filename.ilike(like_query),
                )
            )

        if people_only:
            image_query = image_query.filter(ImageAsset.has_people.is_(True))

        images = image_query.all()
        return render_template(
            "index.html",
            images=images,
            search_query=search_query,
            people_only=people_only,
        )

    @app.post("/upload")
    def upload_image():
        uploaded_file = request.files.get("image")
        if uploaded_file is None or uploaded_file.filename == "":
            flash("Choisissez une image avant de lancer l'envoi.", "warning")
            return redirect(url_for("index"))

        original_filename = secure_filename(uploaded_file.filename)
        if not original_filename or not allowed_file(original_filename):
            flash("Format non pris en charge. Veuillez envoyer un fichier image.", "danger")
            return redirect(url_for("index"))

        file_bytes = uploaded_file.read()
        if not file_bytes:
            flash("Le fichier envoyé est vide.", "danger")
            return redirect(url_for("index"))

        storage = app.extensions["smartdam.storage"]
        vision = app.extensions["smartdam.vision"]
        stored_asset = None

        app.logger.info("Starting upload flow for '%s'.", original_filename)

        try:
            stored_asset = storage.save(
                file_bytes=file_bytes,
                original_filename=original_filename,
                content_type=uploaded_file.mimetype,
            )

            if stored_asset.backend == "azure":
                analysis = vision.analyze_image_url(
                    image_url=stored_asset.url,
                    original_filename=original_filename,
                )
                app.logger.info("Azure Vision analysis succeeded for '%s'.", original_filename)
            else:
                analysis = vision.analyze_image(file_bytes, original_filename)
                app.logger.info("Local analysis completed for '%s'.", original_filename)

            image = ImageAsset(
                original_filename=original_filename,
                image_url=stored_asset.url or "",
                description=analysis.description,
                has_people=analysis.has_people,
                storage_backend=stored_asset.backend,
                storage_path=stored_asset.path,
                content_type=stored_asset.content_type,
                analysis_source=analysis.source,
            )
            image.set_tags(analysis.tags)

            db.session.add(image)
            db.session.flush()

            if stored_asset.backend == "local":
                image.image_url = url_for("image_content", image_id=image.id)

            db.session.commit()
            app.logger.info("Image '%s' saved in database with id=%s.", original_filename, image.id)

            if stored_asset.backend == "azure":
                flash("Image envoyée sur Azure Blob Storage et analysée avec Azure Vision.", "success")
            elif analysis.source == "azure":
                flash("Image envoyée en local et analysée avec Azure Vision.", "success")
            else:
                flash("Image envoyée. Des tags locaux ont été générés en repli.", "info")
        except (StorageError, VisionError, SQLAlchemyError) as exc:
            db.session.rollback()
            app.logger.exception("Upload flow failed for '%s'.", original_filename)

            if stored_asset is not None:
                try:
                    storage.delete_by_reference(stored_asset.backend, stored_asset.path)
                    app.logger.info(
                        "Stored asset '%s' cleaned up after a failed upload.",
                        stored_asset.path,
                    )
                except StorageError:
                    app.logger.exception("Stored asset cleanup failed for '%s'.", original_filename)

            if isinstance(exc, StorageError):
                flash("Le stockage du fichier a échoué. Vérifiez la configuration Azure puis réessayez.", "danger")
            elif isinstance(exc, VisionError):
                flash("L'analyse Azure Vision a échoué. Le fichier n'a pas été enregistré.", "danger")
            else:
                flash("L'enregistrement en base de données a échoué. Réessayez.", "danger")
        except Exception:  # noqa: BLE001
            db.session.rollback()
            app.logger.exception("Unexpected upload error for '%s'.", original_filename)

            if stored_asset is not None:
                try:
                    storage.delete_by_reference(stored_asset.backend, stored_asset.path)
                except StorageError:
                    app.logger.exception("Stored asset cleanup failed after unexpected upload error.")

            flash("Une erreur inattendue s'est produite pendant l'envoi.", "danger")

        return redirect(url_for("index"))

    @app.get("/images/<int:image_id>/content")
    def image_content(image_id: int):
        image = ImageAsset.query.get_or_404(image_id)
        storage = app.extensions["smartdam.storage"]

        try:
            data, content_type = storage.read(image)
        except StorageError as exc:
            app.logger.warning("Image content could not be loaded for image_id=%s: %s", image_id, exc)
            abort(404)

        return send_file(
            BytesIO(data),
            mimetype=content_type,
            download_name=image.original_filename,
            max_age=300,
        )

    @app.post("/images/<int:image_id>/delete")
    def delete_image(image_id: int):
        image = ImageAsset.query.get_or_404(image_id)
        storage = app.extensions["smartdam.storage"]

        try:
            storage.delete(image)
            db.session.delete(image)
            db.session.commit()
            app.logger.info("Image id=%s deleted.", image_id)
            flash("Image supprimée.", "success")
        except Exception:  # noqa: BLE001
            db.session.rollback()
            app.logger.exception("Image deletion failed for image_id=%s.", image_id)
            flash("L'image n'a pas pu être supprimée.", "danger")

        return redirect(url_for("index"))


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
