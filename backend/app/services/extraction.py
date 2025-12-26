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
        self, parsed_data: dict, schema: dict
    ) -> List[Transaction]:
        """
        Extract transactions from parsed markdown data using Pydantic validation.

        This is used for the default schema extraction with full Pydantic validation.
        Processes chunks individually for long documents to prevent cutoff.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction

        Returns:
            List of Transaction objects
        """
        client = self.ade_service.get_client()
        all_transactions = []
        chunks = parsed_data.get("chunks", [])
        markdown_content = parsed_data.get("markdown", "")

        # Process chunks individually for better handling of long documents
        if chunks and len(chunks) > 0:
            print(f"Processing {len(chunks)} chunks individually")

            for i, chunk in enumerate(chunks):
                chunk_markdown = (
                    chunk.get("markdown")
                    if isinstance(chunk, dict)
                    else getattr(chunk, "markdown", None)
                )
                if not chunk_markdown:
                    continue

                print(f"Extracting from chunk {i + 1}/{len(chunks)}")
                try:
                    extract_response = client.extract(
                        markdown=chunk_markdown,
                        schema=json.dumps(schema),
                        model="extract-latest",
                    )

                    extraction_data = AdeClientService.extract_response_data(
                        extract_response
                    )
                    chunk_extraction = BankStatementFieldExtractionSchema(
                        **extraction_data
                    )
                    all_transactions.extend(chunk_extraction.transactions)
                    print(
                        f"Chunk {i + 1}: Found {len(chunk_extraction.transactions)} transactions"
                    )

                except Exception as e:
                    print(f"Error extracting chunk {i + 1}: {e}")
                    # Continue to next chunk
        else:
            # Fallback to full markdown if no chunks available
            print("No chunks found, extracting from full markdown")
            if not markdown_content:
                raise ValueError("No markdown content available for extraction")

            extract_response = client.extract(
                markdown=markdown_content,
                schema=json.dumps(schema),
                model="extract-latest",
            )

            extraction_data = AdeClientService.extract_response_data(extract_response)
            extraction = BankStatementFieldExtractionSchema(**extraction_data)
            all_transactions = extraction.transactions

        return all_transactions

    def extract_transactions_as_dicts(
        self, parsed_data: dict, schema: dict
    ) -> List[Dict[str, Any]]:
        """
        Extract transactions from parsed markdown as raw dictionaries.

        This is used for dynamic CSV generation with custom schemas,
        without Pydantic validation to preserve user-defined fields.

        Args:
            parsed_data: Dictionary with 'markdown' and 'chunks' keys
            schema: JSON Schema for extraction

        Returns:
            List of transaction dictionaries
        """
        client = self.ade_service.get_client()
        all_transactions = []
        chunks = parsed_data.get("chunks", [])
        markdown_content = parsed_data.get("markdown", "")

        if chunks and len(chunks) > 0:
            print(f"Processing {len(chunks)} chunks individually (dynamic schema)")

            for i, chunk in enumerate(chunks):
                chunk_markdown = (
                    chunk.get("markdown")
                    if isinstance(chunk, dict)
                    else getattr(chunk, "markdown", None)
                )
                if not chunk_markdown:
                    continue

                print(f"Extracting from chunk {i + 1}/{len(chunks)}")
                try:
                    extract_response = client.extract(
                        markdown=chunk_markdown,
                        schema=json.dumps(schema),
                        model="extract-latest",
                    )

                    extraction_data = AdeClientService.extract_response_data(
                        extract_response
                    )
                    txns = extraction_data.get("transactions", [])
                    if isinstance(txns, list):
                        all_transactions.extend(txns)
                    print(f"Chunk {i + 1}: Found {len(txns)} transactions")

                except Exception as e:
                    print(f"Error extracting chunk {i + 1}: {e}")
        else:
            print("No chunks found, extracting from full markdown (dynamic schema)")
            if not markdown_content:
                raise ValueError("No markdown content available for extraction")

            extract_response = client.extract(
                markdown=markdown_content,
                schema=json.dumps(schema),
                model="extract-latest",
            )

            extraction_data = AdeClientService.extract_response_data(extract_response)
            txns = extraction_data.get("transactions", [])
            if isinstance(txns, list):
                all_transactions = txns

        return all_transactions
