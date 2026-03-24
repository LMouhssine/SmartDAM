# SmartDAM

SmartDAM est une application Flask de gestion d'assets visuels. Elle permet de téléverser des images, de les stocker, de les analyser avec Azure Vision, puis de rechercher les résultats grâce aux tags et descriptions enregistrés.

Le projet fonctionne toujours en mode local pour le développement, mais le flux principal est désormais :

1. upload du fichier
2. envoi vers Azure Blob Storage
3. récupération de l'URL publique du blob
4. analyse de l'image avec Azure Vision
5. enregistrement des métadonnées dans SQLite
6. affichage direct dans la galerie

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

## Intégration Azure, étape par étape

### 1. Azure Blob Storage

`services/storage.py` gère désormais un mode Azure-first :

- upload du fichier avec `BlobServiceClient`
- définition du `content_type`
- retour du chemin blob et de l'URL publique directe
- suppression du blob en cas d'échec ultérieur du flux

Quand `USE_AZURE_STORAGE=true`, SmartDAM n'utilise plus de repli local silencieux. Si Azure Blob Storage n'est pas disponible, l'upload échoue.

### 2. Azure Vision

`services/azure_vision.py` expose deux modes :

- `analyze_image_url(...)` pour le flux Azure principal à partir d'une URL Blob publique
- `analyze_image(...)` pour le mode local, avec fallback si Azure Vision n'est pas configuré

Les données extraites comprennent :

- les tags
- la description
- la présence éventuelle de personnes

### 3. Base de données

`models.py` stocke désormais :

- `original_filename`
- `image_url`
- `description`
- `tags` en texte miroir pour la recherche simple
- `tags_json` en JSON sérialisé pour garder la liste structurée

Une migration légère au démarrage ajoute `tags_json` si la colonne n'existe pas encore et backfill les anciennes lignes à partir de `tags`.

### 4. Flux d'upload

Dans `app.py`, le flux `POST /upload` suit maintenant cet ordre :

1. validation du fichier
2. upload Azure Blob si activé
3. analyse Azure Vision par URL publique
4. création de l'enregistrement SQL
5. rollback complet en cas d'échec

Si Azure Vision échoue après l'upload Blob, le blob est supprimé et aucun enregistrement n'est créé en base.

### 5. Interface utilisateur

L'interface affiche :

- l'image
- les tags structurés
- la description
- l'origine du stockage et de l'analyse

La recherche continue de s'appuyer sur le texte stocké dans `tags`, `description` et `original_filename`.

## Variables d'environnement

Copiez `.env.example` vers `.env`, puis adaptez les valeurs.

### Base locale

```env
FLASK_SECRET_KEY=change-me
DATABASE_URL=sqlite:///smartdam.db
MAX_CONTENT_LENGTH=16777216
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

- SmartDAM stocke l'URL publique directe du blob
- le conteneur doit donc autoriser la lecture publique des blobs
- si le conteneur est créé par l'application, SmartDAM tente de le créer avec `public_access="blob"`
- si le conteneur existe déjà en privé, il faut activer la lecture publique côté Azure avant de tester l'affichage direct

### Azure Vision

```env
VISION_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com
VISION_KEY=your-azure-vision-key
VISION_LANGUAGE=fr
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

### 3. Démarrer l'application

```powershell
python app.py
```

Ouvrez ensuite [http://127.0.0.1:5000](http://127.0.0.1:5000).

Au premier démarrage, SmartDAM crée les tables SQLite nécessaires et applique une migration légère pour ajouter `tags_json` si la colonne manque encore.

## Configuration Azure minimale

Pour tester le flux Azure de bout en bout, il faut :

1. un compte Azure Storage avec un conteneur Blob lisible publiquement
2. une ressource Azure Vision / Image Analysis avec `VISION_ENDPOINT` et `VISION_KEY`
3. `USE_AZURE_STORAGE=true` dans `.env`

Quand ces trois éléments sont présents, le flux devient :

1. upload du fichier vers Azure Blob Storage
2. récupération de l'URL publique du blob
3. analyse de cette URL via Azure Vision
4. enregistrement en base de `image_url`, `description`, `tags` et `tags_json`
5. affichage direct de l'image depuis Azure dans la galerie

## Logs et erreurs

SmartDAM journalise les étapes clés du flux :

- démarrage d'upload
- succès Azure Blob
- succès Azure Vision
- rollback et nettoyage d'un blob
- erreurs de stockage
- erreurs d'analyse
- erreurs base de données

Les messages techniques détaillés vont dans les logs Flask, tandis que l'utilisateur voit un message `flash` plus simple.

En mode Azure-first, il n'y a pas de repli silencieux si l'upload Blob échoue. Si l'analyse Vision échoue après l'upload, le blob fraîchement créé est supprimé pour éviter les fichiers orphelins.

## Vérifications recommandées

- Upload Azure réussi : l'image s'affiche depuis l'URL Blob et les métadonnées sont en base.
- Échec Azure Blob : aucun enregistrement SQL n'est créé.
- Échec Azure Vision : le blob fraîchement envoyé est supprimé.
- Migration SQLite : `tags_json` est créé et backfill à partir de `tags`.
- Recherche : les mots-clés continuent à matcher `tags`, `description` et `original_filename`.
