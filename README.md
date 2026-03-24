# SmartDAM

SmartDAM est une base d’application de gestion d’actifs numériques construite avec Flask, pensée pour l’upload d’images, le marquage assisté par IA et la recherche par mots-clés.

Le projet démarre avec un fonctionnement local, puis peut évoluer vers Azure :

1. téléverser des images depuis l’interface web
2. enregistrer les fichiers en local ou dans Azure Blob Storage
3. analyser les images avec Azure Vision si la configuration est présente
4. stocker les métadonnées dans SQLite
5. rechercher les images par tags, descriptions et noms de fichiers

## Structure du projet

```text
SmartDAM/
|-- app.py
|-- models.py
|-- requirements.txt
|-- services/
|   |-- __init__.py
|   |-- azure_vision.py
|   `-- storage.py
|-- static/
|   `-- css/
|       `-- style.css
|-- templates/
|   |-- base.html
|   `-- index.html
`-- uploads/
```

## Base du projet, étape par étape

### 1. Structure principale Flask

`app.py` crée l’application Flask, initialise SQLite via SQLAlchemy et expose les routes principales :

- `/` affiche la galerie et le formulaire de recherche
- `/upload` gère le téléversement d’images
- `/images/<id>/content` sert le contenu des images stockées
- `/images/<id>/delete` supprime une image et ses métadonnées

### 2. Interface Bootstrap

L’interface reste volontairement simple :

- une section d’accueil qui affiche le mode de stockage et d’analyse actif
- un formulaire d’upload
- un formulaire de recherche avec un filtre `People only`
- une grille d’images responsive

### 3. Upload local en premier

Par défaut, SmartDAM enregistre les nouveaux fichiers dans le dossier local `uploads/`. Cela permet de valider le flux fonctionnel avant de configurer Azure.

### 4. Base de données et recherche

Chaque image téléversée crée un enregistrement SQLite avec :

- le nom du fichier d’origine
- l’URL interne de l’image
- la description
- les tags
- le backend de stockage
- un indicateur de présence de personnes

La recherche interroge les tags, les descriptions et les noms de fichiers.

### 5. Intégration progressive d’Azure

La couche de services est déjà prête pour Azure :

- `services/storage.py` bascule entre le disque local et Azure Blob Storage
- `services/azure_vision.py` utilise Azure Image Analysis pour la description, les tags et la détection de personnes

Si Azure n’est pas encore configuré, SmartDAM utilise un repli local avec des tags dérivés du nom du fichier.

## Variables d’environnement

Copiez `.env.example` vers `.env`, puis adaptez les valeurs.

### Requises pour le mode local

```env
FLASK_SECRET_KEY=change-me
DATABASE_URL=sqlite:///smartdam.db
UPLOAD_FOLDER=uploads
```

### Optionnelles pour Azure Blob Storage

```env
USE_AZURE_STORAGE=true
AZURE_STORAGE_CONNECTION_STRING=your-azure-storage-connection-string
AZURE_STORAGE_CONTAINER=smartdam-images
```

### Optionnelles pour Azure Vision

```env
VISION_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com
VISION_KEY=your-azure-vision-key
```

## Exécuter le projet

### 1. Créer un environnement virtuel

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Installer les dépendances

```powershell
pip install -r requirements.txt
```

### 3. Démarrer l’application Flask

```powershell
python app.py
```

Ouvrez ensuite `http://127.0.0.1:5000`.

## Notes Azure

- Les uploads Azure Blob suivent le schéma officiel de `azure-storage-blob` avec `BlobServiceClient` et `upload_blob(..., overwrite=True)`.
- Azure Vision utilise le client officiel `azure-ai-vision-imageanalysis` avec les fonctionnalités visuelles `CAPTION`, `TAGS` et `PEOPLE`.
- La documentation Microsoft Learn actuelle s’appuie sur la branche preview du package `azure-ai-vision-imageanalysis`, c’est pourquoi `requirements.txt` utilise `1.0.0b3` ou une version plus récente de cette série.
- L’application sert les images via Flask, ce qui permet de garder le conteneur Blob privé pendant le développement.

## Bonus déjà inclus

- suppression d’image
- filtrage avancé avec `People only`
