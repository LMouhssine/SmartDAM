# SmartDAM

SmartDAM est une application Flask de gestion d'assets visuels orientée photographie food et restauration. Elle permet d'importer des images, de les analyser automatiquement par IA (HuggingFace), et de les retrouver dans une galerie filtrable pensée pour une démonstration produit.

## Fonctionnalités

### Gestion des images

- Import multi-fichiers avec liste de progression par image (glisser-déposer ou sélection)
- Validation réelle via Pillow avant stockage
- Génération de miniatures côté serveur
- Stockage local ou Azure Blob Storage
- Téléchargement en pleine résolution
- Suppression confirmée avec nettoyage du stockage

### Analyse IA (HuggingFace)

- Classification d'image avec `microsoft/resnet-50`
- Détection d'objets avec `facebook/detr-resnet-50`
- Tags générés automatiquement, traduits en français
- Description générée à partir des tags détectés
- Détection de personnes
- Bouton "Réanalyser" sur chaque image (depuis le modal détail)
- Affichage des modèles IA utilisés dans la modale d'import
- Visualisation du processus d'analyse pendant l'upload (état par fichier : analyse en cours → tags obtenus)
- Fallback local si HuggingFace est indisponible

### Recherche et filtres

- Recherche par mots-clés sur tags et description
- **Recherche dynamique** : les résultats se mettent à jour en temps réel (400 ms de debounce sur le champ texte)
- **Filtres dynamiques** : changement immédiat sans clic sur "Appliquer"
- Filtres disponibles : personnes, catégorie food, environnement, orientation, favoris
- Tri : date (récent/ancien), alphabétique
- Surbrillance des termes recherchés dans les cartes de la galerie
- Barre de tags fréquents en haut de la galerie (cliquables)

### Favoris

- Bouton étoile sur chaque carte de la galerie
- Bouton étoile dans le modal détail (synchronisé avec la carte)
- Filtre "Favoris uniquement" dans le panneau de filtres

### Tags

- Tags cliquables dans le modal détail (redirige vers la recherche)
- Tags affichés en français
- Tags fréquents affichés en barre de navigation rapide

## Architecture

### Backend

- `app.py` — Routes Flask, upload synchrone et asynchrone (`/upload/async`), toggle favoris, réanalyse, filtre `highlight`, contexte de template global
- `models.py` — Modèle `ImageAsset`, tags structurés, orientation, is_favorite ; migrations légères via `ensure_image_asset_schema()`
- `services/huggingface.py` — Analyse HuggingFace (classification + détection), traduction des tags en français, détection de personnes, fallback
- `services/search.py` — `SearchParams` (dataclass slots), `parse_search_params()`, `search_images()`, `_build_context()`
- `services/storage.py` — Stockage local ou Azure Blob Storage
- `services/image_processing.py` — Validation et génération de miniatures via Pillow

### Frontend

- `templates/` — Templates Jinja, composants réutilisables (galerie, modal upload, modal détail, filtres, navbar)
- `static/css/style.css` — Design Bootstrap 5 + CSS personnalisé (thème clair/sombre, cartes, tags, upload, highlight)
- `static/js/app.js` — IIFE vanilla JS : upload multi-fichiers, modal détail, favoris, réanalyse, recherche dynamique, filtres dynamiques

### Données de démonstration

- `demo_assets/` — Images versionnées pour la démo
- `scripts/seed_demo.py` — Script idempotent pour charger les assets de démo dans le backend actif

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
|   |-- huggingface.py
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

### Azure Blob Storage (optionnel)

```env
USE_AZURE_STORAGE=true
AZURE_STORAGE_CONNECTION_STRING=your-azure-storage-connection-string
AZURE_STORAGE_CONTAINER=smartdam-images
```

Notes :
- SmartDAM stocke l'URL publique directe du blob pour l'image originale et sa miniature.
- Le conteneur doit autoriser la lecture publique des blobs.

### HuggingFace (optionnel)

```env
HUGGINGFACE_API_KEY=hf_your_token_here
```

Sans clé, l'application fonctionne en mode dégradé (pas d'analyse IA, tags vides).

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

## Préparer une démo

### Seed des images de démonstration

```powershell
python scripts\seed_demo.py
```

Le script est idempotent : si un fichier de démonstration existe déjà en base avec le même nom, il est ignoré.

### Parcours de démonstration recommandé

1. Lancez l'application (`python app.py`).
2. Exécutez `python scripts\seed_demo.py`.
3. Ouvrez la galerie — observez la barre de tags fréquents et les stats.
4. Tapez dans la barre de recherche — les résultats se filtrent en temps réel.
5. Changez un filtre (personnes, food, orientation) — les résultats s'actualisent immédiatement.
6. Cliquez sur une image — observez les tags en français, la description et les modèles IA utilisés.
7. Cliquez sur un tag dans le modal — la galerie se filtre sur ce tag.
8. Cliquez sur "Réanalyser" — observez la mise à jour des tags et de la description.
9. Ajoutez un favori via l'étoile, puis filtrez par "Favoris uniquement".
10. Importez une nouvelle image — suivez la progression par fichier et l'affichage des tags obtenus.

## Qualité et sécurité

- Validation d'extension côté backend
- Validation réelle de l'image via Pillow avant stockage
- Limite de taille via `MAX_CONTENT_LENGTH`
- Nettoyage du blob/fichier en cas d'échec du flux
- Suppression de la miniature et de l'original en même temps
- Secrets uniquement via variables d'environnement
- Logs applicatifs sur upload, recherche, suppression et erreurs
- Filtre `highlight` XSS-safe (`Markup.escape()` avant injection des balises `<mark>`)

## Limites connues

- Pas d'authentification utilisateur
- Pas de renommage d'image
- Pas de pipeline de déploiement production
- L'API HuggingFace peut imposer des limites de taux — l'upload multi-fichiers est séquentiel pour les éviter
