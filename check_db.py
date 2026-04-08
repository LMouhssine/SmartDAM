from models import ImageAsset, db
from app import create_app

app = create_app()
with app.app_context():
    images = ImageAsset.query.all()
    print(f'Total images: {len(images)}')
    for img in images:
        print(f'\nID: {img.id}')
        print(f'File: {img.original_filename}')
        print(f'Tags: {img.tag_list}')
        print(f'Description: {img.description[:100] if img.description else "N/A"}')
        print(f'Analysis Source: {img.analysis_source}')
        print(f'Has People: {img.has_people}')
