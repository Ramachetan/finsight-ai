import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from app.services.ade import get_ade_service
from app.services.storage import StorageService
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="session", autouse=True)
def enable_ade_test_mode():
    """Enable test mode for ADE service to use shorter timeouts during tests."""
    get_ade_service(test_mode=True)

# Global set to track folder IDs created during tests
_test_folder_ids = set()


@pytest.fixture
def temp_local_storage():
    """Create a temporary directory for local storage testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def local_storage_service(monkeypatch):
    """Create a StorageService with LocalBackend for testing using actual local_storage."""
    # Set environment to use local backend with the actual local_storage directory
    monkeypatch.setenv("ENVIRONMENT", "local")
    
    service = StorageService()
    
    # Wrap create_folder to track test folder IDs
    original_create_folder = service.create_folder
    def tracked_create_folder(*args, **kwargs):
        folder = original_create_folder(*args, **kwargs)
        if folder:
            _test_folder_ids.add(folder["id"])
        return folder
    service.create_folder = tracked_create_folder
    
    return service


@pytest.fixture
def sample_folder(local_storage_service):
    """Create a sample folder for testing."""
    folder = local_storage_service.create_folder("Test Folder")
    return folder


@pytest.fixture
def mock_gcs_service(monkeypatch):
    """Mock the GCS backend for testing without GCS credentials."""
    with patch('app.services.storage.storage.Client'):
        service = StorageService()
        service.backend = MagicMock()
        return service


@pytest.fixture
def mock_parse_document():
    """Provide a mock parsed document response for fast testing."""
    return {
        "markdown": "# Bank Statement\n\nDate | Amount | Balance\n2024-01-01 | 1000.00 | 50000.00\n",
        "chunks": [
            {
                "id": "chunk-1",
                "type": "text",
                "markdown": "# Bank Statement\n\nDate | Amount | Balance\n2024-01-01 | 1000.00 | 50000.00\n",
                "page_number": 1,
                "grounding": {"page": 1, "box": {"left": 0, "top": 0, "right": 100, "bottom": 100}},
            }
        ],
    }


def pytest_sessionfinish(session, exitstatus):
    """
    Cleanup hook that runs after all tests complete.
    Only removes folders that were created during this test session.
    """
    import shutil
    from pathlib import Path
    
    if not _test_folder_ids:
        return  # No test folders to clean up
    
    # Path to local_storage directory
    local_storage_path = Path(__file__).parent.parent / "local_storage"
    
    if local_storage_path.exists():
        print(f"\n🧹 Cleaning up {len(_test_folder_ids)} test folders from local_storage...")
        
        removed_count = 0
        
        # Clean up metadata files for tracked folders only
        metadata_dir = local_storage_path / "metadata"
        if metadata_dir.exists():
            for folder_id in _test_folder_ids:
                metadata_file = metadata_dir / f"{folder_id}.json"
                if metadata_file.exists():
                    try:
                        metadata_file.unlink()
                        print(f"  ✓ Removed metadata: {folder_id}.json")
                        removed_count += 1
                    except Exception as e:
                        print(f"  ✗ Failed to remove {folder_id}.json: {e}")
        
        # Clean up uploads directories for tracked folders only
        uploads_dir = local_storage_path / "uploads"
        if uploads_dir.exists():
            for folder_id in _test_folder_ids:
                folder_dir = uploads_dir / folder_id
                if folder_dir.exists() and folder_dir.is_dir():
                    try:
                        shutil.rmtree(folder_dir)
                        print(f"  ✓ Removed uploads folder: {folder_id}")
                        removed_count += 1
                    except Exception as e:
                        print(f"  ✗ Failed to remove uploads {folder_id}: {e}")
        
        # Clean up processed directories for tracked folders only
        processed_dir = local_storage_path / "processed"
        if processed_dir.exists():
            for folder_id in _test_folder_ids:
                folder_dir = processed_dir / folder_id
                if folder_dir.exists() and folder_dir.is_dir():
                    try:
                        shutil.rmtree(folder_dir)
                        print(f"  ✓ Removed processed folder: {folder_id}")
                        removed_count += 1
                    except Exception as e:
                        print(f"  ✗ Failed to remove processed {folder_id}: {e}")
        
        print(f"✅ Cleanup complete! Removed {removed_count} items.\n")
        
        # Clear the tracking set for next test run
        _test_folder_ids.clear()
