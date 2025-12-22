"""ADE (Advanced Document Extraction) client service."""

import os
from typing import Any, Dict, List, Optional

from ade import Ade


class AdeClientService:
    """Service for managing ADE client initialization and document processing."""

    def __init__(self):
        self._client: Optional[Ade] = None

    def get_client(self) -> Ade:
        """
        Get or create an ADE client instance.
        Uses VISION_AGENT_API_KEY or ADE_API_KEY from environment.

        Returns:
            An initialized Ade client

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

        self._client = Ade(
            apikey=api_key,
            # Configure retries and timeout for long documents
            max_retries=3,
            timeout=300.0,  # 5 minutes for large documents
        )
        return self._client

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
_ade_service = AdeClientService()


def get_ade_service() -> AdeClientService:
    """Get the global ADE client service instance."""
    return _ade_service
