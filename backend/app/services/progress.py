"""Progress tracking service for document processing."""

from typing import Dict, Optional


class ProgressTracker:
    """
    In-memory progress tracker for document processing operations.

    Tracks the processing phase, message, and progress percentage for each file.
    """

    def __init__(self):
        # {folder_id/filename: {"phase": str, "message": str, "progress": int}}
        self._progress: Dict[str, dict] = {}

    def _get_key(self, folder_id: str, filename: str) -> str:
        """Generate a unique key for tracking progress of a specific file."""
        return f"{folder_id}/{filename}"

    def update(
        self, folder_id: str, filename: str, phase: str, message: str, progress: int = 0
    ) -> None:
        """
        Update progress tracking for a file being processed.

        Args:
            folder_id: The folder ID
            filename: The filename being processed
            phase: The current processing phase (e.g., "Parsing", "Extracting")
            message: A descriptive message about the current step
            progress: Progress percentage (0-100, automatically capped)
        """
        key = self._get_key(folder_id, filename)
        self._progress[key] = {
            "phase": phase,
            "message": message,
            "progress": min(progress, 100),
        }

    def get(self, folder_id: str, filename: str) -> Optional[Dict[str, any]]:
        """
        Get the current progress for a file.

        Args:
            folder_id: The folder ID
            filename: The filename

        Returns:
            Progress dict with phase, message, and progress, or None if not tracking
        """
        key = self._get_key(folder_id, filename)
        return self._progress.get(key)

    def clear(self, folder_id: str, filename: str) -> None:
        """
        Clear progress tracking after processing completes.

        Args:
            folder_id: The folder ID
            filename: The filename
        """
        key = self._get_key(folder_id, filename)
        self._progress.pop(key, None)


# Global progress tracker instance
_progress_tracker = ProgressTracker()


def get_progress_tracker() -> ProgressTracker:
    """Get the global progress tracker instance."""
    return _progress_tracker
