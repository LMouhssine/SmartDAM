from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, abort, flash, has_request_context, redirect, render_template, request, send_file, url_for
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from models import ImageAsset, db, ensure_image_asset_schema
from services.azure_vision import VisionError, build_vision_service
from services.image_processing import InvalidImageError, process_image_upload
from services.search import build_default_search_context, parse_search_params, search_images
from services.storage import StorageError, StoredAsset, build_storage_manager

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "ico"}
DEFAULT_MAX_CONTENT_LENGTH = 20 * 1024 * 1024


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
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", DEFAULT_MAX_CONTENT_LENGTH)),
        THUMBNAIL_MAX_SIZE=int(os.getenv("THUMBNAIL_MAX_SIZE", 640)),
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


def build_dashboard_stats() -> dict[str, int]:
    all_images = ImageAsset.query.all()
    distinct_tags = {
        tag.strip().lower()
        for image in all_images
        for tag in image.tag_list
        if tag.strip()
    }
    images_with_people = sum(1 for image in all_images if image.has_people)

    return {
        "total_images": len(all_images),
        "distinct_tags": len(distinct_tags),
        "images_with_people": images_with_people,
    }


def clean_redirect_target(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        if has_request_context() and parsed.netloc and parsed.netloc != request.host:
            return None
        path = parsed.path or ""
        if not path.startswith("/"):
            return None
        return path + (f"?{parsed.query}" if parsed.query else "")
    if not value.startswith("/"):
        return None
    return value


def format_size_label(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        size_mb = size_bytes / (1024 * 1024)
        if size_mb.is_integer():
            return f"{int(size_mb)} Mo"
        return f"{size_mb:.1f} Mo"
    return f"{max(1, round(size_bytes / 1024))} Ko"


def thumbnail_filename_for(original_filename: str, extension: str) -> str:
    stem = Path(original_filename).stem
    return f"{stem}_thumb{extension}"


def render_gallery(*, images: list[ImageAsset], search_context: dict[str, object], page_title: str, page_copy: str):
    return render_template(
        "index.html",
        images=images,
        total_assets=ImageAsset.query.count(),
        result_count=len(images),
        dashboard_stats=build_dashboard_stats(),
        search=search_context,
        page_title=page_title,
        page_copy=page_copy,
    )


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
            "max_upload_size_label": format_size_label(app.config["MAX_CONTENT_LENGTH"]),
            "search": build_default_search_context(),
        }

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_entity_too_large(error: RequestEntityTooLarge):
        max_upload_size = app.config["MAX_CONTENT_LENGTH"]
        content_length = request.content_length or 0
        app.logger.warning(
            "Upload rejected because payload is too large (%s bytes received, limit=%s bytes).",
            content_length,
            max_upload_size,
        )
        flash(
            f"Le fichier dépasse la taille maximale autorisée ({format_size_label(max_upload_size)}). "
            "Réduisez sa taille puis réessayez.",
            "warning",
        )
        return redirect(clean_redirect_target(request.referrer) or url_for("index"))

    @app.get("/")
    def index():
        images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
        return render_gallery(
            images=images,
            search_context=build_default_search_context(),
            page_title="Bibliothèque visuelle",
            page_copy="Une galerie prête pour la démo, optimisée pour parcourir, filtrer et présenter vos assets enrichis.",
        )

    @app.get("/search")
    def search():
        params = parse_search_params(request.args)
        image_query, search_context = search_images(params)
        images = image_query.all()

        app.logger.info(
            "Search request executed with q='%s', people='%s', food='%s', environment='%s', orientation='%s', sort='%s'.",
            params.query,
            params.people,
            params.food_category,
            params.environment,
            params.orientation,
            params.sort,
        )

        return render_gallery(
            images=images,
            search_context=search_context,
            page_title="Résultats de recherche",
            page_copy="Les résultats combinent mots-clés, filtres et tri pour retrouver rapidement les bons visuels.",
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

        try:
            processed_image = process_image_upload(
                file_bytes=file_bytes,
                thumbnail_max_size=app.config["THUMBNAIL_MAX_SIZE"],
            )
        except InvalidImageError:
            flash("Le fichier envoyé n'est pas une image valide.", "danger")
            return redirect(url_for("index"))

        storage = app.extensions["smartdam.storage"]
        vision = app.extensions["smartdam.vision"]
        stored_assets: list[StoredAsset] = []

        app.logger.info(
            "Starting upload flow for '%s' (%sx%s, %s).",
            original_filename,
            processed_image.width,
            processed_image.height,
            processed_image.orientation,
        )

        try:
            original_asset = storage.save(
                file_bytes=file_bytes,
                original_filename=original_filename,
                content_type=processed_image.content_type,
            )
            stored_assets.append(original_asset)

            thumbnail_asset = storage.save(
                file_bytes=processed_image.thumbnail_bytes,
                original_filename=thumbnail_filename_for(original_filename, processed_image.thumbnail_extension),
                content_type=processed_image.thumbnail_content_type,
            )
            stored_assets.append(thumbnail_asset)
            app.logger.info("Thumbnail generated and stored for '%s'.", original_filename)

            if original_asset.backend == "azure":
                analysis = vision.analyze_image_url(
                    image_url=original_asset.url,
                    original_filename=original_filename,
                )
                app.logger.info("Azure Vision analysis succeeded for '%s'.", original_filename)
            else:
                analysis = vision.analyze_image(file_bytes, original_filename)
                app.logger.info("Local analysis completed for '%s'.", original_filename)

            image = ImageAsset(
                original_filename=original_filename,
                image_url=original_asset.url or "",
                thumbnail_url=thumbnail_asset.url or "",
                thumbnail_storage_path=thumbnail_asset.path,
                thumbnail_content_type=thumbnail_asset.content_type,
                description=analysis.description,
                has_people=analysis.has_people,
                image_width=processed_image.width,
                image_height=processed_image.height,
                orientation=processed_image.orientation,
                storage_backend=original_asset.backend,
                storage_path=original_asset.path,
                content_type=original_asset.content_type,
                analysis_source=analysis.source,
            )
            image.set_tags(analysis.tags)

            db.session.add(image)
            db.session.flush()

            if original_asset.backend == "local":
                image.image_url = url_for("image_content", image_id=image.id)
                image.thumbnail_url = url_for("image_thumbnail", image_id=image.id)

            db.session.commit()
            app.logger.info("Image '%s' saved in database with id=%s.", original_filename, image.id)

            if original_asset.backend == "azure":
                flash("Image envoyée sur Azure Blob Storage et analysée avec Azure Vision.", "success")
            elif analysis.source == "azure":
                flash("Image envoyée en local et analysée avec Azure Vision.", "success")
            else:
                flash("Image envoyée. Des tags locaux ont été générés en repli.", "info")
        except (StorageError, VisionError, SQLAlchemyError) as exc:
            db.session.rollback()
            app.logger.exception("Upload flow failed for '%s'.", original_filename)

            for stored_asset in reversed(stored_assets):
                try:
                    storage.delete_by_reference(stored_asset.backend, stored_asset.path)
                except StorageError:
                    app.logger.exception("Stored asset cleanup failed for '%s'.", stored_asset.path)

            if isinstance(exc, StorageError):
                flash("Le stockage du fichier a échoué. Vérifiez la configuration Azure puis réessayez.", "danger")
            elif isinstance(exc, VisionError):
                flash("L'analyse Azure Vision a échoué. Le fichier n'a pas été enregistré.", "danger")
            else:
                flash("L'enregistrement en base de données a échoué. Réessayez.", "danger")
        except Exception:  # noqa: BLE001
            db.session.rollback()
            app.logger.exception("Unexpected upload error for '%s'.", original_filename)

            for stored_asset in reversed(stored_assets):
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

    @app.get("/images/<int:image_id>/thumbnail")
    def image_thumbnail(image_id: int):
        image = ImageAsset.query.get_or_404(image_id)
        storage = app.extensions["smartdam.storage"]

        try:
            if image.thumbnail_storage_path:
                data, content_type = storage.read_by_reference(
                    backend_name=image.storage_backend,
                    storage_path=image.thumbnail_storage_path,
                    content_type=image.thumbnail_content_type,
                    filename=image.original_filename,
                )
            else:
                data, content_type = storage.read(image)
        except StorageError as exc:
            app.logger.warning("Thumbnail could not be loaded for image_id=%s: %s", image_id, exc)
            abort(404)

        return send_file(
            BytesIO(data),
            mimetype=content_type,
            download_name=image.original_filename,
            max_age=300,
        )

    @app.get("/images/<int:image_id>/download")
    def download_image(image_id: int):
        image = ImageAsset.query.get_or_404(image_id)
        storage = app.extensions["smartdam.storage"]

        try:
            data, content_type = storage.read(image)
        except StorageError as exc:
            app.logger.warning("Image download could not be loaded for image_id=%s: %s", image_id, exc)
            abort(404)

        return send_file(
            BytesIO(data),
            mimetype=content_type,
            download_name=image.original_filename,
            as_attachment=True,
            max_age=0,
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

        next_url = clean_redirect_target(request.form.get("next"))
        referrer_url = clean_redirect_target(request.referrer)
        return redirect(next_url or referrer_url or url_for("index"))


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
