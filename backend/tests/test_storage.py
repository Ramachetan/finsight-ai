import os
import tempfile
from unittest.mock import MagicMock

import pytest
from app.services.storage import LocalBackend, StorageService

# Import the global tracking set from conftest
from tests.conftest import _test_folder_ids


class TestLocalBackend:
    """Test suite for LocalBackend storage implementation."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp = tempfile.mkdtemp()
        yield temp
        # Cleanup
        import shutil

        if os.path.exists(temp):
            shutil.rmtree(temp)

    @pytest.fixture
    def backend(self, temp_dir, monkeypatch):
        """Create a LocalBackend instance with folder tracking."""
        monkeypatch.setenv("LOCAL_STORAGE_PATH", temp_dir)
        backend_instance = LocalBackend()

        # Wrap create_folder to track test folder IDs
        original_create_folder = backend_instance.create_folder

        def tracked_create_folder(*args, **kwargs):
            folder = original_create_folder(*args, **kwargs)
            if folder:
                _test_folder_ids.add(folder["id"])
            return folder

        backend_instance.create_folder = tracked_create_folder

        return backend_instance

    def test_create_folder(self, backend):
        """Test folder creation."""
        result = backend.create_folder("Test Folder")

        assert result is not None
        assert result["name"] == "Test Folder"
        assert result["status"] == "EMPTY"
        assert "id" in result

    def test_folder_exists_true(self, backend):
        """Test checking if folder exists when it does."""
        folder = backend.create_folder("Test Folder")

        assert backend.folder_exists(folder["id"]) is True

    def test_folder_exists_false(self, backend):
        """Test checking if folder exists when it doesn't."""
        assert backend.folder_exists("nonexistent-id") is False

    def test_list_folders(self, backend):
        """Test listing all folders."""
        backend.create_folder("Folder 1")
        backend.create_folder("Folder 2")

        folders = backend.list_folders()

        assert len(folders) >= 2
        assert any(f["name"] == "Folder 1" for f in folders)
        assert any(f["name"] == "Folder 2" for f in folders)

    def test_get_folder(self, backend):
        """Test getting folder details."""
        created = backend.create_folder("Test Folder")
        retrieved = backend.get_folder(created["id"])

        assert retrieved is not None
        assert retrieved["id"] == created["id"]
        assert retrieved["name"] == "Test Folder"

    def test_get_folder_not_found(self, backend):
        """Test getting non-existent folder."""
        result = backend.get_folder("nonexistent-id")

        assert result is None

    def test_upload_file(self, backend, temp_dir):
        """Test file upload."""
        folder = backend.create_folder("Test Folder")
        test_content = b"test file content"

        from io import BytesIO

        file_obj = BytesIO(test_content)

        result = backend.upload_file(folder["id"], "test.pdf", file_obj)

        # Result is full path, so just check it contains the filename
        assert "test.pdf" in result
        assert backend.folder_exists(folder["id"])

    def test_list_files(self, backend):
        """Test listing files in a folder."""
        folder = backend.create_folder("Test Folder")

        from io import BytesIO

        backend.upload_file(folder["id"], "file1.pdf", BytesIO(b"content1"))
        backend.upload_file(folder["id"], "file2.pdf", BytesIO(b"content2"))

        files = backend.list_files(folder["id"])

        assert len(files) == 2
        assert "file1.pdf" in files
        assert "file2.pdf" in files

    def test_read_file_content(self, backend):
        """Test reading file content."""
        folder = backend.create_folder("Test Folder")
        test_content = b"test file content"

        from io import BytesIO

        backend.upload_file(folder["id"], "test.pdf", BytesIO(test_content))

        content = backend.read_file_content(folder["id"], "test.pdf")

        assert content == test_content

    def test_read_file_content_not_found(self, backend):
        """Test reading non-existent file."""
        folder = backend.create_folder("Test Folder")

        with pytest.raises(Exception):
            backend.read_file_content(folder["id"], "nonexistent.pdf")

    def test_save_processed_file(self, backend):
        """Test saving processed file."""
        folder = backend.create_folder("Test Folder")
        csv_content = "Date,Amount\n2024-01-01,1000.00\n"

        result = backend.save_processed_file(folder["id"], "result.csv", csv_content)

        # Result is full path, so just check it contains the filename
        assert "result.csv" in result

    def test_get_processed_file_content(self, backend):
        """Test retrieving processed file content."""
        folder = backend.create_folder("Test Folder")
        csv_content = "Date,Amount\n2024-01-01,1000.00\n"

        backend.save_processed_file(folder["id"], "result.csv", csv_content)
        retrieved = backend.get_processed_file_content(folder["id"], "result.csv")

        assert retrieved == csv_content

    def test_delete_folder(self, backend):
        """Test folder deletion."""
        folder = backend.create_folder("Test Folder")
        folder_id = folder["id"]

        assert backend.folder_exists(folder_id) is True

        backend.delete_folder(folder_id)

        assert backend.folder_exists(folder_id) is False

    def test_delete_folder_with_files(self, backend):
        """Test deleting folder with files."""
        folder = backend.create_folder("Test Folder")

        from io import BytesIO

        backend.upload_file(folder["id"], "file1.pdf", BytesIO(b"content"))

        folder_id = folder["id"]
        backend.delete_folder(folder_id)

        assert backend.folder_exists(folder_id) is False

    def test_delete_file(self, backend):
        """Test deleting a single file."""
        folder = backend.create_folder("Test Folder")

        from io import BytesIO

        backend.upload_file(folder["id"], "file1.pdf", BytesIO(b"content1"))
        backend.upload_file(folder["id"], "file2.pdf", BytesIO(b"content2"))

        # Verify both files exist
        files = backend.list_files(folder["id"])
        assert len(files) == 2

        # Delete one file
        result = backend.delete_file(folder["id"], "file1.pdf")
        assert result is True

        # Verify only one file remains
        files = backend.list_files(folder["id"])
        assert len(files) == 1
        assert "file2.pdf" in files
        assert "file1.pdf" not in files

    def test_delete_file_with_processed_csv(self, backend):
        """Test deleting a file also deletes its processed CSV."""
        folder = backend.create_folder("Test Folder")

        from io import BytesIO

        backend.upload_file(folder["id"], "test.pdf", BytesIO(b"content"))
        backend.save_processed_file(folder["id"], "test.pdf.csv", "Date,Amount\n")

        # Delete the file
        result = backend.delete_file(folder["id"], "test.pdf")
        assert result is True

        # Verify file is deleted
        files = backend.list_files(folder["id"])
        assert len(files) == 0

        # Verify processed CSV is also deleted
        with pytest.raises(Exception):
            backend.get_processed_file_content(folder["id"], "test.pdf.csv")

    def test_delete_file_updates_folder_status(self, backend):
        """Test that deleting last file updates folder status to EMPTY."""
        folder = backend.create_folder("Test Folder")

        from io import BytesIO

        backend.upload_file(folder["id"], "file1.pdf", BytesIO(b"content"))

        # Verify folder has files
        folder_info = backend.get_folder(folder["id"])
        assert folder_info["status"] == "HAS_FILES"

        # Delete the file
        backend.delete_file(folder["id"], "file1.pdf")

        # Verify folder status is now EMPTY
        folder_info = backend.get_folder(folder["id"])
        assert folder_info["status"] == "EMPTY"


