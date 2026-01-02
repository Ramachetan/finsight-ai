"""Document extraction service for parsing and data extraction."""

import json
from typing import Any, Callable, Dict, List, Optional

from app.models.transaction import BankStatementFieldExtractionSchema, Transaction
from app.services.ade import AdeClientService
from app.services.storage import StorageService


class ExtractionService:
    """Service for document parsing and structured data extraction."""

    def __init__(self, ade_service: AdeClientService, storage_service: StorageService):
        self.ade_service = ade_service
        self.storage_service = storage_service

    def parse_document(
        self,
        file_content: bytes,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Parse a PDF document and extract markdown + chunks.

        Always uses Parse Jobs API which supports up to 6,000 pages / 1 GB.
        This avoids the 100-page limit of the standard parsing API.

        Args:
            file_content: The PDF file as bytes
            filename: Name of the file for logging
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            Dictionary with 'markdown' and 'chunks' keys
        """
        file_size_mb = len(file_content) / (1024 * 1024)
        
        # Always use Parse Jobs to support up to 6,000 pages / 1 GB
        # Standard parse is limited to 100 pages
        print(f"Parsing document with Parse Jobs: {filename} ({file_size_mb:.1f} MB)")
        if progress_callback:
            progress_callback(5, "Starting async parse job...")

        # Create parse job
        job_id = self.ade_service.create_parse_job(file_content)
        print(f"Created parse job: {job_id}")

        if progress_callback:
            progress_callback(10, f"Parse job created: {job_id}")

        # Wait for completion with progress updates
        raw_data = self.ade_service.wait_for_parse_job(
            job_id,
            progress_callback=progress_callback,
        )

        # Get markdown content
        markdown_content = raw_data.get("markdown", "")
        if not markdown_content:
            raise ValueError("No markdown content returned from parsing")

        # Serialize chunks for caching (handles both response objects and dicts)
        chunks = raw_data.get("chunks", [])
        if chunks and hasattr(chunks[0], "markdown"):
            # Response objects - need to serialize using ADE service
            # Create a mock response object for serialize_chunks
            class _ParseResponse:
                def __init__(self, chunks_list):
                    self.chunks = chunks_list
            
            response_obj = _ParseResponse(chunks)
            chunks_data = self.ade_service.serialize_chunks(response_obj)
        else:
            # Already serialized dicts
            chunks_data = chunks

        print(f"Parse completed. Chunks: {len(chunks_data)}")

        return {
            "markdown": markdown_content,
            "chunks": chunks_data,
        }

    def extract_transactions_from_parsed(
        self, parsed_data: dict, schema: dict, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Transaction]:
        """
        Extract transactions from parsed markdown data using Pydantic validation.

        Uses the full markdown content for extraction as per LandingAI API documentation.
        This is the correct approach - chunks are for grounding/visualization, not extraction.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            List of Transaction objects
        """
        client = self.ade_service.get_client()
        markdown_content = parsed_data.get("markdown", "")

        if not markdown_content:
            raise ValueError("No markdown content available for extraction")

        if progress_callback:
            progress_callback(40, "Extracting transactions from document...")

        print(f"Extracting from full markdown ({len(markdown_content)} chars)")

        # Single extraction call with full markdown (correct approach per API docs)
        extract_response = client.extract(
            markdown=markdown_content,
            schema=json.dumps(schema),
            model="extract-latest",
        )

        if progress_callback:
            progress_callback(75, "Processing extraction results...")

        extraction_data = AdeClientService.extract_response_data(extract_response)
        extraction = BankStatementFieldExtractionSchema(**extraction_data)

        print(f"Extracted {len(extraction.transactions)} transactions")

        return extraction.transactions

    def extract_transactions_as_dicts(
        self, parsed_data: dict, schema: dict, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract transactions from parsed markdown as raw dictionaries.

        This is used for dynamic CSV generation with custom schemas,
        without Pydantic validation to preserve user-defined fields.
        Uses the full markdown content for extraction.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction
            progress_callback: Optional callback(progress_pct, message) for updates

        Returns:
            List of transaction dictionaries
        """
        client = self.ade_service.get_client()
        markdown_content = parsed_data.get("markdown", "")

        if not markdown_content:
            raise ValueError("No markdown content available for extraction")

        if progress_callback:
            progress_callback(40, "Extracting data from document...")

        print(f"Extracting from full markdown with custom schema ({len(markdown_content)} chars)")

        # Single extraction call with full markdown
        extract_response = client.extract(
            markdown=markdown_content,
            schema=json.dumps(schema),
            model="extract-latest",
        )

        if progress_callback:
            progress_callback(75, "Processing extraction results...")

        extraction_data = AdeClientService.extract_response_data(extract_response)
        txns = extraction_data.get("transactions", [])

        if isinstance(txns, list):
            print(f"Extracted {len(txns)} transactions (dynamic schema)")
            return txns

        return []
