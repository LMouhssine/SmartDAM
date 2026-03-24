from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
    from azure.storage.blob import BlobServiceClient, ContentSettings

    AZURE_BLOB_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - local mode still works without the SDK.
    BlobServiceClient = None
    ContentSettings = None
    ResourceExistsError = Exception
    ResourceNotFoundError = Exception
    AZURE_BLOB_SDK_AVAILABLE = False


class StorageError(RuntimeError):
    """Raised when the storage backend cannot complete an operation."""


@dataclass(slots=True)
class StoredAsset:
    backend: str
    path: str
    content_type: str


class LocalStorageService:
    def __init__(self, upload_folder: str | Path) -> None:
        self.upload_folder = Path(upload_folder)
        self.upload_folder.mkdir(parents=True, exist_ok=True)

    def save(self, file_bytes: bytes, original_filename: str, content_type: str | None) -> StoredAsset:
        stored_name = f"{uuid4().hex}{Path(original_filename).suffix.lower()}"
        destination = self.upload_folder / stored_name
        destination.write_bytes(file_bytes)

        return StoredAsset(
            backend="local",
            path=stored_name,
            content_type=content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream",
        )

    def read_bytes(self, storage_path: str) -> bytes:
        file_path = self.upload_folder / storage_path
        if not file_path.exists():
            raise StorageError(f"Local file not found: {file_path}")
        return file_path.read_bytes()

    def delete(self, storage_path: str) -> None:
        file_path = self.upload_folder / storage_path
        if file_path.exists():
            file_path.unlink()


class AzureBlobStorageService:
    def __init__(self, connection_string: str, container_name: str) -> None:
        if not AZURE_BLOB_SDK_AVAILABLE:
            raise StorageError("azure-storage-blob is not installed.")

        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            self.blob_service_client.create_container(name=self.container_name)
        except ResourceExistsError:
            return

    def save(self, file_bytes: bytes, original_filename: str, content_type: str | None) -> StoredAsset:
        blob_name = f"{uuid4().hex}{Path(original_filename).suffix.lower()}"
        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=blob_name)
        detected_content_type = content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

        upload_options: dict[str, Any] = {"overwrite": True}
        if ContentSettings is not None:
            upload_options["content_settings"] = ContentSettings(content_type=detected_content_type)

        blob_client.upload_blob(file_bytes, **upload_options)

        return StoredAsset(
            backend="azure",
            path=blob_name,
            content_type=detected_content_type,
        )

    def read_bytes(self, storage_path: str) -> bytes:
        try:
            blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=storage_path)
            return blob_client.download_blob().readall()
        except ResourceNotFoundError as exc:
            raise StorageError(f"Azure blob not found: {storage_path}") from exc

    def delete(self, storage_path: str) -> None:
        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=storage_path)
        try:
            blob_client.delete_blob(delete_snapshots="include")
        except ResourceNotFoundError:
            return


class StorageManager:
    def __init__(
        self,
        upload_folder: str | Path,
        use_azure_storage: bool = False,
        connection_string: str = "",
        container_name: str = "smartdam-images",
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.local = LocalStorageService(upload_folder)
        self.azure: AzureBlobStorageService | None = None
        self.use_azure_storage = use_azure_storage

        if connection_string:
            try:
                self.azure = AzureBlobStorageService(connection_string, container_name)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Azure Blob Storage is unavailable. Using local disk instead: %s", exc)
        elif use_azure_storage:
            self.logger.warning("USE_AZURE_STORAGE is enabled but no connection string was provided.")

    @property
    def azure_enabled(self) -> bool:
        return self.azure is not None

    @property
    def default_backend_label(self) -> str:
        return "Azure Blob Storage" if self.use_azure_storage and self.azure_enabled else "Local disk"

    def save(self, file_bytes: bytes, original_filename: str, content_type: str | None) -> StoredAsset:
        if self.use_azure_storage and self.azure_enabled:
            return self.azure.save(file_bytes, original_filename, content_type)
        return self.local.save(file_bytes, original_filename, content_type)

    def read(self, image: Any) -> tuple[bytes, str]:
        backend = self._backend_for(image.storage_backend)
        content_type = image.content_type or mimetypes.guess_type(image.original_filename)[0] or "application/octet-stream"
        return backend.read_bytes(image.storage_path), content_type

    def delete(self, image: Any) -> None:
        backend = self._backend_for(image.storage_backend)
        backend.delete(image.storage_path)

    def delete_by_reference(self, backend_name: str, storage_path: str) -> None:
        backend = self._backend_for(backend_name)
        backend.delete(storage_path)

    def _backend_for(self, backend_name: str):
        if backend_name == "azure":
            if not self.azure_enabled:
                raise StorageError("Azure storage is not configured for this application.")
            return self.azure
        return self.local


def build_storage_manager(config: dict[str, object], logger: logging.Logger | None = None) -> StorageManager:
    return StorageManager(
        upload_folder=str(config.get("UPLOAD_FOLDER", "uploads")),
        use_azure_storage=bool(config.get("USE_AZURE_STORAGE", False)),
        connection_string=str(config.get("AZURE_STORAGE_CONNECTION_STRING", "")),
        container_name=str(config.get("AZURE_STORAGE_CONTAINER", "smartdam-images")),
        logger=logger,
    )
