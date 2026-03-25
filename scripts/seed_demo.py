from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app  # noqa: E402
from models import ImageAsset, db, ensure_image_asset_schema  # noqa: E402
from services.image_processing import process_image_upload  # noqa: E402
from services.storage import StoredAsset, StorageError  # noqa: E402

DEMO_ASSETS_DIR = BASE_DIR / "demo_assets"

DEMO_IMAGES = [
    {
        "filename": "chef_station_portrait.png",
        "description": "Chef en cuisine devant une plaque de cuisson, prêt pour le service.",
        "tags": ["chef", "people", "kitchen", "restaurant", "cooking", "portrait"],
        "has_people": True,
    },
    {
        "filename": "grilled_chicken_plate.png",
        "description": "Assiette de poulet grillé dressée pour une démonstration culinaire.",
        "tags": ["food", "chicken", "grill", "plate", "prepared meal", "kitchen"],
        "has_people": False,
    },
    {
        "filename": "fruit_market_table.png",
        "description": "Composition de fruits frais présentés sur une table extérieure.",
        "tags": ["fruit", "outdoor", "market", "fresh", "produce", "table"],
        "has_people": False,
    },
    {
        "filename": "dessert_square_showcase.png",
        "description": "Dessert pâtissier en présentation sur un comptoir intérieur.",
        "tags": ["dessert", "bakery", "cake", "sweet", "indoor", "square"],
        "has_people": False,
    },
]


def thumbnail_filename_for(original_filename: str, extension: str) -> str:
    return f"{Path(original_filename).stem}_thumb{extension}"


def seed_demo_assets() -> None:
    app = create_app()

    with app.app_context():
        db.create_all()
        ensure_image_asset_schema(app.logger)

        storage = app.extensions["smartdam.storage"]
        created_count = 0
        skipped_count = 0

        for item in DEMO_IMAGES:
            original_filename = item["filename"]
            if ImageAsset.query.filter_by(original_filename=original_filename).first():
                print(f"SKIP {original_filename}")
                skipped_count += 1
                continue

            asset_path = DEMO_ASSETS_DIR / original_filename
            if not asset_path.exists():
                raise FileNotFoundError(f"Missing demo asset: {asset_path}")

            file_bytes = asset_path.read_bytes()
            processed = process_image_upload(
                file_bytes=file_bytes,
                thumbnail_max_size=app.config["THUMBNAIL_MAX_SIZE"],
            )
            stored_assets: list[StoredAsset] = []

            try:
                original_asset = storage.save(
                    file_bytes=file_bytes,
                    original_filename=original_filename,
                    content_type=processed.content_type,
                )
                stored_assets.append(original_asset)

                thumbnail_asset = storage.save(
                    file_bytes=processed.thumbnail_bytes,
                    original_filename=thumbnail_filename_for(original_filename, processed.thumbnail_extension),
                    content_type=processed.thumbnail_content_type,
                )
                stored_assets.append(thumbnail_asset)

                image = ImageAsset(
                    original_filename=original_filename,
                    image_url=original_asset.url or "",
                    thumbnail_url=thumbnail_asset.url or "",
                    thumbnail_storage_path=thumbnail_asset.path,
                    thumbnail_content_type=thumbnail_asset.content_type,
                    description=item["description"],
                    has_people=item["has_people"],
                    image_width=processed.width,
                    image_height=processed.height,
                    orientation=processed.orientation,
                    storage_backend=original_asset.backend,
                    storage_path=original_asset.path,
                    content_type=original_asset.content_type,
                    analysis_source="seed",
                )
                image.set_tags(item["tags"])

                db.session.add(image)
                db.session.flush()

                if original_asset.backend == "local":
                    image.image_url = f"/images/{image.id}/content"
                    image.thumbnail_url = f"/images/{image.id}/thumbnail"

                db.session.commit()
                print(f"CREATE {original_filename}")
                created_count += 1
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                for stored_asset in reversed(stored_assets):
                    try:
                        storage.delete_by_reference(stored_asset.backend, stored_asset.path)
                    except StorageError:
                        app.logger.exception("Seed cleanup failed for '%s'.", stored_asset.path)
                raise RuntimeError(f"Unable to seed asset '{original_filename}'.") from exc

        print(f"Seed complete. Created={created_count} Skipped={skipped_count}")


if __name__ == "__main__":
    seed_demo_assets()
