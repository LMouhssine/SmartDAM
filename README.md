# SmartDAM

SmartDAM est une application Flask de gestion d'assets visuels orientée photographie food et restauration. Elle permet d'importer des images, de les analyser automatiquement par IA (HuggingFace), et de les retrouver dans une galerie filtrable pensée pour une démonstration produit.

## Fonctionnalités

### Gestion des images

- Import multi-fichiers avec liste de progression par image (glisser-déposer ou sélection)
- Validation réelle via Pillow avant stockage
- Génération de miniatures côté serveur
- Stockage local ou Azure Blob Storage
- Téléchargement en pleine résolution
- Renommage d'image (nom affiché) depuis le modal détail, extension d'origine conservée
- Suppression confirmée avec nettoyage du stockage

### Analyse IA (HuggingFace)

- Classification d'image avec `microsoft/resnet-50`
- Détection d'objets avec `facebook/detr-resnet-50`
- Description générée par légende locale BLIP (`Salesforce/blip-image-captioning-large`), avec repli sur une description construite à partir des tags si BLIP n'est pas disponible
- Tags générés automatiquement, traduits en français (couverture élargie + log si un tag n'a pas encore de traduction)
- Détection de personnes
- Bouton "Réanalyser" sur chaque image (depuis le modal détail)
- Affichage des modèles IA utilisés dans la modale d'import
- Visualisation du processus d'analyse pendant l'upload (état par fichier : analyse en cours → tags obtenus)
- Fallback local si HuggingFace est indisponible

### Recherche et filtres

- Recherche par mots-clés sur tags et description
- **Recherche dynamique** : les résultats se mettent à jour en temps réel (400 ms de debounce sur le champ texte)
- **Recherche vocale** : bouton micro à côté de la barre de recherche, dicte une requête via l'API Web Speech native du navigateur (`fr-FR`, sans dépendance cloud), masqué automatiquement si le navigateur ne la supporte pas
- Panneau de filtres (personnes, catégorie food, environnement, orientation, favoris, tri) — s'applique via le bouton "Appliquer" (rechargement de la liste avec indicateur de chargement)
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

### Authentification

- Compte admin unique (identifiants via variables d'environnement, pas de table utilisateur)
- Session Flask-Login ; toutes les routes de modification (upload, suppression, renommage, réanalyse, favoris) exigent d'être connecté
- Protection CSRF (Flask-WTF) sur tous les formulaires et appels JS de mutation

## Architecture

### Backend

- `app.py` — Routes Flask, upload synchrone et asynchrone (`/upload/async`), renommage, toggle favoris, réanalyse, login/logout, filtre `highlight`, contexte de template global
- `auth.py` — Compte admin unique (Flask-Login), vérification des identifiants
- `models.py` — Modèle `ImageAsset`, tags structurés, orientation, is_favorite ; migrations légères via `ensure_image_asset_schema()`
- `services/huggingface.py` — Analyse HuggingFace (classification + détection + légende BLIP), traduction des tags en français, détection de personnes, fallback
- `services/search.py` — `SearchParams` (dataclass slots), `parse_search_params()`, `search_images()`, `_build_context()`
- `services/storage.py` — Stockage local ou Azure Blob Storage
- `services/image_processing.py` — Validation et génération de miniatures via Pillow

### Frontend

- `templates/` — Templates Jinja, composants réutilisables (galerie, modal upload, modal détail, filtres, navbar, connexion)
- `static/css/style.css` — Design Bootstrap 5 + charte graphique personnalisée (palette food-tech chaleureuse, typographie Fraunces/Manrope, cartes, tags, upload, highlight)
- `static/js/app.js` — IIFE vanilla JS : upload multi-fichiers, modal détail, renommage, favoris, réanalyse, recherche dynamique, recherche vocale

### Données de démonstration

- `demo_assets/` — Images versionnées pour la démo
- `scripts/seed_demo.py` — Script idempotent pour charger les assets de démo dans le backend actif

## Structure du projet

```text
SmartDAM/
|-- app.py
|-- auth.py
|-- models.py
|-- requirements.txt
|-- requirements-notebook.txt
|-- README.md
|-- demo_assets/
|-- notebooks/
|   `-- demarche.ipynb
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
|-- tests/
|   `-- test_huggingface_filtering.py
|-- templates/
|   |-- base.html
|   |-- login.html
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

Si `FLASK_SECRET_KEY` est absent ou laissé à `change-me`, l'application génère une clé aléatoire au démarrage (avec un avertissement dans les logs) : les sessions ne survivent pas à un redémarrage tant qu'une vraie valeur n'est pas configurée.

### Authentification (compte admin)

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=
```

Il n'y a qu'un seul compte, pas de table utilisateur. Générez le hash du mot de passe avec :

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('votre-mot-de-passe'))"
```

Sans `ADMIN_PASSWORD_HASH` configuré, la connexion échoue toujours (aucun mot de passe par défaut).

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
HUGGINGFACE_API_TOKEN=hf_your_token_here
HUGGINGFACE_CLASSIFICATION_MODEL=microsoft/resnet-50
HUGGINGFACE_DETECTION_MODEL=facebook/detr-resnet-50
HUGGINGFACE_CAPTION_MODEL=
HUGGINGFACE_TIMEOUT=20
HUGGINGFACE_MAX_TAGS=8
```

Sans token, l'application fonctionne en mode dégradé (pas d'analyse IA, tags vides).

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

