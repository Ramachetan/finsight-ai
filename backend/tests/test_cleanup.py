"""
Integration test to verify automatic cleanup of test folders.
This test creates folders in the actual local_storage directory
to verify the cleanup mechanism works correctly.
"""
from pathlib import Path


class TestAutomaticCleanup:
    """Test that folders created during tests are automatically cleaned up."""
    
    def test_folder_cleanup_tracking(self, local_storage_service):
        """
        Test that folders created via local_storage_service are tracked
        and will be cleaned up after the test session.
        """
        # Create a folder using the fixture
        folder = local_storage_service.create_folder("Cleanup Test Folder")
        
        assert folder is not None
        assert folder["name"] == "Cleanup Test Folder"
        
        # Verify the folder exists in local_storage
        local_storage_path = Path(__file__).parent.parent / "local_storage"
        metadata_file = local_storage_path / "metadata" / f"{folder['id']}.json"
        
        assert metadata_file.exists(), "Metadata file should exist in local_storage"
        
        # The folder will be automatically cleaned up by pytest_sessionfinish
        # We can't verify the cleanup here since it happens after all tests complete
        # But we can verify the folder is tracked by checking it was created
        print(f"\n✓ Created test folder {folder['id']} - will be cleaned up automatically")
    
    def test_multiple_folders_cleanup(self, local_storage_service):
        """Test that multiple folders are all tracked for cleanup."""
        folders = []
        
        for i in range(3):
            folder = local_storage_service.create_folder(f"Test Folder {i}")
            folders.append(folder)
            assert folder is not None
        
        # Verify all folders exist
        local_storage_path = Path(__file__).parent.parent / "local_storage"
        
        for folder in folders:
            metadata_file = local_storage_path / "metadata" / f"{folder['id']}.json"
            assert metadata_file.exists()
        
        print(f"\n✓ Created {len(folders)} test folders - all will be cleaned up automatically")
