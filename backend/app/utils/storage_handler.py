"""
storage_handler.py

Unified storage handler that supports both local filesystem (development)
and Google Cloud Storage (Cloud Run production).

Usage:
    from app.utils.storage_handler import get_storage_handler
    
    storage = get_storage_handler()
    
    # Upload a file
    storage_path = await storage.upload_file(local_path, job_id)
    
    # Download a file (for worker)
    local_path = await storage.download_file(storage_path)
    
    # Cleanup
    await storage.cleanup_job(job_id)
"""

import os
import logging
import shutil
from pathlib import Path
from typing import Optional, List
from abc import ABC, abstractmethod

from ..core.config import settings

logger = logging.getLogger(__name__)


class StorageHandler(ABC):
    """Abstract base class for storage handlers."""
    
    @abstractmethod
    async def upload_file(self, local_path: str, job_id: str) -> str:
        """
        Upload a file to storage.
        Returns the storage path (local path or GCS URI).
        """
        pass
    
    @abstractmethod
    async def download_file(self, storage_path: str, local_dir: Optional[str] = None) -> str:
        """
        Download a file from storage to local filesystem.
        Returns the local path.
        """
        pass
    
    @abstractmethod
    async def cleanup_job(self, job_id: str) -> None:
        """Clean up all files associated with a job."""
        pass
    
    @abstractmethod
    async def save_bytes(self, content: bytes, filename: str, job_id: str) -> str:
        """
        Save bytes content to storage.
        Returns the storage path.
        """
        pass


class LocalStorageHandler(StorageHandler):
    """Local filesystem storage handler for development."""
    
    def __init__(self):
        self.base_dir = settings.BASE_DIR / "data" / "temp"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Using local storage: {self.base_dir}")
    
    async def upload_file(self, local_path: str, job_id: str) -> str:
        """For local storage, file is already saved. Return the path."""
        return local_path
    
    async def download_file(self, storage_path: str, local_dir: Optional[str] = None) -> str:
        """For local storage, file is already local. Return the path."""
        return storage_path
    
    async def cleanup_job(self, job_id: str) -> None:
        """Remove the job directory."""
        job_dir = self.base_dir / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
            logger.info(f"🗑️ Cleaned up local job directory: {job_id}")
    
    async def save_bytes(self, content: bytes, filename: str, job_id: str) -> str:
        """Save bytes to local filesystem."""
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = job_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
        
        return str(file_path)
    
    def get_job_dir(self, job_id: str) -> Path:
        """Get the job directory path."""
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir


class GCSStorageHandler(StorageHandler):
    """Google Cloud Storage handler for Cloud Run production."""
    
    def __init__(self, bucket_name: str):
        from google.cloud import storage
        
        self.client = storage.Client()
        self.bucket_name = bucket_name
        self.bucket = self.client.bucket(bucket_name)
        self.prefix = "evaluate_jobs"  # GCS path prefix
        
        # Local temp dir for downloaded files
        self.local_temp = Path("/tmp/study-buddy-temp")
        self.local_temp.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"☁️ Using GCS storage: gs://{bucket_name}/{self.prefix}/")
    
    def _get_gcs_path(self, job_id: str, filename: str) -> str:
        """Generate GCS object path."""
        return f"{self.prefix}/{job_id}/{filename}"
    
    def _get_gcs_uri(self, gcs_path: str) -> str:
        """Generate full GCS URI."""
        return f"gs://{self.bucket_name}/{gcs_path}"
    
    async def upload_file(self, local_path: str, job_id: str) -> str:
        """
        Upload a local file to GCS.
        Returns the GCS URI (gs://bucket/path).
        """
        local_file = Path(local_path)
        gcs_path = self._get_gcs_path(job_id, local_file.name)
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_filename(local_path)
        
        gcs_uri = self._get_gcs_uri(gcs_path)
        logger.info(f"☁️ Uploaded to GCS: {gcs_uri}")
        
        # Remove local file after upload
        if local_file.exists():
            local_file.unlink()
        
        return gcs_uri
    
    async def download_file(self, storage_path: str, local_dir: Optional[str] = None) -> str:
        """
        Download a file from GCS to local filesystem.
        storage_path can be gs:// URI or just the GCS path.
        Returns the local path.
        """
        # Parse GCS path
        if storage_path.startswith("gs://"):
            # gs://bucket/prefix/job_id/filename
            path_part = storage_path.replace(f"gs://{self.bucket_name}/", "")
        else:
            path_part = storage_path
        
        # Extract filename
        filename = Path(path_part).name
        
        # Determine local directory
        if local_dir:
            local_path = Path(local_dir) / filename
        else:
            # Use job_id from path
            parts = path_part.split("/")
            if len(parts) >= 2:
                job_id = parts[-2]  # prefix/job_id/filename -> job_id
                local_job_dir = self.local_temp / job_id
                local_job_dir.mkdir(parents=True, exist_ok=True)
                local_path = local_job_dir / filename
            else:
                local_path = self.local_temp / filename
        
        # Download from GCS
        blob = self.bucket.blob(path_part)
        blob.download_to_filename(str(local_path))
        
        logger.info(f"☁️ Downloaded from GCS: {storage_path} -> {local_path}")
        return str(local_path)
    
    async def cleanup_job(self, job_id: str) -> None:
        """Delete all GCS objects for a job and local temp files."""
        prefix = f"{self.prefix}/{job_id}/"
        
        # Delete GCS objects
        blobs = self.bucket.list_blobs(prefix=prefix)
        for blob in blobs:
            blob.delete()
            logger.debug(f"🗑️ Deleted GCS object: {blob.name}")
        
        # Delete local temp directory
        local_job_dir = self.local_temp / job_id
        if local_job_dir.exists():
            shutil.rmtree(local_job_dir)
        
        logger.info(f"🗑️ Cleaned up GCS job: {job_id}")
    
    async def save_bytes(self, content: bytes, filename: str, job_id: str) -> str:
        """
        Save bytes content directly to GCS.
        Returns the GCS URI.
        """
        gcs_path = self._get_gcs_path(job_id, filename)
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(content)
        
        gcs_uri = self._get_gcs_uri(gcs_path)
        logger.info(f"☁️ Saved to GCS: {gcs_uri}")
        
        return gcs_uri
    
    def get_job_dir(self, job_id: str) -> Path:
        """Get local temp directory for job (for compatibility)."""
        job_dir = self.local_temp / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir


# Singleton instance
_storage_handler: Optional[StorageHandler] = None


def get_storage_handler() -> StorageHandler:
    """
    Get the appropriate storage handler based on environment.
    Uses GCS in Cloud Run (when GCS_BUCKET_NAME is set), local filesystem otherwise.
    """
    global _storage_handler
    
    if _storage_handler is None:
        if settings.IS_CLOUD_RUN and settings.GCS_BUCKET_NAME:
            _storage_handler = GCSStorageHandler(settings.GCS_BUCKET_NAME)
        else:
            _storage_handler = LocalStorageHandler()
    
    return _storage_handler


def reset_storage_handler():
    """Reset the singleton (for testing)."""
    global _storage_handler
    _storage_handler = None
