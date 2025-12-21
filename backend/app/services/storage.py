import json
import os
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

from fastapi import HTTPException
from google.cloud import storage

# --- Interface Definition ---


class StorageBackend(ABC):
    @abstractmethod
    def create_folder(self, folder_name: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def folder_exists(self, folder_id: str) -> bool:
        pass

    @abstractmethod
    def list_folders(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_files(self, folder_id: str) -> List[str]:
        pass

    @abstractmethod
    def upload_file(self, folder_id: str, filename: str, file_obj: BinaryIO) -> str:
        pass

    @abstractmethod
    def delete_folder(self, folder_id: str) -> None:
        pass

    @abstractmethod
    def read_file_content(self, folder_id: str, filename: str) -> bytes:
        pass

    @abstractmethod
    def save_processed_file(self, folder_id: str, filename: str, content: str) -> str:
        pass

    @abstractmethod
    def get_processed_file_content(self, folder_id: str, filename: str) -> str:
        pass

    @abstractmethod
    def get_gcs_uri(self, folder_id: str, filename: str) -> str:
        pass

    @abstractmethod
    def get_bucket_name(self) -> str:
        pass

    @abstractmethod
    def list_processed_jsons(self, folder_id: str, filename_prefix: str) -> List[str]:
        pass

    @abstractmethod
    def read_blob_as_bytes(self, blob_name: str) -> bytes:
        pass

    @abstractmethod
    def delete_file(self, folder_id: str, filename: str) -> bool:
        pass

    @abstractmethod
    def save_parsed_output(self, folder_id: str, filename: str, parsed_data: Dict[str, Any]) -> str:
        """Save the raw parsed output (markdown + chunks) for later reprocessing."""
        pass

    @abstractmethod
    def get_parsed_output(self, folder_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Retrieve previously saved parsed output. Returns None if not found."""
        pass


# --- GCS Implementation ---


class GCSBackend(StorageBackend):
    def __init__(self):
        self.bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not self.bucket_name:
            print("Warning: GCS_BUCKET_NAME not set.")
            self.bucket_name = "credit-eval-engine-uploads"

        try:
            self.client = storage.Client()
            self.bucket = self.client.bucket(self.bucket_name)
        except Exception as e:
            print(f"Error initializing GCS client: {e}")
            self.client = None
            self.bucket = None

    def create_folder(self, folder_name: str) -> Dict[str, Any]:
        if not self.bucket:
            return None

        folder_id = str(uuid.uuid4())
        blob = self.bucket.blob(f"metadata/{folder_id}")
        metadata = {"original_name": folder_name, "status": "EMPTY"}
        blob.metadata = metadata
        blob.upload_from_string(
            "", content_type="application/x-www-form-urlencoded;charset=UTF-8"
        )
        blob.metadata = metadata
        blob.patch()

        return {"id": folder_id, "name": folder_name, "status": "EMPTY", "fileCount": 0}

    def folder_exists(self, folder_id: str) -> bool:
        if not self.bucket:
            return False
        blob = self.bucket.blob(f"metadata/{folder_id}")
        return blob.exists()

    def list_folders(self) -> List[Dict[str, Any]]:
        if not self.bucket:
            return []

        # 1. Get all folders first
        blobs = self.client.list_blobs(self.bucket_name, prefix="metadata/")
        folders_dict = {}
        for blob in blobs:
            folder_id = blob.name.split("/")[-1]
            if not folder_id:
                continue

            metadata = blob.metadata or {}
            name = metadata.get("original_name", "Unknown Folder")
            status = metadata.get("status", "UNKNOWN")
            folders_dict[folder_id] = {
                "id": folder_id,
                "name": name,
                "status": status,
                "fileCount": 0
            }
        
        # 2. Count files from uploads/
        # We list all blobs under uploads/ to avoid N API calls
        upload_blobs = self.client.list_blobs(self.bucket_name, prefix="uploads/")
        for blob in upload_blobs:
            # Expected format: uploads/{folder_id}/{filename}
            parts = blob.name.split("/")
            if len(parts) >= 3:
                f_id = parts[1]
                if f_id in folders_dict:
                    folders_dict[f_id]["fileCount"] += 1

        return list(folders_dict.values())

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        if not self.bucket:
            return None

        blob = self.bucket.blob(f"metadata/{folder_id}")
        if not blob.exists():
            return None

        blob.reload()
        metadata = blob.metadata or {}
        return {
            "id": folder_id,
            "name": metadata.get("original_name", "Unknown"),
            "status": metadata.get("status", "UNKNOWN"),
        }

    def list_files(self, folder_id: str) -> List[str]:
        if not self.bucket:
            return []

        blobs = self.client.list_blobs(self.bucket_name, prefix=f"uploads/{folder_id}/")
        files = []
        for blob in blobs:
            filename = blob.name.split("/")[-1]
            if filename:
                files.append(filename)
        return files

    def upload_file(self, folder_id: str, filename: str, file_obj: BinaryIO) -> str:
        if not self.bucket:
            raise HTTPException(status_code=500, detail="Storage service unavailable")

        blob = self.bucket.blob(f"uploads/{folder_id}/{filename}")
        file_obj.seek(0)
        blob.upload_from_file(file_obj)

        self._update_status(folder_id, "HAS_FILES")
        return blob.name

    def delete_folder(self, folder_id: str) -> None:
        if not self.bucket:
            return

        metadata_blob = self.bucket.blob(f"metadata/{folder_id}")
        if metadata_blob.exists():
            metadata_blob.delete()

        blobs = self.bucket.list_blobs(prefix=f"uploads/{folder_id}/")
        for blob in blobs:
            blob.delete()

    def read_file_content(self, folder_id: str, filename: str) -> bytes:
        if not self.bucket:
            raise HTTPException(status_code=500, detail="Storage service unavailable")

        blob = self.bucket.blob(f"uploads/{folder_id}/{filename}")
        if not blob.exists():
            raise HTTPException(status_code=404, detail="File not found")

        return blob.download_as_bytes()

    def save_processed_file(self, folder_id: str, filename: str, content: str) -> str:
        if not self.bucket:
            raise HTTPException(status_code=500, detail="Storage service unavailable")

        blob = self.bucket.blob(f"processed/{folder_id}/{filename}")
        blob.upload_from_string(content, content_type="text/csv")
        return blob.name

    def get_processed_file_content(self, folder_id: str, filename: str) -> str:
        if not self.bucket:
            raise HTTPException(status_code=500, detail="Storage service unavailable")

        blob = self.bucket.blob(f"processed/{folder_id}/{filename}")
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Processed file not found")

        return blob.download_as_text()

    def get_gcs_uri(self, folder_id: str, filename: str) -> str:
        return f"gs://{self.bucket_name}/uploads/{folder_id}/{filename}"

    def get_bucket_name(self) -> str:
        return self.bucket_name

    def list_processed_jsons(self, folder_id: str, filename_prefix: str) -> List[str]:
        if not self.bucket:
            return []

        prefix = f"processed/{folder_id}/{filename_prefix}/"
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)

        json_files = []
        for blob in blobs:
            if blob.name.endswith(".json"):
                json_files.append(blob.name)
        return json_files

    def read_blob_as_bytes(self, blob_name: str) -> bytes:
        if not self.bucket:
            raise HTTPException(status_code=500, detail="Storage service unavailable")
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()

    def delete_file(self, folder_id: str, filename: str) -> bool:
        """Delete a file from GCS uploads and its processed CSV if exists"""
        if not self.bucket:
            return False

        try:
            # Delete the uploaded file
            upload_blob = self.bucket.blob(f"uploads/{folder_id}/{filename}")
            if upload_blob.exists():
                upload_blob.delete()
            
            # Delete the processed CSV if it exists
            processed_blob = self.bucket.blob(f"processed/{folder_id}/{filename}.csv")
            if processed_blob.exists():
                processed_blob.delete()
            
            # Delete the parsed output if it exists
            parsed_blob = self.bucket.blob(f"parsed/{folder_id}/{filename}.json")
            if parsed_blob.exists():
                parsed_blob.delete()
            
            # Check if folder still has files and update status
            remaining_files = self.list_files(folder_id)
            new_status = "HAS_FILES" if remaining_files else "EMPTY"
            self._update_status(folder_id, new_status)
            
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

    def save_parsed_output(self, folder_id: str, filename: str, parsed_data: Dict[str, Any]) -> str:
        """Save the raw parsed output (markdown + chunks) for later reprocessing."""
        if not self.bucket:
            raise HTTPException(status_code=500, detail="Storage service unavailable")

        blob = self.bucket.blob(f"parsed/{folder_id}/{filename}.json")
        blob.upload_from_string(json.dumps(parsed_data, ensure_ascii=False), content_type="application/json")
        return blob.name

    def get_parsed_output(self, folder_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Retrieve previously saved parsed output. Returns None if not found."""
        if not self.bucket:
            return None

        blob = self.bucket.blob(f"parsed/{folder_id}/{filename}.json")
        if not blob.exists():
            return None

        try:
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            print(f"Error reading parsed output: {e}")
            return None

    def _update_status(self, folder_id: str, new_status: str):
        try:
            blob = self.bucket.blob(f"metadata/{folder_id}")
            blob.reload()
            metadata = blob.metadata or {}

            if metadata.get("status") != new_status:
                metadata["status"] = new_status
                blob.metadata = metadata
                blob.patch()
        except Exception as e:
            print(f"Failed to update status for {folder_id}: {e}")


# --- Local Implementation ---


class LocalBackend(StorageBackend):
    def __init__(self):
        # Default local storage path
        self.base_path = Path("local_storage")
        self.base_path.mkdir(exist_ok=True)
        (self.base_path / "metadata").mkdir(exist_ok=True)
        (self.base_path / "uploads").mkdir(exist_ok=True)
        (self.base_path / "processed").mkdir(exist_ok=True)
        (self.base_path / "parsed").mkdir(exist_ok=True)
        print(f"Initialized Local Storage at {self.base_path.absolute()}")

    def _get_metadata_path(self, folder_id: str) -> Path:
        return self.base_path / "metadata" / f"{folder_id}.json"

    def _get_uploads_path(self, folder_id: str) -> Path:
        return self.base_path / "uploads" / folder_id

    def _get_processed_path(self, folder_id: str) -> Path:
        return self.base_path / "processed" / folder_id

    def _get_parsed_path(self, folder_id: str) -> Path:
        return self.base_path / "parsed" / folder_id

    def create_folder(self, folder_name: str) -> Dict[str, Any]:
        folder_id = str(uuid.uuid4())
        metadata = {"original_name": folder_name, "status": "EMPTY", "id": folder_id}

        # Save metadata
        with open(self._get_metadata_path(folder_id), "w") as f:
            json.dump(metadata, f)

        # Create directories
        self._get_uploads_path(folder_id).mkdir(parents=True, exist_ok=True)
        self._get_processed_path(folder_id).mkdir(parents=True, exist_ok=True)

        # Return with correct field names for FolderResponse schema
        return {"id": folder_id, "name": folder_name, "status": "EMPTY", "fileCount": 0}

    def folder_exists(self, folder_id: str) -> bool:
        return self._get_metadata_path(folder_id).exists()

    def list_folders(self) -> List[Dict[str, Any]]:
        folders = []
        metadata_dir = self.base_path / "metadata"
        if not metadata_dir.exists():
            return []

        for file in metadata_dir.glob("*.json"):
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    folder_id = data.get("id", file.stem)
                    # Ensure basic fields exist
                    folders.append(
                        {
                            "id": folder_id,
                            "name": data.get("original_name", "Unknown"),
                            "status": data.get("status", "UNKNOWN"),
                            "fileCount": len(self.list_files(folder_id)),
                        }
                    )
            except Exception as e:
                print(f"Error reading metadata file {file}: {e}")
        return folders

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        path = self._get_metadata_path(folder_id)
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return {
                    "id": data.get("id", folder_id),
                    "name": data.get("original_name", "Unknown"),
                    "status": data.get("status", "UNKNOWN"),
                }
        except Exception:
            return None

    def list_files(self, folder_id: str) -> List[str]:
        upload_dir = self._get_uploads_path(folder_id)
        if not upload_dir.exists():
            return []
        return [f.name for f in upload_dir.iterdir() if f.is_file()]

    def upload_file(self, folder_id: str, filename: str, file_obj: BinaryIO) -> str:
        upload_dir = self._get_uploads_path(folder_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        target_path = upload_dir / filename

        file_obj.seek(0)
        with open(target_path, "wb") as f:
            shutil.copyfileobj(file_obj, f)

        self._update_status(folder_id, "HAS_FILES")
        return str(target_path)

    def delete_folder(self, folder_id: str) -> None:
        # Delete metadata
        metadata_path = self._get_metadata_path(folder_id)
        if metadata_path.exists():
            metadata_path.unlink()

        # Delete uploads
        upload_dir = self._get_uploads_path(folder_id)
        if upload_dir.exists():
            shutil.rmtree(upload_dir)

        # Delete processed
        processed_dir = self._get_processed_path(folder_id)
        if processed_dir.exists():
            shutil.rmtree(processed_dir)

    def read_file_content(self, folder_id: str, filename: str) -> bytes:
        path = self._get_uploads_path(folder_id) / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        with open(path, "rb") as f:
            return f.read()

    def save_processed_file(self, folder_id: str, filename: str, content: str) -> str:
        processed_dir = self._get_processed_path(folder_id)
        processed_dir.mkdir(parents=True, exist_ok=True)
        target_path = processed_dir / filename

        with open(target_path, "w") as f:
            f.write(content)
        return str(target_path)

    def get_processed_file_content(self, folder_id: str, filename: str) -> str:
        path = self._get_processed_path(folder_id) / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="Processed file not found")
        with open(path, "r") as f:
            return f.read()

    def get_gcs_uri(self, folder_id: str, filename: str) -> str:
        # For local, we just return the local absolute path
        return str((self._get_uploads_path(folder_id) / filename).absolute())

    def get_bucket_name(self) -> str:
        return "local-storage"

    def list_processed_jsons(self, folder_id: str, filename_prefix: str) -> List[str]:
        # Local equivalent of searching for processed jsons
        # Assuming structure: processed/{folder_id}/{filename_prefix}/...json
        # Note: save_processed_file just saves directly to processed/{folder_id}/{filename}
        # But GCS implementation looks for prefix. We might need to adjust logic if the usage expects subfolders.
        # GCS impl: prefix = f"processed/{folder_id}/{filename_prefix}/"

        processed_dir = self._get_processed_path(folder_id)
        # Check if there is a directory with filename_prefix or just files starting with it?
        # GCS treats paths with / as folders.

        # If the code writes to processed/{folder_id}/{filename}, then filename_prefix might be just part of filename or a "directory".
        # Let's assume for local it might search in a subdirectory if created, or filter files.
        # But wait, save_processed_file saves as `processed/{folder_id}/{filename}` (flat in folder).
        # The GCS `list_processed_jsons` implementation looks for `processed/{folder_id}/{filename_prefix}/`.
        # This implies that some *other* process (maybe Document AI batch) writes to a subfolder?
        # Since we are mocking, let's just look for files starting with prefix in the processed folder for now,
        # or mock the subdirectory if it exists.

        search_dir = processed_dir / filename_prefix
        if search_dir.exists() and search_dir.is_dir():
            return [str(p) for p in search_dir.glob("*.json")]
        return []

    def read_blob_as_bytes(self, blob_name: str) -> bytes:
        # GCS blob_name is full path from bucket root: processed/... or uploads/...
        # We need to map this to local path.
        # blob_name example: "processed/uuid/file.csv"

        # Naive mapping:
        path = self.base_path / blob_name
        if not path.exists():
            raise HTTPException(
                status_code=404, detail=f"Blob {blob_name} not found locally"
            )
        with open(path, "rb") as f:
            return f.read()

    def delete_file(self, folder_id: str, filename: str) -> bool:
        """Delete a file from local uploads and its processed CSV if exists"""
        try:
            # Delete the uploaded file
            upload_path = self._get_uploads_path(folder_id) / filename
            if upload_path.exists():
                upload_path.unlink()
            
            # Delete the processed CSV if it exists
            processed_path = self._get_processed_path(folder_id) / f"{filename}.csv"
            if processed_path.exists():
                processed_path.unlink()
            
            # Delete the parsed output if it exists
            parsed_path = self._get_parsed_path(folder_id) / f"{filename}.json"
            if parsed_path.exists():
                parsed_path.unlink()
            
            # Check if folder still has files and update status
            remaining_files = self.list_files(folder_id)
            new_status = "HAS_FILES" if remaining_files else "EMPTY"
            self._update_status(folder_id, new_status)
            
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

    def save_parsed_output(self, folder_id: str, filename: str, parsed_data: Dict[str, Any]) -> str:
        """Save the raw parsed output (markdown + chunks) for later reprocessing."""
        parsed_dir = self._get_parsed_path(folder_id)
        parsed_dir.mkdir(parents=True, exist_ok=True)
        target_path = parsed_dir / f"{filename}.json"

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, ensure_ascii=False)
        return str(target_path)

    def get_parsed_output(self, folder_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Retrieve previously saved parsed output. Returns None if not found."""
        path = self._get_parsed_path(folder_id) / f"{filename}.json"
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading parsed output: {e}")
            return None

    def _update_status(self, folder_id: str, new_status: str):
        path = self._get_metadata_path(folder_id)
        if not path.exists():
            return

        try:
            with open(path, "r+") as f:
                data = json.load(f)
                if data.get("status") != new_status:
                    data["status"] = new_status
                    f.seek(0)
                    json.dump(data, f)
                    f.truncate()
        except Exception as e:
            print(f"Failed to update status locally for {folder_id}: {e}")


# --- Service Wrapper ---


class StorageService:
    def __init__(self):
        env = os.getenv("ENVIRONMENT", "gcs").lower()
        if env == "local":
            self.backend: StorageBackend = LocalBackend()
        else:
            self.backend: StorageBackend = GCSBackend()

    def create_folder(self, folder_name: str) -> Dict[str, Any]:
        return self.backend.create_folder(folder_name)

    def folder_exists(self, folder_id: str) -> bool:
        return self.backend.folder_exists(folder_id)

    def list_folders(self) -> List[Dict[str, Any]]:
        return self.backend.list_folders()

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        return self.backend.get_folder(folder_id)

    def list_files(self, folder_id: str) -> List[str]:
        return self.backend.list_files(folder_id)

    def upload_file(self, folder_id: str, filename: str, file_obj: BinaryIO) -> str:
        return self.backend.upload_file(folder_id, filename, file_obj)

    def delete_folder(self, folder_id: str) -> None:
        return self.backend.delete_folder(folder_id)

    def read_file_content(self, folder_id: str, filename: str) -> bytes:
        return self.backend.read_file_content(folder_id, filename)

    def save_processed_file(self, folder_id: str, filename: str, content: str) -> str:
        return self.backend.save_processed_file(folder_id, filename, content)

    def get_processed_file_content(self, folder_id: str, filename: str) -> str:
        return self.backend.get_processed_file_content(folder_id, filename)

    def get_gcs_uri(self, folder_id: str, filename: str) -> str:
        return self.backend.get_gcs_uri(folder_id, filename)

    def get_bucket_name(self) -> str:
        return self.backend.get_bucket_name()

    def list_processed_jsons(self, folder_id: str, filename_prefix: str) -> List[str]:
        return self.backend.list_processed_jsons(folder_id, filename_prefix)

    def read_blob_as_bytes(self, blob_name: str) -> bytes:
        return self.backend.read_blob_as_bytes(blob_name)

    def delete_file(self, folder_id: str, filename: str) -> bool:
        return self.backend.delete_file(folder_id, filename)

    def save_parsed_output(self, folder_id: str, filename: str, parsed_data: Dict[str, Any]) -> str:
        return self.backend.save_parsed_output(folder_id, filename, parsed_data)

    def get_parsed_output(self, folder_id: str, filename: str) -> Optional[Dict[str, Any]]:
        return self.backend.get_parsed_output(folder_id, filename)
