"""ADE (Advanced Document Extraction) client service."""

import os
import time
from typing import Any, Callable, Dict, List, Optional

from landingai_ade import LandingAIADE

# Always use Parse Jobs to avoid the 100-page limit of the standard API.
# Parse Jobs supports up to 6,000 pages / 1 GB and works for all document sizes.


class AdeClientService:
    """Service for managing ADE client initialization and document processing."""

    def __init__(self, test_mode: bool = False):
        self._client: Optional[LandingAIADE] = None
        self.test_mode = test_mode

    def get_client(self) -> LandingAIADE:
        """
        Get or create an ADE client instance.
        Uses VISION_AGENT_API_KEY or ADE_API_KEY from environment.

        Returns:
            An initialized LandingAIADE client

        Raises:
            ValueError: If neither API key is configured
        """
        if self._client is not None:
            return self._client

        # Support both old and new API key env vars for backwards compatibility
        api_key = os.environ.get("ADE_API_KEY") or os.environ.get(
            "VISION_AGENT_API_KEY"
        )
        if not api_key:
            raise ValueError(
                "ADE_API_KEY or VISION_AGENT_API_KEY environment variable is required"
            )

        self._client = LandingAIADE(
            apikey=api_key,
            # Configure retries and timeout for long documents
            max_retries=3,
            timeout=300.0,  # 5 minutes for large documents
        )
        return self._client

    def create_parse_job(
        self, file_content: bytes, model: str = "dpt-2-latest"
    ) -> str:
        """
        Create an async parse job for large documents.

        Args:
            file_content: The PDF file bytes
            model: The parsing model to use

        Returns:
            The job_id for tracking the parse job
        """
        client = self.get_client()
        job = client.parse_jobs.create(document=file_content, model=model)
        return job.job_id

    def get_parse_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of a parse job.

        Args:
            job_id: The parse job ID

        Returns:
            Dictionary with status, progress (0-1), and data (if completed)
        """
        client = self.get_client()
        response = client.parse_jobs.get(job_id)

        result = {
            "job_id": job_id,
            "status": response.status,
            "progress": getattr(response, "progress", 0) or 0,
        }

        # Include parsed data if completed
        if response.status == "completed":
            # For results < 1MB, data is in response.data
            if hasattr(response, "data") and response.data:
                result["data"] = {
                    "markdown": response.data.markdown,
                    "chunks": response.data.chunks,
                }
            # For results >= 1MB, need to fetch from output_url
            elif hasattr(response, "output_url") and response.output_url:
                import requests
                output_response = requests.get(response.output_url)
                output_response.raise_for_status()
                output_data = output_response.json()
                result["data"] = {
                    "markdown": output_data.get("markdown", ""),
                    "chunks": output_data.get("chunks", []),
                }

        # Include failure info if failed
        if response.status == "failed":
            result["error"] = getattr(response, "failure_reason", "Unknown error")

        # Include partial failure info (some pages failed but job completed)
        if hasattr(response, "metadata") and response.metadata:
            meta = response.metadata
            if hasattr(meta, "failed_pages") and meta.failed_pages:
                result["failed_pages"] = meta.failed_pages
                result["failure_reason"] = getattr(meta, "failure_reason", None)

        return result

    def wait_for_parse_job(
        self,
        job_id: str,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Wait for a parse job to complete, with optional progress callbacks.

        Args:
            job_id: The parse job ID
            poll_interval: Seconds between status checks (defaults to 5s, or 0.1s in test mode)
            timeout: Maximum seconds to wait (defaults to 600s, or 10s in test mode)
            progress_callback: Optional callback(progress, message) for updates

        Returns:
            Dictionary with parsed markdown and chunks

        Raises:
            TimeoutError: If job doesn't complete within timeout
            RuntimeError: If job fails
        """
        # Use shorter intervals/timeouts in test mode
        if poll_interval is None:
            poll_interval = 0.1 if self.test_mode else 5.0
        if timeout is None:
            timeout = 10.0 if self.test_mode else 600.0
        
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"Parse job {job_id} timed out after {timeout} seconds"
                )

            status = self.get_parse_job_status(job_id)

            if progress_callback:
                progress_pct = status["progress"] * 100
                progress_callback(
                    progress_pct,
                    "Processing document pages..."
                )

            if status["status"] == "completed":
                if "data" not in status:
                    raise RuntimeError(f"Parse job {job_id} completed but no data returned")
                return status["data"]

            if status["status"] == "failed":
                error_msg = status.get("error", "Unknown error")
                raise RuntimeError(f"Parse job {job_id} failed: {error_msg}")

            time.sleep(poll_interval)

    @staticmethod
    def pydantic_to_json_schema(model: type) -> dict:
        """
        Convert a Pydantic model to JSON schema for ADE extraction.

        Args:
            model: The Pydantic model class

        Returns:
            JSON schema dictionary
        """
        return model.model_json_schema()

    @staticmethod
    def normalize_extraction_response(extraction_data: dict) -> dict:
        """
        Process extraction response from ADE and handle wrapper structures.

        Some ADE responses wrap the extraction in an 'extraction' key.
        This normalizes the response to the actual extraction data.

        Args:
            extraction_data: The raw extraction response

        Returns:
            The normalized extraction data
        """
        # Check if wrapped in 'extraction' key
        if "extraction" in extraction_data:
            return extraction_data["extraction"]
        return extraction_data

    @staticmethod
    def extract_response_data(response: Any) -> Dict[str, Any]:
        """
        Extract structured data from ADE response object.

        Handles different response formats (object, dict, etc).

        Args:
            response: The ADE response object

        Returns:
            Dictionary with extraction data
        """
        if hasattr(response, "extraction"):
            extraction_data = response.extraction
        elif hasattr(response, "to_dict"):
            extraction_data = response.to_dict()
        else:
            extraction_data = dict(response)

        return AdeClientService.normalize_extraction_response(extraction_data)

    @staticmethod
    def serialize_chunks(parse_response: Any) -> List[Dict[str, Any]]:
        """
        Convert chunks from parse response to serializable format for caching.

        The new ADE API uses: id (not chunk_id), type, grounding.box, grounding.page

        Args:
            parse_response: The ADE parse response

        Returns:
            List of serialized chunk dictionaries
        """
        chunks_data = []

        if not parse_response.chunks:
            return chunks_data

        for chunk in parse_response.chunks:
            chunk_dict = {}

            # Markdown content
            if hasattr(chunk, "markdown"):
                chunk_dict["markdown"] = chunk.markdown

            # ID (new API uses 'id', old uses 'chunk_id')
            if hasattr(chunk, "id"):
                chunk_dict["id"] = chunk.id
            elif hasattr(chunk, "chunk_id"):
                chunk_dict["id"] = chunk.chunk_id

            # Chunk type (text, table, etc.)
            if hasattr(chunk, "type"):
                chunk_dict["type"] = chunk.type

            # Grounding information (bounding box + page)
            if hasattr(chunk, "grounding") and chunk.grounding:
                grounding = chunk.grounding
                grounding_dict = {}

                # Page number from grounding
                if hasattr(grounding, "page"):
                    grounding_dict["page"] = grounding.page
                    chunk_dict["page_number"] = (
                        grounding.page
                    )  # Keep for backwards compatibility

                # Bounding box coordinates
                if hasattr(grounding, "box") and grounding.box:
                    box = grounding.box
                    grounding_dict["box"] = {
                        "left": getattr(box, "left", None) or getattr(box, "l", None),
                        "top": getattr(box, "top", None) or getattr(box, "t", None),
                        "right": getattr(box, "right", None) or getattr(box, "r", None),
                        "bottom": getattr(box, "bottom", None)
                        or getattr(box, "b", None),
                    }

                chunk_dict["grounding"] = grounding_dict
            elif hasattr(chunk, "page_number"):
                # Fallback for legacy API
                chunk_dict["page_number"] = chunk.page_number

            chunks_data.append(chunk_dict)

        return chunks_data


# Global ADE client service instance
_ade_service = AdeClientService(test_mode=False)


def get_ade_service(test_mode: bool = False) -> AdeClientService:
    """Get the global ADE client service instance.
    
    Args:
        test_mode: If True, use test mode with shorter timeouts and poll intervals
    
    Returns:
        The ADE service instance, optionally configured for testing
    """
    global _ade_service
    if test_mode:
        _ade_service.test_mode = True
    return _ade_service
