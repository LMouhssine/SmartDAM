# SmartDAM

SmartDAM est une application Flask de gestion d'assets visuels. Elle permet d'importer des images, de les stocker localement ou dans Azure Blob Storage, de les analyser avec Azure Vision, puis de les retrouver dans une galerie filtrable pensée pour une démonstration produit.

Le projet est désormais orienté **démo stable** :

1. import d'image avec aperçu et indicateurs de chargement,
2. analyse et enrichissement automatique,
3. recherche avec filtres,
4. téléchargement en pleine résolution,
5. suppression confirmée,
6. seed local reproductible pour préparer une démo en quelques secondes.

## Architecture

### Backend

- `app.py`
  Gère les routes Flask, l'upload, la suppression, le téléchargement, les miniatures locales et le rendu principal.
- `models.py`
  Définit le modèle `ImageAsset`, les tags structurés, l'orientation, ainsi que les colonnes de miniatures.
- `services/storage.py`
  Gère le stockage local ou Azure Blob Storage, y compris la lecture et la suppression de l'image originale et de sa miniature.
- `services/azure_vision.py`
  Gère l'analyse Azure Vision et le fallback local.
- `services/search.py`
  Construit la recherche par mots-clés, filtres et tri.
- `services/image_processing.py`
  Valide les images avec Pillow et génère une miniature stable pour la galerie.

### Frontend

- `templates/`
  Templates Jinja, composants réutilisables, modals d'upload, détail image et confirmation de suppression.
- `static/css/style.css`
  Design dashboard Bootstrap + CSS personnalisé.
- `static/js/app.js`
  Theme toggle, aperçu avant upload, loading overlay, modal détail et confirmation de suppression.

### Données de démonstration

- `demo_assets/`
  Images versionnées pour la démo.
- `scripts/seed_demo.py`
  Script reproductible pour charger ces assets dans le backend configuré.

## Fonctionnalités principales

- Import d'images avec validation réelle via Pillow
- Génération de miniatures serveur pour accélérer la galerie
- Stockage local ou Azure Blob Storage
- Analyse Azure Vision :
  tags, description, détection de personnes
- Recherche par mots-clés sur tags et description
- Filtres :
  personnes, catégorie food, environnement, orientation
- Téléchargement en pleine résolution
- Suppression confirmée avec nettoyage du stockage
- Interface démo moderne, responsive et orientée SaaS

## Structure du projet

```text
SmartDAM/
|-- app.py
|-- models.py
|-- requirements.txt
|-- README.md
|-- demo_assets/
|-- scripts/
|   `-- seed_demo.py
|-- services/
|   |-- __init__.py
|   |-- azure_vision.py
|   |-- image_processing.py
|   |-- search.py
|   `-- storage.py
|-- static/
|   |-- css/
|   |   `-- style.css
|   `-- js/
|       `-- app.js
|-- templates/
|   |-- base.html
|   |-- index.html
|   `-- components/
`-- uploads/
```

## Variables d'environnement

Copiez `.env.example` vers `.env`, puis adaptez les valeurs.

### Configuration locale

```env
FLASK_SECRET_KEY=change-me
DATABASE_URL=sqlite:///smartdam.db
MAX_CONTENT_LENGTH=20971520
THUMBNAIL_MAX_SIZE=640
UPLOAD_FOLDER=uploads
LOG_LEVEL=INFO
```

### Azure Blob Storage

```env
USE_AZURE_STORAGE=true
AZURE_STORAGE_CONNECTION_STRING=your-azure-storage-connection-string
AZURE_STORAGE_CONTAINER=smartdam-images
```

Important :

- SmartDAM stocke l'URL publique directe du blob pour l'image originale et sa miniature.
- Le conteneur doit donc autoriser la lecture publique des blobs.
- Si le conteneur existe déjà en privé, il faut activer cet accès côté Azure avant l'affichage direct.

### Azure Vision

```env
VISION_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com
VISION_KEY=your-azure-vision-key
VISION_LANGUAGE=fr
```

## Installation

### 1. Créer un environnement virtuel

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Installer les dépendances

```powershell
pip install -r requirements.txt
```

### 3. Démarrer l'application

```powershell
python app.py
```

Ouvrez ensuite [http://127.0.0.1:5000](http://127.0.0.1:5000).

Au premier démarrage, SmartDAM crée les tables SQLite nécessaires et applique les migrations légères du modèle.

## Configuration Azure, étape par étape

### 1. Blob Storage

1. Créez un compte Azure Storage.
2. Créez un conteneur Blob.
3. Activez la lecture publique au niveau blob.
4. Copiez la connection string dans `AZURE_STORAGE_CONNECTION_STRING`.

### 2. Azure Vision

1. Créez une ressource Azure AI Vision / Image Analysis.
2. Récupérez `VISION_ENDPOINT` et `VISION_KEY`.
3. Ajoutez-les dans `.env`.

### 3. Activation

1. Passez `USE_AZURE_STORAGE=true`.
2. Redémarrez l'application.
3. Testez le parcours complet :
   import, analyse, recherche, téléchargement.

## Préparer une démo

### Seed des images de démonstration

Le script suivant charge les images versionnées dans le backend actif et génère aussi leurs miniatures :

```powershell
python scripts\seed_demo.py
```

Le script est idempotent : si un fichier de démonstration existe déjà en base avec le même nom, il est ignoré.

### Parcours de démonstration recommandé

1. Lancez l'application.
2. Exécutez `python scripts\seed_demo.py`.
3. Ouvrez la galerie.
4. Montrez les stats et les filtres.
5. Ouvrez une image dans le modal détail.
6. Téléchargez l'original.
7. Testez une recherche par tags.
8. Importez une nouvelle image.
9. Montrez la suppression confirmée.

## Qualité et sécurité de base

- Validation d'extension côté backend
- Validation réelle de l'image via Pillow avant stockage
- Limite de taille via `MAX_CONTENT_LENGTH`
- Nettoyage du blob/fichier en cas d'échec du flux
- Suppression de la miniature et de l'original en même temps
- Secrets Azure uniquement via variables d'environnement
- Logs applicatifs sur upload, recherche, suppression et erreurs

## Notes d'implémentation

- La galerie utilise une miniature générée côté serveur quand elle existe.
- Le modal détail et le téléchargement utilisent toujours l'image originale.
- Les assets seedés utilisent des métadonnées stables pour une démo reproductible.
- Le mode debug Flask est pratique en local, mais ne constitue pas un déploiement de production.

## Vérifications recommandées

- `python -m compileall app.py models.py services scripts`
- Vérifier `/`, `/search` et `/images/<id>/download`
- Vérifier qu'une suppression retire aussi la miniature
- Vérifier qu'un upload invalide est refusé
- Vérifier le seed sur un dépôt fraîchement configuré

## Limites connues

- Pas d'authentification utilisateur
- Pas de renommage d'image
- Pas de favoris
- Pas de voix Azure Speech-to-Text dans cette phase
- Pas de pipeline de déploiement production