class TestStorageService:
    """Test suite for StorageService wrapper."""

    @pytest.fixture
    def service(self):
        """Create a StorageService with mocked backend."""
        service = StorageService()
        service.backend = MagicMock()
        return service

    def test_create_folder_delegates_to_backend(self, service):
        """Test that create_folder delegates to backend."""
        service.backend.create_folder.return_value = {
            "id": "test-id",
            "name": "Test",
            "status": "EMPTY",
        }

        result = service.create_folder("Test")

        assert result["name"] == "Test"
        service.backend.create_folder.assert_called_once_with("Test")

    def test_list_folders_delegates_to_backend(self, service):
        """Test that list_folders delegates to backend."""
        service.backend.list_folders.return_value = [
            {"id": "test-id", "name": "Test", "status": "EMPTY"}
        ]

        result = service.list_folders()

        assert len(result) == 1
        service.backend.list_folders.assert_called_once()


class TestSchemaStorage:
    """Test suite for schema storage functionality in LocalBackend."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp = tempfile.mkdtemp()
        yield temp
        import shutil

        if os.path.exists(temp):
            shutil.rmtree(temp)

    @pytest.fixture
    def backend(self, temp_dir, monkeypatch):
        """Create a LocalBackend instance for testing."""
        monkeypatch.setenv("LOCAL_STORAGE_PATH", temp_dir)
        backend_instance = LocalBackend()

        # Wrap create_folder to track test folder IDs
        original_create_folder = backend_instance.create_folder

        def tracked_create_folder(*args, **kwargs):
            folder = original_create_folder(*args, **kwargs)
            if folder:
                _test_folder_ids.add(folder["id"])
            return folder

        backend_instance.create_folder = tracked_create_folder

        return backend_instance

    def test_save_extraction_schema(self, backend):
        """Test saving a custom extraction schema."""
        folder = backend.create_folder("Test Folder")
        schema = {"type": "object", "properties": {"transactions": {"type": "array"}}}

        result = backend.save_extraction_schema(folder["id"], "test.pdf", schema)

        assert "test.pdf.json" in result
        # Verify file was created
        assert backend.get_extraction_schema(folder["id"], "test.pdf") == schema

    def test_get_extraction_schema_exists(self, backend):
        """Test retrieving an existing custom schema."""
        folder = backend.create_folder("Test Folder")
        schema = {"type": "object", "properties": {"custom_field": {"type": "string"}}}

        backend.save_extraction_schema(folder["id"], "test.pdf", schema)

        result = backend.get_extraction_schema(folder["id"], "test.pdf")

        assert result is not None
        assert result == schema

    def test_get_extraction_schema_not_found(self, backend):
        """Test retrieving schema when none exists."""
        folder = backend.create_folder("Test Folder")

        result = backend.get_extraction_schema(folder["id"], "nonexistent.pdf")

        assert result is None

    def test_delete_extraction_schema_exists(self, backend):
        """Test deleting an existing custom schema."""
        folder = backend.create_folder("Test Folder")
        schema = {"type": "object"}
        backend.save_extraction_schema(folder["id"], "test.pdf", schema)

        # Verify schema exists
        assert backend.get_extraction_schema(folder["id"], "test.pdf") is not None

        # Delete it
        result = backend.delete_extraction_schema(folder["id"], "test.pdf")

        assert result is True
        # Verify it's gone
        assert backend.get_extraction_schema(folder["id"], "test.pdf") is None

    def test_delete_extraction_schema_not_found(self, backend):
        """Test deleting schema when none exists."""
        folder = backend.create_folder("Test Folder")

        result = backend.delete_extraction_schema(folder["id"], "nonexistent.pdf")

        assert result is False

    def test_schema_unicode_content(self, backend):
        """Test saving schema with unicode content."""
        folder = backend.create_folder("Test Folder")
        schema = {"type": "object", "description": "Schema with unicode: 日本語 🎉"}

        backend.save_extraction_schema(folder["id"], "test.pdf", schema)

        result = backend.get_extraction_schema(folder["id"], "test.pdf")
        assert result["description"] == "Schema with unicode: 日本語 🎉"

    def test_multiple_schemas_per_folder(self, backend):
        """Test storing different schemas for different files in same folder."""
        folder = backend.create_folder("Test Folder")

        schema1 = {"type": "object", "properties": {"field1": {"type": "string"}}}
        schema2 = {"type": "object", "properties": {"field2": {"type": "number"}}}

        backend.save_extraction_schema(folder["id"], "file1.pdf", schema1)
        backend.save_extraction_schema(folder["id"], "file2.pdf", schema2)

        assert backend.get_extraction_schema(folder["id"], "file1.pdf") == schema1
        assert backend.get_extraction_schema(folder["id"], "file2.pdf") == schema2