La galerie est consultable sans connexion, mais importer, renommer, supprimer, réanalyser ou mettre en favori une image nécessite d'être connecté avec le compte admin configuré dans `.env` (voir [Authentification (compte admin)](#authentification-compte-admin)).

## Préparer une démo

### Seed des images de démonstration

```powershell
python scripts\seed_demo.py
```

Le script est idempotent : si un fichier de démonstration existe déjà en base avec le même nom, il est ignoré.

### Parcours de démonstration recommandé

1. Lancez l'application (`python app.py`).
2. Exécutez `python scripts\seed_demo.py`.
3. Connectez-vous avec le compte admin (bouton "Connexion" dans la barre de navigation).
4. Ouvrez la galerie — observez la barre de tags fréquents et les stats.
5. Tapez dans la barre de recherche, ou cliquez sur le bouton micro et dictez une requête — les résultats se filtrent en temps réel.
6. Changez un filtre (personnes, food, orientation) puis cliquez sur "Appliquer" — les résultats s'actualisent.
7. Cliquez sur une image — observez les tags en français, la description et les modèles IA utilisés.
8. Cliquez sur l'icône crayon à côté du titre pour renommer l'image.
9. Cliquez sur un tag dans le modal — la galerie se filtre sur ce tag.
10. Cliquez sur "Réanalyser" — observez la mise à jour des tags et de la description.
11. Ajoutez un favori via l'étoile, puis filtrez par "Favoris uniquement".
12. Importez une nouvelle image — suivez la progression par fichier et l'affichage des tags obtenus.

## Qualité et sécurité

- Authentification (Flask-Login) requise sur toutes les routes de modification
- Protection CSRF (Flask-WTF) sur tous les formulaires et appels JS de mutation
- `SECRET_KEY` jamais codée en dur : générée aléatoirement (avec avertissement) si non configurée
- Validation d'extension côté backend
- Validation réelle de l'image via Pillow avant stockage
- Limite de taille via `MAX_CONTENT_LENGTH`
- Nettoyage du blob/fichier en cas d'échec du flux
- Suppression de la miniature et de l'original en même temps
- Secrets uniquement via variables d'environnement
- Logs applicatifs sur upload, recherche, suppression et erreurs
- Filtre `highlight` XSS-safe (`Markup.escape()` avant injection des balises `<mark>`)
- Suite de tests (`pytest tests/`) couvrant le filtrage des tags IA (voir `notebooks/demarche.ipynb` pour le détail de l'investigation)

## Limites connues

- Un seul compte admin (pas de gestion multi-utilisateurs / rôles)
- Pas de pipeline de déploiement production
- L'API HuggingFace peut imposer des limites de taux — l'upload multi-fichiers est séquentiel pour les éviter
- La recherche vocale dépend du support navigateur de la Web Speech API (indisponible sur Firefox ; le bouton micro se masque automatiquement dans ce cas)
