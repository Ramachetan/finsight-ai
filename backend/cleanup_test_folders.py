#!/usr/bin/env python3
"""
Cleanup script for removing test-created folders from local_storage.

This script can be run manually to clean up test artifacts:
    python cleanup_test_folders.py

Or to preview what would be deleted without actually deleting:
    python cleanup_test_folders.py --dry-run
"""

import shutil
from pathlib import Path


def cleanup_local_storage(dry_run: bool = False):
    """
    Remove all test-created folders from local_storage directory.
    
    Args:
        dry_run: If True, only print what would be deleted without actually deleting
    """
    # Path to local_storage directory
    local_storage_path = Path(__file__).parent / "local_storage"
    
    if not local_storage_path.exists():
        print("ℹ️  No local_storage directory found. Nothing to clean up.")
        return
    
    action = "Would remove" if dry_run else "Removing"
    print(f"\n🧹 {action} test folders from local_storage...")
    
    total_removed = 0
    
    # Clean up metadata files
    metadata_dir = local_storage_path / "metadata"
    if metadata_dir.exists():
        metadata_files = list(metadata_dir.glob("*.json"))
        if metadata_files:
            print(f"\n📄 Metadata files ({len(metadata_files)}):")
            for metadata_file in metadata_files:
                try:
                    if not dry_run:
                        metadata_file.unlink()
                    print(f"  ✓ {action}: {metadata_file.name}")
                    total_removed += 1
                except Exception as e:
                    print(f"  ✗ Failed to remove {metadata_file.name}: {e}")
    
    # Clean up uploads directories
    uploads_dir = local_storage_path / "uploads"
    if uploads_dir.exists():
        upload_folders = [d for d in uploads_dir.iterdir() if d.is_dir()]
        if upload_folders:
            print(f"\n📤 Upload folders ({len(upload_folders)}):")
            for folder_dir in upload_folders:
                try:
                    if not dry_run:
                        shutil.rmtree(folder_dir)
                    file_count = len(list(folder_dir.rglob("*"))) if folder_dir.exists() else 0
                    print(f"  ✓ {action}: {folder_dir.name} ({file_count} files)")
                    total_removed += 1
                except Exception as e:
                    print(f"  ✗ Failed to remove {folder_dir.name}: {e}")
    
    # Clean up processed directories
    processed_dir = local_storage_path / "processed"
    if processed_dir.exists():
        processed_folders = [d for d in processed_dir.iterdir() if d.is_dir()]
        if processed_folders:
            print(f"\n📊 Processed folders ({len(processed_folders)}):")
            for folder_dir in processed_folders:
                try:
                    if not dry_run:
                        shutil.rmtree(folder_dir)
                    file_count = len(list(folder_dir.rglob("*"))) if folder_dir.exists() else 0
                    print(f"  ✓ {action}: {folder_dir.name} ({file_count} files)")
                    total_removed += 1
                except Exception as e:
                    print(f"  ✗ Failed to remove {folder_dir.name}: {e}")
    
    if total_removed == 0:
        print("\nℹ️  No test folders found to clean up.")
    else:
        status = "would be" if dry_run else "were"
        print(f"\n✅ {total_removed} items {status} removed!\n")
        if dry_run:
            print("💡 Run without --dry-run to actually delete these files.\n")


def main():
    """Main entry point for the cleanup script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Clean up test-created folders from local_storage directory"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )
    
    args = parser.parse_args()
    cleanup_local_storage(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
