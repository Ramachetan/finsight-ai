from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestFoldersEndpoints:
    """Test suite for folder management endpoints."""
    
    @patch('app.routers.folders.storage_service.create_folder')
    def test_create_folder_success(self, mock_create, client):
        """Test successful folder creation."""
        mock_create.return_value = {
            "id": "test-folder-id",
            "name": "Test Folder",
            "status": "EMPTY"
        }
        
        response = client.post("/api/folders/", json={"name": "Test Folder"})
        
        assert response.status_code == 200
        assert response.json()["name"] == "Test Folder"
        assert response.json()["status"] == "EMPTY"
        mock_create.assert_called_once_with("Test Folder")
    
    @patch('app.routers.folders.storage_service.create_folder')
    def test_create_folder_failure(self, mock_create, client):
        """Test folder creation failure."""
        mock_create.return_value = None
        
        response = client.post("/api/folders/", json={"name": "Test Folder"})
        
        assert response.status_code == 500
        assert "Failed to create folder" in response.json()["detail"]
    
    @patch('app.routers.folders.storage_service.list_folders')
    def test_get_folders(self, mock_list, client):
        """Test listing all folders."""
        mock_list.return_value = [
            {"id": "folder1", "name": "Folder 1", "status": "EMPTY"},
            {"id": "folder2", "name": "Folder 2", "status": "HAS_FILES"}
        ]
        
        response = client.get("/api/folders/")
        
        assert response.status_code == 200
        assert len(response.json()) == 2
        assert response.json()[0]["name"] == "Folder 1"
        mock_list.assert_called_once()
    
    @patch('app.routers.folders.storage_service.get_folder')
    @patch('app.routers.folders.storage_service.list_files')
    def test_get_folder_details(self, mock_list_files, mock_get, client):
        """Test getting folder details."""
        mock_get.return_value = {
            "id": "folder1",
            "name": "Test Folder",
            "status": "HAS_FILES"
        }
        mock_list_files.return_value = ["file1.pdf", "file2.pdf"]
        
        response = client.get("/api/folders/folder1")
        
        assert response.status_code == 200
        assert response.json()["id"] == "folder1"
        assert len(response.json()["files"]) == 2
        assert "file1.pdf" in response.json()["files"]
    
    @patch('app.routers.folders.storage_service.get_folder')
    def test_get_folder_not_found(self, mock_get, client):
        """Test getting non-existent folder."""
        mock_get.return_value = None
        
        response = client.get("/api/folders/nonexistent")
        
        assert response.status_code == 404
        assert "Folder not found" in response.json()["detail"]
    
    @patch('app.routers.folders.storage_service.folder_exists')
    @patch('app.routers.folders.storage_service.delete_folder')
    def test_delete_folder_success(self, mock_delete, mock_exists, client):
        """Test successful folder deletion."""
        mock_exists.return_value = True
        
        response = client.delete("/api/folders/folder1")
        
        assert response.status_code == 204
        mock_delete.assert_called_once_with("folder1")
    
    @patch('app.routers.folders.storage_service.folder_exists')
    def test_delete_folder_not_found(self, mock_exists, client):
        """Test deleting non-existent folder."""
        mock_exists.return_value = False
        
        response = client.delete("/api/folders/nonexistent")
        
        assert response.status_code == 404
        assert "Folder not found" in response.json()["detail"]
    
    @patch('app.routers.folders.storage_service.folder_exists')
    @patch('app.routers.folders.storage_service.upload_file')
    def test_upload_files_success(self, mock_upload, mock_exists, client):
        """Test successful file upload."""
        mock_exists.return_value = True
        mock_upload.return_value = "file.pdf"
        
        response = client.post(
            "/api/folders/folder1/upload",
            files={"files": ("test.pdf", b"fake pdf content", "application/pdf")}
        )
        
        assert response.status_code == 200
        assert "files" in response.json()
        assert "test.pdf" in response.json()["files"]
    
    @patch('app.routers.folders.storage_service.folder_exists')
    def test_upload_files_folder_not_found(self, mock_exists, client):
        """Test file upload to non-existent folder."""
        mock_exists.return_value = False
        
        response = client.post(
            "/api/folders/nonexistent/upload",
            files={"files": ("test.pdf", b"fake pdf content", "application/pdf")}
        )
        
        assert response.status_code == 404
        assert "Folder not found" in response.json()["detail"]
    
    @patch('app.routers.folders.storage_service.folder_exists')
    @patch('app.routers.folders.storage_service.upload_file')
    def test_upload_multiple_files(self, mock_upload, mock_exists, client):
        """Test uploading multiple files."""
        mock_exists.return_value = True
        mock_upload.return_value = "file.pdf"
        
        response = client.post(
            "/api/folders/folder1/upload",
            files=[
                ("files", ("test1.pdf", b"content1", "application/pdf")),
                ("files", ("test2.pdf", b"content2", "application/pdf"))
            ]
        )
        
        assert response.status_code == 200
        assert len(response.json()["files"]) == 2
    
    @patch('app.routers.folders.storage_service.folder_exists')
    @patch('app.routers.folders.storage_service.list_files')
    @patch('app.routers.folders.storage_service.delete_file')
    def test_delete_file_success(self, mock_delete, mock_list, mock_exists, client):
        """Test successful file deletion."""
        mock_exists.return_value = True
        mock_list.return_value = ["test.pdf", "other.pdf"]
        mock_delete.return_value = True
        
        response = client.delete("/api/folders/folder1/files/test.pdf")
        
        assert response.status_code == 204
        mock_delete.assert_called_once_with("folder1", "test.pdf")
    
    @patch('app.routers.folders.storage_service.folder_exists')
    def test_delete_file_folder_not_found(self, mock_exists, client):
        """Test deleting file from non-existent folder."""
        mock_exists.return_value = False
        
        response = client.delete("/api/folders/nonexistent/files/test.pdf")
        
        assert response.status_code == 404
        assert "Folder not found" in response.json()["detail"]
    
    @patch('app.routers.folders.storage_service.folder_exists')
    @patch('app.routers.folders.storage_service.list_files')
    def test_delete_file_not_found(self, mock_list, mock_exists, client):
        """Test deleting non-existent file."""
        mock_exists.return_value = True
        mock_list.return_value = ["other.pdf"]
        
        response = client.delete("/api/folders/folder1/files/nonexistent.pdf")
        
        assert response.status_code == 404
        assert "File not found" in response.json()["detail"]
    
    @patch('app.routers.folders.storage_service.folder_exists')
    @patch('app.routers.folders.storage_service.list_files')
    @patch('app.routers.folders.storage_service.delete_file')
    def test_delete_file_failure(self, mock_delete, mock_list, mock_exists, client):
        """Test file deletion failure."""
        mock_exists.return_value = True
        mock_list.return_value = ["test.pdf"]
        mock_delete.return_value = False
        
        response = client.delete("/api/folders/folder1/files/test.pdf")
        
        assert response.status_code == 500
        assert "Failed to delete file" in response.json()["detail"]
